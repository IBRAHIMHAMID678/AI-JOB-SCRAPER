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

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "jobpilot.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(_root)],
        log_level="info",
    )
