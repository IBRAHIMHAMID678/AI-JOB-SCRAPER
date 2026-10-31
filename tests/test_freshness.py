import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import unittest
from datetime import datetime, timezone, timedelta
from freshness_engine import parse_iso_or_epoch, verify_24h_freshness, contains_dead_job_markers

class TestFreshnessEngine(unittest.TestCase):
    def setUp(self):
        self.ref_now = datetime(2026, 10, 24, 15, 0, 0, tzinfo=timezone.utc)

    def test_recent_2h_pass(self):
        # 2 hours ago
        dt = self.ref_now - timedelta(hours=2)
        is_fresh, hrs, parsed_dt, reason = verify_24h_freshness(dt.isoformat(), reference_time=self.ref_now)
        self.assertTrue(is_fresh)
        self.assertAlmostEqual(hrs, 2.0, places=1)
        self.assertIn("PASS", reason)

    def test_edge_23h59m_pass(self):
        # 23 hours 59 minutes ago
        dt = self.ref_now - timedelta(hours=23, minutes=59)
        is_fresh, hrs, parsed_dt, reason = verify_24h_freshness(dt.isoformat(), reference_time=self.ref_now)
        self.assertTrue(is_fresh)
        self.assertAlmostEqual(hrs, 23.98, places=1)
        self.assertIn("PASS", reason)

    def test_edge_24h01m_reject(self):
        # 24 hours 1 minute ago
        dt = self.ref_now - timedelta(hours=24, minutes=1)
        is_fresh, hrs, parsed_dt, reason = verify_24h_freshness(dt.isoformat(), reference_time=self.ref_now)
        self.assertFalse(is_fresh)
        self.assertGreater(hrs, 24.0)
        self.assertIn("REJECTED", reason)

    def test_30_days_old_reject(self):
        dt = self.ref_now - timedelta(days=30)
        is_fresh, hrs, parsed_dt, reason = verify_24h_freshness(dt.isoformat(), reference_time=self.ref_now)
        self.assertFalse(is_fresh)
        self.assertIn("REJECTED", reason)

    def test_missing_or_invalid_reject(self):
        for invalid in [None, "", "null", "undefined", "random text without date"]:
            is_fresh, hrs, parsed_dt, reason = verify_24h_freshness(invalid, reference_time=self.ref_now)
            self.assertFalse(is_fresh)
            self.assertIn("REJECTED", reason)

    def test_epoch_timestamp(self):
        # 3 hours ago in epoch ms
        dt = self.ref_now - timedelta(hours=3)
        epoch_ms = int(dt.timestamp() * 1000)
        is_fresh, hrs, parsed_dt, reason = verify_24h_freshness(epoch_ms, reference_time=self.ref_now)
        self.assertTrue(is_fresh)
        self.assertAlmostEqual(hrs, 3.0, places=1)

    def test_dead_job_markers(self):
        sample_page = "<html><body>Sorry, this position has been filled. Explore other opportunities.</body></html>"
        is_dead, marker = contains_dead_job_markers(sample_page)
        self.assertTrue(is_dead)
        self.assertEqual(marker, "this position has been filled")

        active_page = "<html><body>We are looking for a Senior Staff AI Engineer to build distributed LLMs. Apply below!</body></html>"
        is_dead, marker = contains_dead_job_markers(active_page)
        self.assertFalse(is_dead)

if __name__ == "__main__":
    unittest.main()
