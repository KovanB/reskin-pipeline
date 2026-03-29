"""Job management — create, track, and run reskin pipeline jobs."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CreateJobRequest, JobProgress, JobResponse, JobStatus

# In-memory job store (swap for Redis/DB in production)
_jobs: dict[str, dict[str, Any]] = {}

# WebSocket subscribers per job
_subscribers: dict[str, list[asyncio.Queue]] = {}

import os

JOBS_DIR = Path(os.environ.get("DATA_DIR", "/tmp/reskin-data")) / "jobs"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _to_response(job: dict) -> JobResponse:
    job_dir = _job_dir(job["id"])
    package_dir = job_dir / "output" / "package"

    preview_urls = []
    preview_dir = job_dir / "output" / "generated"
    if preview_dir.exists():
        for img in sorted(preview_dir.rglob("*.png"))[:12]:
            preview_urls.append(f"/api/jobs/{job['id']}/preview/{img.relative_to(preview_dir)}")

    download_url = None
    if job["progress"].status == JobStatus.COMPLETED and package_dir.exists():
        download_url = f"/api/jobs/{job['id']}/download"

    return JobResponse(
        id=job["id"],
        name=job["name"],
        status=job["progress"].status,
        style_prompt=job["style_prompt"],
        backend=job["backend"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        progress=job["progress"],
        asset_count=job.get("asset_count", 0),
        preview_urls=preview_urls,
        download_url=download_url,
        error=job.get("error"),
    )


async def _notify(job_id: str, progress: JobProgress) -> None:
    """Push progress update to all WebSocket subscribers."""
    for queue in _subscribers.get(job_id, []):
        await queue.put(progress.model_dump())


def subscribe(job_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.setdefault(job_id, []).append(queue)
    return queue


def unsubscribe(job_id: str, queue: asyncio.Queue) -> None:
    subs = _subscribers.get(job_id, [])
    if queue in subs:
        subs.remove(queue)


def create_job(req: CreateJobRequest, ue_project_path: str) -> JobResponse:
    job_id = uuid.uuid4().hex[:12]
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    job = {
        "id": job_id,
        "name": req.name,
        "style_prompt": req.style_prompt,
        "backend": req.backend.value,
        "categories": req.categories,
        "quality": req.quality.model_dump(),
        "api_key": req.api_key,
        "author": req.author,
        "description": req.description,
        "ue_project_path": ue_project_path,
        "created_at": _now(),
        "updated_at": _now(),
        "progress": JobProgress(status=JobStatus.PENDING),
    }
    _jobs[job_id] = job
    return _to_response(job)


def get_job(job_id: str) -> JobResponse | None:
    job = _jobs.get(job_id)
    if job is None:
        return None
    return _to_response(job)


def list_jobs() -> list[JobResponse]:
    return [_to_response(j) for j in sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)]


def get_job_dir(job_id: str) -> Path:
    return _job_dir(job_id)


async def run_job(job_id: str) -> None:
    """Execute the full reskin pipeline for a job. Runs in a background task."""
    import yaml

    job = _jobs.get(job_id)
    if not job:
        return

    job_dir = _job_dir(job_id)
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write a temporary config YAML for the pipeline
    config_data = {
        "name": job["name"],
        "style_prompt": job["style_prompt"],
        "backend": job["backend"],
        "ue_project_path": job["ue_project_path"],
        "output_dir": str(output_dir),
        "categories": job["categories"],
        "quality": job["quality"],
        "author": job["author"],
        "description": job["description"],
    }
    if job.get("api_key"):
        config_data["api_key"] = job["api_key"]

    config_path = job_dir / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    try:
        from reskin.config import load_config

        config = load_config(config_path)

        # Stage 1: Extract
        job["progress"] = JobProgress(status=JobStatus.EXTRACTING, stage="extract", message="Scanning UE project...")
        job["updated_at"] = _now()
        await _notify(job_id, job["progress"])

        from reskin.extractor import extract as run_extract
        manifest_path = await asyncio.to_thread(run_extract, config)

        from reskin.utils import load_json
        manifest = load_json(manifest_path)
        total_assets = manifest["total_assets"]
        job["asset_count"] = total_assets

        # Stage 2: Generate
        job["progress"] = JobProgress(
            status=JobStatus.GENERATING, stage="generate",
            total=total_assets, message="Generating reskinned textures..."
        )
        job["updated_at"] = _now()
        await _notify(job_id, job["progress"])

        from reskin.generator import generate as run_generate
        await asyncio.to_thread(run_generate, config)

        # Stage 3: Bake
        job["progress"] = JobProgress(
            status=JobStatus.BAKING, stage="bake",
            total=total_assets, message="Baking textures..."
        )
        job["updated_at"] = _now()
        await _notify(job_id, job["progress"])

        from reskin.baker import bake as run_bake
        await asyncio.to_thread(run_bake, config)

        if config.quality.consistency_pass:
            from reskin.consistency import consistency_pass
            await asyncio.to_thread(consistency_pass, config)

        # Stage 4: Package
        job["progress"] = JobProgress(
            status=JobStatus.PACKAGING, stage="package",
            message="Building UE plugin..."
        )
        job["updated_at"] = _now()
        await _notify(job_id, job["progress"])

        from reskin.packager import package as run_package
        await asyncio.to_thread(run_package, config)

        # Done
        job["progress"] = JobProgress(
            status=JobStatus.COMPLETED, stage="done",
            current=total_assets, total=total_assets,
            percent=100.0, message="Skin ready for download"
        )
        job["updated_at"] = _now()
        await _notify(job_id, job["progress"])

    except Exception as e:
        job["error"] = str(e)
        job["progress"] = JobProgress(
            status=JobStatus.FAILED, message=f"Pipeline failed: {e}"
        )
        job["updated_at"] = _now()
        await _notify(job_id, job["progress"])
