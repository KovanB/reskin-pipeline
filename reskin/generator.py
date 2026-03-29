"""Pluggable AI generation backends for reskinning textures."""

from __future__ import annotations

import base64
import io
import json
import time
from abc import ABC, abstractmethod
from pathlib import Path

import httpx
from PIL import Image

from .config import SkinConfig, QualitySettings
from .utils import load_image, load_json, logger, save_image, save_json


class GeneratorBackend(ABC):
    """Abstract base for image generation backends."""

    def __init__(self, config: SkinConfig):
        self.config = config
        self.quality = config.quality

    @abstractmethod
    def generate(
        self,
        source_image: Image.Image,
        style_prompt: str,
        style_refs: list[Image.Image],
        asset_info: dict,
    ) -> Image.Image:
        """Generate a reskinned version of source_image."""
        ...

    def _encode_image_base64(self, img: Image.Image, fmt: str = "PNG") -> str:
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return base64.b64encode(buf.getvalue()).decode()

    def _decode_image_base64(self, data: str) -> Image.Image:
        return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGBA")


class LucyBackend(GeneratorBackend):
    """Decart Lucy API backend."""

    def __init__(self, config: SkinConfig):
        super().__init__(config)
        self.api_url = config.api_url or "https://api.decart.ai/v1"
        self.api_key = config.api_key
        if not self.api_key:
            raise ValueError("Lucy backend requires api_key in config")

    def generate(
        self,
        source_image: Image.Image,
        style_prompt: str,
        style_refs: list[Image.Image],
        asset_info: dict,
    ) -> Image.Image:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "prompt": style_prompt,
            "image": self._encode_image_base64(source_image),
            "strength": self.quality.strength,
            "guidance_scale": self.quality.guidance_scale,
            "num_inference_steps": self.quality.steps,
        }

        if style_refs:
            payload["style_images"] = [
                self._encode_image_base64(ref) for ref in style_refs
            ]

        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{self.api_url}/generate",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            result = resp.json()

        return self._decode_image_base64(result["image"])


class StabilityBackend(GeneratorBackend):
    """Stability AI img2img backend."""

    def __init__(self, config: SkinConfig):
        super().__init__(config)
        self.api_url = config.api_url or "https://api.stability.ai/v2beta"
        self.api_key = config.api_key
        if not self.api_key:
            raise ValueError("Stability backend requires api_key in config")

    def generate(
        self,
        source_image: Image.Image,
        style_prompt: str,
        style_refs: list[Image.Image],
        asset_info: dict,
    ) -> Image.Image:
        buf = io.BytesIO()
        source_image.convert("RGB").save(buf, format="PNG")
        buf.seek(0)

        files = {"image": ("source.png", buf, "image/png")}
        data = {
            "prompt": style_prompt,
            "strength": self.quality.strength,
            "cfg_scale": self.quality.guidance_scale,
            "steps": self.quality.steps,
            "output_format": "png",
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "image/*",
        }

        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{self.api_url}/stable-image/generate/sd3-turbo",
                headers=headers,
                files=files,
                data=data,
            )
            resp.raise_for_status()

        return Image.open(io.BytesIO(resp.content)).convert("RGBA")


class ComfyUIBackend(GeneratorBackend):
    """ComfyUI local server backend."""

    def __init__(self, config: SkinConfig):
        super().__init__(config)
        self.api_url = config.api_url or "http://127.0.0.1:8188"
        self.workflow_path = config.comfyui_workflow

    def _load_workflow(self) -> dict:
        if self.workflow_path and self.workflow_path.exists():
            return load_json(self.workflow_path)
        return self._default_workflow()

    def _default_workflow(self) -> dict:
        """Minimal img2img workflow for ComfyUI."""
        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 42,
                    "steps": self.quality.steps,
                    "cfg": self.quality.guidance_scale,
                    "sampler_name": "euler_ancestral",
                    "scheduler": "normal",
                    "denoise": self.quality.strength,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["12", 0],
                },
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "", "clip": ["4", 1]},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "blurry, low quality, distorted", "clip": ["4", 1]},
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            },
            "10": {
                "class_type": "LoadImage",
                "inputs": {"image": ""},
            },
            "12": {
                "class_type": "VAEEncode",
                "inputs": {"pixels": ["10", 0], "vae": ["4", 2]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"images": ["8", 0], "filename_prefix": "reskin"},
            },
        }

    def generate(
        self,
        source_image: Image.Image,
        style_prompt: str,
        style_refs: list[Image.Image],
        asset_info: dict,
    ) -> Image.Image:
        # Upload source image to ComfyUI
        buf = io.BytesIO()
        source_image.convert("RGB").save(buf, format="PNG")
        buf.seek(0)

        with httpx.Client(timeout=120) as client:
            upload_resp = client.post(
                f"{self.api_url}/upload/image",
                files={"image": ("input.png", buf, "image/png")},
            )
            upload_resp.raise_for_status()
            uploaded_name = upload_resp.json()["name"]

            # Build workflow
            workflow = self._load_workflow()
            if "6" in workflow:
                workflow["6"]["inputs"]["text"] = style_prompt
            if "10" in workflow:
                workflow["10"]["inputs"]["image"] = uploaded_name

            # Queue prompt
            queue_resp = client.post(
                f"{self.api_url}/prompt",
                json={"prompt": workflow},
            )
            queue_resp.raise_for_status()
            prompt_id = queue_resp.json()["prompt_id"]

            # Poll for completion
            while True:
                history_resp = client.get(f"{self.api_url}/history/{prompt_id}")
                history = history_resp.json()
                if prompt_id in history:
                    break
                time.sleep(1)

            # Get output image
            outputs = history[prompt_id]["outputs"]
            image_node = outputs.get("9", {})
            images = image_node.get("images", [])
            if not images:
                raise RuntimeError("ComfyUI returned no output images")

            img_info = images[0]
            img_resp = client.get(
                f"{self.api_url}/view",
                params={
                    "filename": img_info["filename"],
                    "subfolder": img_info.get("subfolder", ""),
                    "type": img_info.get("type", "output"),
                },
            )
            img_resp.raise_for_status()

        return Image.open(io.BytesIO(img_resp.content)).convert("RGBA")


