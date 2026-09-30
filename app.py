"""Vercel entrypoint for the API service (see vercel.json). The package lives in src/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from winback.api import app  # noqa: E402

__all__ = ["app"]
