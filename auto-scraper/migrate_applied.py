#!/usr/bin/env python3
"""Normalize applied.json status values (2026-10-09 P0).

Safe migration:
- Creates a timestamped backup before any change.
- Idempotent: running twice produces the same result.
- Reversible: restore from the backup file to undo.
- Unknown/missing statuses -> "needs_review" with the original value preserved
  in "_original_status". They NEVER blacklist; needs_review is non-terminal.

Canonical statuses:
  applied, submitted, submitted_confirmed, sent, rejected, dead, skipped,
  blocked, pending, needs_review

Usage: python3 migrate_applied.py [--dry-run]
"""
import json
import os
import shutil
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
APPLIED = os.path.join(BASE, "applied.json")
DRY = "--dry-run" in sys.argv

# mapping: old -> canonical. Terminal statuses block re-suggesting the company.
STATUS_MAP = {
    "submitted": "submitted",
    "submitted_confirmed": "submitted_confirmed",
    "confirmed": "submitted_confirmed",
    "sent": "sent",
    "applied": "applied",
    "rejected": "rejected",
    "rejected_visa_wall": "rejected",
    "dead": "dead",
    "skipped": "skipped",
    "skip": "skipped",
    "blocked": "blocked",
    "blocked_bot_check": "blocked",
    "blocked_captcha": "blocked",
    "blocked_site_crashes_renderer_3x": "blocked",
    "skipped_cloudflare_blocked": "blocked",
    "pending_browser": "pending",
    "pending_account": "pending",
    "pending_call": "pending",
    "draft_pending_approval": "pending",
    "submitted_unverified": "pending",
    "submitted_unconfirmed": "pending",
    "already_applied_in_portal": "applied",
    "bounced — resend pending": "pending",
    "bounced — no resend (already applied 2026-10-05)": "skipped",
}
# canonical terminal statuses (digest must not re-suggest these companies)
TERMINAL = {"submitted", "submitted_confirmed", "sent", "applied",
            "rejected", "dead", "blocked"}
# all canonical statuses (including non-terminal) — for idempotency check
CANONICAL_STATUSES = set(STATUS_MAP.values()) | {"needs_review"}


def main():
    with open(APPLIED) as f:
        data = json.load(f)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(BASE, f"applied.json.bak-{ts}")
    report = {"migrated_at": ts, "total": len(data), "mapped": 0,
              "already_canonical": 0, "needs_review": 0, "details": []}

    for e in data:
        old = e.get("status")
        # Idempotency: already-migrated records (canonical status + _original_status)
        # are left untouched. This preserves the true original on re-runs.
        if "_original_status" in e and old in CANONICAL_STATUSES:
            report["already_canonical"] += 1
            continue
        if old is None or (isinstance(old, str) and not old.strip()):
            new = "needs_review"
            e["_original_status"] = old
            e["status"] = new
            report["needs_review"] += 1
            report["details"].append({"company": e.get("company"), "title": e.get("title"),
                                     "old": old, "new": new})
        elif old in STATUS_MAP:
            new = STATUS_MAP[old]
            if new != old:
                e["_original_status"] = old
                e["status"] = new
                report["mapped"] += 1
            else:
                report["already_canonical"] += 1
        else:
            # unknown status: do NOT guess — needs_review, never terminal
            e["_original_status"] = old
            e["status"] = "needs_review"
            report["needs_review"] += 1
            report["details"].append({"company": e.get("company"), "title": e.get("title"),
                                      "old": old, "new": "needs_review"})

    print(f"total={report['total']} mapped={report['mapped']} "
          f"already_canonical={report['already_canonical']} "
          f"needs_review={report['needs_review']}")
    if DRY:
        print("DRY RUN — no changes written")
        for d in report["details"][:10]:
            print(f"  {d['company']} | {d['old']!r} -> {d['new']!r}")
        return

    shutil.copy2(APPLIED, backup)
    print(f"backup: {backup}")
    tmp = APPLIED + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, APPLIED)
    with open(os.path.join(BASE, f"applied-migration-{ts}.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(f"migrated {APPLIED}; report: applied-migration-{ts}.json")
    print("To undo: cp", backup, APPLIED)


if __name__ == "__main__":
    sys.exit(main())
