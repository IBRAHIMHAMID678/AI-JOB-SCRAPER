"""
Main pipeline orchestrator for JOBPILOT.
Coordinates all agents in the correct sequence:

  Sources → Normalization → Deduplication → Analysis → Matching
                                                           ↓
                                              Resume + Cover Letter
                                                           ↓
                                              Application tracking + Notifications

Supports:
- Parallel source fetching
- Sequential per-job pipeline
- Parallel analysis within a batch
- Event emission at each stage
- Full DB persistence
- SSE streaming for live dashboard
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..core.config import settings
from ..core.database import db_session
from ..core.events import EventType, bus
from ..core.logging import get_logger, sse_emit_job, sse_emit_pending, sse_log
from ..core.schemas import JobAnalysisResult, JobMatchResult, NormalizedJob, RawJob
from ..core.security import hash_url

logger = get_logger(__name__)

_pipeline_lock = threading.Lock()
_is_running = False
_source_stats: Dict[str, int] = {}


def is_pipeline_running() -> bool:
    return _is_running


def get_source_stats() -> Dict[str, int]:
    return dict(_source_stats)


def run_pipeline(trigger: str = "manual", user_id: Optional[str] = None) -> dict:
    """
    Full job discovery → evaluation pipeline, scoped to user_id.
    Jobs are scraped globally; matching/applications are per-user.
    """
    global _is_running, _source_stats

    with _pipeline_lock:
        if _is_running:
            return {"status": "already_running"}
        _is_running = True
        _source_stats = {}

    started_at = datetime.now(timezone.utc)
    bus.emit(EventType.PIPELINE_STARTED, {"trigger": trigger})
    summary = {"matched": 0, "pending": 0, "skipped": 0, "errors": 0, "applied": 0}

    # Resolve which users to run for
    if user_id:
        user_ids = [user_id]
    else:
        # Scheduled run — process all active users with at least one CV
        from ..core.models import User, UploadedCV
        with db_session() as db:
            users_with_cvs = (
                db.query(User.id)
                .join(UploadedCV, UploadedCV.user_id == User.id)
                .filter(User.is_active == True, UploadedCV.is_active == True)
                .distinct()
                .all()
            )
            user_ids = [u[0] for u in users_with_cvs]

    if not user_ids:
        sse_log("[JOBPILOT] No users with CVs found. Upload a CV first.")
        _is_running = False
        return summary

    try:
        # ── Phase 1: Source fetching (parallel, shared for all users) ────────
        print("[JOBPILOT] Phase 1: Discovering jobs from all sources...", flush=True)
        sse_log("[JOBPILOT] Phase 1: Discovering jobs from all sources...")
        raw_jobs = _fetch_all_sources()
        print(f"[JOBPILOT] Raw jobs collected: {len(raw_jobs)}", flush=True)
        sse_log(f"[JOBPILOT] Raw jobs collected: {len(raw_jobs)}")

        # ── Phase 2: Normalization ───────────────────────────────────────────
        print(f"[JOBPILOT] Phase 2: Normalizing {len(raw_jobs)} raw jobs...", flush=True)
        sse_log("[JOBPILOT] Phase 2: Normalizing job data...")
        from ..agents.normalization.agent import NormalizationAgent
        normalized = NormalizationAgent().run(raw_jobs, trigger=trigger) or []
        print(f"[JOBPILOT] Normalized: {len(normalized)} jobs", flush=True)
        sse_log(f"[JOBPILOT] Normalized: {len(normalized)} jobs")

        # ── Phase 2b: Eligibility precheck (items 21/24) ────────────────────────
        # Filter ineligible jobs (senior, 4+ yrs, US-only, non-tech) BEFORE the
        # global dedup, so bad postings never consume a dedup slot or pollute
        # the 30-day dedup history. The per-user gate in _analyze_match_and_persist
        # still runs afterwards; this stage fails open on checker errors.
        print(f"[JOBPILOT] Phase 2b: Eligibility precheck on {len(normalized)} jobs...", flush=True)
        sse_log("[JOBPILOT] Phase 2b: Eligibility precheck...")
        from ..core.eligibility import evaluate_job_eligibility
        _eligible_jobs = []
        for job in normalized:
            try:
                _elig = evaluate_job_eligibility(
                    job_id=job.canonical_job_id or job.url_hash or job.title,
                    title=job.title,
                    company=job.company,
                    description=job.description or "",
                    location=job.location,
                )
                if _elig.is_eligible:
                    _eligible_jobs.append(job)
                else:
                    summary["skipped"] += 1
            except Exception as exc:
                logger.warning("Eligibility precheck failed for '%s': %s", job.title, exc)
                _eligible_jobs.append(job)
        normalized = _eligible_jobs
        print(f"[JOBPILOT] Eligible after precheck: {len(normalized)} jobs", flush=True)
        sse_log(f"[JOBPILOT] Eligible after precheck: {len(normalized)} jobs")

        # ── Phase 3: Deduplication ───────────────────────────────────────────
        print(f"[JOBPILOT] Phase 3: Deduplicating {len(normalized)} jobs...", flush=True)
        sse_log("[JOBPILOT] Phase 3: Deduplicating...")
        from ..agents.deduplication.agent import DeduplicationAgent
        unique = DeduplicationAgent().run(normalized, trigger=trigger) or []
        print(f"[JOBPILOT] Unique new jobs: {len(unique)}", flush=True)
        sse_log(f"[JOBPILOT] Unique new jobs: {len(unique)}")

        if not unique:
            print("[JOBPILOT] No new jobs found. Pipeline complete.", flush=True)
            sse_log("[JOBPILOT] No new jobs found. Pipeline complete.")
            return summary

        # ── Phase 4-6: Per-user matching + persist ───────────────────────────
        for uid in user_ids:
            print(f"[JOBPILOT] Phase 4-6: Scoring & Auto-Applying across {len(unique)} jobs for user {uid[:8]}...", flush=True)
            sse_log(f"[JOBPILOT] Phase 4-6: Scoring {len(unique)} jobs for user {uid[:8]}...")
            _analyze_match_and_persist(unique, summary, uid)

    except Exception as exc:
        logger.error("Pipeline error: %s", exc)
        sse_log(f"[ERROR] Pipeline error: {exc}")
        summary["errors"] += 1
    finally:
        _is_running = False
        duration = (datetime.now(timezone.utc) - started_at).total_seconds()
        bus.emit(EventType.PIPELINE_COMPLETED, {"summary": summary, "duration": duration})
        sse_log(
            f"[JOBPILOT] Pipeline complete in {duration:.1f}s — "
            f"Matched: {summary['matched']}, Pending: {summary['pending']}, Skipped: {summary['skipped']}"
        )
        # Telegram notify per user
        for uid in (user_ids if 'user_ids' in dir() else []):
            try:
                from ..services.telegram_service import notify_pipeline_done_for_user
                notify_pipeline_done_for_user(
                    user_id=uid,
                    total=summary["matched"] + summary["pending"] + summary["skipped"],
                    applied=summary.get("applied", 0),
                    high=summary["matched"],
                )
            except Exception:
                pass
        sse_log("DONE")

    return summary


def _fetch_all_sources() -> List[RawJob]:
    """Fetch from all enabled sources in parallel."""
    from ..integrations.sources.himalayas import HimalayasAdapter
    from ..integrations.sources.remotive import RemotiveAdapter
    from ..integrations.sources.remoteok import RemoteOKAdapter
    from ..integrations.sources.weworkremotely import WeWorkRemotelyAdapter
    from ..integrations.sources.arbeitnow import ArbeitnowAdapter
    from ..integrations.sources.themuse import TheMuseAdapter
    from ..integrations.sources.nodesk import NodeDeskAdapter
    from ..integrations.sources.rozee import RozeeAdapter
    from ..integrations.sources.scrapfly_adapter import ScrapflyAdapter
    from ..integrations.sources.ats_greenhouse import GreenhouseATSAdapter
    from ..integrations.sources.ats_lever import LeverATSAdapter
    from ..integrations.sources.ashby import AshbyATSAdapter
    from ..integrations.sources.jobicy import JobicyAdapter
    from ..integrations.sources.workingnomads import WorkingNomadsAdapter

    adapters = [
        ("Jobicy", JobicyAdapter()),
        ("WorkingNomads", WorkingNomadsAdapter()),
        ("Remotive", RemotiveAdapter()),
        ("WeWorkRemotely", WeWorkRemotelyAdapter()),
        ("TheMuse", TheMuseAdapter()),
        ("Arbeitnow", ArbeitnowAdapter()),
        ("RemoteOK", RemoteOKAdapter()),
        ("Himalayas", HimalayasAdapter()),
        ("NodeDesk", NodeDeskAdapter()),
        ("GreenhouseATS", GreenhouseATSAdapter()),
        ("LeverATS", LeverATSAdapter()),
        ("AshbyATS", AshbyATSAdapter()),
        ("Rozee", RozeeAdapter()),
        ("Scrapfly", ScrapflyAdapter()),
    ]

    # LinkedInPostsAdapter is intentionally NOT registered: its fetch() is a
    # stub that always returns [] — counting it would mislead source stats
    # (see integrations/sources/linkedin_posts.py).

    # JobSpy (LinkedIn/Indeed) is optional — requires pandas + python-jobspy
    try:
        from ..integrations.sources.jobspy import JobSpyAdapter
        adapters.insert(0, ("JobSpy", JobSpyAdapter()))
    except ImportError:
        sse_log("[WARN] JobSpy not installed — LinkedIn/Indeed scraping skipped. "
                "Install: pip install pandas python-jobspy --only-binary=:all:")

    all_jobs: List[RawJob] = []

    def fetch_one(name: str, adapter) -> List[RawJob]:
        try:
            jobs = adapter.get_jobs()
            _source_stats[name] = len(jobs)
            sse_log(f"[SOURCE] {name}: {len(jobs)} jobs")
            return jobs
        except Exception as exc:
            logger.error("Source %s failed: %s", name, exc)
            _source_stats[name] = 0
            sse_log(f"[ERROR] Source {name} failed: {exc}")
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(fetch_one, name, adapter): name for name, adapter in adapters}
        for future in concurrent.futures.as_completed(futures):
            try:
                all_jobs.extend(future.result())
            except Exception:
                pass

    return all_jobs


def _analyze_match_and_persist(jobs: List[NormalizedJob], summary: dict, user_id: str) -> None:
    """Run analysis + per-user matching + DB persistence in parallel per job."""
    from ..agents.analysis.agent import AnalysisAgent
    from ..agents.matching.agent import MatchingAgent
    from ..core.models import Job, JobAnalysis, JobMatch, Application, UploadedCV, UserSettings

    analysis_agent = AnalysisAgent()
    matching_agent = MatchingAgent()

    # Load this user's default CV and settings once
    with db_session() as db:
        cv = (
            db.query(UploadedCV)
            .filter_by(user_id=user_id, is_default=True, is_active=True)
            .first()
        )
        if not cv:
            cv = db.query(UploadedCV).filter_by(user_id=user_id, is_active=True).first()
        cv_path = str(cv.file_path or "") if cv else ""
        cv_skills = list(cv.skills or []) if cv else []
        cv_roles = list(cv.roles or []) if cv else []
        cv_keywords = list(cv.keywords or []) if cv else []
        cv_exp_years = float(getattr(cv, "experience_years", 0) or 0) if cv else 0.0

        user_settings = db.query(UserSettings).filter_by(user_id=user_id).first()
        user_location = (user_settings.location or "").strip().lower() if user_settings else ""

    # Build profile from CV data (falls back to defaults inside matching agent if empty)
    user_profile = {
        "skills": cv_skills + cv_keywords,
        "technologies": cv_skills,
        "preferred_roles": cv_roles,
        "seniority_preference": ["junior", "entry", "mid"],
        "min_hourly_usd": 10,
        "max_hourly_usd": 40,
        "years_experience": cv_exp_years,
        "career_level": "junior",
    }

    # India location exclusion keywords
    _INDIA_KEYWORDS = [
        "india", "bangalore", "bengaluru", "delhi", "mumbai",
        "hyderabad", "pune", "chennai", "kolkata", "noida", "gurgaon",
    ]

    def process_job(job: NormalizedJob) -> Optional[str]:
        """Returns 'matched', 'pending', 'skipped', or None on error."""
        try:
            title = job.title
            company = job.company
            title_lower = title.lower()
            loc_lower = (job.location or "").lower()

            # Skip India-based jobs
            if any(city in loc_lower for city in _INDIA_KEYWORDS):
                sse_log(f"[SKIP] India location: {title} at {company}")
                return "skipped"

            # For on-site/in-person jobs, only allow if they match user's city
            is_remote = job.remote_type in ("remote", "hybrid") or "remote" in loc_lower
            if not is_remote and user_location:
                if user_location not in loc_lower:
                    sse_log(f"[SKIP] On-site job not in user's city ({user_location}): {title}")
                    return "skipped"

            # Item 21: ground-truth eligibility gate (seniority, experience,
            # geography, tech relevance) — catches "Remote, US"/"Remote - US"
            # and other restrictions the local heuristics miss.
            from ..core.eligibility import evaluate_job_eligibility
            elig = evaluate_job_eligibility(
                job_id=job.canonical_job_id or job.url_hash,
                title=title,
                company=company,
                description=job.description or "",
                location=job.location,
            )
            if not elig.is_eligible:
                sse_log(f"[SKIP] {elig.decision}: {title} at {company} ({elig.reason})")
                return "skipped"

            senior_kw = ["senior", "lead", "staff", "principal", "director", "vp ", "head of", "architect", "sr."]
            if any(k in title_lower for k in senior_kw):
                sse_log(f"[SKIP] Senior role: {title} at {company}")
                return "skipped"

            # Build tech keywords from user's CV skills + default tech terms
            cv_tech_kw = [s.lower() for s in (cv_skills + cv_roles) if s]
            default_tech_kw = ["ai", "python", "react", "node", "software", "developer", "engineer",
                                "programmer", "frontend", "backend", "web", "data", "tech", "fastapi", "llm", "full stack"]
            all_tech_kw = cv_tech_kw + default_tech_kw
            if not any(k in title_lower for k in all_tech_kw):
                sse_log(f"[SKIP] Non-tech role: {title}")
                return "skipped"

            analysis: Optional[JobAnalysisResult] = analysis_agent.run(job, trigger="pipeline")
            if analysis and analysis.us_only:
                sse_log(f"[SKIP] US-only: {title} at {company}")
                return "skipped"

            # Filter jobs requiring more than 3 years experience (target max 2-3 years)
            if analysis and analysis.years_experience_min and analysis.years_experience_min > 3:
                sse_log(f"[SKIP] Experience required ({analysis.years_experience_min} yrs > 3 yrs): {title} at {company}")
                return "skipped"

            match: Optional[JobMatchResult] = matching_agent.run(
                {"job": job, "analysis": analysis, "user_profile": user_profile},
                trigger="pipeline",
            )
            if not match or match.overall_score < settings.SCORE_MIN_THRESHOLD:
                return "skipped"

            # Emit to SSE immediately
            job_dict = job.model_dump()
            job_dict["match_score"] = match.overall_score
            job_dict["score_label"] = match.score_label
            job_dict["match_reason"] = match.match_reason_summary
            job_dict["is_pakistan_eligible"] = analysis.pakistan_eligible if analysis else True

            if match.auto_approved:
                sse_emit_job(job_dict)
                sse_log(f"[MATCH] {title} at {company} — Score: {match.overall_score}%")
            else:
                sse_emit_pending(job_dict)
                sse_log(f"[PENDING] {title} at {company} — Score: {match.overall_score}% (needs review)")

            # Persist immediately (no second pass needed)
            with db_session() as db:
                if db.query(Job).filter(Job.url_hash == job.url_hash).first():
                    return "skipped"

                job_orm = Job(
                    source_name=job.source_name,
                    source_job_id=job.source_job_id,
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    remote_type=job.remote_type,
                    employment_type=job.employment_type,
                    salary_min=job.salary_min,
                    salary_max=job.salary_max,
                    currency=job.currency,
                    salary_raw=job.salary_raw,
                    description=job.description,
                    skills_raw=job.skills_raw,
                    posting_date=job.posting_date,
                    application_url=job.application_url,
                    url_hash=job.url_hash,
                    content_hash=job.content_hash,
                    canonical_job_id=job.canonical_job_id,
                )
                db.add(job_orm)
                db.flush()

                if analysis:
                    db.add(JobAnalysis(
                        job_id=job_orm.id,
                        required_skills=analysis.required_skills,
                        preferred_skills=analysis.preferred_skills,
                        technologies=analysis.technologies,
                        years_experience_min=analysis.years_experience_min,
                        years_experience_max=analysis.years_experience_max,
                        education_required=analysis.education_required,
                        certifications=analysis.certifications,
                        seniority=analysis.seniority,
                        industry=analysis.industry,
                        us_only=analysis.us_only,
                        pakistan_eligible=analysis.pakistan_eligible,
                        visa_required=analysis.visa_required,
                        red_flags=analysis.red_flags,
                        suspicious_requirements=analysis.suspicious_requirements,
                        model_used=analysis.model_used,
                        prompt_version=analysis.prompt_version,
                        confidence=analysis.confidence,
                    ))

                db.add(JobMatch(
                    job_id=job_orm.id,
                    user_id=user_id,
                    overall_score=match.overall_score,
                    score_label=match.score_label,
                    skills_score=match.breakdown.skills_score,
                    experience_score=match.breakdown.experience_score,
                    role_score=match.breakdown.role_score,
                    location_score=match.breakdown.location_score,
                    salary_score=match.breakdown.salary_score,
                    education_score=match.breakdown.education_score,
                    technology_score=match.breakdown.technology_score,
                    strong_matches=match.strong_matches,
                    missing_requirements=match.missing_requirements,
                    transferable_skills=match.transferable_skills,
                    risks=match.risks,
                    reasons_to_apply=match.reasons_to_apply,
                    reasons_to_reject=match.reasons_to_reject,
                    match_reason_summary=match.match_reason_summary,
                    auto_approved=match.auto_approved,
                    requires_manual_review=match.requires_manual_review,
                    decision=match.decision,
                    model_used=match.model_used,
                ))

                db.add(Application(
                    job_id=job_orm.id,
                    canonical_job_id=job.canonical_job_id,
                    user_id=user_id,
                    status="MATCHED" if match.auto_approved else "DISCOVERED",
                    mode=settings.APPLICATION_MODE,
                ))
                db.flush()
                job_orm_id = job_orm.id

            # ── Auto-apply for high-score jobs (per-user credentials) ─────────
            if match.overall_score >= settings.TIER2_SCORE_MIN and cv_path:
                try:
                    from ..services.auto_apply import apply_to_job, can_apply
                    if can_apply(match.overall_score, user_id=user_id):
                        applied = apply_to_job(
                            job_id=job_orm_id,
                            job_title=job.title,
                            company=job.company,
                            source=job.source_name,
                            apply_url=job.application_url,
                            score=match.overall_score,
                            description=job.description or "",
                            cv_path=cv_path,
                            user_id=user_id,
                            canonical_job_id=job.canonical_job_id,
                        )
                        if applied:
                            summary["applied"] += 1
                            print(f"[APPLY SUCCESS #{summary['applied']}] {job.title} @ {job.company} (Score: {match.overall_score}%)", flush=True)
                except Exception as apply_exc:
                    logger.warning("Auto-apply error for %s: %s", job.title, apply_exc)

            return "matched" if match.auto_approved else "pending"

        except Exception as exc:
            logger.warning("Error processing job '%s': %s", job.title, exc)
            # Item 34: dead-letter record instead of a bare log line
            try:
                from ..core.dead_letter import write_dead_letter
                write_dead_letter(
                    job.canonical_job_id or job.url_hash,
                    stage="pipeline:process_job",
                    error=exc,
                    extra={"title": job.title, "company": job.company, "source": job.source_name},
                )
            except Exception:
                pass
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.QUEUE_MAX_WORKERS) as ex:
        futures = [ex.submit(process_job, job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            try:
                outcome = future.result()
                if outcome == "matched":
                    summary["matched"] += 1
                elif outcome == "pending":
                    summary["pending"] += 1
                elif outcome == "skipped":
                    summary["skipped"] += 1
                else:
                    summary["errors"] += 1
            except Exception:
                summary["errors"] += 1
