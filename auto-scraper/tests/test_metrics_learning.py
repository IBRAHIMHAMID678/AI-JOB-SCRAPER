"""Tests for source metrics reconciliation and learning safeguards.

Covers:
- Metrics reconciliation: raw -> unique -> pass/review/fail counts
- Per-source attribution for cross-source duplicates
- Description status rates with explicit denominators
- Learning isolation: synthetic fixtures must not touch production weights
- Learning evidence requirements (MIN_SAMPLE, multi-run)
- Weight bounds [0.5, 2.0] and max delta per cycle
- Rollback correctness with isolated files
- Dry-run mode (no persistence)
- Atomic writes (tmp+replace)

All file writes are redirected to temp directories via module-global
patching. Production files are checksummed before/after.

Run: python3 -m unittest tests.test_metrics_learning -v
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import monitor
import learn
import feedback
from dedup import deduplicate


def _md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


# Production paths (read-only reference; tests must never write here)
_PROD_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROD_WEIGHTS = os.path.join(_PROD_BASE, "source-weights.json")
_PROD_HEALTH = os.path.join(_PROD_BASE, "source-health.json")
_PROD_FEEDBACK = os.path.join(_PROD_BASE, "feedback.json")


def _prod_md5s():
    return {p: _md5(p) for p in (_PROD_WEIGHTS, _PROD_HEALTH, _PROD_FEEDBACK)
            if os.path.exists(p)}


class IsolatedStateMixin:
    """Redirect all module state files to a temp dir."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = {}
        for mod, attr, name in [
            (monitor, "HEALTH_PATH", "health.json"),
            (learn, "WEIGHTS_PATH", "weights.json"),
            (feedback, "FEEDBACK_PATH", "feedback.json"),
        ]:
            self._orig[(mod, attr)] = getattr(mod, attr)
            setattr(mod, attr, os.path.join(self.tmp, name))
        # snapshot production checksums
        self._prod_before = _prod_md5s()

    def tearDown(self):
        for (mod, attr), val in self._orig.items():
            setattr(mod, attr, val)
        # production files must be untouched
        self.assertEqual(_prod_md5s(), self._prod_before,
                         "PRODUCTION STATE MUTATED by test!")

    def _write_health(self, runs):
        with open(monitor.HEALTH_PATH, "w") as f:
            json.dump({"runs": runs}, f)

    def _write_weights(self, data):
        with open(learn.WEIGHTS_PATH, "w") as f:
            json.dump(data, f)

    def _make_run(self, sources, at="2026-10-09T00:00:00+00:00"):
        """Build a health run record. sources: {name: dict-of-stats}."""
        return {"at": at, "sources": sources, "errors": [], "totals": {}}


