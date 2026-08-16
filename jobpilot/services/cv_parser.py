"""
CV parsing service — extracts text from PDF/DOCX, then uses LLM to
pull out skills, keywords, roles, experience, and education.
"""
from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime
from typing import Optional

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)


def extract_text_from_pdf(file_path: str) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        return "\n".join(page.get_text() for page in doc)
    except ImportError:
        logger.warning("PyMuPDF not installed, falling back to basic PDF read")
        with open(file_path, "rb") as f:
            raw = f.read()
        # crude fallback — strips binary, keeps ASCII text
        return raw.decode("latin-1", errors="ignore")


def extract_text_from_docx(file_path: str) -> str:
    from docx import Document
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text(file_path: str, mime_type: str = "") -> str:
    path = pathlib.Path(file_path)
    ext = path.suffix.lower()
    if ext == ".pdf" or "pdf" in mime_type:
        return extract_text_from_pdf(file_path)
    if ext in (".docx", ".doc") or "word" in mime_type:
        return extract_text_from_docx(file_path)
    # plain text
    return path.read_text(encoding="utf-8", errors="ignore")


_PARSE_PROMPT = """You are a CV/resume parser. Extract structured information from the CV text below.

Return ONLY valid JSON with this exact structure:
{{
  "skills": ["skill1", "skill2"],
  "keywords": ["keyword1", "keyword2"],
  "roles": ["Software Engineer", "AI Engineer"],
  "experience_years": 3.5,
  "education": [
    {{"degree": "BSc Computer Science", "institution": "NUST", "year": 2021}}
  ],
  "summary": "One paragraph professional summary"
}}

Rules:
- skills: technical skills, tools, languages, frameworks
- keywords: important terms for job searching (combine skills + domain terms)
- roles: job titles this person is suited for (3-6 titles)
- experience_years: total years of professional experience (number)
- education: list of degrees
- summary: 2-3 sentence professional summary

CV TEXT:
---
{cv_text}
---

JSON only, no explanation:"""


def parse_cv_with_llm(raw_text: str) -> dict:
    """Use LLM to extract structured data from CV text."""
    if not settings.GROQ_API_KEY and not settings.OPENROUTER_API_KEY:
        return _parse_cv_fallback(raw_text)

    prompt = _PARSE_PROMPT.format(cv_text=raw_text[:6000])

    try:
        if settings.LLM_PROVIDER == "groq" and settings.GROQ_API_KEY:
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY)
            resp = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1024,
            )
            raw = resp.choices[0].message.content.strip()
        else:
            import httpx
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                json={
                    "model": settings.OPENROUTER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
                timeout=30,
            )
            raw = resp.json()["choices"][0]["message"]["content"].strip()

        # strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)

    except Exception as exc:
        logger.warning("LLM CV parse failed: %s — using fallback", exc)
        return _parse_cv_fallback(raw_text)


def _parse_cv_fallback(text: str) -> dict:
    """Rule-based fallback when no LLM key is available."""
    tech_keywords = [
        "python", "javascript", "typescript", "react", "nextjs", "node",
        "fastapi", "django", "flask", "sql", "postgresql", "mongodb",
        "redis", "docker", "kubernetes", "aws", "gcp", "azure",
        "machine learning", "deep learning", "nlp", "llm", "langchain",
        "openai", "huggingface", "tensorflow", "pytorch", "scikit",
        "pandas", "numpy", "git", "linux", "rest api", "graphql",
    ]
    text_lower = text.lower()
    found_skills = [kw for kw in tech_keywords if kw in text_lower]

    return {
        "skills": found_skills,
        "keywords": found_skills,
        "roles": ["Software Engineer", "Developer"],
        "experience_years": 0,
        "education": [],
        "summary": text[:300].strip(),
    }


def parse_cv(file_path: str, mime_type: str = "") -> dict:
    """Full CV parse pipeline: extract text → LLM parse → return structured data."""
    raw_text = extract_text(file_path, mime_type)
    parsed = parse_cv_with_llm(raw_text)
    parsed["raw_text"] = raw_text
    parsed["parsed_at"] = datetime.utcnow().isoformat()
    return parsed
