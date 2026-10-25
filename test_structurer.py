import unittest
from matcha_structurer import extract_salary_range, extract_remote_regions, classify_taxonomy, generate_crisp_summary, structure_job_object

class TestMatchaStructurer(unittest.TestCase):
    def test_salary_extraction_formats(self):
        # Full format
        s_min, s_max, curr = extract_salary_range("Software Engineer ($120,000 - $180,000)")
        self.assertEqual(s_min, 120000)
        self.assertEqual(s_max, 180000)
        self.assertEqual(curr, "USD")

        # Shorthand 140k - 190k
        s_min, s_max, curr = extract_salary_range("Base compensation: $140k - $190k per year")
        self.assertEqual(s_min, 140000)
        self.assertEqual(s_max, 190000)
        self.assertEqual(curr, "USD")

        # Euro format
        s_min, s_max, curr = extract_salary_range("Salary: €75,000 - €95,000 gross")
        self.assertEqual(s_min, 75000)
        self.assertEqual(s_max, 95000)
        self.assertEqual(curr, "EUR")

    def test_remote_regions_us_vs_worldwide(self):
        # US restricted via description
        regions, summary = extract_remote_regions("Remote", "Candidates must reside in the US and have US work authorization.")
        self.assertEqual(regions, ["US"])
        self.assertIn("United States only", summary)

        # Real Thatch case: San Francisco, California; Remote (US)
        regions, summary = extract_remote_regions("San Francisco, California; Remote (US)", "We are hiring an infrastructure engineer.")
        self.assertEqual(regions, ["US"])
        self.assertIn("United States only", summary)

        # Real Buildkite case: United States - Pacific Time
        regions, summary = extract_remote_regions("United States - Pacific Time", "Forward deployed engineer role.")
        self.assertEqual(regions, ["US"])
        self.assertIn("United States", summary)

        # Worldwide
        regions, summary = extract_remote_regions("Remote", "We are a fully distributed team hiring anywhere in the world.")
        self.assertEqual(regions, ["Worldwide"])
        self.assertIn("worldwide", summary.lower())

        # Twin cities
        regions, summary = extract_remote_regions("Islamabad, Pakistan", "On-site role in Islamabad.")
        self.assertEqual(regions, ["Twin Cities"])

    def test_crisp_summary(self):
        desc = "Build next-generation RAG pipelines with Python, FastAPI, and LangChain for our enterprise LLM customers."
        summary = generate_crisp_summary("AI Engineer", "Together AI", desc)
        self.assertTrue(len(summary) > 20)
        self.assertIn("Together AI", summary)

    def test_full_structuring(self):
        job = {
            "title": "Full Stack AI Engineer",
            "company": "Together AI",
            "location": "Remote",
            "description": "Salary: $150,000 - $220,000. Build generative AI systems using Python, React, and PyTorch. Fully remote worldwide."
        }
        res = structure_job_object(job)
        self.assertEqual(res["salary_min"], 150000)
        self.assertEqual(res["salary_max"], 220000)
        self.assertEqual(res["remote_regions"], ["Worldwide"])
        self.assertEqual(res["job_type"], "ai_ml")
        self.assertTrue("job_summary" in res)

if __name__ == "__main__":
    unittest.main()
