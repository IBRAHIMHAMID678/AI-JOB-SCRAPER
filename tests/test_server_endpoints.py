import unittest
import os
import sys
from fastapi.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from server import app
from database import save_job_to_db

class TestServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Seed a fresh job
        cls.test_job = {
            "url": "https://test.together.ai/careers/fde-202",
            "title": "Forward Deployed LLM Engineer",
            "company": "Together AI",
            "location": "Remote",
            "description": "Distributed GPU inference post-training pipelines.",
            "source": "ats_greenhouse",
            "match_score": 98,
            "match_reason": "High-signal AI Match",
            "estimated_pay": "$190k - $250k",
            "direct_career_url": "https://together.ai/careers/fde-202?gh_jid=202",
            "salary_min": 190000,
            "salary_max": 250000,
            "salary_currency": "USD",
            "remote_regions": ["Worldwide"],
            "job_summary": "Lead client integration and post-training optimization of large language models on distributed GPU clusters.",
            "remote_summary": "Fully remote worldwide",
            "date_posted": "2026-10-24T18:00:00Z",
            "is_24h_fresh": True,
            "company_size": 445,
            "funding_total": "$305M Series B",
            "key_investors": ["NVIDIA", "Salesforce Ventures"],
            "logo_url": "https://example.com/logo.png"
        }
        save_job_to_db(cls.test_job)

    def test_get_fresh_jobs(self):
        resp = self.client.get("/api/jobs/fresh?hours=24")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "success")
        self.assertTrue(data.get("count", 0) > 0)
        urls = [j.get("url") for j in data.get("jobs", [])]
        self.assertIn(self.test_job["url"], urls)

    def test_search_jobs_with_filters(self):
        # Filter by keyword
        resp = self.client.get("/api/jobs/search?q=Together")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("count", 0) > 0)

        # Filter by investor
        resp_inv = self.client.get("/api/jobs/search?investor=NVIDIA")
        self.assertEqual(resp_inv.status_code, 200)
        data_inv = resp_inv.json()
        self.assertTrue(data_inv.get("count", 0) > 0)

    def test_apply_redirect(self):
        target = "https://together.ai/careers/fde-202?gh_jid=202"
        resp = self.client.get(f"/job/apply-redirect?url={target}", follow_redirects=False)
        self.assertEqual(resp.status_code, 307)
        self.assertEqual(resp.headers.get("location"), target)

    def test_legacy_saved_endpoint_intact(self):
        resp = self.client.get("/api/jobs/saved")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("jobs", data)

if __name__ == "__main__":
    unittest.main()
