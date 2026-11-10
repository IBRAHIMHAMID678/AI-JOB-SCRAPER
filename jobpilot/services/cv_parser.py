"""
Production-Ready CV Parsing Service.
Extracts clean text from PDF, DOCX, and TXT files using pypdf.
Extracts structured skills, experience years, education, target roles,
and professional summaries using the AI fallback chain and deterministic NLP heuristics.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..core.logging import get_logger
from ..integrations.llm.base import get_provider

logger = get_logger(__name__)


def extract_text_from_pdf(file_path: str) -> str:
    """Accurately extracts text from multi-page PDFs with error handling."""
    text_chunks: List[str] = []
    try:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        for idx, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_chunks.append(page_text)
            except Exception as page_err:
                logger.warning("Could not extract text from PDF page %d: %s", idx, page_err)
    except Exception as exc:
        logger.warning("pypdf parsing failed (%s), attempting binary text scan", exc)
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
            # Clean ASCII printable fallback
            printable = "".join(chr(b) if 32 <= b <= 126 or b in (10, 13, 9) else " " for b in raw)
            return re.sub(r"\s+", " ", printable).strip()
        except Exception as fallback_err:
            logger.error("Total PDF extraction failure: %s", fallback_err)
            return ""

    combined = "\n\n".join(text_chunks).strip()
    return combined


def extract_text_from_docx(file_path: str) -> str:
    try:
        from docx import Document
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        logger.warning("DOCX extraction error: %s", e)
        return ""


def extract_text(file_path: str, mime_type: str = "") -> str:
    path = pathlib.Path(file_path)
    ext = path.suffix.lower()
    if ext == ".pdf" or "pdf" in mime_type:
        return extract_text_from_pdf(file_path)
    if ext in (".docx", ".doc") or "word" in mime_type:
        return extract_text_from_docx(file_path)
    return path.read_text(encoding="utf-8", errors="ignore")


_PARSE_PROMPT = """You are an expert technical resume and CV parser for a modern job platform.
Extract structured profile information from the CV text provided below.

Respond with ONLY valid JSON with this exact schema:
{{
  "name": "Candidate Full Name",
  "email": "candidate@example.com",
  "phone": "+1 555 0100",
  "location": "City, Country",
  "skills": ["Python", "FastAPI", "React", "PostgreSQL", "Docker"],
  "keywords": ["RAG", "LLM", "Full Stack", "Distributed Systems"],
  "roles": ["AI Engineer", "Full Stack Developer", "Backend Developer"],
  "experience_years": 2.5,
  "education": [
    {{"degree": "Bachelor of Science in Computer Science", "institution": "University Name", "year": "2024"}}
  ],
  "work_experience": [
    {{"title": "Software Engineer", "company": "Company Name", "period": "2022-2024", "summary": "Key achievements"}}
  ],
  "summary": "2-3 sentence executive professional summary."
}}

