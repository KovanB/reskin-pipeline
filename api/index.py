"""Vercel serverless entry point — mounts the FastAPI app."""

import sys
from pathlib import Path

# Ensure project root is on the path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.api.main import app