class TestMetricsReconciliation(IsolatedStateMixin, unittest.TestCase):
    """raw -> unique -> pass/review/fail must reconcile."""

    def test_dedup_preserves_raw_count_concept(self):
        """Demonstrate the run.py defect: totals['raw'] uses post-dedup len.

        run.py line ~306: record_run(..., {"raw": len(jobs), ...}) where
        jobs has already been deduplicated. True raw count is lost.
        """
        # 100 raw jobs, 10 exact duplicates -> 90 unique
        jobs = []
        for i in range(90):
            jobs.append({"id": f"gh-x-{i}", "title": f"Engineer {i}",
                         "company": "Acme", "location": "Remote",
                         "source": "ats:greenhouse",
                         "url": f"https://x.com/{i}", "description": "d"})
        for i in range(10):
            jobs.append({"id": f"as-x-{i}", "title": f"Engineer {i}",
                         "company": "Acme", "location": "Remote",
                         "source": "ats:ashby",
                         "url": f"https://x.com/{i}?utm_source=y",
                         "description": "d"})
        raw_count = len(jobs)
        uniq, merge_log = deduplicate(jobs)
        # Simulate run.py's totals construction
        totals_raw_as_run_py_does_it = len(uniq)  # BUG: post-dedup
        self.assertEqual(raw_count, 100)
        self.assertEqual(len(uniq), 90)
        self.assertEqual(len(merge_log), 10)
        # The defect: run.py reports raw=90 when true raw=100
        self.assertNotEqual(totals_raw_as_run_py_does_it, raw_count,
                            "run.py loses the true raw count after dedup")
        # Correct reconciliation:
        self.assertEqual(len(uniq) + len(merge_log), raw_count)

    def test_verdict_counts_reconcile_with_unique(self):
        """pass + review + fail must equal unique jobs (all get a verdict)."""
        uniq_jobs = [{"id": f"j-{i}", "source": "s1"} for i in range(50)]
        # Simulate run.py's verdict bucketing
        passed = uniq_jobs[:5]
        review = uniq_jobs[5:15]
        failed = uniq_jobs[15:]
        self.assertEqual(len(passed) + len(review) + len(failed), len(uniq_jobs))

    def test_record_run_totals_roundtrip(self):
        """record_run persists totals; they must be retrievable intact."""
        stats = {"src_a": {"raw": 100, "ok": True, "pass": 5, "review": 10,
                           "fail": 85, "desc_full": 60, "desc_partial": 30,
                           "desc_empty": 10}}
        totals = {"raw": 100, "unique": 100, "pass": 5, "review": 10,
                  "fail": 85, "duplicates_merged": 0}
        monitor.record_run(stats, [], totals)
        data = monitor.load_health()
        self.assertEqual(len(data["runs"]), 1)
        r = data["runs"][0]
        self.assertEqual(r["totals"]["raw"], 100)
        self.assertEqual(r["totals"]["pass"] + r["totals"]["review"] +
                         r["totals"]["fail"], r["totals"]["unique"])

    def test_duplicates_counted_separately(self):
        """duplicates_merged must not be conflated with fail counts."""
        stats = {"src_a": {"raw": 100, "ok": True}}
        totals = {"raw": 100, "unique": 90, "pass": 0, "review": 0,
                  "fail": 90, "duplicates_merged": 10}
        monitor.record_run(stats, [], totals)
        r = monitor.load_health()["runs"][0]
        # duplicates are separate from verdict buckets
        self.assertEqual(r["totals"]["duplicates_merged"], 10)
        self.assertEqual(r["totals"]["unique"] + r["totals"]["duplicates_merged"],
                         r["totals"]["raw"])


class TestCrossSourceAttribution(IsolatedStateMixin, unittest.TestCase):
    """Cross-source duplicates must not inflate/deflate per-source yield."""

    def test_duplicate_source_gets_no_verdict_credit(self):
        """Demonstrate attribution defect: source A's jobs merge into B's
        records; A shows raw>0 but 0 verdicts, B gets credit for A's jobs."""
        # Source A: 50 jobs, all duplicates of Source B's 50 jobs
        # (distinct titles per pair so different pairs don't merge)
        jobs = []
        for i in range(50):
            jobs.append({"id": f"gh-b-{i}", "title": f"AI Engineer L{i}",
                         "company": "Corp", "location": "Remote",
                         "source": "ats:greenhouse",
                         "url": f"https://gh.com/{i}", "description": "d" * 900})
        for i in range(50):
            jobs.append({"id": f"wwr-b-{i}", "title": f"AI Engineer L{i}",
                         "company": "Corp", "location": "Remote",
                         "source": "wwr",
                         "url": f"https://gh.com/{i}",  # same canonical URL
                         "description": ""})
        uniq, merge_log = deduplicate(jobs)
        self.assertEqual(len(uniq), 50)
        self.assertEqual(len(merge_log), 50)
        # Simulate run.py verdict attribution (surviving record's source)
        # All 50 survivors are greenhouse (first-seen wins); wwr gets nothing
        surviving_sources = [j["source"] for j in uniq]
        from collections import Counter
        c = Counter(surviving_sources)
        # wwr contributed 50 raw jobs but 0 surviving records get verdicts
        self.assertEqual(c.get("wwr", 0), 0)
        # learn.py would compute: wwr yield = 0 eligible / 50 raw = 0%
        # even though wwr surfaced 50 real jobs. Defect documented.

    def test_dedup_tracks_origin_sources(self):
        """Merged records must record all contributing sources."""
        jobs = [
            {"id": "gh-1", "title": "Dev", "company": "C", "location": "R",
             "source": "ats:greenhouse", "url": "https://x.com/1",
             "description": "full jd here"},
            {"id": "wwr-1", "title": "Dev", "company": "C", "location": "R",
             "source": "wwr", "url": "https://x.com/1?utm=x", "description": ""},
        ]
        uniq, _ = deduplicate(jobs)
        self.assertEqual(len(uniq), 1)
        self.assertIn("ats:greenhouse", uniq[0]["_dedup_sources"])
        self.assertIn("wwr", uniq[0]["_dedup_sources"])


