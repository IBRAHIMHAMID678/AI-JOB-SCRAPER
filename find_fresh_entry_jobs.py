#!/usr/bin/env python3
"""
CLI runner for finding fresh, verified entry-level AI, Python, Full Stack, and Prompt Engineering jobs.
Usage:
    python find_fresh_entry_jobs.py [--hours 24] [--output results.json]
"""
import sys
import os
import argparse
import json

# Ensure UTF-8 output encoding across Windows terminals
sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scrapers.fresh_entry_scraper import FreshEntryJobFinder


def main():
    parser = argparse.ArgumentParser(
        description="Harvest and verify fresh entry-level (< 2 yrs) jobs (Twin Cities & Worldwide Remote)."
    )
    parser.add_argument(
        "--hours", type=float, default=24.0, help="Maximum age of job postings in hours (default: 24.0)"
    )
    parser.add_argument(
        "--output", type=str, default="", help="Optional JSON file path to save verified jobs"
    )
    args = parser.parse_args()

    print(f"============================================================")
    print(f" FRESH ENTRY-LEVEL JOB HARVESTER (Past {args.hours} Hours)")
    print(f" Targets: AI/ML, Full Stack, Python, Prompt Roles (<= 2 yrs)")
    print(f" Locations: Twin Cities (ISB/RWP) & Worldwide Remote")
    print(f"============================================================\n")

    finder = FreshEntryJobFinder(hours_old=args.hours)
    results = finder.harvest()

    twin_cities = results.get("twin_cities", [])
    worldwide = results.get("worldwide_remote", [])

    print(f"\n📍 TWIN CITIES LOCAL JOBS ({len(twin_cities)} Verified Found):")
    print("-" * 60)
    if twin_cities:
        for idx, j in enumerate(twin_cities, 1):
            print(f" {idx}. {j['title']} @ {j['company']}")
            print(f"    Location: {j['location']}")
            print(f"    Link: {j['url']}")
            print(f"    Status: {j['verification_status']} | Exp: {j['experience_rating']}")
    else:
        print(" No Twin Cities postings matching criteria found in this harvest window.")

    print(f"\n🌐 WORLDWIDE REMOTE JOBS ({len(worldwide)} Verified Found):")
    print("-" * 60)
    if worldwide:
        for idx, j in enumerate(worldwide, 1):
            print(f" {idx}. {j['title']} @ {j['company']}")
            print(f"    Location: {j['location']}")
            print(f"    Link: {j['url']}")
            print(f"    Status: {j['verification_status']} | Exp: {j['experience_rating']}")
    else:
        print(" No Worldwide Remote postings matching criteria found in this harvest window.")

    if args.output:
        out_path = os.path.abspath(args.output)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nSaved verified job results to: {out_path}")


if __name__ == "__main__":
    main()
