"""
Job Analysis Agent.
Extracts structured information from a normalized job using:
  1. Fast deterministic rule-based extraction (always runs)
  2. LLM extraction for complex fields (only for promising jobs)

Returns JobAnalysisResult with full structured data.
Never calls LLM on jobs that fail basic rule-based filters (cost control).
"""
from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel

from ...core.config import settings
from ...core.schemas import JobAnalysisResult, NormalizedJob
from ...core.security import detect_prompt_injection, sanitize_for_prompt
from ...integrations.llm.base import get_provider
from ..base import BaseAgent, AgentError

# Prompt injection protection — loaded on import
import importlib, os as _os
_PROMPT_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))), "prompts")


def _load_prompt(name: str) -> str:
    path = _os.path.join(_PROMPT_DIR, name)
    if _os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


# ── Rule-based helpers ────────────────────────────────────────────────────────

_US_RESTRICTION_PATTERNS = [
    r"\bus(-only|only)\b",
    r"\busa(-only|only)\b",
    r"\b(us|usa)\s+(citizens?|citizenship|residents?|based\s+only)\b",
    r"\b(must\s+reside|authorized\s+to\s+work)\s+in\s+the\s+us\b",
    r"\b(north\s+america\s+only|us/canada\s+only)\b",
    r"\bwork\s+authorization\s+in\s+the\s+(us|usa|united\s+states)\b",
]
_US_COMPILED = [re.compile(p, re.IGNORECASE) for p in _US_RESTRICTION_PATTERNS]

_US_STATES = re.compile(
    r"\b(al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy)\b",
    re.IGNORECASE,
)

_WORLDWIDE_KEYWORDS = [
    "worldwide", "anywhere", "pakistan", "global remote",
    "work from anywhere", "any country", "all countries",
]

_SENIOR_KEYWORDS = ["senior", "lead", "staff", "principal", "director", "vp ", "head of", "architect", "manager", "sr.", "sr ", " iii", " iv"]
_JUNIOR_KEYWORDS = ["junior", "entry level", "entry-level", "0-2 years", "graduate", "associate", "intern", "new grad"]

_TECH_SKILLS = [
    "python", "fastapi", "react", "next.js", "nextjs", "node", "node.js", "nodejs",
    "nestjs", "langchain", "rag", "mongodb", "llm", "typescript", "javascript",
    "openai", "hugging face", "vector database", "pinecone", "chroma", "weaviate",
    "docker", "kubernetes", "aws", "gcp", "azure", "postgresql", "redis",
    "celery", "fastapi", "django", "flask", "graphql", "rest api",
]


_ISLAMABAD_KEYWORDS = ["islamabad", "rawalpindi", "pindi", "isb"]


def _is_local_pk(location: str, description: str) -> bool:
    text = (location + " " + description).lower()
    return any(k in text for k in _ISLAMABAD_KEYWORDS)


def _is_us_only(location: str, description: str) -> bool:
    text = (location + " " + description).lower()
    if any(k in text for k in _WORLDWIDE_KEYWORDS) or _is_local_pk(location, description):
        return False
    for pat in _US_COMPILED:
        if pat.search(text):
            return True
    if _US_STATES.search(location) and "remote" not in location.lower():
        return True
    return False


def _extract_skills(text: str) -> List[str]:
    text_lower = text.lower()
    return [s for s in _TECH_SKILLS if re.search(r"\b" + re.escape(s) + r"\b", text_lower)]


def _extract_seniority(title: str, description: str) -> str:
    text = (title + " " + description[:500]).lower()
    if any(k in text for k in _SENIOR_KEYWORDS):
        return "senior"
    if any(k in text for k in _JUNIOR_KEYWORDS):
        return "junior"
    return "mid"


