"""Discovery yield smoke test — repo-root-relative, works on any OS."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from production_batch_run import ProductionPipelineOrchestrator

orch = ProductionPipelineOrchestrator()
raw = orch.discover_raw_jobs()
print(f"Discovered raw jobs count: {len(raw)}")
qual = orch.filter_qualify_deduplicate(raw)
print(f"Filtered qualified opportunities: {len(qual)}")
for i, q in enumerate(qual[:25]):
    co = q['company']
    ti = q['title']
    loc = q['location']
    dt = q['posted_at']
    src = q['source']
    cid = q['canonical_job_id']
    print(f"{i+1:2d}. {co} -- {ti} -- {loc} -- {dt} -- {src} -- {cid}")
