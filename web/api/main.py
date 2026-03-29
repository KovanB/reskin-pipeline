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

from .jobs import create_job, get_job, get_job_dir, list_jobs, subscribe, unsubscribe
from .models import CreateJobRequest, JobListResponse, JobProgress, JobStatus

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


def _ensure_demo_project() -> Path:
    """Unpack bundled demo character textures to /tmp if not already there."""
    demo_dir = DATA_ROOT / "demo_project"
    content_dir = demo_dir / "Content" / "Characters"
    if content_dir.exists():
        return demo_dir

    from PIL import Image, ImageDraw

    def hex_to_rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    chars = {
        "Knight": {"body": "#4a5568", "accent": "#c0a050", "trim": "#2d3748"},
        "Mage": {"body": "#4c1d95", "accent": "#a78bfa", "trim": "#1e1b4b"},
        "Rogue": {"body": "#1a1a2e", "accent": "#e94560", "trim": "#16213e"},
        "Ranger": {"body": "#2d5016", "accent": "#84cc16", "trim": "#1a2e05"},
        "Cleric": {"body": "#f5f5dc", "accent": "#daa520", "trim": "#8b7355"},
    }

    for name, pal in chars.items():
        char_dir = content_dir / name
        char_dir.mkdir(parents=True, exist_ok=True)
        body_c, acc_c, trim_c = hex_to_rgb(pal["body"]), hex_to_rgb(pal["accent"]), hex_to_rgb(pal["trim"])

        # Body
        img = Image.new("RGB", (512, 512), body_c)
        d = ImageDraw.Draw(img)
        for y in range(0, 512, 64):
            d.line([(0, y), (512, y)], fill=trim_c, width=2)
        for x in range(0, 512, 64):
            d.line([(x, 0), (x, 512)], fill=trim_c, width=2)
        d.rectangle([180, 200, 332, 312], fill=acc_c, outline=trim_c, width=3)
        d.ellipse([220, 220, 292, 292], fill=trim_c, outline=acc_c, width=2)
        img.save(str(char_dir / f"{name}_Body.png"))

        # Face
        face = Image.new("RGB", (256, 256), (232, 201, 160))
        fd = ImageDraw.Draw(face)
        fd.ellipse([40, 20, 216, 236], fill=(219, 184, 150), outline=(184, 149, 106), width=2)
        fd.ellipse([80, 90, 110, 115], fill="white", outline="#333")
        fd.ellipse([146, 90, 176, 115], fill="white", outline="#333")
        fd.ellipse([90, 96, 104, 110], fill="#333")
        fd.ellipse([156, 96, 170, 110], fill="#333")
        fd.arc([100, 140, 156, 175], 0, 180, fill=(139, 94, 60), width=2)
        fd.rectangle([30, 0, 226, 30], fill=acc_c, outline=trim_c, width=2)
        face.save(str(char_dir / f"{name}_Face.png"))

        # Arms
        arms = Image.new("RGB", (256, 512), body_c)
        ad = ImageDraw.Draw(arms)
        ad.rectangle([0, 0, 256, 256], outline=trim_c, width=3)
        ad.rectangle([0, 256, 256, 512], outline=trim_c, width=3)
        ad.rectangle([20, 200, 236, 256], fill=acc_c, outline=trim_c, width=2)
        ad.rectangle([20, 456, 236, 512], fill=acc_c, outline=trim_c, width=2)
        arms.save(str(char_dir / f"{name}_Arms.png"))

        # Legs
        legs = Image.new("RGB", (256, 512), body_c)
        ld = ImageDraw.Draw(legs)
        ld.rectangle([0, 380, 128, 512], fill=trim_c, outline=acc_c, width=2)
        ld.rectangle([128, 380, 256, 512], fill=trim_c, outline=acc_c, width=2)
        ld.ellipse([30, 230, 98, 280], fill=acc_c, outline=trim_c, width=2)
        ld.ellipse([158, 230, 226, 280], fill=acc_c, outline=trim_c, width=2)
        legs.save(str(char_dir / f"{name}_Legs.png"))

        # Weapon
        wep = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        wd = ImageDraw.Draw(wep)
        if name == "Knight":
            wd.rectangle([110, 10, 146, 200], fill=(136, 136, 136), outline=(85, 85, 85), width=2)
            wd.rectangle([80, 190, 176, 210], fill=acc_c, outline=trim_c, width=2)
        elif name == "Mage":
            wd.rectangle([120, 30, 136, 220], fill=(101, 67, 33))
            wd.ellipse([96, 0, 160, 64], fill=acc_c, outline=trim_c, width=3)
        elif name == "Rogue":
            wd.polygon([(128, 10), (160, 180), (128, 170), (96, 180)], fill=(170, 170, 170))
            wd.rectangle([108, 175, 148, 195], fill=acc_c)
        elif name == "Ranger":
            wd.arc([60, 20, 196, 240], 200, 340, fill=(101, 67, 33), width=6)
        elif name == "Cleric":
            wd.rectangle([118, 60, 138, 256], fill=acc_c, outline=trim_c, width=2)
            wd.rectangle([80, 30, 176, 70], fill=acc_c, outline=trim_c, width=2)
        wep.save(str(char_dir / f"{name}_Weapon.png"))

    return demo_dir


