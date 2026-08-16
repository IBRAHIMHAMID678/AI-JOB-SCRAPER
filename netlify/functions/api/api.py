"""Netlify serverless entry point for JOBPILOT (AWS Lambda via mangum)."""
import os
import sys
import pathlib

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/jobpilot.db")
os.environ.setdefault("SCRAPE_INTERVAL_HOURS", "0")
os.environ.setdefault("LLM_PROVIDER", "groq")

_root = pathlib.Path(__file__).parent.parent.parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

os.environ.setdefault("JOBPILOT_STATIC_DIR", str(_root / "jobpilot" / "static"))

from jobpilot.core.database import init_db
init_db()  # lifespan=off skips startup — init DB here

from mangum import Mangum
from jobpilot.api.main import app

_mangum = Mangum(app, lifespan="off")


def handler(event, context):
    """
    Netlify redirects /api/* → this function with :splat, which strips the
    /api/ prefix from the path. FastAPI routes are all registered under /api/
    so we restore the prefix before handing off to Mangum.
    """
    path = event.get("path", "/")
    if not path.startswith("/api"):
        event = dict(event)
        event["path"] = "/api/" + path.lstrip("/")
    return _mangum(event, context)
