"""
Unit tests for Fresh Entry-Level Job Harvester and Filter Engine.
"""
import unittest
from scrapers.fresh_entry_scraper import (
    normalize_text,
    matches_target_role,
    is_entry_level_experience,
    classify_location,
    verify_live_url
)


class TestFreshEntryScraper(unittest.TestCase):
    def test_unicode_normalization(self):
        self.assertEqual(normalize_text("Islamābād"), "Islamabad")
        self.assertEqual(normalize_text("Rāwalpindi"), "Rawalpindi")
        self.assertEqual(normalize_text("São Paulo"), "Sao Paulo")

    def test_role_matching(self):
        # Positive matches
        self.assertTrue(matches_target_role("Junior AI Engineer"))
        self.assertTrue(matches_target_role("Machine Learning Engineer"))
        self.assertTrue(matches_target_role("Full Stack Developer"))
        self.assertTrue(matches_target_role("Prompt Engineer"))
        self.assertTrue(matches_target_role("Python Developer"))
        self.assertTrue(matches_target_role("Software Engineer"))

        # Negative senior exclusions
        self.assertFalse(matches_target_role("Senior AI Engineer"))
        self.assertFalse(matches_target_role("Lead Machine Learning Engineer"))
        self.assertFalse(matches_target_role("Staff Full Stack Developer"))
        self.assertFalse(matches_target_role("Engineering Manager"))
        self.assertFalse(matches_target_role("Principal Python Architect"))

        # Negative non-technical/non-target exclusions
        self.assertFalse(matches_target_role("QA Engineer"))
        self.assertFalse(matches_target_role("Sales Development Representative"))
        self.assertFalse(matches_target_role("Technical Support Specialist"))

    def test_experience_bounds(self):
        self.assertTrue(is_entry_level_experience("Looking for 1-2 years experience")[0])
        self.assertTrue(is_entry_level_experience("Entry level / fresh graduates welcome")[0])
        self.assertTrue(is_entry_level_experience("0-1 year experience in Python")[0])

        # Exclusions (>= 3 years)
        self.assertFalse(is_entry_level_experience("Requires 3+ years experience")[0])
        self.assertFalse(is_entry_level_experience("Minimum 5 years of software engineering")[0])
        self.assertFalse(is_entry_level_experience("At least 4 years in ML")[0])

    def test_location_classification(self):
        # Twin Cities
        cat, ok = classify_location("Islamabad, Pakistan")
        self.assertTrue(ok)
        self.assertEqual(cat, "Twin Cities (Islamabad/Rawalpindi)")

        # Diacritics test
        cat, ok = classify_location("Islāmābād, Pakistan")
        self.assertTrue(ok)
        self.assertEqual(cat, "Twin Cities (Islamabad/Rawalpindi)")

        cat, ok = classify_location("Rawalpindi")
        self.assertTrue(ok)
        self.assertEqual(cat, "Twin Cities (Islamabad/Rawalpindi)")

        # Worldwide Remote
        cat, ok = classify_location("Worldwide / Remote")
        self.assertTrue(ok)
        self.assertEqual(cat, "Worldwide Remote")

        cat, ok = classify_location("Remote (Work from anywhere)")
        self.assertTrue(ok)
        self.assertEqual(cat, "Worldwide Remote")

        # Ineligible / Restricted
        cat, ok = classify_location("Remote (US Only)")
        self.assertFalse(ok)

        cat, ok = classify_location("New York, NY")
        self.assertFalse(ok)

    def test_verify_live_url(self):
        ok, msg = verify_live_url("invalid-url")
        self.assertFalse(ok)
        self.assertEqual(msg, "Invalid URL format")


if __name__ == "__main__":
    unittest.main()
