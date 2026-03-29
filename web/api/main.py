"""FastAPI application — reskin pipeline web API."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .jobs import create_job, get_job, get_job_dir, list_jobs, run_job, subscribe, unsubscribe
from .models import CreateJobRequest, JobListResponse

app = FastAPI(title="Reskin Pipeline", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Use /tmp on Vercel (serverless), data/ locally
import os

DATA_ROOT = Path(os.environ.get("DATA_DIR", "/tmp/reskin-data"))
DATA_ROOT.mkdir(parents=True, exist_ok=True)
(DATA_ROOT / "jobs").mkdir(parents=True, exist_ok=True)
(DATA_ROOT / "uploads").mkdir(parents=True, exist_ok=True)


# ──────────────────────────────── REST endpoints ────────────────────────────────


@app.post("/api/jobs")
async def api_create_job(req: CreateJobRequest, ue_project_path: str = "") -> dict:
    """Create a new reskin job and start it."""
    if not ue_project_path:
        raise HTTPException(400, "ue_project_path query param required")

    job = create_job(req, ue_project_path)
    # Fire and forget the pipeline
    asyncio.create_task(run_job(job.id))
    return job.model_dump()


@app.get("/api/jobs")
async def api_list_jobs() -> dict:
    """List all jobs."""
    jobs = list_jobs()
    return JobListResponse(jobs=jobs, total=len(jobs)).model_dump()


@app.get("/api/jobs/{job_id}")
async def api_get_job(job_id: str) -> dict:
    """Get job details."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.model_dump()


@app.get("/api/jobs/{job_id}/preview/{path:path}")
async def api_preview(job_id: str, path: str) -> FileResponse:
    """Serve a preview image from a job's generated output."""
    job_dir = get_job_dir(job_id)
    file_path = job_dir / "output" / "generated" / path
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "Preview not found")
    return FileResponse(file_path, media_type="image/png")


@app.get("/api/jobs/{job_id}/originals/{path:path}")
async def api_original(job_id: str, path: str) -> FileResponse:
    """Serve an original extracted image for before/after comparison."""
    job_dir = get_job_dir(job_id)
    file_path = job_dir / "output" / "extracted" / path
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "Original not found")
    return FileResponse(file_path)


@app.get("/api/jobs/{job_id}/download")
async def api_download(job_id: str) -> FileResponse:
    """Download the packaged skin as a zip."""
    job_dir = get_job_dir(job_id)
    package_dir = job_dir / "output" / "package"
    if not package_dir.exists():
        raise HTTPException(404, "Package not ready")

    # Create zip
    zip_path = job_dir / "skin_package"
    if not Path(f"{zip_path}.zip").exists():
        shutil.make_archive(str(zip_path), "zip", package_dir)

    return FileResponse(
        f"{zip_path}.zip",
        media_type="application/zip",
        filename=f"reskin_{job_id}.zip",
    )


@app.post("/api/upload/project")
async def api_upload_project(file: UploadFile = File(...)) -> dict:
    """Upload a zipped UE project (or Content/ folder) for processing."""
    upload_dir = DATA_ROOT / "uploads" / file.filename.replace(".zip", "")
    upload_dir.mkdir(parents=True, exist_ok=True)

    zip_path = upload_dir / file.filename
    with open(zip_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Extract zip
    shutil.unpack_archive(zip_path, upload_dir / "project")

    return {"project_path": str(upload_dir / "project"), "message": "Project uploaded"}


@app.get("/api/jobs/{job_id}/assets")
async def api_list_assets(job_id: str) -> dict:
    """List all assets in a job with their before/after paths."""
    job_dir = get_job_dir(job_id)
    manifest_path = job_dir / "output" / "bake_manifest.json"

    if not manifest_path.exists():
        # Try generation manifest
        manifest_path = job_dir / "output" / "generation_manifest.json"
    if not manifest_path.exists():
        manifest_path = job_dir / "output" / "extraction_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, "No manifest found yet")

    from reskin.utils import load_json
    manifest = load_json(manifest_path)
    assets = manifest.get("assets", [])

    result = []
    for asset in assets:
        rel = asset["relative_path"]
        cat = asset["category"]
        entry = {
            "relative_path": rel,
            "category": cat,
            "width": asset["width"],
            "height": asset["height"],
            "original_url": f"/api/jobs/{job_id}/originals/{cat}/{rel}",
        }
        if asset.get("generated_path"):
            entry["preview_url"] = f"/api/jobs/{job_id}/preview/{cat}/{rel}"
        result.append(entry)

    return {"assets": result, "total": len(result)}


# ──────────────────────────────── WebSocket ────────────────────────────────


@app.websocket("/ws/jobs/{job_id}")
async def ws_job_progress(websocket: WebSocket, job_id: str):
    """Stream live progress updates for a job."""
    await websocket.accept()

    job = get_job(job_id)
    if not job:
        await websocket.close(code=4004, reason="Job not found")
        return

    # Send current state immediately
    await websocket.send_json(job.progress.model_dump())

    queue = subscribe(job_id)
    try:
        while True:
            update = await queue.get()
            await websocket.send_json(update)
            if update.get("status") in ("completed", "failed"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(job_id, queue)