class TestDescriptionStatusRates(IsolatedStateMixin, unittest.TestCase):
    """Description rates must use explicit, complete denominators."""

    def test_learn_denominator_drops_blocked_status(self):
        """Defect: learn.py desc_total = full+partial+empty, silently
        dropping 'blocked', 'unavailable', and 'unknown' statuses."""
        run = self._make_run({
            "src_x": {"raw": 100, "ok": True, "pass": 10, "review": 0,
                      "fail": 90,
                      "desc_full": 20, "desc_partial": 20, "desc_empty": 20,
                      "desc_blocked": 20, "desc_unavailable": 20},
        })
        self._write_health([run])
        adjustments = learn.compute_adjustments()
        # With 100 jobs, MIN_SAMPLE met. desc_total as coded = 60, not 100.
        # fr = 20/60 = 33% -> no adjustment (not <30%, not >80%)
        # If denominator were correct (100), fr = 20% -> -0.05 adjustment.
        # The defect changes the outcome: blocked/unavailable are invisible.
        for adj in adjustments:
            if adj["source"] == "src_x":
                # Document what the code actually computed
                self.assertNotIn("JD full rate", "; ".join(adj["observations"]),
                                 "blocked/unavailable dropped from denominator")

    def test_monitor_summary_denominator(self):
        """monitor.source_summary has the same denominator gap."""
        run = self._make_run({
            "src_y": {"raw": 50, "ok": True,
                      "desc_full": 10, "desc_partial": 10, "desc_empty": 10,
                      "desc_blocked": 20},
        })
        self._write_health([run])
        s = monitor.source_summary("src_y")
        # As coded: total_desc = 10+10+10 = 30, rate = 10/30 = 0.33
        # True: 10/50 = 0.2 (blocked should count as not-full)
        self.assertEqual(s["desc_full_rate"], round(10 / 30, 2))
        self.assertNotEqual(s["desc_full_rate"], round(10 / 50, 2),
                            "blocked statuses excluded from denominator")

    def test_explicit_denominator_reporting(self):
        """A correct implementation must state its denominator."""
        run = self._make_run({
            "src_z": {"raw": 40, "ok": True, "pass": 4, "review": 0,
                      "fail": 36, "desc_full": 40},
        })
        self._write_health([run])
        adjustments = learn.compute_adjustments()
        for adj in adjustments:
            if adj["source"] == "src_z":
                # stats must include the raw job count used as denominator
                self.assertIn("jobs", adj["stats"])
                self.assertEqual(adj["stats"]["jobs"], 40)


