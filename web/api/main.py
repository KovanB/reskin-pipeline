"""FastAPI application — reskin pipeline web API."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
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


@app.get("/api/gallery")
async def api_gallery():
    """Landing page — pick a character, enter a style, Lucy reskins it live."""
    import base64
    import io

    # Pre-generate demo characters and build base64 thumbnails for the picker
    demo_dir = _ensure_demo_project()
    content_dir = demo_dir / "Content" / "Characters"

    chars = {}
    for char_dir in sorted(content_dir.iterdir()):
        if not char_dir.is_dir():
            continue
        name = char_dir.name
        body_path = char_dir / f"{name}_Body.png"
        if body_path.exists():
            from PIL import Image as PILImage
            img = PILImage.open(body_path).convert("RGB").resize((128, 128), PILImage.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            chars[name] = base64.b64encode(buf.getvalue()).decode()

    # Build character cards HTML
    char_cards = ""
    for name, thumb in chars.items():
        char_cards += f'''<div class="char-card" data-name="{name}" onclick="selectChar('{name}')">
<img src="data:image/png;base64,{thumb}">
<div class="char-name">{name}</div>
<div class="char-parts">Body / Face / Arms / Legs / Weapon</div>
</div>'''

    style_presets_html = ""
    presets = [
        ("Cyberpunk Neon", "cyberpunk neon aesthetic, glowing edges, dark background with vibrant pink and cyan accents, holographic shimmer"),
        ("Dark Souls", "dark medieval fantasy, weathered and battle-scarred, muted earth tones, grim atmosphere, souls-like aesthetic"),
        ("Cel Shaded", "cel-shaded cartoon style, bold black outlines, flat vibrant colors, anime inspired, Borderlands aesthetic"),
        ("Ice Frost", "frozen ice crystal aesthetic, pale blue and white, frost patterns, translucent icy surfaces, arctic winter"),
        ("Lava Infernal", "molten lava and fire, glowing orange cracks, charred black surface, ember particles, volcanic demon"),
        ("Vaporwave", "vaporwave aesthetic, pastel pink and purple, chrome reflections, retro 80s, sunset gradients, glitch art"),
    ]
    for pname, prompt in presets:
        style_presets_html += f'<button class="preset-btn" onclick="selectPreset(this)" data-prompt="{prompt}">{pname}</button>'

    html = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reskin Pipeline</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:#08080d;color:#e4e4ef;min-height:100vh}
.container{max-width:1100px;margin:0 auto;padding:32px 24px}
.logo{font-size:22px;font-weight:700;margin-bottom:32px;letter-spacing:-0.5px}
.logo span{color:#7c5cfc}

/* Steps */
.step{margin-bottom:32px;display:none}
.step.active{display:block}
.step-label{font-size:12px;font-weight:600;text-transform:uppercase;color:#7c5cfc;letter-spacing:1px;margin-bottom:12px}
.step-title{font-size:20px;font-weight:600;margin-bottom:16px}

/* Character picker */
.char-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}
.char-card{background:#12121a;border:2px solid #1e1e2e;border-radius:12px;padding:12px;cursor:pointer;transition:all 0.2s;text-align:center}
.char-card:hover{border-color:#7c5cfc;transform:translateY(-2px)}
.char-card.selected{border-color:#7c5cfc;background:#1a1a2e;box-shadow:0 0 20px rgba(124,92,252,0.2)}
.char-card img{width:100%;border-radius:8px;margin-bottom:8px}
.char-name{font-weight:600;font-size:15px}
.char-parts{font-size:11px;color:#6b6b80;margin-top:2px}

/* Style input */
.style-area{margin-top:20px}
.presets{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.preset-btn{padding:8px 16px;border-radius:20px;border:1px solid #2a2a3a;background:#12121a;color:#b0b0c0;font-size:13px;cursor:pointer;transition:all 0.2s}
.preset-btn:hover{border-color:#7c5cfc;color:#e4e4ef}
.preset-btn.active{background:#7c5cfc;border-color:#7c5cfc;color:white}
textarea{width:100%;padding:14px;background:#12121a;border:1px solid #2a2a3a;border-radius:10px;color:#e4e4ef;font-size:14px;font-family:inherit;resize:vertical;min-height:70px}
textarea:focus{outline:none;border-color:#7c5cfc}

/* Strength slider */
.slider-row{display:flex;align-items:center;gap:12px;margin-top:12px}
.slider-row label{font-size:13px;color:#8888a0;min-width:70px}
.slider-row input[type=range]{flex:1;accent-color:#7c5cfc}
.slider-val{font-size:13px;color:#7c5cfc;min-width:32px;text-align:right}

/* Go button */
.go-btn{margin-top:20px;padding:14px 40px;border-radius:10px;border:none;background:#7c5cfc;color:white;font-size:16px;font-weight:600;cursor:pointer;transition:all 0.2s}
.go-btn:hover{background:#9b7fff;transform:translateY(-1px)}
.go-btn:disabled{opacity:0.4;cursor:not-allowed;transform:none}

/* Status bar */
.status-bar{padding:14px 20px;border-radius:10px;margin-bottom:24px;font-size:14px;display:none;animation:fadeIn 0.3s}
.status-bar.show{display:flex;align-items:center;gap:12px}
.status-bar.running{background:rgba(124,92,252,0.12);color:#a78bfa}
.status-bar.done{background:rgba(52,211,153,0.12);color:#34d399}
.status-bar.error{background:rgba(248,113,113,0.12);color:#f87171}
.spinner{width:18px;height:18px;border:2px solid transparent;border-top-color:currentColor;border-radius:50%;animation:spin 0.8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes fadeIn{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}

/* Progress */
.progress{width:100%;height:4px;background:#1a1a26;border-radius:2px;overflow:hidden;margin-top:8px}
.progress-fill{height:100%;background:#7c5cfc;border-radius:2px;transition:width 0.4s ease;width:0%}

/* Results grid */
.results{display:none}
.results.show{display:block}
.results-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.results-title{font-size:18px;font-weight:600}
.char-section{margin-bottom:28px}
.char-section-title{font-size:15px;font-weight:600;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #1e1e2e}
.tex-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.tex-card{background:#12121a;border:1px solid #1e1e2e;border-radius:10px;overflow:hidden;animation:fadeIn 0.4s}
.tex-title{padding:8px 12px;font-size:12px;font-weight:600;border-bottom:1px solid #1e1e2e;display:flex;justify-content:space-between}
.tex-title span{color:#6b6b80;font-weight:400}
.compare{display:grid;grid-template-columns:1fr 1fr}
.compare img{width:100%;display:block}
.side{position:relative}
.label{position:absolute;top:6px;left:6px;padding:2px 8px;background:rgba(0,0,0,0.75);border-radius:4px;font-size:10px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase}
.label.after{color:#7c5cfc}

/* Download */
.dl-btn{padding:10px 24px;border-radius:8px;border:none;background:#34d399;color:#0a0a0f;font-size:13px;font-weight:600;cursor:pointer;display:none}
.dl-btn.show{display:inline-flex;align-items:center;gap:6px}

/* Back */
.back-btn{padding:8px 16px;border-radius:8px;border:1px solid #2a2a3a;background:transparent;color:#8888a0;font-size:13px;cursor:pointer;margin-bottom:20px;display:none}
.back-btn.show{display:inline-block}
</style></head><body>
<div class="container">
<div class="logo">reskin<span>.pipeline</span></div>

<button class="back-btn" id="backBtn" onclick="goBack()">Back to characters</button>

<div id="status" class="status-bar"></div>

<!-- Step 1: Pick a character -->
<div class="step active" id="step1">
<div class="step-label">Step 1</div>
<div class="step-title">Pick a character</div>
<div class="char-grid">""" + char_cards + """</div>
</div>

<!-- Step 2: Style -->
<div class="step" id="step2">
<div class="step-label">Step 2</div>
<div class="step-title" id="styleTitle">Style your character</div>
<div class="style-area">
<div style="font-size:13px;color:#8888a0;margin-bottom:8px">Quick presets</div>
<div class="presets">""" + style_presets_html + """</div>
<div style="font-size:13px;color:#8888a0;margin:12px 0 6px">Or describe your own style</div>
<textarea id="promptInput" placeholder="Describe the visual style you want..."></textarea>
<div class="slider-row">
<label>Strength</label>
<input type="range" id="strengthSlider" min="0" max="1" step="0.05" value="0.75">
<span class="slider-val" id="strengthVal">0.75</span>
</div>
<button class="go-btn" id="goBtn" onclick="startReskin()" disabled>Reskin with Lucy</button>
</div>
</div>

<!-- Results -->
<div class="results" id="results">
<div class="results-header">
<div class="results-title" id="resultsTitle">Results</div>
</div>
<div id="resultsGrid"></div>
</div>

</div>
<script>
let selectedChar = null;

function selectChar(name) {
  selectedChar = name;
  document.querySelectorAll('.char-card').forEach(c => c.classList.remove('selected'));
  document.querySelector('[data-name="'+name+'"]').classList.add('selected');
  document.getElementById('step2').classList.add('active');
  document.getElementById('styleTitle').textContent = 'Style ' + name;
  checkReady();
}

function selectPreset(btn) {
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('promptInput').value = btn.dataset.prompt;
  checkReady();
}

function checkReady() {
  const hasPrompt = document.getElementById('promptInput').value.trim().length > 0;
  document.getElementById('goBtn').disabled = !(selectedChar && hasPrompt);
}

document.getElementById('promptInput').addEventListener('input', checkReady);
document.getElementById('strengthSlider').addEventListener('input', function() {
  document.getElementById('strengthVal').textContent = this.value;
});

function setStatus(msg, type) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = 'status-bar show ' + (type || 'running');
  if (type === 'running') {
    el.innerHTML = '<div class="spinner"></div>' + msg;
  }
}

function goBack() {
  document.getElementById('step1').classList.add('active');
  document.getElementById('step2').classList.add('active');
  document.getElementById('results').classList.remove('show');
  document.getElementById('status').classList.remove('show');
  document.getElementById('backBtn').classList.remove('show');
  document.getElementById('goBtn').disabled = false;
}

async function startReskin() {
  const prompt = document.getElementById('promptInput').value.trim();
  const strength = document.getElementById('strengthSlider').value;
  document.getElementById('goBtn').disabled = true;
  document.getElementById('step1').classList.remove('active');
  document.getElementById('step2').classList.remove('active');
  document.getElementById('backBtn').classList.add('show');
  document.getElementById('results').classList.add('show');
  document.getElementById('resultsTitle').textContent = selectedChar + ' — Reskinning...';
  document.getElementById('resultsGrid').innerHTML = '';
  setStatus('Starting Lucy...', 'running');

  const params = new URLSearchParams({character: selectedChar, style_prompt: prompt, strength: strength});
  try {
    const res = await fetch('/api/reskin?' + params.toString());
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});
      const parts = buf.split('\\n');
      buf = parts.pop();
      for (const line of parts) {
        if (!line.trim()) continue;
        try {
          const ev = JSON.parse(line);
          if (ev.type === 'status') setStatus(ev.message, ev.cls || 'running');
          if (ev.type === 'card') addCard(ev);
          if (ev.type === 'done') {
            setStatus(ev.message, 'done');
            document.getElementById('resultsTitle').textContent = selectedChar + ' — ' + prompt;
          }
        } catch(e) {}
      }
    }
  } catch(e) {
    setStatus('Connection error: ' + e.message, 'error');
  }
}

function addCard(ev) {
  const grid = document.getElementById('resultsGrid');
  // Find or create character section
  let section = document.getElementById('section-' + ev.character);
  if (!section) {
    section = document.createElement('div');
    section.className = 'char-section';
    section.id = 'section-' + ev.character;
    section.innerHTML = '<div class="char-section-title">' + ev.character + '</div><div class="tex-grid" id="texgrid-' + ev.character + '"></div>';
    grid.appendChild(section);
  }
  const texGrid = document.getElementById('texgrid-' + ev.character);
  const card = document.createElement('div');
  card.className = 'tex-card';
  card.innerHTML = '<div class="tex-title">' + ev.texture + ' <span>' + ev.width + 'x' + ev.height + '</span></div>'
    + '<div class="compare">'
    + '<div class="side"><div class="label">Before</div><img src="data:image/png;base64,' + ev.original + '"></div>'
    + '<div class="side"><div class="label after">After</div><img src="data:image/png;base64,' + ev.reskinned + '"></div>'
    + '</div>';
  texGrid.appendChild(card);
}
</script>
</body></html>"""

    return HTMLResponse(html)