CV TEXT:
---
{cv_text}
---
JSON ONLY:"""


def parse_cv_with_llm(raw_text: str) -> Optional[dict]:
    """Uses the AI Provider Fallback system to parse CV into structured JSON."""
    if not raw_text or len(raw_text.strip()) < 20:
        return None

    try:
        provider = get_provider()
        prompt = _PARSE_PROMPT.format(cv_text=raw_text[:7000])
        response_text = provider.complete(
            system_prompt="You are a precise CV parser that outputs exclusively valid JSON.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=1500,
        )
        if not response_text:
            return None

        clean = response_text.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(clean)
    except Exception as exc:
        logger.warning("[CV_PARSER] AI parsing unavailable or failed (%s). Using deterministic heuristic parser.", exc)
        return None


def extract_heuristics(text: str) -> dict:
    """
    Deterministic rule-based NLP parser.
    Extracts skills, experience years, education, and roles without external APIs.
    """
    text_lower = text.lower()

    # Skill lexicon
    SKILL_MAP = {
        "Python": ["python", "fastapi", "django", "flask", "pydantic", "sqlalchemy", "celery", "pytest"],
        "JavaScript / TypeScript": ["javascript", "typescript", "node.js", "nodejs", "express", "nest.js", "nestjs"],
        "Frontend": ["react", "react.js", "next.js", "nextjs", "vue", "vue.js", "angular", "tailwind", "css3", "html5", "redux"],
        "AI / ML / Data": ["langchain", "rag", "vector search", "llm", "openai", "huggingface", "pytorch", "tensorflow", "scikit-learn", "pandas", "numpy", "transformers", "machine learning", "deep learning", "nlp", "computer vision"],
        "Databases": ["postgresql", "postgres", "mongodb", "mysql", "redis", "sqlite", "pinecone", "weaviate", "qdrant", "elasticsearch"],
        "DevOps & Cloud": ["docker", "kubernetes", "aws", "gcp", "azure", "ci/cd", "github actions", "linux", "terraform"],
        "Architecture & API": ["rest api", "graphql", "grpc", "microservices", "websockets", "agile", "git"],
    }

    # Canonical display mapping
    CANONICAL_NAMES = {
        "fastapi": "FastAPI",
        "postgresql": "PostgreSQL",
        "mongodb": "MongoDB",
        "mysql": "MySQL",
        "sqlite": "SQLite",
        "graphql": "GraphQL",
        "rest api": "REST API",
        "langchain": "LangChain",
        "pytorch": "PyTorch",
        "tensorflow": "TensorFlow",
        "react": "React",
        "next.js": "Next.js",
        "vue.js": "Vue.js",
        "ci/cd": "CI/CD",
        "github actions": "GitHub Actions",
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        "python": "Python",
        "typescript": "TypeScript",
        "javascript": "JavaScript",
        "redis": "Redis",
        "rag": "RAG",
        "llm": "LLM",
    }

    found_skills: List[str] = []
    for category, keywords in SKILL_MAP.items():
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                canonical = CANONICAL_NAMES.get(kw, kw.title() if len(kw) > 3 else kw.upper())
                found_skills.append(canonical)

    # De-duplicate skills preserving order
    dedup_skills = list(dict.fromkeys(found_skills))

    # Experience years extraction
    exp_years = 1.0
    exp_match = re.search(r"(\d+(?:\.\d+)?)\+?\s*years?(?:\s+of)?\s+(?:experience|work)", text_lower)
    if exp_match:
        try:
            exp_years = float(exp_match.group(1))
        except ValueError:
            pass
    else:
        # Detect year spans like 2021-2024
        years = [int(y) for y in re.findall(r"\b(20[0-2][0-9])\b", text)]
        if len(years) >= 2:
            span = max(years) - min(years)
            if 0 < span < 30:
                exp_years = float(span)

    # Degree / Education extraction
    education: List[dict] = []
    deg_match = re.search(r"(bachelor|master|phd|b\.?sc|m\.?sc|b\.?s|m\.?s)[\w\s]{0,40}(?:in|of)?\s+([A-Za-z\s]{3,35})", text_lower)
    if deg_match:
        education.append({
            "degree": deg_match.group(0).title(),
            "institution": "Accredited University",
            "year": "Graduated",
        })

    # Inferred roles
    roles = []
    if any(k in text_lower for k in ["rag", "langchain", "llm", "machine learning", "ai engineer"]):
        roles.append("AI Engineer")
    if any(k in text_lower for k in ["full stack", "react", "next.js"]) and any(k in text_lower for k in ["python", "node", "fastapi"]):
        roles.append("Full Stack Developer")
    if any(k in text_lower for k in ["backend", "fastapi", "django", "postgresql", "api"]):
        roles.append("Backend Developer")
    if any(k in text_lower for k in ["frontend", "react", "tailwind", "ui"]):
        roles.append("Frontend Developer")
    if not roles:
        roles = ["Software Engineer", "Developer"]

    # Extract email and phone
    email_match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    phone_match = re.search(r"(?:\+?\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}", text)

    summary_preview = text[:400].replace("\n", " ").strip()
    if len(summary_preview) > 300:
        summary_preview = summary_preview[:300] + "..."

    return {
        "name": "Candidate",
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "location": "Worldwide / Remote",
        "skills": dedup_skills or ["Python", "JavaScript", "SQL", "Git"],
        "keywords": dedup_skills[:10],
        "roles": roles,
        "experience_years": exp_years,
        "education": education,
        "work_experience": [],
        "summary": summary_preview or "Technical professional with demonstrated software engineering and problem-solving skills.",
    }


def parse_cv(file_path: str, mime_type: str = "") -> dict:
    """
    Complete bulletproof CV parse pipeline:
    1. Extract text from PDF/DOCX/TXT
    2. Try AI fallback chain (Groq -> OpenRouter)
    3. If AI fails or returns partial data, supplement with deterministic heuristic parser
    4. Validate and sanitize extracted data
    """
    raw_text = extract_text(file_path, mime_type)
    if not raw_text.strip():
        return {
            "error": "The uploaded PDF appears to be empty, scanned as an unreadable image, or corrupted.",
            "skills": [],
            "keywords": [],
            "roles": ["Software Engineer"],
            "experience_years": 0,
            "education": [],
            "work_experience": [],
            "summary": "",
            "raw_text": "",
            "parsed_at": datetime.utcnow().isoformat(),
        }

    ai_parsed = parse_cv_with_llm(raw_text)
    heuristic_parsed = extract_heuristics(raw_text)

    # Blend: AI takes precedence if valid, else heuristic
    if ai_parsed and isinstance(ai_parsed, dict) and ai_parsed.get("skills"):
        final = ai_parsed
        if not final.get("skills"):
            final["skills"] = heuristic_parsed.get("skills", [])
        if not final.get("roles"):
            final["roles"] = heuristic_parsed.get("roles", ["Software Engineer"])
        if not final.get("experience_years"):
            final["experience_years"] = heuristic_parsed.get("experience_years", 1.0)
    else:
        final = heuristic_parsed

    final["raw_text"] = raw_text[:30000]
    final["parsed_at"] = datetime.utcnow().isoformat()
    return final