def _extract_experience(text: str) -> tuple[Optional[int], Optional[int]]:
    patterns = [
        r"(\d+)\s*[-–to]+\s*(\d+)\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
        r"(\d+)\+\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
        r"(?:minimum|min|at\s+least)\s*(\d+)\s*(?:years?|yrs?)",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            groups = [g for g in m.groups() if g is not None]
            if len(groups) >= 2:
                return int(groups[0]), int(groups[1])
            return int(groups[0]), None
    return None, None


# ── LLM schema ───────────────────────────────────────────────────────────────

class _LLMAnalysisSchema(BaseModel):
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    technologies: List[str] = []
    years_experience_min: Optional[int] = None
    years_experience_max: Optional[int] = None
    education_required: Optional[str] = None
    certifications: List[str] = []
    seniority: Optional[str] = None
    industry: Optional[str] = None
    red_flags: List[str] = []
    suspicious_requirements: List[str] = []
    pakistan_eligible: bool = True
    us_only: bool = False
    visa_required: bool = False


# ── Agent ────────────────────────────────────────────────────────────────────

class AnalysisAgent(BaseAgent[NormalizedJob, JobAnalysisResult]):
    name = "analysis_agent"

    def _execute(self, job: NormalizedJob) -> JobAnalysisResult:
        title = job.title or ""
        desc = job.description or ""
        loc = job.location or "Remote"
        full_text = f"{title} {desc}"

        us_only_flag = _is_us_only(loc, desc)
        is_pk_local = _is_local_pk(loc, desc)
        evidence = "Islamabad/Rawalpindi local job" if is_pk_local else ("Worldwide/Global remote opportunity" if not us_only_flag else "US location restriction detected")

        # Fast rule-based analysis (always runs)
        result = JobAnalysisResult(
            required_skills=_extract_skills(full_text),
            technologies=_extract_skills(full_text),
            seniority=_extract_seniority(title, desc),
            us_only=us_only_flag,
            pakistan_eligible=not us_only_flag,
            is_local_pk=is_pk_local,
            eligibility_evidence=evidence,
            prompt_version="1.0",
            model_used="rule-based",
            confidence=0.7,
        )
        exp_min, exp_max = _extract_experience(full_text)
        result.years_experience_min = exp_min
        result.years_experience_max = exp_max

        # LLM analysis for deeper extraction (only if not US-only, has description, and API key configured)
        has_key = bool(settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY)
        if not result.us_only and desc and len(desc) > 100 and has_key:
            try:
                llm_result = self._llm_analyze(title, desc, loc)
                if llm_result:
                    result = self._merge(result, llm_result)
            except Exception as exc:
                self.logger.warning("LLM analysis failed for '%s', using rule-based only: %s", title, exc)

        return result

    def _llm_analyze(self, title: str, desc: str, location: str) -> Optional[_LLMAnalysisSchema]:
        provider = get_provider()
        system = _load_prompt("job_analysis.txt") or _DEFAULT_ANALYSIS_PROMPT
        # IMPORTANT: sanitize job content before sending to LLM
        safe_desc = sanitize_for_prompt(desc, max_length=3000)
        user = f"Job Title: {title}\nLocation: {location}\n\n{safe_desc}"
        return provider.complete_json(system, user, schema=_LLMAnalysisSchema, temperature=0.1)

    def _merge(self, rule: JobAnalysisResult, llm: _LLMAnalysisSchema) -> JobAnalysisResult:
        """Merge rule-based and LLM results. Rule-based takes precedence for safety."""
        combined_skills = list(set(rule.required_skills + llm.required_skills))
        return JobAnalysisResult(
            required_skills=combined_skills,
            preferred_skills=llm.preferred_skills,
            technologies=list(set(rule.technologies + llm.technologies)),
            years_experience_min=rule.years_experience_min or llm.years_experience_min,
            years_experience_max=rule.years_experience_max or llm.years_experience_max,
            education_required=llm.education_required,
            certifications=llm.certifications,
            seniority=llm.seniority or rule.seniority,
            industry=llm.industry,
            red_flags=llm.red_flags,
            suspicious_requirements=llm.suspicious_requirements,
            us_only=rule.us_only or llm.us_only,  # rule-based takes precedence
            pakistan_eligible=not (rule.us_only or llm.us_only),
            visa_required=llm.visa_required,
            model_used=settings.LLM_PROVIDER,
            prompt_version="1.0",
            confidence=0.9,
        )


_DEFAULT_ANALYSIS_PROMPT = """You are an expert job description analyst.
Extract structured information from the job description provided.
Return ONLY valid JSON with these fields:
{
  "required_skills": ["string"],
  "preferred_skills": ["string"],
  "technologies": ["string"],
  "years_experience_min": null or integer,
  "years_experience_max": null or integer,
  "education_required": null or string,
  "certifications": ["string"],
  "seniority": "junior" | "mid" | "senior" | null,
  "industry": null or string,
  "red_flags": ["string"],
  "suspicious_requirements": ["string"],
  "pakistan_eligible": true or false,
  "us_only": true or false,
  "visa_required": true or false
}
Be accurate. Do not fabricate. If uncertain, omit or use null."""
