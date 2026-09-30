"""Project paths and environment (.env is loaded once, here)."""

from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parents[2]
CONFIG_DIR = ROOT / "config"
PROMPTS_DIR = ROOT / "prompts"

load_dotenv(ROOT / ".env")
