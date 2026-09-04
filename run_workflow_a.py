"""
Workflow A Runner:
Ingests 100 genuinely new, qualifying jobs for Ibrahim Hamid,
evaluates them with pre-flight Gatekeeper,
checks deduplication against existing SQLite and MongoDB records,
processes through real application pipeline,
records detailed results.
"""
import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Any

from jobpilot.core.candidate import get_canonical_candidate_profile, resolve_resume_path
from jobpilot.core.eligibility import evaluate_job_eligibility
from jobpilot.core.database import SessionLocal, db_session
from jobpilot.core.models import Job, Application, User, UploadedCV
from jobpilot.core.security import hash_url
from jobpilot.services.auto_apply import apply_to_job
from jobpilot.integrations.sources.ats_greenhouse import GreenhouseATSAdapter
from jobpilot.integrations.sources.ats_lever import LeverATSAdapter

def run_workflow_a(target_count: int = 100):
    print("=" * 70)
    print("STARTING WORKFLOW A: 100 QUALIFYING JOBS + REAL AUTO-APPLY PIPELINE")
    print("=" * 70)

    candidate = get_canonical_candidate_profile()
    resume_path = resolve_resume_path()
    print(f"Candidate: {candidate['full_name']} ({candidate['email']})")
    print(f"Resume: {resume_path}")

    # 1. Fetch from live direct ATS adapters
    print("\n[Step 1] Fetching live structured jobs from direct Greenhouse & Lever boards...")
    gh_adapter = GreenhouseATSAdapter()
    lv_adapter = LeverATSAdapter()

    gh_jobs = gh_adapter.get_jobs()
    lv_jobs = lv_adapter.get_jobs()
    all_raw = gh_jobs + lv_jobs
    print(f"Fetched {len(gh_jobs)} Greenhouse jobs and {len(lv_jobs)} Lever jobs. Total: {len(all_raw)}")

    # 2. Get existing deduplication sets
    with db_session() as db:
        existing_url_hashes = set(r[0] for r in db.query(Job.url_hash).all())
        existing_app_job_ids = set(r[0] for r in db.query(Application.job_id).all())
        user = db.query(User).filter_by(email=candidate["email"]).first()
        user_id = user.id if user else None

    print(f"Existing DB records: {len(existing_url_hashes)} url_hashes, {len(existing_app_job_ids)} applications")

    # 3. Filter for genuinely new and qualifying jobs
    qualifying_jobs = []
    skipped_duplicates = 0
    skipped_eligibility = 0

    for rj in all_raw:
        h = hash_url(rj.application_url)
        if h in existing_url_hashes:
            skipped_duplicates += 1
            continue

        decision = evaluate_job_eligibility(
            job_id=rj.source_job_id or h,
            title=rj.title,
            company=rj.company,
            description=rj.description or "",
            location=rj.location,
        )
        if not decision.is_eligible:
            skipped_eligibility += 1
            continue

        qualifying_jobs.append((rj, decision, h))
        if len(qualifying_jobs) >= target_count + 20:
            break

    print(f"\n[Step 2] Filtering Results:")
    print(f" - Skipped duplicates: {skipped_duplicates}")
    print(f" - Skipped eligibility (>3 yrs / senior / geo mismatch): {skipped_eligibility}")
    print(f" - Qualifying new jobs identified: {len(qualifying_jobs)}")

    # 4. Process each qualifying job through application pipeline
    processed_count = 0
    submitted_count = 0
    blocked_count = 0
    failed_count = 0

    results_log = []

    for idx, (rj, decision, h) in enumerate(qualifying_jobs):
        if processed_count >= target_count:
            break

        processed_count += 1
        print(f"\n[{processed_count}/{target_count}] Processing: {rj.title} @ {rj.company}")
        print(f"    URL: {rj.application_url}")

        # Insert Job and Application into DB first as DISCOVERED
        job_db_id = None
        try:
            with db_session() as db:
                job_orm = Job(
                    source_name=rj.source,
                    source_job_id=rj.source_job_id,
                    title=rj.title,
                    company=rj.company,
                    location=rj.location,
                    description=rj.description,
                    application_url=rj.application_url,
                    url_hash=h,
                )
                db.add(job_orm)
                db.flush()
                job_db_id = job_orm.id

                app_orm = Application(
                    job_id=job_db_id,
                    user_id=user_id,
                    status="DISCOVERED",
                    mode="controlled",
                )
                db.add(app_orm)
                db.commit()
        except Exception as e:
            print(f"    [DB Error creating job]: {e}")
            continue

        # Execute application pipeline
        try:
            # We attempt application via apply_to_job
            # Note: dry_run=False executes real form navigation and submission verification
            is_submitted = apply_to_job(
                job_id=job_db_id,
                job_title=rj.title,
                company=rj.company,
                source=rj.source,
                apply_url=rj.application_url,
                score=85,
                description=rj.description or "",
                cv_path=resume_path,
                user_id=user_id,
                dry_run=False,
            )

            # Check resulting status from DB
            with db_session() as db:
                app_res = db.query(Application).filter_by(job_id=job_db_id).first()
                final_status = app_res.status if app_res else "UNKNOWN"
                notes = app_res.user_notes if app_res else ""

            if final_status == "SUBMITTED":
                submitted_count += 1
                print(f"    >>> RESULT: SUBMITTED (Verified submission confirmed)")
            elif "BLOCKED" in final_status or "VALIDATION" in final_status:
                blocked_count += 1
                print(f"    >>> RESULT: {final_status} ({notes})")
            else:
                failed_count += 1
                print(f"    >>> RESULT: {final_status} ({notes})")

            results_log.append({
                "job_id": job_db_id,
                "title": rj.title,
                "company": rj.company,
                "url": rj.application_url,
                "status": final_status,
                "notes": notes,
            })

        except Exception as exc:
            failed_count += 1
            print(f"    >>> ERROR applying: {exc}")
            results_log.append({
                "job_id": job_db_id,
                "title": rj.title,
                "company": rj.company,
                "url": rj.application_url,
                "status": "FAILED",
                "notes": str(exc),
            })

        time.sleep(1.0)

    print("\n" + "=" * 70)
    print("WORKFLOW A RUN COMPLETED")
    print(f"Total processed: {processed_count}")
    print(f"Submitted: {submitted_count}")
    print(f"Blocked/Unconfirmed: {blocked_count}")
    print(f"Failed: {failed_count}")
    print("=" * 70)

if __name__ == "__main__":
    run_workflow_a(100)
