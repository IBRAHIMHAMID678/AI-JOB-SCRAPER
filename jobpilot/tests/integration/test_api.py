"""Integration tests for JOBPILOT API — hit a real SQLite DB."""
import pytest
from fastapi.testclient import TestClient
from jobpilot.api.main import app


from jobpilot.api.routes.auth import get_current_user
from jobpilot.core.models import User


@pytest.fixture(scope="module")
def client():
    mock_user = User(id="test-user-id", username="testuser", email="test@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()



class TestHealth:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_system_status(self, client):
        r = client.get("/api/system/status")
        assert r.status_code == 200
        data = r.json()
        assert data["database"] == "connected"
        assert "jobs_total" in data
        assert "next_scheduled_run" in data

    def test_system_config(self, client):
        r = client.get("/api/system/config")
        assert r.status_code == 200
        data = r.json()
        assert "score_thresholds" in data
        assert "candidate" in data


class TestProfile:
    def test_get_profile(self, client):
        r = client.get("/api/profile")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Ibrahim Hamid"
        assert isinstance(data["skills"], list)
        assert "Python" in data["skills"]

    def test_update_profile_name(self, client):
        try:
            r = client.put("/api/profile", json={"name": "Updated Name"})
            assert r.status_code == 200
            assert r.json()["status"] == "updated"

            r2 = client.get("/api/profile")
            assert r2.json()["name"] == "Updated Name"
        finally:
            client.put("/api/profile", json={"name": "Ibrahim Hamid"})

    def test_update_profile_skills(self, client):
        r = client.put("/api/profile", json={"skills": ["Python", "Go", "Rust"]})
        assert r.status_code == 200
        r2 = client.get("/api/profile")
        assert r2.json()["skills"] == ["Python", "Go", "Rust"]

    def test_partial_update_leaves_other_fields(self, client):
        client.put("/api/profile", json={"location": "Lahore, Pakistan"})
        r = client.get("/api/profile")
        data = r.json()
        assert data["location"] == "Lahore, Pakistan"
        assert data["email"] == "ibrahimhamid.2600@gmail.com"  # unchanged


class TestSettings:
    def test_get_settings_empty(self, client):
        r = client.get("/api/settings")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_upsert_setting(self, client):
        r = client.put("/api/settings/SCORE_AUTO_APPROVE", json={"value": 50})
        assert r.status_code == 200
        assert r.json()["key"] == "SCORE_AUTO_APPROVE"

        r2 = client.get("/api/settings")
        assert "SCORE_AUTO_APPROVE" in r2.json()

    def test_rejects_unknown_setting(self, client):
        r = client.put("/api/settings/EVIL_SETTING", json={"value": "hack"})
        assert r.status_code == 400


class TestJobs:
    def test_list_jobs_empty(self, client):
        r = client.get("/api/jobs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_analytics_summary(self, client):
        r = client.get("/api/analytics/summary")
        assert r.status_code == 200
        data = r.json()
        assert "jobs_discovered" in data

    def test_applications_list(self, client):
        r = client.get("/api/applications")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_404_for_missing_application(self, client):
        r = client.get("/api/applications/nonexistent-id")
        assert r.status_code == 404

    def test_404_for_missing_resume(self, client):
        r = client.get("/api/applications/nonexistent-id/resume")
        assert r.status_code == 404
