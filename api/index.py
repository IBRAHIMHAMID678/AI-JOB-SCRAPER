"""Vercel serverless entry point for JOBPILOT."""
import os
import sys
import pathlib

# Point database to /tmp (writable on Vercel) before any other imports
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/jobpilot.db")
os.environ.setdefault("SCRAPE_INTERVAL_HOURS", "0")   # disable APScheduler on serverless
os.environ.setdefault("LLM_PROVIDER", "groq")

# Make sure the project root is on sys.path so `jobpilot` package is found
root = pathlib.Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from jobpilot.api.main import app  # noqa: E402  — must come after env setup
