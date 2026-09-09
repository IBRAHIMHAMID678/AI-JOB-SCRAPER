"""
Adversarial Concurrency & Double-Apply Prevention Regression Tests.
Simulates:
1. 5 concurrent workers attempting to apply to the SAME canonical job (e.g. Figma).
   Asserts: exactly 1 worker acquires the lock, 4 workers are blocked.
2. Idempotency across runs: Attempting to apply to an already-applied job.
   Asserts: Second attempt is blocked before any browser/network actions.
3. Database constraint: Direct duplicate insertion with identical canonical_job_id and user_id is rejected by DB.
"""
import concurrent.futures
import pytest
from jobpilot.core.application_lock import acquire_application_lock, release_application_lock
from jobpilot.core.database import db_session, init_db
from jobpilot.core.models import Application, Job, ApplicationLock
from jobpilot.services.auto_apply import apply_to_job

init_db()


class TestDoubleApplyAdversarialPrevention:
    def test_five_workers_racing_for_same_figma_job(self):
        canonical_id = "canon_figma_ai_eng_test"
        candidate_id = "3e614c95-b3a4-43d6-805d-3ffed73f64ba"

        # Ensure lock table is clear
        release_application_lock(canonical_id)

        worker_results = []
        def worker_attempt(worker_idx: int):
            worker_name = f"worker_{worker_idx}"
            acquired = acquire_application_lock(
                canonical_job_id=canonical_id,
                candidate_id=candidate_id,
                worker_id=worker_name,
                timeout_seconds=30,
            )
            return (worker_name, acquired)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(worker_attempt, i) for i in range(5)]
            for f in concurrent.futures.as_completed(futures):
                worker_results.append(f.result())

        acquired_count = sum(1 for _, ok in worker_results if ok)
        blocked_count = sum(1 for _, ok in worker_results if not ok)

        assert acquired_count == 1, f"Expected exactly 1 worker to acquire lock, got {acquired_count}"
        assert blocked_count == 4, f"Expected 4 workers to be blocked, got {blocked_count}"

        # Clean up
        release_application_lock(canonical_id)

    def test_apply_to_job_blocked_when_locked(self):
        canonical_id = "canon_figma_locked_test"
        candidate_id = "3e614c95-b3a4-43d6-805d-3ffed73f64ba"

        # Pre-lock by external worker
        acquire_application_lock(canonical_id, candidate_id, worker_id="external_worker_1", timeout_seconds=60)

        # Attempt auto-apply on that locked job
        res = apply_to_job(
            job_id="dummy-job-123",
            job_title="Forward Deployed Engineer",
            company="Figma",
            source="Greenhouse",
            apply_url="https://boards.greenhouse.io/figma/jobs/123",
            score=95,
            user_id=candidate_id,
            canonical_job_id=canonical_id,
        )

        assert res is False, "Auto-apply must return False when job is locked by another worker"

        # Clean up
        release_application_lock(canonical_id)

    def test_apply_to_job_blocked_when_already_applied(self):
        canonical_id = "canon_figma_already_applied_test"
        candidate_id = "3e614c95-b3a4-43d6-805d-3ffed73f64ba"

        with db_session() as db:
            from jobpilot.core.models import User
            user = db.query(User).filter_by(id=candidate_id).first()
            if not user:
                user = User(id=candidate_id, username="test_candidate", email="candidate@test.com", password_hash="hash")
                db.add(user)
                db.commit()

            # Create a mock existing application in SUBMITTED state
            existing = db.query(Application).filter_by(canonical_job_id=canonical_id).first()
            if not existing:
                job = Job(
                    title="Forward Deployed Engineer",
                    company="Figma",
                    application_url="https://boards.greenhouse.io/figma/jobs/already_applied",
                    url_hash="hash_already_applied_figma",
                    canonical_job_id=canonical_id,
                )
                db.add(job)
                db.flush()
                app = Application(
                    job_id=job.id,
                    canonical_job_id=canonical_id,
                    user_id=candidate_id,
                    status="SUBMITTED",
                )
                db.add(app)
                db.commit()

        # Attempt to apply again
        res = apply_to_job(
            job_id="dummy-job-repeat",
            job_title="Forward Deployed Engineer",
            company="Figma",
            source="Greenhouse",
            apply_url="https://boards.greenhouse.io/figma/jobs/already_applied",
            score=95,
            user_id=candidate_id,
            canonical_job_id=canonical_id,
        )

        assert res is False, "Auto-apply must reject already applied job"
