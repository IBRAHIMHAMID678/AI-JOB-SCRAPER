"""
conftest.py for jobpilot/tests/

Inherits all fixtures from the parent conftest at jobpilot/conftest.py.
This file repeats the sys.path and env-var setup so that tests can also be
run with pytest invoked directly from the `tests/` or `tests/unit/`
directory.
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
# 2. Ensure project root is on sys.path.
# ---------------------------------------------------------------------------
# This file lives at:  <root>/jobpilot/tests/conftest.py
# The package root is: <root>/  (two levels up)
_TESTS_DIR = pathlib.Path(__file__).parent            # …/jobpilot/tests/
_PACKAGE_DIR = _TESTS_DIR.parent                      # …/jobpilot/
_PROJECT_ROOT = _PACKAGE_DIR.parent                   # …/AI-JOB-SCRAPER-main/

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# 3. Session-scoped autouse fixture.
# ---------------------------------------------------------------------------
import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _set_test_env():
    """
    Guarantees the required environment variables are set for the entire test
    session and restores original values on teardown.
    """
    env_patch = {
        "DATABASE_URL": "sqlite:///./test_jobpilot.db",
        "GROQ_API_KEY": "test-key",
        "LLM_PROVIDER": "groq",
    }
    original = {k: os.environ.get(k) for k in env_patch}
    os.environ.update(env_patch)
    yield
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
