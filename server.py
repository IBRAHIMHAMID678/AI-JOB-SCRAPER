"""
JobPortal Main Server Entry Point.
Production-ready FastAPI application server.
Run with:
    python server.py
    OR
    python jobpilot/run.py
    OR
    uvicorn jobpilot.api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
import sys
import pathlib

# Ensure repo root is on sys.path
_ROOT = pathlib.Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from jobpilot.api.main import app
from jobpilot.core.config import settings

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Starting JobPortal Production Server on http://{host}:{port} ...", flush=True)
    uvicorn.run(
        "jobpilot.api.main:app",
        host=host,
        port=port,
        reload=settings.DEBUG,
        log_level="info",
    )
