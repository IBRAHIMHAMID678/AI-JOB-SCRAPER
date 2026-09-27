"""Run a frozen application batch (JSON) through the production apply pipeline.

Usage:
    python run_frozen_batch_apply.py [batch_file.json]

The batch file defaults to the most recent AUTO_APPLY_BATCH_*.json under the
repo's batches/ directory. Paths are resolved from the repo root via pathlib
so this works on Linux as well as Windows (audit item 43).
"""
import json
import sys
from pathlib import Path

# Repo root: this script's directory (previously a hardcoded Windows path).
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from production_batch_run import ProductionPipelineOrchestrator  # noqa: E402


def _default_batch_file() -> Path:
    batches_dir = REPO_ROOT / "batches"
    candidates = sorted(
        batches_dir.glob("AUTO_APPLY_BATCH_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No AUTO_APPLY_BATCH_*.json found under {batches_dir}. "
            "Pass a batch file path as the first CLI argument."
        )
    return candidates[0]


def main():
    if len(sys.argv) > 1:
        batch_file = Path(sys.argv[1])
        if not batch_file.is_absolute():
            batch_file = (REPO_ROOT / batch_file).resolve()
    else:
        batch_file = _default_batch_file()

    with open(batch_file, "r", encoding="utf-8") as f:
        batch_payload = json.load(f)

    batch_id = batch_payload["batch_id"]
    batch_jobs = batch_payload["jobs"]
    print(f"Loaded Batch: {batch_id} with {len(batch_jobs)} jobs (from {batch_file}).")

    orch = ProductionPipelineOrchestrator()
    results = orch.execute_batch_applications(batch_id, batch_jobs)

    print("\n" + "=" * 80)
    print("  BATCH EXECUTION COMPLETED")
    print("=" * 80)
    print("Stats:")
    print(json.dumps(orch.stats, indent=2))


if __name__ == "__main__":
    main()
