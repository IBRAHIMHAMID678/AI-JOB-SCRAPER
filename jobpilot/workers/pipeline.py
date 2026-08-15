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
from datetime import datetime
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


def run_pipeline(trigger: str = "manual") -> dict:
    """
    Full job discovery → evaluation pipeline.
    Safe to call from a background thread.
    Returns summary dict.
    """
    global _is_running, _source_stats

    with _pipeline_lock:
        if _is_running:
            return {"status": "already_running"}
        _is_running = True
        _source_stats = {}

    started_at = datetime.utcnow()
    bus.emit(EventType.PIPELINE_STARTED, {"trigger": trigger})
    summary = {"matched": 0, "pending": 0, "skipped": 0, "errors": 0}

    try:
        # ── Phase 1: Source fetching (parallel) ─────────────────────────────
        sse_log("[JOBPILOT] Phase 1: Discovering jobs from all sources...")
        raw_jobs = _fetch_all_sources()
        sse_log(f"[JOBPILOT] Raw jobs collected: {len(raw_jobs)}")

        # ── Phase 2: Normalization ───────────────────────────────────────────
        sse_log("[JOBPILOT] Phase 2: Normalizing job data...")
        from ..agents.normalization.agent import NormalizationAgent
        normalized = NormalizationAgent().run(raw_jobs, trigger=trigger) or []
        sse_log(f"[JOBPILOT] Normalized: {len(normalized)} jobs")

        # ── Phase 3: Deduplication ───────────────────────────────────────────
        sse_log("[JOBPILOT] Phase 3: Deduplicating...")
        from ..agents.deduplication.agent import DeduplicationAgent
        unique = DeduplicationAgent().run(normalized, trigger=trigger) or []
        sse_log(f"[JOBPILOT] Unique new jobs: {len(unique)}")

        if not unique:
            sse_log("[JOBPILOT] No new jobs found. Pipeline complete.")
            return summary

        # ── Phase 4-6: Analysis + Matching + Persist (parallel per job) ───────
        sse_log(f"[JOBPILOT] Phase 4-6: Analyzing, scoring, and persisting {len(unique)} jobs...")
        _analyze_match_and_persist(unique, summary)

    except Exception as exc:
        logger.error("Pipeline error: %s", exc)
        sse_log(f"[ERROR] Pipeline error: {exc}")
        summary["errors"] += 1
    finally:
        _is_running = False
        duration = (datetime.utcnow() - started_at).total_seconds()
        bus.emit(EventType.PIPELINE_COMPLETED, {"summary": summary, "duration": duration})
        sse_log(
            f"[JOBPILOT] Pipeline complete in {duration:.1f}s — "
            f"Matched: {summary['matched']}, Pending: {summary['pending']}, Skipped: {summary['skipped']}"
        )
        sse_log("DONE")

    return summary


def _fetch_all_sources() -> List[RawJob]:
    """Fetch from all enabled sources in parallel."""
    from ..integrations.sources.jobspy import JobSpyAdapter
    from ..integrations.sources.himalayas import HimalayasAdapter
    from ..integrations.sources.remotive import RemotiveAdapter
    from ..integrations.sources.remoteok import RemoteOKAdapter
    from ..integrations.sources.weworkremotely import WeWorkRemotelyAdapter
    from ..integrations.sources.arbeitnow import ArbeitnowAdapter
    from ..integrations.sources.themuse import TheMuseAdapter
    from ..integrations.sources.nodesk import NodeDeskAdapter

    adapters = [
        ("JobSpy", JobSpyAdapter()),
        ("Himalayas", HimalayasAdapter()),
        ("Remotive", RemotiveAdapter()),
        ("RemoteOK", RemoteOKAdapter()),
        ("WeWorkRemotely", WeWorkRemotelyAdapter()),
        ("Arbeitnow", ArbeitnowAdapter()),
        ("TheMuse", TheMuseAdapter()),
        ("NodeDesk", NodeDeskAdapter()),
    ]

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


def _analyze_match_and_persist(jobs: List[NormalizedJob], summary: dict) -> None:
    """Run analysis + matching + DB persistence in parallel per job."""
    from ..agents.analysis.agent import AnalysisAgent
    from ..agents.matching.agent import MatchingAgent
    from ..core.models import Job, JobAnalysis, JobMatch, Application

    analysis_agent = AnalysisAgent()
    matching_agent = MatchingAgent()

    def process_job(job: NormalizedJob) -> Optional[str]:
        """Returns 'matched', 'pending', 'skipped', or None on error."""
        try:
            title = job.title
            company = job.company
            title_lower = title.lower()

            senior_kw = ["senior", "lead", "staff", "principal", "director", "vp ", "head of", "architect", "sr."]
            if any(k in title_lower for k in senior_kw):
                sse_log(f"[SKIP] Senior role: {title} at {company}")
                return "skipped"

            tech_kw = ["ai", "python", "react", "node", "software", "developer", "engineer",
                       "programmer", "frontend", "backend", "web", "data", "tech", "fastapi", "llm", "full stack"]
            if not any(k in title_lower for k in tech_kw):
                sse_log(f"[SKIP] Non-tech role: {title}")
                return "skipped"

            analysis: Optional[JobAnalysisResult] = analysis_agent.run(job, trigger="pipeline")
            if analysis and analysis.us_only:
                sse_log(f"[SKIP] US-only: {title} at {company}")
                return "skipped"

            match: Optional[JobMatchResult] = matching_agent.run({"job": job, "analysis": analysis}, trigger="pipeline")
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
                    status="MATCHED" if match.auto_approved else "DISCOVERED",
                    mode=settings.APPLICATION_MODE,
                ))

            return "matched" if match.auto_approved else "pending"

        except Exception as exc:
            logger.warning("Error processing job '%s': %s", job.title, exc)
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
