"""Vercel serverless entry point for JOBPILOT."""
import os
import sys
import pathlib

# Set env vars before any imports — these apply on Vercel serverless
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/jobpilot.db")
os.environ.setdefault("SCRAPE_INTERVAL_HOURS", "0")   # disable APScheduler on serverless
os.environ.setdefault("LLM_PROVIDER", "groq")

# Resolve the repo root (parent of api/) and add to sys.path so `jobpilot` is importable
_api_dir = pathlib.Path(__file__).parent.resolve()
_root = _api_dir.parent
for _p in (_root, _api_dir):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Override the static directory to an absolute path resolvable at runtime on Vercel
os.environ.setdefault("JOBPILOT_STATIC_DIR", str(_root / "jobpilot" / "static"))

from jobpilot.api.main import app  # noqa: E402  — must come after path/env setup
