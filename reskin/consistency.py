"""Cross-asset style consistency pass — harmonize palettes across related assets."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from .config import SkinConfig
from .utils import load_image, load_json, logger, save_image, save_json


def extract_palette(img: Image.Image, n_colors: int = 8) -> np.ndarray:
    """Extract dominant colors using quantization."""
    small = img.convert("RGB").resize((64, 64), Image.LANCZOS)
    quantized = small.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()[:n_colors * 3]
    return np.array(palette, dtype=np.float32).reshape(-1, 3)


def compute_target_palette(
    style_refs: list[Image.Image],
    generated_images: list[Image.Image],
    n_colors: int = 8,
) -> np.ndarray:
    """Compute a target palette from style references (or generated average if no refs)."""
    sources = style_refs if style_refs else generated_images
    if not sources:
        return np.array([[128, 128, 128]] * n_colors, dtype=np.float32)

    all_palettes = [extract_palette(img, n_colors) for img in sources]
    return np.mean(all_palettes, axis=0)


def shift_palette(
    img: Image.Image,
    current_palette: np.ndarray,
    target_palette: np.ndarray,
    strength: float = 0.3,
) -> Image.Image:
    """
    Shift an image's colors towards the target palette.
    Uses a soft color transfer approach: adjust mean/std of each channel.
    """
    arr = np.array(img.convert("RGB"), dtype=np.float32)

    for c in range(3):
        channel = arr[:, :, c]
        src_mean = channel.mean()
        src_std = channel.std() + 1e-6
        tgt_mean = target_palette[:, c].mean()
        tgt_std = current_palette[:, c].std() + 1e-6

        # Shift towards target distribution
        shifted = (channel - src_mean) * (tgt_std / src_std) + tgt_mean
        # Blend with original
        arr[:, :, c] = channel * (1 - strength) + shifted * strength

    arr = arr.clip(0, 255).astype(np.uint8)
    result = Image.fromarray(arr, mode="RGB")

    # Preserve alpha if present
    if img.mode == "RGBA":
        result = result.convert("RGBA")
        result.putalpha(img.getchannel("A"))

    return result


# Grouping heuristics: assets with these keywords are related
ASSET_GROUPS = {
    "wood": ["wood", "plank", "lumber", "timber", "bark"],
    "metal": ["metal", "steel", "iron", "copper", "chrome", "aluminum"],
    "stone": ["stone", "rock", "brick", "concrete", "marble", "granite"],
    "fabric": ["fabric", "cloth", "leather", "silk", "canvas"],
    "nature": ["grass", "leaf", "tree", "flower", "moss", "vine"],
    "ui": ["button", "panel", "frame", "border", "icon", "hud"],
    "sky": ["sky", "cloud", "hdri", "panorama", "cubemap"],
}


def group_assets(assets: list[dict]) -> dict[str, list[dict]]:
    """Group assets by material similarity based on path keywords."""
    groups: dict[str, list[dict]] = defaultdict(list)

    for asset in assets:
        rel = asset.get("relative_path", "").lower()
        assigned = False
        for group_name, keywords in ASSET_GROUPS.items():
            if any(kw in rel for kw in keywords):
                groups[group_name].append(asset)
                assigned = True
                break
        if not assigned:
            groups["other"].append(asset)

    return dict(groups)


def consistency_pass(config: SkinConfig) -> None:
    """
    Run a consistency pass across baked assets:
    1. Group related assets
    2. Compute target palette from style references
    3. Harmonize each group's palette towards the target
    """
    bake_manifest_path = config.output_dir / "bake_manifest.json"
    manifest = load_json(bake_manifest_path)
    assets = manifest["assets"]

    # Only process assets that were baked
    baked_assets = [a for a in assets if a.get("baked_path")]
    if not baked_assets:
        logger.warning("No baked assets to harmonize")
        return

    # Load style references for target palette
    style_refs = []
    for ref_path in config.style_reference_images:
        if ref_path.exists():
            style_refs.append(load_image(ref_path))

    # Group assets
    groups = group_assets(baked_assets)
    logger.info(f"Consistency pass: {len(baked_assets)} assets in {len(groups)} groups")

    for group_name, group_assets_list in groups.items():
        if len(group_assets_list) < 2:
            continue

        logger.info(f"  Harmonizing group '{group_name}': {len(group_assets_list)} assets")

        # Load all images in group
        images = []
        for asset in group_assets_list:
            baked_path = Path(asset["baked_path"])
            if baked_path.exists():
                images.append(load_image(baked_path))

        if not images:
            continue

        # Compute target palette
        target = compute_target_palette(style_refs, images)

        # Harmonize each asset
        for asset, img in zip(group_assets_list, images):
            current = extract_palette(img)
            harmonized = shift_palette(img, current, target, strength=0.3)

            baked_path = Path(asset["baked_path"])
            fmt = config.quality.output_format
            save_image(harmonized, baked_path, fmt=fmt)

    # Update manifest
    manifest["consistency_pass"] = True
    save_json(manifest, bake_manifest_path)
    logger.info("Consistency pass complete")
