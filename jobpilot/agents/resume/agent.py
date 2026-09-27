"""
ATS Resume Optimization Agent.
Generates a tailored resume version for a specific job.

CRITICAL RULES:
- NEVER fabricate employment, education, skills, or experience
- ONLY use facts from the candidate knowledge base
- NEVER overwrite the master resume
- Create a new ResumeVersion with tracked changes
- Optimize for ATS keyword matching without stuffing
"""
from __future__ import annotations

import os
from typing import List, Optional

from pydantic import BaseModel

from ...core.config import settings
from ...core.logging import get_logger
from ...core.security import sanitize_for_prompt
from ...integrations.llm.base import get_provider
from ..base import BaseAgent

logger = get_logger(__name__)

_PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompts")


def _load_prompt(name: str) -> str:
    path = os.path.join(_PROMPT_DIR, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def _canonical_university() -> str:
    """Single-sourced university from the canonical candidate profile (audit item 46)."""
    from ...core.candidate import get_canonical_candidate_profile
    return get_canonical_candidate_profile()["university"]


# ── Candidate master profile ──────────────────────────────────────────────────
# This is the immutable source of truth. AI can rearrange, not invent.

MASTER_RESUME = """
# {name}
{email} | {location} | LinkedIn: {linkedin} | GitHub: {github}

## Professional Summary
Computer Science graduate (2026) specializing in AI/ML engineering and full-stack development.
Experienced in building production-grade AI systems with Python, FastAPI, LangChain, and RAG pipelines.
Passionate about integrating LLMs into scalable web applications.

## Technical Skills
- **Languages**: Python, TypeScript, JavaScript
- **AI/ML**: LangChain, RAG, LLM Integration (OpenAI, Groq), Vector Databases (MongoDB Atlas, Pinecone)
- **Backend**: FastAPI, Node.js, NestJS, REST APIs, WebSockets
- **Frontend**: React, Next.js, HTML5, CSS3, Tailwind CSS
- **Databases**: MongoDB, PostgreSQL, Redis
- **DevOps**: Docker, Git, GitHub Actions, AWS (basic)

## Education
**Bachelor of Science in Computer Science** | {university} | 2022–2026
- Relevant Coursework: Data Structures, Algorithms, Machine Learning, Database Systems, Software Engineering

## Projects
### AI Job Scraper & Evaluation System
- Built a multi-source job scraper aggregating listings from 8 job boards with parallel execution
- Implemented AI-powered job scoring system using rule-based + LLM evaluation
- Tech: Python, FastAPI, MongoDB, Groq API, SSE, React

### LangChain RAG Application
- Developed a Retrieval-Augmented Generation (RAG) system for document Q&A
- Integrated vector embeddings, semantic search, and conversational memory
- Tech: Python, LangChain, MongoDB Atlas Vector Search, FastAPI

### Full Stack Web Application
- Built responsive full-stack web application with authentication and real-time features
- Tech: Next.js, Node.js, NestJS, PostgreSQL, Redis

## Achievements
- Developed production AI systems as a self-taught developer before graduation
- Strong open-source portfolio demonstrating practical LLM/RAG implementation

## Work Authorization
Available for worldwide remote positions (based in Pakistan)
Open to USD hourly contracts ($10-$40/hr) or full-time USD roles
""".format(
    name=settings.CANDIDATE_NAME or "Ibrahim Hamid",
    email=settings.CANDIDATE_EMAIL or "ibrahimhamid.2600@gmail.com",
    location=settings.CANDIDATE_LOCATION or "Islamabad, Pakistan",
    linkedin=getattr(settings, "CANDIDATE_LINKEDIN", None) or "https://linkedin.com/in/ibrahim-hamid678",
    github=getattr(settings, "CANDIDATE_GITHUB", None) or "https://github.com/IBRAHIMHAMID678",
    university=_canonical_university(),
)


# TODO (audit item 45, partial): ResumeAgent currently outputs tailored markdown
# saved to the DB (ResumeVersion) but there is NO PDF render/upload pipeline —
# applications always attach the canonical PDF from resolve_resume_path().
# Wiring a markdown→PDF renderer + per-job upload selection is future work;
# the agent files are intentionally kept in place. Do not fabricate resume PDFs.


class _ResumeTailoringSchema(BaseModel):
    tailored_summary: str
    keywords_added: List[str]
    keywords_to_emphasize: List[str]
    sections_to_reorder: List[str]
    ats_optimization_notes: str
    estimated_ats_score: int


class ResumeAgent(BaseAgent):
    name = "resume_agent"

    def _execute(self, input_data: dict) -> dict:
        """
        input_data = {
            "job_id": str,
            "application_id": str,
            "job_title": str,
            "company": str,
            "job_description": str,
            "required_skills": List[str],
        }
        Returns: {"resume_markdown": str, "keywords_added": [...], "ats_score": int}
        """
        job_title = input_data.get("job_title", "")
        company = input_data.get("company", "")
        job_desc = input_data.get("job_description", "")
        required_skills = input_data.get("required_skills", [])

        # Sanitize job description (untrusted external content)
        safe_desc = sanitize_for_prompt(job_desc, max_length=2000)

        try:
            provider = get_provider()
            system = _load_prompt("resume.txt") or _RESUME_SYSTEM_PROMPT
            user = f"""Target Role: {job_title} at {company}
Required Skills: {', '.join(required_skills[:15])}

{safe_desc}

Master Resume (IMMUTABLE - use only these facts, do not fabricate):
{MASTER_RESUME}
"""
            result: Optional[_ResumeTailoringSchema] = provider.complete_json(
                system, user, schema=_ResumeTailoringSchema, temperature=0.2
            )
        except Exception as exc:
            logger.warning("LLM resume tailoring failed, using master resume: %s", exc)
            result = None

        if result:
            tailored = self._apply_tailoring(result, required_skills)
            keywords_added = result.keywords_added
            ats_score = result.estimated_ats_score
        else:
            tailored = MASTER_RESUME
            keywords_added = []
            ats_score = 60

        # Save to DB
        self._save_version(input_data, tailored, keywords_added, ats_score)

        return {
            "resume_markdown": tailored,
            "keywords_added": keywords_added,
            "ats_score": ats_score,
        }

    def _apply_tailoring(self, tailoring: _ResumeTailoringSchema, required_skills: List[str]) -> str:
        """Insert tailored summary and keyword highlights into master resume."""
        resume = MASTER_RESUME
        if tailoring.tailored_summary:
            resume = resume.replace(
                "Computer Science graduate (2026) specializing in AI/ML engineering and full-stack development.",
                tailoring.tailored_summary[:500],
            )
        return resume

    def _save_version(self, input_data: dict, content: str, keywords: List[str], ats_score: int) -> None:
        try:
            from ...core.database import db_session
            from ...core.models import Resume, ResumeVersion
            with db_session() as db:
                # Get or create master resume
                master = db.query(Resume).filter(Resume.is_master == True).first()
                if not master:
                    master = Resume(name="Master Resume", is_master=True, content_markdown=MASTER_RESUME)
                    db.add(master)
                    db.flush()

                # Count existing versions
                version_num = db.query(ResumeVersion).filter(
                    ResumeVersion.resume_id == master.id
                ).count() + 1

                version = ResumeVersion(
                    resume_id=master.id,
                    application_id=input_data.get("application_id"),
                    job_id=input_data.get("job_id"),
                    version_number=version_num,
                    content_markdown=content,
                    keywords_added=keywords,
                    ats_score=ats_score,
                    model_used=settings.LLM_PROVIDER,
                )
                db.add(version)
        except Exception as exc:
            self.logger.warning("Could not save resume version: %s", exc)


_RESUME_SYSTEM_PROMPT = """You are an expert ATS resume optimizer.
Your job is to help tailor a resume to a specific job posting.

STRICT RULES:
1. NEVER fabricate employment history, education, skills, projects, or achievements
2. ONLY use information from the provided master resume
3. You may reorder sections, rephrase bullet points, and emphasize relevant keywords
4. Do NOT add skills the candidate does not have
5. Optimize for ATS without keyword stuffing

Return ONLY valid JSON:
{
  "tailored_summary": "2-3 sentence professional summary tailored to this role",
  "keywords_added": ["list of keywords to add/emphasize"],
  "keywords_to_emphasize": ["list of existing skills to highlight"],
  "sections_to_reorder": ["order: Skills, Experience, Projects, Education"],
  "ats_optimization_notes": "brief notes on changes",
  "estimated_ats_score": 0-100
}"""
