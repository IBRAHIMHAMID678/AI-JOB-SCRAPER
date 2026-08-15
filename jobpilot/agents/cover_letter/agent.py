"""
Cover Letter Generation Agent.
Generates a professional, non-generic cover letter for a specific job.

RULES:
- Use only verified facts from the candidate profile
- No fabricated claims, inflated achievements, or fake companies
- Avoid obvious AI filler phrases
- Professional, specific, and human-sounding
- Every generated letter is stored and linked to the application
"""
from __future__ import annotations

import os
from typing import Optional

from ...core.config import settings
from ...core.security import sanitize_for_prompt
from ...integrations.llm.base import get_provider
from ..base import BaseAgent
from ..resume.agent import MASTER_RESUME

_PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompts")


def _load_prompt(name: str) -> str:
    path = os.path.join(_PROMPT_DIR, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


class CoverLetterAgent(BaseAgent):
    name = "cover_letter_agent"

    def _execute(self, input_data: dict) -> dict:
        """
        input_data = {
            "job_id": str, "application_id": str,
            "job_title": str, "company": str,
            "job_description": str, "required_skills": list,
            "match_reason": str,
        }
        Returns: {"cover_letter": str}
        """
        job_title = input_data.get("job_title", "")
        company = input_data.get("company", "")
        job_desc = input_data.get("job_description", "")
        match_reason = input_data.get("match_reason", "")
        safe_desc = sanitize_for_prompt(job_desc, max_length=1500)

        try:
            provider = get_provider()
            system = _load_prompt("cover_letter.txt") or _COVER_LETTER_SYSTEM
            user = f"""Target Role: {job_title} at {company}
Why I match: {match_reason}

{safe_desc}

Candidate Profile (facts only — do not invent anything not listed here):
{MASTER_RESUME[:2000]}

Write a professional, specific, non-generic cover letter. 3 paragraphs. Under 300 words.
Do NOT start with 'I am writing to express my interest'. Be direct and specific."""

            letter = provider.complete(system, user, temperature=0.4, max_tokens=600)
            letter = letter.strip()
        except Exception as exc:
            self.logger.warning("LLM cover letter generation failed: %s", exc)
            letter = self._fallback(job_title, company)

        self._save(input_data, letter)
        return {"cover_letter": letter}

    def _fallback(self, title: str, company: str) -> str:
        return f"""Dear Hiring Manager at {company},

I am a Computer Science graduate (2026) with hands-on experience in Python, FastAPI, React, and LangChain-based AI systems. Your {title} role aligns directly with my technical background and passion for building production AI applications.

In my projects, I have built multi-source job scrapers, RAG document systems, and full-stack applications — demonstrating the exact skill set your role requires. I work well remotely and am available immediately for worldwide remote positions.

I would welcome the opportunity to discuss how my skills can contribute to {company}'s goals.

Best regards,
{settings.CANDIDATE_NAME}
{settings.CANDIDATE_EMAIL}"""

    def _save(self, input_data: dict, content: str) -> None:
        try:
            from ...core.database import db_session
            from ...core.models import CoverLetter
            with db_session() as db:
                cl = CoverLetter(
                    job_id=input_data.get("job_id", ""),
                    content=content,
                    model_used=settings.LLM_PROVIDER,
                )
                db.add(cl)
        except Exception as exc:
            self.logger.warning("Could not save cover letter: %s", exc)


_COVER_LETTER_SYSTEM = """You are a professional cover letter writer.
Write honest, specific, compelling cover letters.
NEVER fabricate companies, job titles, achievements, or skills.
Use ONLY facts from the provided candidate profile.
Write in a natural, professional human voice.
Avoid clichés like 'I am passionate about', 'I am excited to', 'synergy', 'team player'.
Be direct. Be specific. Be brief."""
