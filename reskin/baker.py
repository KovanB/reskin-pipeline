"""Bake generated images into UE-compatible asset formats."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from .config import SkinConfig
from .utils import load_image, load_json, logger, nearest_power_of_2, save_image, save_json


def resize_to_match(generated: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize generated image to match original asset resolution (power-of-2 aligned)."""
    w = nearest_power_of_2(target_w)
    h = nearest_power_of_2(target_h)
    if generated.size != (w, h):
        generated = generated.resize((w, h), Image.LANCZOS)
    return generated


def generate_normal_from_albedo(albedo: Image.Image) -> Image.Image:
    """
    Generate a simple normal map from an albedo texture using Sobel-like edge detection.
    This is a rough approximation — for production, use a dedicated model.
    """
    gray = albedo.convert("L")
    arr = np.array(gray, dtype=np.float32) / 255.0

    # Sobel gradients
    dx = np.zeros_like(arr)
    dy = np.zeros_like(arr)
    dx[:, 1:-1] = (arr[:, 2:] - arr[:, :-2]) / 2.0
    dy[1:-1, :] = (arr[2:, :] - arr[:-2, :]) / 2.0

    # Normal map: R=dx, G=dy, B=up
    strength = 2.0
    nx = -dx * strength
    ny = -dy * strength
    nz = np.ones_like(arr)

    # Normalize
    length = np.sqrt(nx**2 + ny**2 + nz**2)
    nx /= length
    ny /= length
    nz /= length

    # Map from [-1,1] to [0,255]
    r = ((nx + 1) / 2 * 255).clip(0, 255).astype(np.uint8)
    g = ((ny + 1) / 2 * 255).clip(0, 255).astype(np.uint8)
    b = ((nz + 1) / 2 * 255).clip(0, 255).astype(np.uint8)

    return Image.merge("RGB", [
        Image.fromarray(r),
        Image.fromarray(g),
        Image.fromarray(b),
    ]).convert("RGBA")


def generate_roughness_from_albedo(albedo: Image.Image) -> Image.Image:
    """
    Estimate a roughness map from albedo.
    Bright/saturated areas = smoother, dark/desaturated = rougher.
    """
    gray = albedo.convert("L")
    arr = np.array(gray, dtype=np.float32) / 255.0

    # Invert and add some noise-based detail
    roughness = 1.0 - arr * 0.5  # bias towards rough
    roughness = (roughness * 255).clip(0, 255).astype(np.uint8)

    img = Image.fromarray(roughness, mode="L")
    return img.convert("RGBA")


def fix_tile_seams(img: Image.Image, border_px: int = 16) -> Image.Image:
    """Blend tile borders to reduce visible seams when tiling."""
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]

    if border_px >= min(h, w) // 4:
        return img  # image too small for seam fix

    # Horizontal seam: blend left edge with right edge
    for i in range(border_px):
        alpha = i / border_px
        left_col = arr[:, i].copy()
        right_col = arr[:, w - border_px + i].copy()
        blended = left_col * alpha + right_col * (1 - alpha)
        arr[:, i] = blended
        arr[:, w - border_px + i] = left_col * (1 - alpha) + right_col * alpha

    # Vertical seam: blend top edge with bottom edge
    for i in range(border_px):
        alpha = i / border_px
        top_row = arr[i].copy()
        bottom_row = arr[h - border_px + i].copy()
        blended = top_row * alpha + bottom_row * (1 - alpha)
        arr[i] = blended
        arr[h - border_px + i] = top_row * (1 - alpha) + bottom_row * alpha

    return Image.fromarray(arr.clip(0, 255).astype(np.uint8), mode=img.mode)


def is_tiling_texture(asset_info: dict) -> bool:
    """Heuristic: textures in certain categories/paths are likely tiling."""
    rel = asset_info.get("relative_path", "").lower()
    tiling_hints = ["floor", "wall", "ground", "tile", "brick", "wood", "stone",
                    "metal", "fabric", "concrete", "grass", "rock", "terrain"]
    return any(hint in rel for hint in tiling_hints)


def bake(config: SkinConfig) -> Path:
    """
    Run the baking phase:
    1. Load generation manifest
    2. Resize each generated image to match original resolution
    3. Fix tile seams where appropriate
    4. Generate PBR maps if needed
    5. Write baked assets and manifest

    Returns path to bake manifest.
    """
    manifest_path = config.output_dir / "generation_manifest.json"
    manifest = load_json(manifest_path)
    assets = manifest["assets"]

    baked_dir = config.baked_dir()
    baked_dir.mkdir(parents=True, exist_ok=True)

    fmt = config.quality.output_format
    baked_count = 0

    for i, asset in enumerate(assets):
        gen_path = asset.get("generated_path")
        if not gen_path or not Path(gen_path).exists():
            continue

        rel_path = Path(asset["relative_path"])
        target_w = asset["width"]
        target_h = asset["height"]
        category = asset["category"]

        logger.info(f"[{i + 1}/{len(assets)}] Baking: {rel_path}")

        generated = load_image(Path(gen_path))

        # Resize to match original
        baked = resize_to_match(generated, target_w, target_h)

        # Seam fix for tiling textures
        if config.quality.tile_seam_fix and is_tiling_texture(asset):
            baked = fix_tile_seams(baked)
            logger.debug(f"  Applied seam fix: {rel_path}")

        # Save baked albedo
        out_path = baked_dir / category / rel_path.with_suffix(f".{fmt}")
        save_image(baked, out_path, fmt=fmt)
        asset["baked_path"] = str(out_path)

        # PBR map generation
        if not config.quality.preserve_pbr:
            # Generate normal map
            normal = generate_normal_from_albedo(baked)
            normal_path = baked_dir / category / rel_path.with_name(
                rel_path.stem + "_Normal"
            ).with_suffix(f".{fmt}")
            save_image(normal, normal_path, fmt=fmt)
            asset["baked_normal_path"] = str(normal_path)

            # Generate roughness map
            roughness = generate_roughness_from_albedo(baked)
            roughness_path = baked_dir / category / rel_path.with_name(
                rel_path.stem + "_Roughness"
            ).with_suffix(f".{fmt}")
            save_image(roughness, roughness_path, fmt=fmt)
            asset["baked_roughness_path"] = str(roughness_path)

        baked_count += 1

    # Write bake manifest
    bake_manifest_path = config.output_dir / "bake_manifest.json"
    manifest["baked_count"] = baked_count
    save_json(manifest, bake_manifest_path)
    logger.info(f"Baking complete: {baked_count} assets baked")

    return bake_manifest_path
