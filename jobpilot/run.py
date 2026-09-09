"""
JOBPILOT entry point.
Run from repo root:  python jobpilot/run.py
  OR from jobpilot/: python run.py
"""
import sys
import pathlib

# Ensure the repo root (parent of this file's directory) is on sys.path
# so `import jobpilot` works whether run.py is invoked from inside or outside
_here = pathlib.Path(__file__).parent.resolve()
_root = _here.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    is_dev = os.environ.get("ENV", "").lower() == "development"
    uvicorn.run(
        "jobpilot.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=is_dev,
        reload_dirs=[str(_root)] if is_dev else None,
        log_level="info",
    )

