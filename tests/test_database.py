import unittest
import sqlite3
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from database import init_sqlite, save_job_to_db, get_active_jobs_from_db, get_fresh_24h_jobs_from_db, SQLITE_DB_PATH

class TestDatabaseParity(unittest.TestCase):
    def test_schema_columns_exist(self):
        init_sqlite()
        conn = sqlite3.connect(SQLITE_DB_PATH)
        c = conn.cursor()
        c.execute("PRAGMA table_info(matched_jobs)")
        cols = {row[1] for row in c.fetchall()}
        conn.close()

        required = [
            "direct_career_url", "salary_min", "salary_max", "salary_currency",
            "remote_regions", "job_summary", "remote_summary", "date_posted",
            "is_24h_fresh", "company_size", "funding_total", "key_investors", "logo_url"
        ]
        for col in required:
            self.assertIn(col, cols, f"Missing column {col} in matched_jobs")

    def test_save_and_retrieve_matcha_job(self):
        sample_job = {
            "url": "https://test.example.com/careers/test-engineer-101",
            "title": "Senior AI Systems Architect",
            "company": "Together AI",
            "location": "Remote",
            "description": "Building next gen AI infra.",
            "source": "ats_greenhouse",
            "match_score": 95,
            "match_reason": "Top AI match",
            "estimated_pay": "$180,000 - $240,000",
            "direct_career_url": "https://together.ai/careers/101?gh_jid=101",
            "salary_min": 180000,
            "salary_max": 240000,
            "salary_currency": "USD",
            "remote_regions": ["Worldwide"],
            "job_summary": "Architect distributed LLM serving systems.",
            "remote_summary": "Fully remote worldwide",
            "date_posted": "2026-10-24T12:00:00Z",
            "is_24h_fresh": True,
            "company_size": 445,
            "funding_total": "$305M Series B",
            "key_investors": ["NVIDIA", "Salesforce Ventures"],
            "logo_url": "https://example.com/logo.png"
        }
        saved = save_job_to_db(sample_job)
        self.assertTrue(saved)

        active = get_active_jobs_from_db()
        matched = [j for j in active if j.get("url") == sample_job["url"]]
        self.assertTrue(len(matched) > 0)
        found = matched[0]
        self.assertEqual(found["direct_career_url"], sample_job["direct_career_url"])
        self.assertEqual(found["salary_min"], 180000)
        self.assertEqual(found["salary_max"], 240000)
        self.assertEqual(found["company_size"], 445)

        # Check fresh query
        fresh = get_fresh_24h_jobs_from_db()
        fresh_matched = [j for j in fresh if j.get("url") == sample_job["url"]]
        self.assertTrue(len(fresh_matched) > 0)

if __name__ == "__main__":
    unittest.main()
