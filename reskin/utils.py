"""Shared utilities for image I/O, hashing, and logging."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger("reskin")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def file_hash(path: Path) -> str:
    """SHA-256 hash of a file (first 16 hex chars)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_image(path: Path) -> Image.Image:
    """Load an image, converting to RGBA."""
    return Image.open(path).convert("RGBA")


def save_image(img: Image.Image, path: Path, fmt: str = "png") -> None:
    """Save an image, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "tga":
        img.save(path.with_suffix(".tga"), format="TGA")
    else:
        img.save(path.with_suffix(".png"), format="PNG")


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def save_json(data: dict | list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def nearest_power_of_2(n: int) -> int:
    """Round to nearest power of 2."""
    if n <= 0:
        return 1
    p = 1
    while p < n:
        p *= 2
    # Pick closer of p and p//2
    if p - n > n - p // 2 and p // 2 > 0:
        return p // 2
    return p