@app.get("/api/demo/characters")
async def api_demo_characters() -> dict:
    """List the 5 bundled demo characters and their textures."""
    _ensure_demo_project()
    characters = ["Knight", "Mage", "Rogue", "Cleric", "Ranger"]
    textures = ["Body", "Face", "Arms", "Legs", "Weapon"]
    return {
        "characters": characters,
        "textures_per_character": textures,
        "total_assets": len(characters) * len(textures),
        "project_path": "demo",
    }


# ──────────────────────────────── REST endpoints ────────────────────────────────


@app.post("/api/jobs")
async def api_create_job(req: CreateJobRequest, ue_project_path: str = "") -> dict:
    """Create a new reskin job (does not start it — use /api/jobs/{id}/run SSE endpoint)."""
    if not ue_project_path or ue_project_path == "demo":
        ue_project_path = str(_ensure_demo_project())

    if req.backend.value == "lucy" and not req.api_key:
        env_key = os.environ.get("LUCY_API_KEY")
        if env_key:
            req.api_key = env_key

    job = create_job(req, ue_project_path)
    return job.model_dump()


@app.get("/api/jobs/{job_id}/run")
async def api_run_job(job_id: str):
    """Run the full pipeline as a streaming SSE response. Keeps connection alive."""
    import yaml
    from .jobs import _jobs, _now

    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    async def run_pipeline():
        job_dir = get_job_dir(job_id)
        output_dir = job_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

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

        def send_event(status, stage, message, current=0, total=0):
            pct = (current / total * 100) if total > 0 else 0
            progress = {"status": status, "stage": stage, "message": message,
                        "current": current, "total": total, "percent": round(pct, 1)}
            job["progress"] = JobProgress(**progress)
            job["updated_at"] = _now()
            return f"data: {json.dumps(progress)}\n\n"

        try:
            from reskin.config import load_config
            config = load_config(config_path)

            yield send_event("extracting", "extract", "Scanning project...")

            from reskin.extractor import extract as run_extract
            manifest_path = await asyncio.to_thread(run_extract, config)

            from reskin.utils import load_json
            manifest = load_json(manifest_path)
            total = manifest["total_assets"]
            job["asset_count"] = total

            yield send_event("generating", "generate", f"Generating {total} assets with Lucy...", 0, total)

            from reskin.generator import generate as run_generate
            await asyncio.to_thread(run_generate, config)

            yield send_event("baking", "bake", "Baking textures...", total, total)

            from reskin.baker import bake as run_bake
            await asyncio.to_thread(run_bake, config)

            if config.quality.consistency_pass:
                yield send_event("baking", "consistency", "Running consistency pass...", total, total)
                from reskin.consistency import consistency_pass
                await asyncio.to_thread(consistency_pass, config)

            yield send_event("packaging", "package", "Building UE plugin...", total, total)

            from reskin.packager import package as run_package
            await asyncio.to_thread(run_package, config)

            yield send_event("completed", "done", "Skin ready for download!", total, total)

        except Exception as e:
            job["error"] = str(e)
            yield send_event("failed", "error", f"Pipeline failed: {e}")

    return StreamingResponse(run_pipeline(), media_type="text/event-stream")


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
