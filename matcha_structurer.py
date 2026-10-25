"""
Matcha-Grade Structured Extraction Pipeline.
Extracts normalized salary min/max/currency, remote regions, job category taxonomy,
and crisp 2-sentence actionable job summaries.
"""
from __future__ import annotations

import re
import os
from typing import Dict, Any, List, Optional, Tuple

def extract_salary_range(text: str) -> Tuple[Optional[int], Optional[int], str]:
    """
    Extracts normalized salary min, max, and currency from job title or description.
    Supports formats:
      - '$120,000 - $180,000'
      - '$120k - $180k'
      - '120,000 to 180,000 USD'
      - '€80,000 - €110,000'
      - '£60,000 - £90,000'
    """
    if not text:
        return None, None, "USD"

    # Identify currency symbol
    curr = "USD"
    if "€" in text or "eur" in text.lower():
        curr = "EUR"
    elif "£" in text or "gbp" in text.lower():
        curr = "GBP"
    elif "cad" in text.lower() or "c$" in text:
        curr = "CAD"
    elif "pkr" in text.lower() or "rs" in text.lower():
        curr = "PKR"

    # Pattern for full numbers: $120,000 - $180,000 or 120000 - 180000
    p1 = r'(?:[\$\€\£])?\s*(\d{2,3}(?:,\d{3})+|\d{5,6})\s*(?:-|to|–)\s*(?:[\$\€\£])?\s*(\d{2,3}(?:,\d{3})+|\d{5,6})'
    m1 = re.search(p1, text)
    if m1:
        try:
            s_min = int(m1.group(1).replace(",", ""))
            s_max = int(m1.group(2).replace(",", ""))
            if 15000 <= s_min <= 2000000 and s_min <= s_max:
                return s_min, s_max, curr
        except Exception:
            pass

    # Pattern for shorthand: $120k - $180k or 120k-180k
    p2 = r'(?:[\$\€\£])?\s*(\d{2,3})\s*[kK]\s*(?:-|to|–)\s*(?:[\$\€\£])?\s*(\d{2,3})\s*[kK]'
    m2 = re.search(p2, text)
    if m2:
        try:
            s_min = int(m2.group(1)) * 1000
            s_max = int(m2.group(2)) * 1000
            if s_min <= s_max:
                return s_min, s_max, curr
        except Exception:
            pass

    # Single number pattern: $150,000 / yr or $150k
    p3 = r'(?:[\$\€\£])\s*(\d{2,3}(?:,\d{3})+|\d{5,6})'
    m3 = re.search(p3, text)
    if m3:
        try:
            val = int(m3.group(1).replace(",", ""))
            if 25000 <= val <= 2000000:
                return val, val, curr
        except Exception:
            pass

    return None, None, curr

def extract_remote_regions(location_str: str, desc_str: str) -> Tuple[List[str], str]:
    """
    Determines remote regions list (e.g. ['Worldwide'], ['US'], ['Twin Cities'])
    and human-readable remote summary.
    """
    loc_clean = (location_str or "").lower()
    desc_clean = (desc_str or "").lower()
    combined = f"{loc_clean} {desc_clean}"

    # Twin Cities check
    if any(k in loc_clean for k in ["islamabad", "rawalpindi", "isb", "rwp"]):
        return ["Twin Cities"], "Twin Cities (Islamabad/Rawalpindi) On-site / Hybrid"

    if "pakistan" in loc_clean or "pakistan remote" in combined:
        return ["Pakistan"], "Remote Pakistan"

    # US strict identification patterns (Location string, title, or requirement)
    us_loc_patterns = [
        r'\b(us|usa|united states|u\.s\.|u\.s\.a\.)\b',
        r'remote\s*[\(\-\,\:\/]\s*(us|usa|united states)',
        r'(us|usa|united states)\s*[\(\-\,\:\/]\s*remote',
        r'\b(us|usa)\s+remote\b',
        r'\bremote\s+(us|usa)\b',
        r'\b(san\s+francisco|california|new\s+york|seattle|austin|chicago|los\s+angeles|boston|denver|atlanta|miami)\b',
        r'\b(ca|ny|tx|wa|il|ma|co|fl|va|ga|nc|pa|oh)\s*[,;]\s*(united states|usa|us)\b',
        r'[,;]\s*(california|new york|texas|washington)\b',
        r'\bunited states\s*-\s*\w+\b'
    ]
    us_desc_patterns = [
        r'\b(us|usa)\s*(-only|only)\b',
        r'\b(us|usa)\s+(citizens?|residents?|based\s+only)\b',
        r'\b(must\s+reside\s+in\s+the\s+us|must\s+be\s+located\s+in\s+the\s+us|located\s+in\s+the\s+us)\b',
        r'\b(us\s+work\s+authorization|authorized\s+to\s+work\s+in\s+the\s+us|w2\s+only)\b',
        r'\b(north\s+america\s+only|us/canada\s+only)\b'
    ]

    is_us_loc = any(re.search(pat, loc_clean) for pat in us_loc_patterns)
    is_us_desc = any(re.search(pat, desc_clean) for pat in us_desc_patterns)
    is_us_restricted = is_us_loc or is_us_desc

    if is_us_restricted:
        is_remote_clause = "remote" in loc_clean or "remote" in desc_clean[:200]
        if is_remote_clause:
            return ["US"], "Remote United States only"
        else:
            return ["US"], "United States (On-site / Hybrid)"

    # Europe / UK check
    if any(k in loc_clean for k in ["europe", "uk", "united kingdom", "london", "germany", "berlin", "france", "paris", "emea"]):
        return ["Europe"], "Remote Europe / UK"

    # Canada check
    if any(k in loc_clean for k in ["canada", "toronto", "vancouver", "montreal"]):
        return ["Canada"], "Remote Canada only"

    # Worldwide signals (ONLY valid if not geofenced above)
    worldwide_patterns = [
        r'\bworldwide\b', r'\banywhere\b', r'\bglobal remote\b',
        r'\bwork from anywhere\b', r'\bfully distributed\b', r'\ball countries\b',
        r'\bany country\b', r'\bhire anywhere\b', r'\bworldwide remote\b'
    ]
    is_worldwide = any(re.search(pat, loc_clean) or re.search(pat, desc_clean) for pat in worldwide_patterns)

    if is_worldwide:
        return ["Worldwide"], "Fully remote worldwide"

    # Pure remote fallback if location is simply "Remote" without country restrictions
    if loc_clean.strip() in ["remote", "work from home", "telecommute"]:
        return ["Worldwide"], "Fully remote worldwide"

    return [location_str.strip() or "Remote"], f"Remote: {location_str.strip() or 'Unspecified'}"

