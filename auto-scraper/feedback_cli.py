#!/usr/bin/env python3
"""Manual feedback CLI — record human verification without editing code.

Usage:
  python3 feedback_cli.py dead --company Jumio --title "Machine Learning Engineer" --note "WWR paywall, confirmed dead 2026-10-09"
  python3 feedback_cli.py unsuitable --company "X Corp" --title "Y" --note "reason"
  python3 feedback_cli.py useful --company "Z" --title "AI Engineer"
  python3 feedback_cli.py block-company --company "BadCorp" --note "spam"
  python3 feedback_cli.py list --decision dead
  python3 feedback_cli.py list-companies

Decisions: applied | rejected | dead | unsuitable | useful | interview | offer
dead/unsuitable/rejected suppress the job from all future sweeps and digests.
"""
import argparse
import sys

from feedback import (record_job_feedback, record_company_block, list_feedback,
                      load_feedback, JOB_DECISIONS)


def main():
    ap = argparse.ArgumentParser(description="Record manual job feedback")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ["dead", "unsuitable", "useful", "applied", "rejected",
                 "interview", "offer"]:
        p = sub.add_parser(name, help=f"mark job as {name}")
        p.add_argument("--company", required=True)
        p.add_argument("--title", required=True)
        p.add_argument("--url", default="")
        p.add_argument("--id", default="", help="stable job id if known (e.g. wad-slug)")
        p.add_argument("--note", default="")

    p = sub.add_parser("block-company", help="block an entire company")
    p.add_argument("--company", required=True)
    p.add_argument("--note", default="")

    p = sub.add_parser("list", help="list feedback entries")
    p.add_argument("--decision", default=None, choices=sorted(JOB_DECISIONS))
    p.add_argument("--limit", type=int, default=30)

    sub.add_parser("list-companies", help="list blocked companies")

    args = ap.parse_args()

    if args.cmd == "list":
        for r in list_feedback(args.decision, args.limit):
            print(f"[{r['decision']}] {r['title']} @ {r['company']} ({r['decided_at'][:10]})"
                  + (f" — {r['note'][:60]}" if r.get("note") else ""))
        return
    if args.cmd == "list-companies":
        data = load_feedback()
        for k, v in data["companies"].items():
            print(f"[blocked] {v['company']} — {v.get('reason','')[:60]}")
        return
    if args.cmd == "block-company":
        key = record_company_block(args.company, args.note)
        print(f"blocked company: {args.company} (key {key})")
        return

    job = {"company": args.company, "title": args.title,
           "url": args.url, "id": args.id}
    cid = record_job_feedback(job, args.cmd, note=args.note)
    print(f"recorded '{args.cmd}' for {args.title} @ {args.company} (id {cid})")


if __name__ == "__main__":
    sys.exit(main())
