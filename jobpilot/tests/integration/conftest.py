"""Integration test setup — fresh database per test session."""
import os
import pathlib
import pytest

# Must be set before any jobpilot imports
os.environ["GROQ_API_KEY"] = "test-key"
os.environ["DATABASE_URL"] = "sqlite:///./test_integration.db"
os.environ["LLM_PROVIDER"] = "groq"
os.environ["SCRAPE_INTERVAL_HOURS"] = "0"  # disable auto-scheduler in tests


@pytest.fixture(scope="session", autouse=True)
def fresh_db():
    """Delete the integration test DB before the session starts."""
    try:
        pathlib.Path("test_integration.db").unlink(missing_ok=True)
    except PermissionError:
        pass  # Windows file lock from previous process; reuse or let next cleanup handle
    yield
    try:
        pathlib.Path("test_integration.db").unlink(missing_ok=True)
    except PermissionError:
        pass  # Windows may still hold a lock; cleanup happens next session start
