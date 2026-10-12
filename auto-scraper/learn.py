"""Explainable feedback-driven ranking (2026-10-09 P2).

Adjusts SOURCE PRIORITY WEIGHTS (not eligibility rules) based on observed
outcomes. Deterministic, bounded, fully explainable.

Inputs:
- source-health.json: per-source yield (pass/review/fail, JD full rate)
- feedback.json: manual labels (useful, dead, unsuitable, junk)

Rules:
- Minimum 10 jobs from a source in the window before any adjustment.
- Rolling window: last 20 runs.
- Weight bounds: [0.5, 2.0]. Max change per cycle: ±0.2.
- One example never flips policy: adjustments need 3+ supporting observations.
- NEVER modifies legal, geographic, clearance, or seniority gates.
- Every change records: previous weight, new weight, reason, date, ruleset version.
- Rollback: `python3 learn.py --rollback` restores the previous weights.

Output: source-weights.json consumed by rank.py.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_PATH = os.path.join(BASE, "source-weights.json")
RULESET_VERSION = "2026-10-09-p2"

MIN_SAMPLE = 10       # min jobs from a source before adjusting
WINDOW_RUNS = 20      # rolling evaluation window
MIN_RUNS = 3          # min distinct runs with data (prevents single-run spikes)
MAX_DELTA = 0.2       # max weight change per cycle
MIN_WEIGHT, MAX_WEIGHT = 0.5, 2.0
MIN_OBSERVATIONS = 3  # supporting observations needed


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_weights(path: str | None = None) -> dict:
    p = path or WEIGHTS_PATH
    try:
        with open(p) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"weights": {}, "history": [], "ruleset_version": RULESET_VERSION}


def save_weights(data: dict, path: str | None = None):
    p = path or WEIGHTS_PATH
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, p)


def compute_adjustments() -> list[dict]:
    """Analyze health + feedback, propose bounded weight adjustments."""
    try:
        from monitor import load_health
        health = load_health()
    except ImportError:
        health = {"runs": []}
    try:
        from feedback import load_feedback
        fb = load_feedback()
    except ImportError:
        fb = {"jobs": {}}

    runs = health.get("runs", [])[-WINDOW_RUNS:]
    if not runs:
        return []

    # aggregate per source
    # Evidence model:
    # - Operational metrics (errors): count per-run (repeated observations valid)
    # - Quality metrics (yield, JD rate): use UNIQUE job IDs across runs.
    #   Repeated observations of the same postings do NOT inflate sample size.
    agg: dict[str, dict] = {}
    for r in runs:
        run_ids = r.get("job_ids", {})
        run_elig = r.get("eligible_ids", {})
        run_desc = r.get("desc_status", {})
        run_aliases = r.get("identity_aliases", {})
        run_unambig = r.get("unambiguous_ids", {})
        for src, s in r.get("sources", {}).items():
            a = agg.setdefault(src, {"jobs": 0, "eligible": 0, "desc_full": 0,
                                     "desc_total": 0, "errors": 0, "runs": 0,
                                     "unique_ids": set(), "eligible_ids": set(),
                                     "desc_by_id": {}, "alias_map": {},
                                     "unambiguous_ids": set()})
            a["runs"] += 1
            if s.get("error"):
                a["errors"] += 1
            ids = run_ids.get(src, [])
            eids = run_elig.get(src, [])
            dmap = run_desc.get(src, {})
            amap = run_aliases.get(src, {})
            uids = run_unambig.get(src, [])
            if ids:
                def canonical(jid):
                    aliases = amap.get(jid, {})
                    for known_id, known_aliases in a["alias_map"].items():
                        for layer in ("stable_id", "url", "ct"):
                            if (aliases.get(layer) and known_aliases.get(layer) and
                                    aliases[layer] == known_aliases[layer]):
                                return known_id
                    return jid

                id_set = set(ids)
                elig_set = set(eids)
                unambig_set = set(uids)
                canon_ids = {canonical(jid) for jid in id_set}
                canon_elig = {canonical(jid) for jid in elig_set}
                canon_unambig = {canonical(jid) for jid in unambig_set}
                for jid in id_set:
                    cj = canonical(jid)
                    if cj not in a["alias_map"]:
                        a["alias_map"][cj] = amap.get(jid, {})
                a["unique_ids"] |= canon_ids
                a["unambiguous_ids"] |= canon_unambig
                # Quality metrics use UNAMBIGUOUS IDs only (single-source attribution)
                # Ambiguous cross-source records cannot drive per-source adjustments
                newly_ineligible = (canon_ids - canon_elig) & a["eligible_ids"]
                a["eligible_ids"] -= newly_ineligible
                a["eligible_ids"] |= canon_elig
                for jid in id_set:
                    cj = canonical(jid)
                    if jid in dmap:
                        a["desc_by_id"][cj] = dmap[jid]
                # Use unambiguous counts for quality denominators
                # (fallback to all unique if unambiguous tracking unavailable)
                if a["unambiguous_ids"]:
                    a["jobs"] = len(a["unambiguous_ids"])
                    # Eligible must be subset of unambiguous
                    a["eligible"] = len(a["eligible_ids"] & a["unambiguous_ids"])
                else:
                    a["jobs"] = len(a["unique_ids"])
                    a["eligible"] = len(a["eligible_ids"])
                if a["eligible"] > a["jobs"]:
                    a["eligible"] = a["jobs"]
                # Description: only unambiguous jobs
                if a["unambiguous_ids"]:
                    a["desc_full"] = sum(1 for jid, st in a["desc_by_id"].items()
                                        if jid in a["unambiguous_ids"] and st == "full")
                    a["desc_total"] = len([j for j in a["desc_by_id"] if j in a["unambiguous_ids"]])
                else:
                    a["desc_full"] = sum(1 for st in a["desc_by_id"].values() if st == "full")
                    a["desc_total"] = len(a["desc_by_id"])
            else:
                a["legacy"] = True
                eligible = s.get("pass", 0) + s.get("review", 0)
                a["jobs"] += s.get("raw", 0)
                a["eligible"] += eligible
                df = s.get("desc_full", 0)
                dt = (df + s.get("desc_partial", 0) + s.get("desc_empty", 0)
                      + s.get("desc_blocked", 0) + s.get("desc_unavailable", 0))
                a["desc_full"] += df
                a["desc_total"] += dt

    # manual feedback per source
    fb_useful: dict[str, int] = {}
    fb_junk: dict[str, int] = {}
    for rec in fb.get("jobs", {}).values():
        src = rec.get("source", "manual")
        if rec.get("decision") == "useful":
            fb_useful[src] = fb_useful.get(src, 0) + 1
        elif rec.get("decision") in ("dead", "unsuitable"):
            fb_junk[src] = fb_junk.get(src, 0) + 1

    adjustments = []
    for src, a in agg.items():
        # Legacy mixed window: if source has BOTH legacy (summed) and new (unique-ID)
        # records, denominators are incompatible. Skip yield/desc adjustments
        # for this source until window is consistently new-format.
        # (Errors and feedback still work — they don't use job denominators.)
        has_legacy = a.get("legacy", False)
        has_new = len(a.get("unique_ids", set())) > 0
        mixed = has_legacy and has_new
        if a["jobs"] < MIN_SAMPLE:
            continue
        if a["runs"] < MIN_RUNS:
            continue
        observations = []
        delta = 0.0

        # eligible yield: >5% eligible is good, <1% is poor
        # Skip if mixed legacy/new window (incompatible denominators)
        if not mixed:
            y = a["eligible"] / max(a["jobs"], 1)
            if y > 0.05:
                delta += 0.1
                observations.append(f"eligible yield {y:.1%} (>{a['jobs']} jobs)")
            elif y < 0.01 and a["jobs"] >= 30:
                delta -= 0.1
                observations.append(f"eligible yield {y:.1%} (<1%, {a['jobs']} jobs)")

        # description completeness (skip if mixed window)
        if not mixed and a["desc_total"] >= MIN_SAMPLE:
            fr = a["desc_full"] / a["desc_total"]
            if fr > 0.8:
                delta += 0.05
                observations.append(f"JD full rate {fr:.0%}")
            elif fr < 0.3:
                delta -= 0.05
                observations.append(f"JD full rate {fr:.0%}")

        # manual feedback
        if fb_useful.get(src, 0) >= MIN_OBSERVATIONS:
            delta += 0.1
            observations.append(f"{fb_useful[src]} manual 'useful' labels")
        if fb_junk.get(src, 0) >= MIN_OBSERVATIONS:
            delta -= 0.1
            observations.append(f"{fb_junk[src]} manual junk/dead labels")

        # persistent errors
        if a["errors"] >= len(runs) // 2 and len(runs) >= 4:
            delta -= 0.1
            observations.append(f"errors in {a['errors']}/{len(runs)} runs")

        if not observations or delta == 0:
            continue
        delta = max(-MAX_DELTA, min(MAX_DELTA, delta))
        adjustments.append({
            "source": src, "delta": round(delta, 2),
            "observations": observations,
            "stats": {"jobs": a["jobs"], "eligible": a["eligible"],
                      "yield": round(y, 3)},
        })
    return adjustments


def apply_adjustments(dry_run: bool = False, weights_path: str | None = None) -> dict:
    data = load_weights(weights_path)
    weights = data.setdefault("weights", {})
    adjustments = compute_adjustments()
    applied = []
    cycle_at = _now_iso()  # single timestamp for the whole cycle (rollback groups by this)
    for adj in adjustments:
        src = adj["source"]
        old = weights.get(src, 1.0)
        new = round(max(MIN_WEIGHT, min(MAX_WEIGHT, old + adj["delta"])), 2)
        if new == old:
            continue
        record = {
            "at": cycle_at, "source": src,
            "previous_weight": old, "new_weight": new,
            "delta": adj["delta"], "reason": "; ".join(adj["observations"]),
            "stats": adj["stats"], "ruleset_version": RULESET_VERSION,
        }
        applied.append(record)
        if not dry_run:
            weights[src] = new
            data.setdefault("history", []).append(record)
    if not dry_run and applied:
        data["ruleset_version"] = RULESET_VERSION
        save_weights(data, weights_path)
    return {"applied": applied, "dry_run": dry_run}


def rollback(weights_path: str | None = None) -> bool:
    """Restore weights to before the last adjustment cycle."""
    data = load_weights(weights_path)
    hist = data.get("history", [])
    if not hist:
        return False
    last_at = hist[-1]["at"]
    # revert all changes from the last cycle (same timestamp)
    for rec in reversed(hist):
        if rec["at"] != last_at:
            break
        data["weights"][rec["source"]] = rec["previous_weight"]
    data["history"] = [h for h in hist if h["at"] != last_at]
    data["history"].append({"at": _now_iso(), "action": "rollback",
                            "reverted_cycle": last_at,
                            "ruleset_version": RULESET_VERSION})
    save_weights(data, weights_path)
    return True


def get_weight(source: str) -> float:
    return load_weights().get("weights", {}).get((source or "").lower(), 1.0)


if __name__ == "__main__":
    if "--rollback" in sys.argv:
        print("rolled back" if rollback() else "nothing to roll back")
    elif "--dry-run" in sys.argv:
        r = apply_adjustments(dry_run=True)
        print(f"would apply {len(r['applied'])} adjustments:")
        for a in r["applied"]:
            print(f"  {a['source']}: {a['previous_weight']} -> {a['new_weight']} ({a['reason'][:70]})")
    else:
        r = apply_adjustments()
        print(f"applied {len(r['applied'])} adjustments")
        for a in r["applied"]:
            print(f"  {a['source']}: {a['previous_weight']} -> {a['new_weight']}")
