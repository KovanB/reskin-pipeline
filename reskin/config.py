"""Skin configuration loading and validation."""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


ASSET_CATEGORIES = ("textures", "ui", "skyboxes", "particles", "materials")

BackendName = Literal["lucy", "stability", "comfyui", "local"]


@dataclass
class QualitySettings:
    """Controls generation and baking quality."""

    strength: float = 0.75  # img2img strength (0=keep original, 1=full restyle)
    guidance_scale: float = 7.5
    steps: int = 30
    output_format: str = "png"  # png or tga
    preserve_pbr: bool = True  # keep original normal/roughness maps
    tile_seam_fix: bool = True
    consistency_pass: bool = True


@dataclass
class SkinConfig:
    """Full configuration for a reskin job."""

    name: str
    style_prompt: str
    ue_project_path: Path
    output_dir: Path
    backend: BackendName = "local"
    style_reference_images: list[Path] = field(default_factory=list)
    categories: list[str] = field(default_factory=lambda: list(ASSET_CATEGORIES))
    quality: QualitySettings = field(default_factory=QualitySettings)

    # Backend-specific config
    api_key: str | None = None
    api_url: str | None = None
    comfyui_workflow: Path | None = None

    # Metadata for packaging
    author: str = ""
    description: str = ""
    version: str = "1.0.0"
    target_ue_version: str = "5.4"

    def staging_dir(self) -> Path:
        return self.output_dir / "staging"

    def extracted_dir(self) -> Path:
        return self.output_dir / "extracted"

    def generated_dir(self) -> Path:
        return self.output_dir / "generated"

    def baked_dir(self) -> Path:
        return self.output_dir / "baked"

    def package_dir(self) -> Path:
        return self.output_dir / "package"


def load_config(path: Path) -> SkinConfig:
    """Load a SkinConfig from a YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    quality_raw = raw.pop("quality", {})
    quality = QualitySettings(**quality_raw)

    # Resolve paths relative to the config file's directory
    config_dir = path.parent
    for key in ("ue_project_path", "output_dir", "comfyui_workflow"):
        if raw.get(key):
            p = Path(raw[key])
            if not p.is_absolute():
                raw[key] = config_dir / p
            else:
                raw[key] = p

    ref_images = raw.pop("style_reference_images", [])
    resolved_refs = []
    for img in ref_images:
        p = Path(img)
        resolved_refs.append(p if p.is_absolute() else config_dir / p)

    return SkinConfig(
        **raw,
        style_reference_images=resolved_refs,
        quality=quality,
    )