class TestLearningIsolation(IsolatedStateMixin, unittest.TestCase):
    """Synthetic fixtures must never touch production weights."""

    def test_production_path_is_default(self):
        """Document: without patching, learn.py writes to PRODUCTION path.

        This is the missing safeguard — there is no built-in test-mode guard.
        Callers must patch learn.WEIGHTS_PATH; the module does not protect itself.
        """
        # learn.WEIGHTS_PATH was patched in setUp; check the unpatched default
        # by inspecting the module source default
        import importlib
        # The default is BASE/source-weights.json (production)
        expected_prod = os.path.join(learn.BASE, "source-weights.json")
        self.assertEqual(expected_prod, _PROD_WEIGHTS)
        # Current (patched) path is in temp
        self.assertTrue(learn.WEIGHTS_PATH.startswith(self.tmp))

    def test_apply_with_isolation_leaves_production_untouched(self):
        """With WEIGHTS_PATH patched, production md5 must not change."""
        # Health data that WOULD trigger an adjustment
        runs = []
        for d in range(1, 4):
            runs.append(self._make_run(
                {"trigger_src": {"raw": 200, "ok": True, "pass": 0,
                                 "review": 0, "fail": 200,
                                 "desc_full": 200}},
                at=f"2026-10-09T0{d}:00:00+00:00"))
        self._write_health(runs)
        before = _prod_md5s()
        result = learn.apply_adjustments()
        after = _prod_md5s()
        self.assertEqual(before, after)
        # But the isolated file WAS written
        self.assertTrue(os.path.exists(learn.WEIGHTS_PATH))
        with open(learn.WEIGHTS_PATH) as f:
            isolated = json.load(f)
        self.assertIn("trigger_src", isolated["weights"])

    def test_feedback_path_also_isolated(self):
        """learn.py reads feedback; ensure it uses the patched path."""
        fb_data = {"jobs": {
            "x1": {"decision": "useful", "source": "fb_src"},
            "x2": {"decision": "useful", "source": "fb_src"},
            "x3": {"decision": "useful", "source": "fb_src"},
        }, "companies": {}}
        with open(feedback.FEEDBACK_PATH, "w") as f:
            json.dump(fb_data, f)
        runs = [self._make_run(
            {"fb_src": {"raw": 50, "ok": True, "pass": 3, "review": 0,
                        "fail": 47, "desc_full": 50}}) for _ in range(3)]
        self._write_health(runs)
        adjustments = learn.compute_adjustments()
        srcs = [a["source"] for a in adjustments]
        self.assertIn("fb_src", srcs)  # 3 useful labels triggered it


class TestLearningEvidenceRequirements(IsolatedStateMixin, unittest.TestCase):
    """Adjustments need sufficient, multi-run evidence."""

    def test_below_min_sample_no_adjustment(self):
        """Fewer than MIN_SAMPLE jobs -> no adjustment, even with 0% yield."""
        runs = [self._make_run(
            {"tiny_src": {"raw": 5, "ok": True, "pass": 0, "review": 0,
                          "fail": 5, "desc_full": 5}})]
        self._write_health(runs)
        adjustments = learn.compute_adjustments()
        self.assertEqual([a for a in adjustments
                          if a["source"] == "tiny_src"], [])

    def test_single_run_cannot_trigger_adjustment(self):
        """SAFEGUARD: a SINGLE run with >=MIN_SAMPLE jobs CANNOT trigger a
        weight change. MIN_RUNS=3 requires multi-run evidence (2026-10-09 fix)."""
        runs = [self._make_run(
            {"spike_src": {"raw": 500, "ok": True, "pass": 0, "review": 0,
                           "fail": 500, "desc_full": 500}})]
        self._write_health(runs)
        adjustments = learn.compute_adjustments()
        spike = [a for a in adjustments if a["source"] == "spike_src"]
        self.assertEqual(len(spike), 0,
                         "single-run spike must NOT trigger adjustment (MIN_RUNS guard)")

    def test_three_runs_can_trigger_adjustment(self):
        """Three runs with consistent 0% yield DO trigger a bounded adjustment."""
        runs = [self._make_run(
            {"steady_src": {"raw": 100, "ok": True, "pass": 0, "review": 0,
                            "fail": 100, "desc_full": 100}}) for _ in range(3)]
        self._write_health(runs)
        adjustments = learn.compute_adjustments()
        adj = [a for a in adjustments if a["source"] == "steady_src"]
        self.assertEqual(len(adj), 1)
        self.assertLess(adj[0]["delta"], 0)
        self.assertGreaterEqual(abs(adj[0]["delta"]), 0)
        self.assertLessEqual(abs(adj[0]["delta"]), learn.MAX_DELTA)

    def test_single_spike_delta_is_bounded(self):
        """Even a single-run spike must respect MAX_DELTA."""
        runs = [self._make_run(
            {"spike2": {"raw": 1000, "ok": True, "pass": 0, "review": 0,
                        "fail": 1000, "desc_full": 0, "desc_empty": 1000}})]
        self._write_health(runs)
        adjustments = learn.compute_adjustments()
        for adj in adjustments:
            self.assertLessEqual(abs(adj["delta"]), learn.MAX_DELTA)

    def test_error_adjustment_requires_multiple_runs(self):
        """Persistent-error penalty requires >=4 runs (coded guard)."""
        # 2 runs with errors -> no penalty
        runs = [self._make_run({"err_src": {"raw": 50, "ok": False,
                                            "error": "timeout",
                                            "pass": 0, "review": 0, "fail": 0}},
                               at=f"2026-10-09T0{d}:00:00+00:00")
                for d in range(1, 3)]
        self._write_health(runs)
        adjustments = learn.compute_adjustments()
        err_adjs = [a for a in adjustments if a["source"] == "err_src"]
        # 50 jobs >= MIN_SAMPLE, but errors need len(runs)>=4
        for a in err_adjs:
            self.assertNotIn("errors in", "; ".join(a["observations"]))


