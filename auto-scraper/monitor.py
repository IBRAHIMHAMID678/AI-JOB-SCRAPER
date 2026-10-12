"""Per-source health monitoring (2026-10-09 P1).

Tracks, per sweep run and per source:
  - last successful run, raw count, unique count
  - HTTP / parsing failures
  - description extraction success (full/partial/empty/blocked)
  - verdict distribution (pass/review/fail)
  - duplicate merge rate

Stored in source-health.json (rolling window of recent runs). A source that
fails is logged with its error — partial failures never hide behind a
successful overall exit code.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
HEALTH_PATH = os.path.join(BASE, "source-health.json")
MAX_RUNS_KEPT = 30  # rolling window


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_health() -> dict:
    try:
        with open(HEALTH_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"runs": []}


def save_health(data: dict):
    tmp = HEALTH_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, HEALTH_PATH)


def record_run(source_stats: dict, errors: list[str], totals: dict,
               source_job_ids: dict[str, set[str]] | None = None,
               source_eligible_ids: dict[str, set[str]] | None = None,
               source_desc_status: dict[str, dict[str, str]] | None = None,
               source_identity_aliases: dict[str, dict[str, dict]] | None = None,
               source_unambiguous_ids: dict[str, set[str]] | None = None):
    """Record one sweep run. source_stats: {source: {raw, unique, ...}}.
    source_job_ids: {source: set of job IDs} for unique-evidence tracking.
    source_eligible_ids: {source: set of eligible job IDs} for yield calculation.
    source_desc_status: {source: {job_id: status}} for description rate consistency.
    source_identity_aliases: {source: {job_id: {layer: value}}} for ID reconciliation.
    source_unambiguous_ids: {source: set of IDs} with single-source attribution."""
    data = load_health()
    run_rec = {
        "at": _now_iso(),
        "sources": source_stats,
        "errors": errors,
        "totals": totals,
    }
    if source_job_ids:
        run_rec["job_ids"] = {s: sorted(ids) for s, ids in source_job_ids.items() if ids}
    if source_eligible_ids:
        run_rec["eligible_ids"] = {s: sorted(ids) for s, ids in source_eligible_ids.items() if ids}
    if source_desc_status:
        run_rec["desc_status"] = {s: dict(m) for s, m in source_desc_status.items() if m}
    if source_identity_aliases:
        run_rec["identity_aliases"] = {s: dict(m) for s, m in source_identity_aliases.items() if m}
    if source_unambiguous_ids:
        run_rec["unambiguous_ids"] = {s: sorted(ids) for s, ids in source_unambiguous_ids.items() if ids}
    data["runs"].append(run_rec)
    data["runs"] = data["runs"][-MAX_RUNS_KEPT:]
    save_health(data)


def source_summary(source: str, window: int = 10) -> dict:
    """Aggregate stats for a source over the last `window` runs."""
    data = load_health()
    runs = data["runs"][-window:]
    agg = {"runs": 0, "ok_runs": 0, "raw": 0, "unique": 0,
           "desc_full": 0, "desc_partial": 0, "desc_empty": 0,
           "pass": 0, "review": 0, "fail": 0, "errors": []}
    for r in runs:
        s = r["sources"].get(source)
        if not s:
            continue
        agg["runs"] += 1
        if s.get("ok"):
            agg["ok_runs"] += 1
        for k in ("raw", "unique", "desc_full", "desc_partial", "desc_empty",
                  "pass", "review", "fail"):
            agg[k] += s.get(k, 0)
        if s.get("error"):
            agg["errors"].append(s["error"])
    if agg["runs"]:
        agg["success_rate"] = round(agg["ok_runs"] / agg["runs"], 2)
        total_desc = agg["desc_full"] + agg["desc_partial"] + agg["desc_empty"]
        agg["desc_full_rate"] = round(agg["desc_full"] / total_desc, 2) if total_desc else None
    return agg


def health_report(window: int = 10) -> str:
    """Human-readable per-source health summary."""
    data = load_health()
    sources = set()
    for r in data["runs"][-window:]:
        sources.update(r["sources"].keys())
    lines = [f"# Source health — last {window} runs", ""]
    for s in sorted(sources):
        a = source_summary(s, window)
        lines.append(
            f"- **{s}**: {a['ok_runs']}/{a['runs']} ok | "
            f"raw/run ~{a['raw'] // max(a['runs'], 1)} | "
            f"JD full {a['desc_full_rate']} | "
            f"pass {a['pass']}/review {a['review']}/fail {a['fail']}"
            + (f" | ERRORS: {a['errors'][-1][:60]}" if a["errors"] else "")
        )
    return "\n".join(lines)
