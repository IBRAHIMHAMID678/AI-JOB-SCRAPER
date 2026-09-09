import json
import os
import sys
from datetime import datetime

# Add root to sys.path
sys.path.insert(0, r"d:\Job Scraper")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from production_batch_run import ProductionPipelineOrchestrator

def main():
    batch_file = r"d:\Job Scraper\batches\AUTO_APPLY_BATCH_20260905_181243.json"
    with open(batch_file, "r", encoding="utf-8") as f:
        batch_payload = json.load(f)

    batch_id = batch_payload["batch_id"]
    batch_jobs = batch_payload["jobs"]
    print(f"Loaded Batch: {batch_id} with {len(batch_jobs)} jobs.")

    orch = ProductionPipelineOrchestrator()
    results = orch.execute_batch_applications(batch_id, batch_jobs)

    print("\n" + "="*80)
    print("  BATCH EXECUTION COMPLETED")
    print("="*80)
    print("Stats:")
    print(json.dumps(orch.stats, indent=2))

if __name__ == "__main__":
    main()