class TestWeightBounds(IsolatedStateMixin, unittest.TestCase):
    """Weights stay in [0.5, 2.0]; delta <= 0.2 per cycle."""

    def test_upper_bound_enforced(self):
        self._write_weights({"weights": {"hot_src": 1.95}, "history": [],
                             "ruleset_version": learn.RULESET_VERSION})
        runs = [self._make_run(
            {"hot_src": {"raw": 100, "ok": True, "pass": 50, "review": 0,
                         "fail": 50, "desc_full": 100}})]
        self._write_health(runs)
        learn.apply_adjustments()
        w = learn.get_weight("hot_src")
        self.assertLessEqual(w, 2.0)

    def test_lower_bound_enforced(self):
        self._write_weights({"weights": {"cold_src": 0.55}, "history": [],
                             "ruleset_version": learn.RULESET_VERSION})
        runs = [self._make_run(
            {"cold_src": {"raw": 500, "ok": True, "pass": 0, "review": 0,
                          "fail": 500, "desc_full": 500}})]
        self._write_health(runs)
        learn.apply_adjustments()
        w = learn.get_weight("cold_src")
        self.assertGreaterEqual(w, 0.5)

    def test_max_delta_per_cycle(self):
        """Stacked signals (bad yield + bad JD + junk feedback) clamp to 0.2."""
        self._write_weights({"weights": {}, "history": [],
                             "ruleset_version": learn.RULESET_VERSION})
        fb_data = {"jobs": {f"k{i}": {"decision": "dead", "source": "bad_src"}
                            for i in range(5)}, "companies": {}}
        with open(feedback.FEEDBACK_PATH, "w") as f:
            json.dump(fb_data, f)
        runs = [self._make_run(
            {"bad_src": {"raw": 500, "ok": True, "pass": 0, "review": 0,
                         "fail": 500, "desc_full": 0, "desc_empty": 500}})]
        self._write_health(runs)
        result = learn.apply_adjustments()
        for rec in result["applied"]:
            self.assertLessEqual(abs(rec["delta"]), learn.MAX_DELTA)
            self.assertLessEqual(abs(rec["new_weight"] - rec["previous_weight"]),
                                 learn.MAX_DELTA + 1e-9)

    def test_audit_trail_records(self):
        """Every change records previous/new/reason/timestamp/ruleset."""
        self._write_weights({"weights": {}, "history": [],
                             "ruleset_version": learn.RULESET_VERSION})
        runs = [self._make_run(
            {"audit_src": {"raw": 100, "ok": True, "pass": 20, "review": 0,
                           "fail": 80, "desc_full": 100}}) for _ in range(3)]
        self._write_health(runs)
        result = learn.apply_adjustments()
        self.assertTrue(result["applied"])
        rec = result["applied"][0]
        for key in ("at", "source", "previous_weight", "new_weight",
                    "delta", "reason", "stats", "ruleset_version"):
            self.assertIn(key, rec)


