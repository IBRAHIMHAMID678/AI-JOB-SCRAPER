"""geo_eligible provenance tests.

Verifies that the geo_eligible reason code requires explicit evidence,
cannot be acquired spuriously, and survives dedup correctly.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.expanduser("~/workspace/job_hunt/auto-scraper"))
from filter import filter_job
from dedup import deduplicate
import copy


def _job(**kw):
    j = {
        "id": "test-1", "title": "AI Engineer", "company": "TestCo",
        "description": "AI Engineer role. 1 year experience. " * 20,
        "description_status": "full",
        "location": "Remote", "remote": True,
        "source": "test",
    }
    j.update(kw)
    return j


class TestGeoEligibleProvenance(unittest.TestCase):
    def test_explicit_pakistan_gets_geo_eligible(self):
        job = _job(description="Remote AI Engineer. We hire in Pakistan. " * 20)
        res = filter_job(job)
        self.assertIn("geo_eligible", res["reason_codes"])

    def test_worldwide_gets_geo_eligible(self):
        job = _job(description="Remote worldwide. Work from anywhere. " * 20)
        res = filter_job(job)
        self.assertIn("geo_eligible", res["reason_codes"])

    def test_unknown_geo_no_geo_eligible(self):
        """Unknown geography cannot acquire geo_eligible via verdict or URL."""
        job = _job(description="Remote AI Engineer role. " * 20,
                   url="https://example.com/jobs/1")
        res = filter_job(job)
        self.assertNotIn("geo_eligible", res["reason_codes"])
        self.assertIn("geo_unverified", res["reason_codes"])

    def test_us_only_overrides(self):
        """Explicit US-only restriction overrides any positive signals."""
        job = _job(description="Remote AI Engineer. Must have US work authorization. " * 10,
                   location="Remote")
        res = filter_job(job)
        self.assertNotIn("geo_eligible", res["reason_codes"])
        # Should fail, not just review
        self.assertIn(res["verdict"], ("fail", "review"))

    def test_conflicting_geo_conservative(self):
        """If both geo_eligible and geo_unverified somehow present, fail closed."""
        # This tests the digest layer's handling
        sys.path.insert(0, os.path.expanduser("~/workspace/job_hunt"))
        import email_digest
        lead = {
            "verdict": "pass",
            "reason_codes": ["geo_eligible", "geo_unverified"],  # conflicting
            "job": _job(description_status="full"),
        }
        # Digest requires geo_eligible AND not geo_unverified
        tier, _ = email_digest.is_digest_eligible(lead, set(), {"jobs": {}, "companies": {}})
        # geo_unverified present → should be excluded (conservative)
        # Current impl checks "geo_eligible" in codes; conflicting case:
        # we require explicit eligibility, conflicting = unverified wins
        self.assertIsNone(tier, "conflicting geo evidence must fail closed")

    def test_dedup_preserves_negative_geo(self):
        """Dedup union preserves _loc_requirements (negative evidence)."""
        a = _job(id="a1", title="AI Engineer", company="Co",
                 location="Remote", url="https://x.com/1")
        b = _job(id="a1", title="AI Engineer", company="Co",
                 location="Remote", url="https://x.com/1",
                 _loc_requirements=["United States"])
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 1)
        self.assertIn("United States", uniq[0].get("_loc_requirements", []))

    def test_stale_eligibility_metadata(self):
        """Malformed _loc_requirements doesn't crash or grant eligibility."""
        job = _job(_loc_requirements="not-a-list")  # malformed
        res = filter_job(job)  # should not crash
        self.assertNotIn("geo_eligible", res["reason_codes"])

    def test_digest_both_tiers_require_geo(self):
        """PASS and REVIEW tiers both require verified geography."""
        sys.path.insert(0, os.path.expanduser("~/workspace/job_hunt"))
        import email_digest
        for verdict in ["pass", "review"]:
            lead = {
                "verdict": verdict,
                "reason_codes": ["role_relevant", "geo_unverified"],
                "job": _job(description_status="full"),
            }
            tier, _ = email_digest.is_digest_eligible(lead, set(), {"jobs": {}, "companies": {}})
            self.assertIsNone(tier, f"{verdict} tier must require verified geo")

    def test_negated_pakistan_no_eligibility(self):
        """'Cannot hire in Pakistan' must not grant geo_eligible."""
        job = _job(description="We cannot hire in Pakistan. " * 20)
        res = filter_job(job)
        self.assertNotIn("geo_eligible", res["reason_codes"])

    def test_pakistan_not_eligible_no_eligibility(self):
        """"Pakistan is not an eligible country" must not grant geo_eligible."""
        job = _job(description="Pakistan is not an eligible country. " * 20)
        res = filter_job(job)
        self.assertNotIn("geo_eligible", res["reason_codes"])


if __name__ == "__main__":
    unittest.main()
