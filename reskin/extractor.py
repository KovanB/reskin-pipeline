"""Extract and categorize textures from an Unreal Engine project."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from .config import SkinConfig
from .utils import file_hash, logger, save_json

# File extensions we treat as image assets
IMAGE_EXTENSIONS = {".png", ".tga", ".bmp", ".jpg", ".jpeg", ".exr", ".hdr", ".tif", ".tiff"}

# Path patterns for categorization (checked against relative path within Content/)
CATEGORY_PATTERNS: dict[str, list[str]] = {
    "ui": ["UI", "HUD", "Widget", "Slate", "Icon", "Menu", "Font"],
    "skyboxes": ["HDRI", "Sky", "Skybox", "Cubemap", "Environment", "Panorama"],
    "particles": ["Particles", "FX", "Effect", "Niagara", "VFX", "Cascade"],
    "materials": ["Material", "Shader"],  # material-adjacent textures
}


def categorize_asset(rel_path: Path) -> str:
    """Determine asset category from its path within Content/."""
    path_str = str(rel_path).replace("\\", "/")
    parts_upper = path_str.upper()

    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if pattern.upper() in parts_upper:
                return category

    return "textures"  # default


def get_image_info(path: Path) -> dict | None:
    """Get image metadata. Returns None if file can't be read as image."""
    try:
        with Image.open(path) as img:
            return {
                "width": img.width,
                "height": img.height,
                "mode": img.mode,
                "format": img.format,
            }
    except Exception:
        return None


def scan_content_dir(content_dir: Path) -> list[dict]:
    """Recursively scan Content/ for image assets."""
    assets = []

    if not content_dir.exists():
        logger.error(f"Content directory not found: {content_dir}")
        return assets

    for file_path in sorted(content_dir.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        rel_path = file_path.relative_to(content_dir)
        category = categorize_asset(rel_path)
        info = get_image_info(file_path)

        if info is None:
            logger.warning(f"Skipping unreadable image: {rel_path}")
            continue

        assets.append({
            "source_path": str(file_path),
            "relative_path": str(rel_path),
            "category": category,
            "width": info["width"],
            "height": info["height"],
            "mode": info["mode"],
            "format": info["format"],
            "hash": file_hash(file_path),
        })

    return assets


def extract(config: SkinConfig) -> Path:
    """
    Run the extraction phase:
    1. Scan the UE project's Content/ directory
    2. Categorize all image assets
    3. Copy them to a staging directory organized by category
    4. Write an extraction manifest

    Returns the path to the extraction manifest.
    """
    content_dir = config.ue_project_path / "Content"
    extracted_dir = config.extracted_dir()
    extracted_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Scanning: {content_dir}")
    all_assets = scan_content_dir(content_dir)

    # Filter by configured categories
    assets = [a for a in all_assets if a["category"] in config.categories]
    logger.info(f"Found {len(assets)} assets ({len(all_assets)} total, {len(all_assets) - len(assets)} filtered out)")

    # Copy to staging organized by category
    for asset in assets:
        src = Path(asset["source_path"])
        category = asset["category"]
        rel = Path(asset["relative_path"])
        dest = extracted_dir / category / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        asset["extracted_path"] = str(dest)

    # Write manifest
    manifest_path = config.output_dir / "extraction_manifest.json"
    manifest = {
        "skin_name": config.name,
        "ue_project": str(config.ue_project_path),
        "total_assets": len(assets),
        "by_category": {},
        "assets": assets,
    }
    for cat in config.categories:
        count = sum(1 for a in assets if a["category"] == cat)
        if count > 0:
            manifest["by_category"][cat] = count

    save_json(manifest, manifest_path)
    logger.info(f"Extraction manifest written to: {manifest_path}")

    for cat, count in manifest["by_category"].items():
        logger.info(f"  {cat}: {count} assets")

    return manifest_path
