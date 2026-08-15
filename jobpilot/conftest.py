"""
Root-level conftest.py for the jobpilot package.

Ensures the project root (AI-JOB-SCRAPER-main) is on sys.path so that
`import jobpilot` resolves correctly regardless of how pytest is invoked.
Environment variables required by jobpilot modules are set here at module
level so they are present before any jobpilot code is imported.
"""
import os
import sys
import pathlib

# ---------------------------------------------------------------------------
# 1. Set required environment variables BEFORE any jobpilot module is imported.
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_jobpilot.db")
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("LLM_PROVIDER", "groq")

# ---------------------------------------------------------------------------
# 2. Make sure the project root (parent of the `jobpilot` package directory)
#    is on sys.path so `from jobpilot.xxx import yyy` works.
# ---------------------------------------------------------------------------
# This file lives at:  <root>/jobpilot/conftest.py
# The package root is: <root>/  (one level up)
_PACKAGE_DIR = pathlib.Path(__file__).parent          # …/jobpilot/
_PROJECT_ROOT = _PACKAGE_DIR.parent                   # …/AI-JOB-SCRAPER-main/

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# 3. Shared session-scoped fixture (available to every test under jobpilot/).
# ---------------------------------------------------------------------------
import pytest  # noqa: E402 — import after sys.path is set


@pytest.fixture(scope="session", autouse=True)
def _set_test_env():
    """
    Session-scoped autouse fixture that guarantees the required environment
    variables are set for the entire test session.  Values are set at module
    level above as well, but keeping them here makes the intent explicit and
    guards against any later mutation.
    """
    env_patch = {
        "DATABASE_URL": "sqlite:///./test_jobpilot.db",
        "GROQ_API_KEY": "test-key",
        "LLM_PROVIDER": "groq",
    }
    original = {k: os.environ.get(k) for k in env_patch}
    os.environ.update(env_patch)
    yield
    # Restore original values after the session finishes.
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