@app.get("/api/reskin")
async def api_reskin(
    character: str = "Knight",
    style_prompt: str = "cyberpunk neon aesthetic",
    strength: float = 0.75,
):
    """
    Stream Lucy reskin results for a single character as newline-delimited JSON.
    Each line is {type: "status"|"card"|"done", ...}.
    """
    import base64
    import io
    import yaml

    async def stream_reskin():
        demo_dir = _ensure_demo_project()
        char_dir = demo_dir / "Content" / "Characters" / character

        if not char_dir.exists():
            yield json.dumps({"type": "status", "message": f"Character '{character}' not found", "cls": "error"}) + "\n"
            return

        # Set up minimal config for the generator
        job_dir = DATA_ROOT / f"reskin_{character}"
        job_dir.mkdir(parents=True, exist_ok=True)
        output_dir = job_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        api_key = os.environ.get("LUCY_API_KEY", "")
        config_data = {
            "name": f"Reskin_{character}",
            "style_prompt": style_prompt,
            "backend": "lucy",
            "ue_project_path": str(demo_dir),
            "output_dir": str(output_dir),
            "categories": ["textures"],
            "quality": {"strength": strength, "guidance_scale": 7.5, "steps": 30,
                        "preserve_pbr": True, "tile_seam_fix": True, "consistency_pass": False},
        }
        if api_key:
            config_data["api_key"] = api_key

        config_path = job_dir / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        from reskin.config import load_config
        config = load_config(config_path)

        from reskin.generator import get_backend
        from reskin.utils import load_image

        gen_backend = get_backend(config)

        # Find all textures for this character
        textures = sorted(char_dir.glob("*.png"))
        total = len(textures)

        yield json.dumps({"type": "status", "message": f"Reskinning {character} ({total} textures)..."}) + "\n"

        def img_to_b64(img):
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()

        for i, tex_path in enumerate(textures):
            tex_name = tex_path.stem.replace(f"{character}_", "")

            yield json.dumps({"type": "status", "message": f"({i+1}/{total}) {character} / {tex_name}..."}) + "\n"

            try:
                source = load_image(tex_path)
                orig_b64 = img_to_b64(source)

                asset_info = {"relative_path": str(tex_path.relative_to(demo_dir / "Content")), "category": "textures"}
                result = await asyncio.to_thread(
                    gen_backend.generate, source, style_prompt, [], asset_info
                )
                gen_b64 = img_to_b64(result)

                yield json.dumps({
                    "type": "card",
                    "character": character,
                    "texture": tex_name,
                    "width": source.width,
                    "height": source.height,
                    "original": orig_b64,
                    "reskinned": gen_b64,
                }) + "\n"

            except Exception as e:
                yield json.dumps({"type": "status", "message": f"Error on {tex_name}: {e}", "cls": "error"}) + "\n"

        yield json.dumps({"type": "done", "message": f"Done! {total} textures reskinned for {character}."}) + "\n"

    return StreamingResponse(stream_reskin(), media_type="application/x-ndjson")