class LocalDiffusionBackend(GeneratorBackend):
    """Local Stable Diffusion pipeline via diffusers library."""

    def __init__(self, config: SkinConfig):
        super().__init__(config)
        self._pipe = None

    def _get_pipe(self):
        if self._pipe is not None:
            return self._pipe

        try:
            import torch
            from diffusers import AutoPipelineForImage2Image
        except ImportError:
            raise ImportError(
                "Local backend requires diffusers + torch. "
                "Install with: pip install reskin-pipeline[local]"
            )

        self._pipe = AutoPipelineForImage2Image.from_pretrained(
            "stabilityai/sdxl-turbo",
            torch_dtype=torch.float16,
            variant="fp16",
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._pipe = self._pipe.to(device)
        logger.info(f"Loaded local diffusion pipeline on {device}")
        return self._pipe

    def generate(
        self,
        source_image: Image.Image,
        style_prompt: str,
        style_refs: list[Image.Image],
        asset_info: dict,
    ) -> Image.Image:
        pipe = self._get_pipe()

        # Resize source to a reasonable generation size (max 1024)
        src = source_image.convert("RGB")
        max_dim = max(src.size)
        if max_dim > 1024:
            scale = 1024 / max_dim
            src = src.resize(
                (int(src.width * scale), int(src.height * scale)),
                Image.LANCZOS,
            )

        result = pipe(
            prompt=style_prompt,
            image=src,
            strength=self.quality.strength,
            guidance_scale=self.quality.guidance_scale,
            num_inference_steps=self.quality.steps,
        )

        return result.images[0].convert("RGBA")


BACKENDS: dict[str, type[GeneratorBackend]] = {
    "lucy": LucyBackend,
    "stability": StabilityBackend,
    "comfyui": ComfyUIBackend,
    "local": LocalDiffusionBackend,
}


def get_backend(config: SkinConfig) -> GeneratorBackend:
    """Instantiate the configured generation backend."""
    cls = BACKENDS.get(config.backend)
    if cls is None:
        raise ValueError(f"Unknown backend: {config.backend}. Options: {list(BACKENDS)}")
    return cls(config)


def generate(config: SkinConfig) -> Path:
    """
    Run the generation phase:
    1. Load extraction manifest
    2. For each asset, generate a reskinned version
    3. Save outputs and update manifest with generated paths

    Supports checkpoint/resume — skips assets that already have generated output.
    Returns path to generation manifest.
    """
    manifest_path = config.output_dir / "extraction_manifest.json"
    manifest = load_json(manifest_path)
    assets = manifest["assets"]

    generated_dir = config.generated_dir()
    generated_dir.mkdir(parents=True, exist_ok=True)

    backend = get_backend(config)
    logger.info(f"Using backend: {config.backend}")

    # Load style reference images
    style_refs = []
    for ref_path in config.style_reference_images:
        if ref_path.exists():
            style_refs.append(load_image(ref_path))
            logger.info(f"Loaded style reference: {ref_path}")

    # Checkpoint tracking
    checkpoint_path = config.output_dir / "generation_checkpoint.json"
    completed: set[str] = set()
    if checkpoint_path.exists():
        completed = set(load_json(checkpoint_path).get("completed", []))
        logger.info(f"Resuming: {len(completed)} assets already generated")

    total = len(assets)
    for i, asset in enumerate(assets):
        rel_path = asset["relative_path"]

        if rel_path in completed:
            continue

        src_path = Path(asset["extracted_path"])
        out_path = generated_dir / asset["category"] / Path(rel_path).with_suffix(".png")

        logger.info(f"[{i + 1}/{total}] Generating: {rel_path}")

        try:
            source = load_image(src_path)
            result = backend.generate(
                source_image=source,
                style_prompt=config.style_prompt,
                style_refs=style_refs,
                asset_info=asset,
            )
            save_image(result, out_path)
            asset["generated_path"] = str(out_path)
            completed.add(rel_path)

            # Save checkpoint periodically
            if len(completed) % 10 == 0:
                save_json({"completed": list(completed)}, checkpoint_path)

        except Exception as e:
            logger.error(f"Failed to generate {rel_path}: {e}")
            asset["generation_error"] = str(e)

    # Final checkpoint
    save_json({"completed": list(completed)}, checkpoint_path)

    # Write generation manifest
    gen_manifest_path = config.output_dir / "generation_manifest.json"
    manifest["generated_count"] = len(completed)
    manifest["failed_count"] = total - len(completed)
    save_json(manifest, gen_manifest_path)
    logger.info(f"Generation complete: {len(completed)}/{total} assets")

    return gen_manifest_path