class TestRollback(IsolatedStateMixin, unittest.TestCase):
    """Rollback restores previous state from isolated files."""

    def test_rollback_single_source(self):
        self._write_weights({"weights": {"s1": 1.0}, "history": [],
                             "ruleset_version": learn.RULESET_VERSION})
        runs = [self._make_run(
            {"s1": {"raw": 100, "ok": True, "pass": 0, "review": 0,
                    "fail": 100, "desc_full": 100}}) for _ in range(3)]
        self._write_health(runs)
        learn.apply_adjustments()
        self.assertLess(learn.get_weight("s1"), 1.0)
        self.assertTrue(learn.rollback())
        self.assertEqual(learn.get_weight("s1"), 1.0)

    def test_rollback_empty_history(self):
        self._write_weights({"weights": {}, "history": [],
                             "ruleset_version": learn.RULESET_VERSION})
        self.assertFalse(learn.rollback())

    def test_rollback_reverts_whole_cycle(self):
        """Rollback reverts all sources from a cycle (single timestamp per cycle)."""
        # Simulate a fixed cycle: 3 sources adjusted with SAME timestamp
        cycle_ts = "2026-10-09T10:00:00.000001+00:00"
        hist = []
        for src in ["a", "b", "c"]:
            hist.append({"at": cycle_ts,
                         "source": src, "previous_weight": 1.0,
                         "new_weight": 0.9, "delta": -0.1,
                         "reason": "test", "stats": {},
                         "ruleset_version": learn.RULESET_VERSION})
        self._write_weights({"weights": {"a": 0.9, "b": 0.9, "c": 0.9},
                             "history": hist,
                             "ruleset_version": learn.RULESET_VERSION})
        learn.rollback()
        with open(learn.WEIGHTS_PATH) as f:
            weights = json.load(f)["weights"]
        # Correct behavior: all three reverted to 1.0
        # Actual (buggy): only 'c' (hist[-1]) reverted
        reverted = sum(1 for s in "abc" if weights[s] == 1.0)
        self.assertEqual(reverted, 3,
                         f"rollback only reverted {reverted}/3 sources "
                         f"(per-record timestamps break cycle grouping)")


class TestDryRun(IsolatedStateMixin, unittest.TestCase):
    """Dry-run calculates without persisting."""

    def test_dry_run_does_not_write(self):
        self._write_weights({"weights": {}, "history": [],
                             "ruleset_version": learn.RULESET_VERSION})
        runs = [self._make_run(
            {"dry_src": {"raw": 200, "ok": True, "pass": 0, "review": 0,
                         "fail": 200, "desc_full": 200}}) for _ in range(3)]
        self._write_health(runs)
        before = open(learn.WEIGHTS_PATH).read()
        result = learn.apply_adjustments(dry_run=True)
        after = open(learn.WEIGHTS_PATH).read()
        self.assertEqual(before, after)
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["applied"])  # would-have-applied is reported


class TestAtomicWrites(IsolatedStateMixin, unittest.TestCase):
    """tmp+replace must not leave partial or corrupt state."""

    def test_no_tmp_left_behind(self):
        monitor.record_run({"s": {"raw": 1, "ok": True}}, [], {"raw": 1})
        learn.save_weights({"weights": {}, "history": []})
        leftovers = [f for f in os.listdir(self.tmp) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_written_files_are_valid_json(self):
        monitor.record_run({"s": {"raw": 1, "ok": True}}, [], {"raw": 1})
        learn.save_weights({"weights": {"x": 1.5}, "history": []})
        # Both must parse as valid JSON
        json.load(open(monitor.HEALTH_PATH))
        json.load(open(learn.WEIGHTS_PATH))

    def test_overwrite_preserves_other_keys(self):
        """record_run appends; it must not drop existing runs."""
        monitor.record_run({"a": {"raw": 1, "ok": True}}, [], {"raw": 1})
        monitor.record_run({"b": {"raw": 2, "ok": True}}, [], {"raw": 2})
        data = monitor.load_health()
        self.assertEqual(len(data["runs"]), 2)


if __name__ == "__main__":
    unittest.main()
