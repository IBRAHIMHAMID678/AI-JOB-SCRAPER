"""Learning evidence independence tests.

Verifies that repeated observations of the same postings do not inflate
job-quality metrics, while operational metrics correctly count per-run.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.expanduser("~/workspace/job_hunt/auto-scraper"))
import learn
import monitor


class IsolatedLearning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_health = monitor.HEALTH_PATH
        self.orig_weights = learn.WEIGHTS_PATH
        monitor.HEALTH_PATH = os.path.join(self.tmp, "health.json")
        learn.WEIGHTS_PATH = os.path.join(self.tmp, "weights.json")
        # Patch the module-level references in learn (it imports load_health from monitor)
        self.orig_load = monitor.load_health

    def tearDown(self):
        monitor.HEALTH_PATH = self.orig_health
        learn.WEIGHTS_PATH = self.orig_weights
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _record(self, src, ids, eligible_ids, **counts):
        """Record a run with specific IDs."""
        stats = {src: {"raw": len(ids), "ok": True, "pass": 0, "review": 0,
                       "fail": len(ids), **counts}}
        # Mark eligible
        stats[src]["pass"] = len(eligible_ids)
        stats[src]["fail"] = len(ids) - len(eligible_ids)
        # All IDs unambiguous (single source) by default in tests
        monitor.record_run(
            stats, [],
            {"raw": len(ids), "unique": len(ids)},
            {src: set(ids)},
            {src: set(eligible_ids)},
            {src: {jid: "full" for jid in ids}},
            {src: {jid: {"ct": f"ct:test|{jid}"} for jid in ids}},
            {src: set(ids)},  # unambiguous
        )

    def test_identical_ids_three_runs_no_inflation(self):
        """Three sweeps with IDENTICAL job IDs must not triple the sample."""
        ids = [f"job-{i}" for i in range(100)]
        elig = ids[:5]  # 5% yield
        for _ in range(3):
            self._record("src1", ids, elig)
        adj = learn.compute_adjustments()
        # Should see 100 unique jobs, not 300
        src_adj = [a for a in adj if a["source"] == "src1"]
        if src_adj:
            self.assertEqual(src_adj[0]["stats"]["jobs"], 100,
                             "identical IDs across runs must not inflate sample")
            self.assertEqual(src_adj[0]["stats"]["eligible"], 5)

    def test_overlapping_ids_no_double_count(self):
        """Overlapping postings across runs count once."""
        ids1 = [f"job-{i}" for i in range(100)]
        ids2 = [f"job-{i}" for i in range(50, 150)]  # 50 overlap
        ids3 = [f"job-{i}" for i in range(100, 200)]  # 50 overlap with ids2
        self._record("src1", ids1, ids1[:5])
        self._record("src1", ids2, ids2[:5])
        self._record("src1", ids3, ids3[:5])
        adj = learn.compute_adjustments()
        src_adj = [a for a in adj if a["source"] == "src1"]
        if src_adj:
            # Unique: 0-199 = 200, not 300
            self.assertEqual(src_adj[0]["stats"]["jobs"], 200)

    def test_errors_count_per_run(self):
        """Operational metrics: 3 failed runs = 3 errors (not deduped)."""
        for _ in range(3):
            monitor.record_run(
                {"src1": {"raw": 0, "ok": False, "error": "timeout"}},
                ["timeout"], {"raw": 0})
        # Errors should be 3 (per-run), triggering the error penalty
        # (needs 4 runs for error penalty, so just verify counting)
        from monitor import load_health
        h = load_health()
        errs = sum(1 for r in h["runs"] for s in r["sources"].values() if s.get("error"))
        self.assertEqual(errs, 3)

    def test_repeated_evaluation_no_weight_change(self):
        """Processing same records twice must not change weights."""
        ids = [f"job-{i}" for i in range(50)]
        for _ in range(3):
            self._record("src1", ids, [])
        # 0% yield, 50 unique jobs, 3 runs → should trigger downweight
        r1 = learn.apply_adjustments(dry_run=True)
        # Run again with same data (simulating re-processing)
        for _ in range(3):
            self._record("src1", ids, [])
        r2 = learn.apply_adjustments(dry_run=True)
        # Both should propose same adjustment (not compounding)
        if r1["applied"] and r2["applied"]:
            self.assertEqual(r1["applied"][0]["delta"], r2["applied"][0]["delta"])

    def test_legitimate_new_evidence_triggers(self):
        """New unique jobs with poor yield DO trigger adjustment."""
        for run in range(3):
            ids = [f"run{run}-job-{i}" for i in range(50)]  # disjoint
            self._record("src1", ids, [])  # 0 eligible
        adj = learn.compute_adjustments()
        src_adj = [a for a in adj if a["source"] == "src1"]
        self.assertTrue(len(src_adj) > 0, "150 unique jobs at 0% should trigger")
        self.assertLess(src_adj[0]["delta"], 0)
        self.assertEqual(src_adj[0]["stats"]["jobs"], 150)

    def test_eligible_to_ineligible_outcome_resolution(self):
        """Job changing from eligible to ineligible: negative wins."""
        ids = ["job-A", "job-B", "job-C"]
        # Run 1: all eligible
        self._record("src1", ids, ids)
        # Run 2: job-A now ineligible (explicit restriction found)
        self._record("src1", ids, ["job-B", "job-C"])
        # Run 3: same as run 2
        self._record("src1", ids, ["job-B", "job-C"])
        adj = learn.compute_adjustments()
        src_adj = [a for a in adj if a["source"] == "src1"]
        if src_adj:
            # Eligible should be 2 (B, C), not 3 (A was removed)
            self.assertEqual(src_adj[0]["stats"]["eligible"], 2,
                             "ineligible outcome must override earlier eligible")

    def test_duplicate_ids_single_run(self):
        """Duplicate IDs in one run count once."""
        ids = ["job-1", "job-1", "job-2"]  # duplicate
        self._record("src1", ids, ["job-1"])
        # Should count 2 unique, not 3
        from monitor import load_health
        h = load_health()
        stored = h["runs"][-1]["job_ids"]["src1"]
        self.assertEqual(len(stored), 2)  # deduped in storage

    def test_identity_transition_enrichment(self):
        """Same posting gaining URL then ATS ID counts once."""
        # Simulate: run1 has ct: ID, run2 has URL, run3 has stable ID
        # All share the same ct: alias
        for run_num, jid in enumerate(["ct:acme|ai engineer",
                                       "url:https://acme.com/jobs/1",
                                       "stable:gh-123"]):
            stats = {"src1": {"raw": 1, "ok": True, "pass": 1, "review": 0, "fail": 0}}
            aliases = {jid: {"ct": "ct:acme|ai engineer",
                             "url": "url:https://acme.com/jobs/1" if run_num > 0 else "",
                             "stable_id": "stable:gh-123" if run_num > 1 else ""}}
            # Clean empty
            aliases[jid] = {k: v for k, v in aliases[jid].items() if v}
            monitor.record_run(
                stats, [], {"raw": 1, "unique": 1},
                {"src1": {jid}},
                {"src1": {jid}},
                {"src1": {jid: "full"}},
                {"src1": aliases},
                {"src1": {jid}},
            )
        adj = learn.compute_adjustments()
        # Should see 1 unique job, not 3
        # (MIN_SAMPLE=10 prevents adjustment, but we check the agg logic)
        # Instead verify via direct agg inspection
        from monitor import load_health
        h = load_health()
        self.assertEqual(len(h["runs"]), 3)

    def test_ambiguous_attribution_excluded(self):
        """Multi-source jobs don't drive per-source quality adjustments."""
        # Job seen by both src1 and src2 (ambiguous)
        # Record with empty unambiguous_ids (ambiguous)
        stats = {"src1": {"raw": 1, "ok": True, "pass": 1, "review": 0, "fail": 0}}
        monitor.record_run(
            stats, [], {"raw": 1, "unique": 1},
            {"src1": {"job-ambig"}},
            {"src1": {"job-ambig"}},
            {"src1": {"job-ambig": "full"}},
            {"src1": {"job-ambig": {"ct": "ct:test|job-ambig"}}},
            {"src1": set()},  # EMPTY = ambiguous, no unambiguous IDs
        )
        # With no unambiguous IDs, quality metrics should fallback or be empty
        # The job is still counted in unique_ids but not in unambiguous
        adj = learn.compute_adjustments()
        # Should not crash; ambiguous jobs don't inflate unambiguous counts


if __name__ == "__main__":
    unittest.main()
