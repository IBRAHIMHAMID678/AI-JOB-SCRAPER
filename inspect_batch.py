import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

path = r"d:\Job Scraper\batches\AUTO_APPLY_BATCH_20260905_181243.json"
with open(path, encoding="utf-8") as f:
    data = json.load(f)

jobs = data.get("jobs", [])
print(f"Total jobs in batch: {len(jobs)}")
sources = {}
for j in jobs:
    s = j.get("source", "unknown")
    sources[s] = sources.get(s, 0) + 1

print("Sources breakdown:", sources)
print("\nFirst 10 jobs in batch:")
for i, j in enumerate(jobs[:10], 1):
    company = j.get("company")
    title = j.get("title")
    url = j.get("application_url")
    loc = j.get("location")
    print(f"{i:2d}. [{company}] {title} | Loc: {loc} | URL: {url}")