def classify_taxonomy(title: str, desc: str) -> Tuple[str, str]:
    """
    Classifies job_type and experience_level.
    """
    t = title.lower()
    full = f"{t} {desc.lower()[:500]}"

    # Experience level
    if any(s in t for s in ["lead", "principal", "staff", "architect", "director", "head of", "vp"]):
        exp = "lead"
    elif any(s in t for s in ["senior", "sr.", "sr ", "iii", "iv"]):
        exp = "senior"
    elif any(j in t for j in ["junior", "entry", "intern", "associate", "fresher", "grad"]):
        exp = "junior"
    else:
        exp = "mid"

    # Job type
    if any(k in t for k in ["ai", "ml", "machine learning", "artificial intelligence", "llm", "rag", "genai", "prompt"]):
        jtype = "ai_ml"
    elif any(k in t for k in ["full stack", "fullstack", "full-stack"]):
        jtype = "full_stack"
    elif any(k in t for k in ["backend", "back-end", "python", "django", "fastapi"]):
        jtype = "backend"
    elif any(k in t for k in ["frontend", "front-end", "react", "next.js", "vue"]):
        jtype = "frontend"
    elif any(k in t for k in ["data engineer", "data platform", "analytics engineer"]):
        jtype = "data_engineering"
    elif any(k in t for k in ["devops", "sre", "infrastructure", "cloud", "platform"]):
        jtype = "devops"
    elif any(k in t for k in ["design", "ui/ux", "product design"]):
        jtype = "product_design"
    else:
        jtype = "software_engineering"

    return jtype, exp

def generate_crisp_summary(title: str, company: str, description: str) -> str:
    """
    Generates a high-signal 2-sentence summary outlining primary duties, tech stack, and key requirements.
    """
    clean = re.sub(r'<[^>]+>', ' ', description or '')
    clean = re.sub(r'\s+', ' ', clean).strip()

    # Look for key requirement phrases
    req_matches = []
    # Tech stack detection
    tech_keywords = [
        "python", "fastapi", "django", "react", "next.js", "typescript", "node.js",
        "llm", "rag", "pytorch", "tensorflow", "docker", "kubernetes", "aws", "gcp",
        "sql", "postgres", "redis", "langchain", "llamaindex", "cuda"
    ]
    detected_tech = [k.title() for k in tech_keywords if re.search(r'\b' + re.escape(k) + r'\b', clean.lower())]

    # Sentence extraction
    sentences = re.split(r'(?<=[.!?]) +', clean)
    lead_sentence = ""
    for s in sentences[:5]:
        if len(s) > 30 and not any(skip in s.lower() for skip in ["about us", "equal opportunity", "benefits", "privacy policy"]):
            lead_sentence = s.strip()
            break

    if not lead_sentence:
        lead_sentence = f"Work as {title} at {company} to design and scale core software architecture."

    tech_part = f" Core stack: {', '.join(detected_tech[:6])}." if detected_tech else ""
    summary = f"At {company}, {lead_sentence[:160].rstrip('.')}.{tech_part}"
    return summary[:280].strip()

def structure_job_object(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enriches and normalizes the job object with Matcha structured fields.
    """
    title = job.get("title", "")
    desc = job.get("description", "")
    loc = job.get("location", "Remote")
    co = job.get("company", "")

    # Salary
    s_min, s_max, curr = extract_salary_range(f"{title} {job.get('salary_raw', '')} {desc[:800]}")
    job["salary_min"] = s_min
    job["salary_max"] = s_max
    job["salary_currency"] = curr

    # Remote regions
    regions, remote_summary = extract_remote_regions(loc, desc)
    job["remote_regions"] = regions
    job["remote_summary"] = remote_summary

    # Taxonomy
    jtype, exp_lvl = classify_taxonomy(title, desc)
    job["job_type"] = jtype
    job["experience_level"] = exp_lvl

    # 2-sentence summary
    job["job_summary"] = generate_crisp_summary(title, co, desc)
    return job
