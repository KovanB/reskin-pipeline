"""Package baked assets into a distributable UE plugin skin."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from string import Template

from .config import SkinConfig
from .utils import load_json, logger, save_json


def sanitize_name(name: str) -> str:
    """Convert skin name to a valid C++ / UE identifier."""
    return "".join(c if c.isalnum() else "_" for c in name)


def build_redirect_map(assets: list[dict], config: SkinConfig) -> dict[str, str]:
    """
    Build a map of original UE asset paths to reskinned asset paths.
    Keys are UE content paths like /Game/Textures/Wood_Albedo
    Values are plugin content paths like /ReskinCyberpunkNeon/Textures/Wood_Albedo
    """
    plugin_name = f"Reskin{sanitize_name(config.name)}"
    redirect_map = {}

    for asset in assets:
        if not asset.get("baked_path"):
            continue

        # Convert filesystem relative path to UE content path
        rel = Path(asset["relative_path"])
        # Strip file extension for UE content reference
        ue_path = "/Game/" + str(rel.with_suffix("")).replace("\\", "/")
        reskin_path = f"/{plugin_name}/{str(rel.with_suffix('')).replace(chr(92), '/')}"
        redirect_map[ue_path] = reskin_path

    return redirect_map


def copy_baked_to_plugin(assets: list[dict], content_dir: Path) -> int:
    """Copy baked textures into the plugin's Content directory."""
    count = 0
    for asset in assets:
        baked_path = asset.get("baked_path")
        if not baked_path or not Path(baked_path).exists():
            continue

        rel = Path(asset["relative_path"])
        dest = content_dir / asset["category"] / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(baked_path, dest)
        count += 1

        # Also copy PBR maps if they exist
        for pbr_key in ("baked_normal_path", "baked_roughness_path"):
            pbr_path = asset.get(pbr_key)
            if pbr_path and Path(pbr_path).exists():
                pbr_rel = Path(pbr_path).name
                shutil.copy2(pbr_path, dest.parent / pbr_rel)

    return count


def render_template(template_dir: Path, output_dir: Path, context: dict) -> None:
    """Render all template files with the given context variables."""
    for template_file in template_dir.rglob("*"):
        if not template_file.is_file():
            continue

        rel = template_file.relative_to(template_dir)
        # Replace template markers in file names
        out_name = str(rel)
        for key, val in context.items():
            out_name = out_name.replace(f"ReskinLoader", val if key == "plugin_name" else out_name)

        out_path = output_dir / out_name
        out_path.parent.mkdir(parents=True, exist_ok=True)

        content = template_file.read_text(encoding="utf-8")
        rendered = Template(content).safe_substitute(context)
        out_path.write_text(rendered, encoding="utf-8")


def package(config: SkinConfig) -> Path:
    """
    Run the packaging phase:
    1. Load bake manifest
    2. Build UE plugin directory structure
    3. Copy baked textures into plugin Content/
    4. Generate redirect map
    5. Render C++ plugin from templates
    6. Write skin manifest

    Returns path to the packaged plugin directory.
    """
    bake_manifest_path = config.output_dir / "bake_manifest.json"
    manifest = load_json(bake_manifest_path)
    assets = manifest["assets"]

    plugin_name = f"Reskin{sanitize_name(config.name)}"
    package_dir = config.package_dir() / plugin_name
    package_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Packaging skin: {plugin_name}")

    # 1. Copy baked textures
    content_dir = package_dir / "Content"
    count = copy_baked_to_plugin(assets, content_dir)
    logger.info(f"  Copied {count} baked textures to plugin")

    # 2. Build redirect map
    redirect_map = build_redirect_map(assets, config)
    redirect_path = package_dir / "Config" / "redirect_map.json"
    save_json(redirect_map, redirect_path)
    logger.info(f"  Redirect map: {len(redirect_map)} entries")

    # 3. Render plugin templates
    template_dir = Path(__file__).parent.parent / "templates" / "plugin"
    if template_dir.exists():
        context = {
            "plugin_name": plugin_name,
            "skin_name": config.name,
            "skin_description": config.description,
            "skin_version": config.version,
            "author": config.author,
            "target_ue_version": config.target_ue_version,
        }
        render_template(template_dir, package_dir, context)
        logger.info("  Rendered plugin templates")
    else:
        logger.warning(f"  Template directory not found: {template_dir}")

    # 4. Write skin manifest
    skin_manifest = {
        "name": config.name,
        "plugin_name": plugin_name,
        "author": config.author,
        "description": config.description,
        "version": config.version,
        "target_ue_version": config.target_ue_version,
        "asset_count": count,
        "redirect_count": len(redirect_map),
        "categories": list(set(a["category"] for a in assets if a.get("baked_path"))),
    }
    save_json(skin_manifest, package_dir / "skin_manifest.json")

    logger.info(f"Package ready at: {package_dir}")
    return package_dir
