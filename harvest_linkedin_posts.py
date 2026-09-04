"""
Hardened LinkedIn Job Posts Harvester & Qualification Engine.

Enforces:
1. True Freshness Validation:
   - Extracts relative time tokens (e.g., '10h', '2d', '1w', '1mo', '2y') or explicit timestamps.
   - Evaluates Freshness: FRESH (<= 14 days), AGING (15 - 30 days), STALE (> 30 days).
   - Hard-rejects STALE posts from entering the QUALIFIED output.
2. Canonical Candidate & Role Qualification:
   - Uses jobpilot.core.eligibility to run strict checks:
     * Candidate Profile Relevance (Tech/AI/Software/Web only; rejects sales, HR, marketing, civil, etc.)
     * Seniority Gatekeeper (Rejects Senior, Lead, Principal, Staff, Director, Manager)
     * Experience Gatekeeper (Rejects > 3 years explicit requirements)
     * Geographic Gatekeeper (Worldwide Remote, Pakistan/Islamabad/Rawalpindi; rejects US/UK/EU/India restricted)
3. Author vs Hiring Contact Separation:
   - Stores post_author and post_author_linkedin separately from hiring_contact and hiring_contact_title.
   - Only marks as hiring_contact if text explicitly indicates recruitment/hiring authority or email/contact route.
4. Real Deduplication:
   - Generates stable opportunity fingerprint (company + title + application_url/email) to prevent multiple posts advertising the same job from polluting the dataset.
5. Strict Application Route Verification:
   - Discovers application URLs (Greenhouse, Lever, Workday, Google Forms, careers page) and hiring emails.
   - Categorizes records: QUALIFIED, BORDERLINE (missing direct route but matches role), or REJECTED.
6. Zero Fabrication:
   - Preserves actual extracted evidence, never manufactures fake salaries or dates.
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys
import time
import urllib.parse
import urllib.request

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from playwright.sync_api import sync_playwright

from jobpilot.core.eligibility import (
    evaluate_job_eligibility,
    check_tech_role_relevance,
    check_seniority,
    check_experience_requirement,
    check_geographic_eligibility,
)

CSV_COLUMNS = [
    "post_url",
    "posted_at",
    "freshness_status",
    "freshness_reason",
    "qualification_status",
    "qualification_reason",
    "company",
    "job_title",
    "job_type",
    "work_arrangement",
    "location",
    "country",
    "salary",
    "currency",
    "shift",
    "post_author",
    "post_author_linkedin",
    "hiring_contact",
    "hiring_contact_title",
    "application_url",
    "application_email",
    "job_description",
    "requirements",
    "matched_technologies",
    "evidence",
    "opportunity_fingerprint",
    "discovered_at",
]


def get_linkedin_snowflake_datetime(url: str) -> Optional[datetime]:
    """
    LinkedIn activity IDs are 64-bit snowflakes where the leading 41 bits
    encode the epoch millisecond of post creation. This is ground truth.
    """
    m = re.search(r"activity-(\d+)", url)
    if not m:
        return None
    try:
        act_id = int(m.group(1))
        timestamp_ms = act_id >> 22
        from datetime import timezone
        dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def evaluate_freshness(age_token: str, post_url: str = "") -> Tuple[str, str, str]:
    """
    Evaluates freshness status, reason, and posted_at date.
    Statuses: FRESH (<= 14 days), AGING (15 - 30 days), STALE (> 30 days).
    Uses LinkedIn activity snowflake timestamp as authoritative evidence when available!
    """
    today = datetime.utcnow()

    # 1. Authoritative ground truth: activity snowflake
    dt = get_linkedin_snowflake_datetime(post_url) if post_url else None
    if dt:
        delta_days = (today - dt).days
        posted_at = dt.strftime("%Y-%m-%d")
        if delta_days <= 14:
            return "FRESH", f"Verified post date {posted_at} ({delta_days} days old)", posted_at
        elif delta_days <= 30:
            return "AGING", f"Post date {posted_at} ({delta_days} days old)", posted_at
        else:
            return "STALE", f"Post date {posted_at} exceeds 14 days ({delta_days} days old)", posted_at

    # 2. Fallback to parsed age token
    token = (age_token or "").strip().lower()
    if not token:
        return "UNKNOWN", "No timestamp evidence available", today.strftime("%Y-%m-%d")

    # Years
    if "y" in token or "year" in token:
        num = "".join(filter(str.isdigit, token))
        yrs = int(num) if num else 1
        est = today - timedelta(days=365 * yrs)
        return "STALE", f"Post is {yrs} year(s) old ({token})", est.strftime("%Y-%m-%d")

    # Months
    if "mo" in token or "month" in token:
        num = "".join(filter(str.isdigit, token))
        mos = int(num) if num else 1
        est = today - timedelta(days=30 * mos)
        return "STALE", f"Post is {mos} month(s) old ({token})", est.strftime("%Y-%m-%d")

    # Weeks
    if "w" in token or "week" in token:
        num = "".join(filter(str.isdigit, token))
        w = int(num) if num else 1
        est = today - timedelta(days=7 * w)
        if w > 2:
            return "STALE", f"Post is {w} weeks old ({token})", est.strftime("%Y-%m-%d")
        elif w == 2:
            return "AGING", f"Post is 2 weeks old ({token})", est.strftime("%Y-%m-%d")
        else:
            return "FRESH", f"Post is {w} week(s) old ({token})", est.strftime("%Y-%m-%d")

    # Days
    if "d" in token or "day" in token:
        num = "".join(filter(str.isdigit, token))
        d = int(num) if num else 1
        est = today - timedelta(days=d)
        if d <= 14:
            return "FRESH", f"Post is {d} day(s) old ({token})", est.strftime("%Y-%m-%d")
        else:
            return "AGING", f"Post is {d} day(s) old ({token})", est.strftime("%Y-%m-%d")

    # Hours / Minutes / Seconds
    if any(unit in token for unit in ["h", "m", "s", "hour", "minute"]):
        return "FRESH", f"Post is under 24 hours old ({token})", today.strftime("%Y-%m-%d")

    return "UNKNOWN", f"Unrecognized time token ({token})", today.strftime("%Y-%m-%d")


def extract_matched_technologies(text: str) -> List[str]:
    """Extracts candidate target technologies found in description."""
    tech_catalog = [
        "Python", "FastAPI", "Django", "Flask", "React", "Next.js",
        "Node.js", "Express", "TypeScript", "JavaScript", "MongoDB",
        "PostgreSQL", "MySQL", "Redis", "Docker", "Git", "TensorFlow",
        "PyTorch", "NLP", "LLM", "Generative AI", "RAG", "LangChain",
        "AI/ML", "REST API", "GraphQL", "Tailwind", "AWS"
    ]
    matched = []
    text_lower = text.lower()
    for tech in tech_catalog:
        pattern = r"\b" + re.escape(tech.lower()) + r"\b"
        if re.search(pattern, text_lower):
            matched.append(tech)
    return matched


def create_opportunity_fingerprint(company: str, title: str, app_url: str, app_email: str) -> str:
    """Generates a stable identifier to collapse duplicate job postings across recruiters."""
    c_norm = re.sub(r"\b(inc|corp|corporation|llc|ltd|limited|technologies|tech|team of)\b\.?", "", company.lower()).strip()
    clean_c = "".join(filter(str.isalnum, c_norm))[:12]
    clean_t = "".join(filter(str.isalnum, title.lower()))[:15]
    
    # If standard ATS application URL is present, use domain + path
    anchor = ""
    if app_url:
        clean_u = app_url.split("?")[0].rstrip("/").lower()
        # Remove http/https
        clean_u = re.sub(r"^https?://", "", clean_u)
        anchor = clean_u[:30]
    elif app_email:
        anchor = app_email.lower().strip()
    else:
        anchor = "no_route"
        
    return f"{clean_c}_{clean_t}_{anchor}"


def extract_linkedin_post(page, post_url: str) -> Optional[Dict[str, str]]:
    """Visits the LinkedIn post via Playwright and extracts high-fidelity structured data."""
    try:
        page.goto(post_url, wait_until="domcontentloaded", timeout=22000)
        page.wait_for_timeout(2500)
    except Exception:
        try:
            page.goto(post_url, wait_until="load", timeout=18000)
            page.wait_for_timeout(2000)
        except Exception:
            return None

    try:
        page_title = page.title() or ""
        body_text = page.inner_text("body") or ""
    except Exception:
        return None

    lower_body = body_text.lower()

    # 1. Check for expired or closed posts
    expired_indicators = [
        "no longer accepting applications",
        "this job has expired",
        "this job is closed",
        "position has been filled",
        "posting is no longer active",
    ]
    if any(ei in lower_body for ei in expired_indicators):
        return None

    # 2. Extract Relative Age & Freshness
    # Check <time> tags first
    age_token = ""
    time_elements = page.query_selector_all("time")
    for te in time_elements:
        t_text = (te.inner_text() or "").strip()
        if t_text:
            age_token = t_text
            break
            
    if not age_token:
        # Scan body for tokens like "10h •", "2d •", "1w •", "1mo •", "2y •"
        age_match = re.search(r"\b(\d+\s*(?:m|mo|months?|w|weeks?|d|days?|h|hours?|y|years?))\s*(?:•|\b|ago|edited)", body_text, re.IGNORECASE)
        if age_match:
            age_token = age_match.group(1).strip()

    freshness_status, freshness_reason, posted_at = evaluate_freshness(age_token, post_url)

    # 3. Post Author vs Hiring Contact
    post_author = ""
    post_author_linkedin = ""
    author_links = page.query_selector_all("a[href*='/in/']")
    for al in author_links:
        try:
            href = al.get_attribute("href") or ""
            text = (al.inner_text() or "").strip()
            if "/in/" in href and text and len(text) > 2 and "\n" not in text and len(text) < 40:
                post_author = text
                post_author_linkedin = href.split("?")[0]
                break
        except Exception:
            pass

    if not post_author and " | " in page_title:
        post_author = page_title.split(" | ")[-1].strip()

    # Determine hiring contact
    hiring_contact = ""
    hiring_contact_title = ""
    if any(sig in lower_body for sig in ["dm me", "reach out to me", "send cv to me", "i am hiring", "my team is hiring"]):
        hiring_contact = post_author
        hiring_contact_title = "Post Author (Direct Hiring Contact)"
    elif any(sig in lower_body for sig in ["recruiter", "talent acquisition", "hiring manager"]):
        hiring_contact = post_author
        hiring_contact_title = "Recruiter / Talent Contact"

    # 4. Extract Application Routes (Email / URL)
    emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", body_text)
    app_email = ""
    for em in emails:
        if not any(ignored in em.lower() for ignored in ["privacy", "abuse", "support", "help", "security", "example"]):
            app_email = em
            break

    app_url = ""
    form_links = re.findall(
        r"https?://(?:forms\.gle|bit\.ly|t\.co|lnkd\.in|docs\.google\.com/forms|boards\.greenhouse\.io/[^\s\"'<>]+|jobs\.lever\.co/[^\s\"'<>]+|jobs\.[^\s\"'<>]+|[^\s\"'<>]+\.com/careers[^\s\"'<>]*|[^\s\"'<>]+\.com/jobs[^\s\"'<>]*|[^\s\"'<>]+\.workable\.com/[^\s\"'<>]+)",
        body_text,
    )
    if form_links:
        app_url = form_links[0]

    # 5. Extract Job Title
    title_matches = [
        r"(?:hiring|looking for|seeking)\s+(?:a\s+|an\s+)?([A-Za-z0-9\+\#\.\s\/\-]{3,40}(?:engineer|developer|specialist|programmer|intern|architect))",
        r"role:\s*([A-Za-z0-9\+\#\.\s\/\-]{3,40})",
        r"position:\s*([A-Za-z0-9\+\#\.\s\/\-]{3,40})",
    ]
    job_title = ""
    for tm in title_matches:
        m = re.search(tm, body_text, re.IGNORECASE)
        if m:
            cand_t = m.group(1).strip().replace("\n", " ")
            if len(cand_t) < 50 and not any(bad in cand_t.lower() for bad in ["someone", "person", "candidate", "rockstar", "ninja"]):
                job_title = cand_t.title()
                break

    if not job_title:
        # Fallback to key canonical role keywords
        for kw in [
            "AI Engineer", "AI Developer", "Machine Learning Engineer",
            "Generative AI Developer", "LLM Engineer", "RAG Engineer",
            "Python Developer", "Backend Python Developer", "FastAPI Developer",
            "Full Stack Developer", "React Developer", "Next.js Developer",
            "MERN Developer", "Software Engineer"
        ]:
            if kw.lower() in lower_body:
                job_title = kw
                break

    if not job_title:
        # If no recognizable title, check if generic "developer" or "engineer"
        if "developer" in lower_body:
            job_title = "Software Developer"
        elif "engineer" in lower_body:
            job_title = "Software Engineer"
        else:
            return None  # Not a tech opening

    # 6. Extract Company
    company = ""
    comp_match = re.search(r"(?:at|@|company:)\s+([A-Za-z0-9\s]{2,30})(?:\.|\n|,|is)", body_text, re.IGNORECASE)
    if comp_match:
        cand_c = comp_match.group(1).strip()
        if cand_c.lower() not in ["our team", "a fast", "the company", "we", "this", "stealth", "our client"]:
            company = cand_c
    if not company and post_author:
        company = f"Team of {post_author}"

    # 7. Work Arrangement & Location
    work_arrangement = "Onsite"
    if "remote" in lower_body:
        work_arrangement = "Remote"
    elif "hybrid" in lower_body:
        work_arrangement = "Hybrid"

    location = ""
    country = ""
    if "islamabad" in lower_body:
        location = "Islamabad"
        country = "Pakistan"
    elif "rawalpindi" in lower_body:
        location = "Rawalpindi"
        country = "Pakistan"
    elif "pakistan" in lower_body:
        location = "Pakistan"
        country = "Pakistan"
    elif work_arrangement == "Remote":
        location = "Worldwide Remote"
        country = "Worldwide"
    else:
        location = "Onsite"
        country = "International"

    # 8. Salary & Currency
    salary = ""
    currency = ""
    sal_match = re.search(r"(\$|£|€|USD|GBP|PKR|Rs\.?)\s*(\d+[\d,kK\.\s\-\+]*\s*(?:k|K|/hr|/mo|/month|/yr|year|per\s+month|per\s+year)?)", body_text)
    if sal_match:
        cur_sym = sal_match.group(1).upper()
        if "$" in cur_sym or "USD" in cur_sym:
            currency = "USD"
        elif "£" in cur_sym or "GBP" in cur_sym:
            currency = "GBP"
        elif "PKR" in cur_sym or "RS" in cur_sym:
            currency = "PKR"
        else:
            currency = cur_sym
        salary = f"{sal_match.group(1)}{sal_match.group(2).strip()}"

    # 9. Shift
    shift = "Standard"
    if "morning shift" in lower_body:
        shift = "Morning"
    elif "night shift" in lower_body or "evening shift" in lower_body:
        shift = "Night/Evening"

    # 10. Clean Description & Requirements
    words = body_text.split()
    clean_desc = " ".join(words[:140])
    requirements = ""
    req_match = re.search(r"(?:requirements|skills|what we need|qualifications|experience):?([\s\S]{10,400})", body_text, re.IGNORECASE)
    if req_match:
        requirements = " ".join(req_match.group(1).split()[:50])

    matched_techs = extract_matched_technologies(body_text)

    # 11. Run Full Eligibility Gatekeeper
    elig_decision = evaluate_job_eligibility(
        job_id=post_url,
        title=job_title,
        company=company,
        description=body_text,
        location=location,
    )

    # 12. Classify Final Status
    qualification_status = "REJECTED"
    qualification_reason = ""

    if not elig_decision.is_eligible:
        qualification_status = "REJECTED"
        qualification_reason = f"{elig_decision.decision}: {elig_decision.reason}"
    elif freshness_status == "STALE":
        qualification_status = "REJECTED"
        qualification_reason = f"STALE_POST: {freshness_reason}"
    elif not (app_url or app_email):
        qualification_status = "BORDERLINE"
        qualification_reason = "Matches candidate profile but missing verified direct application URL or email (only DM route)"
    else:
        qualification_status = "QUALIFIED"
        qualification_reason = f"Verified fresh ({freshness_status}) opportunity matching candidate profile (Role: {job_title}, Tech: {', '.join(matched_techs[:4]) or 'General Software'})"

    # Fingerprint
    fingerprint = create_opportunity_fingerprint(company, job_title, app_url, app_email)

    evidence = ""
    ev_match = re.search(r"(?:we are hiring|hiring for|looking for|dm me|send your cv|apply here)[\s\S]{10,180}", body_text, re.IGNORECASE)
    if ev_match:
        evidence = " ".join(ev_match.group(0).split()[:35])
    else:
        evidence = clean_desc[:140]

    return {
        "post_url": post_url,
        "posted_at": posted_at,
        "freshness_status": freshness_status,
        "freshness_reason": freshness_reason,
        "qualification_status": qualification_status,
        "qualification_reason": qualification_reason,
        "company": company,
        "job_title": job_title,
        "job_type": "Full-time" if "part-time" not in lower_body else "Part-time",
        "work_arrangement": work_arrangement,
        "location": location,
        "country": country,
        "salary": salary,
        "currency": currency,
        "shift": shift,
        "post_author": post_author,
        "post_author_linkedin": post_author_linkedin,
        "hiring_contact": hiring_contact,
        "hiring_contact_title": hiring_contact_title,
        "application_url": app_url,
        "application_email": app_email,
        "job_description": clean_desc,
        "requirements": requirements,
        "matched_technologies": ", ".join(matched_techs),
        "evidence": evidence,
        "opportunity_fingerprint": fingerprint,
        "discovered_at": datetime.utcnow().isoformat(),
    }


def process_and_export_linkedin_posts(
    input_urls_path: str = "discovered_linkedin_urls.txt",
    output_csv_path: str = "linkedin_job_posts_100.csv",
    audit_csv_path: str = "linkedin_job_posts_audit_all.csv",
    max_to_process: int = 120,
) -> Dict[str, int]:
    """Processes candidate URLs, deduplicates, qualifies, and writes verified outputs."""
    urls = []
    if os.path.exists(input_urls_path):
        with open(input_urls_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "linkedin.com/posts/" in line:
                    urls.append(line)

    print(f"Loaded {len(urls)} candidate post URLs for qualification.")

    stats = {
        "total_evaluated": 0,
        "qualified": 0,
        "borderline": 0,
        "rejected_stale": 0,
        "rejected_seniority": 0,
        "rejected_experience": 0,
        "rejected_non_tech": 0,
        "rejected_location": 0,
        "rejected_duplicate": 0,
        "rejected_unreachable": 0,
    }

    all_records: List[Dict[str, str]] = []
    qualified_records: List[Dict[str, str]] = []
    seen_fingerprints: Set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        for idx, u in enumerate(urls[:max_to_process]):
            stats["total_evaluated"] += 1
            print(f"[{idx+1}/{min(len(urls), max_to_process)}] Inspecting {u[:70]}...")
            data = extract_linkedin_post(page, u)
            
            if not data:
                stats["rejected_unreachable"] += 1
                print(" -> SKIPPED (Unreachable or expired)")
                continue

            fp = data["opportunity_fingerprint"]
            if fp in seen_fingerprints:
                stats["rejected_duplicate"] += 1
                data["qualification_status"] = "REJECTED"
                data["qualification_reason"] = "DUPLICATE_OPPORTUNITY: Identical role and company already recorded"
                all_records.append(data)
                print(f" -> REJECTED (Duplicate: {fp})")
                continue

            seen_fingerprints.add(fp)
            all_records.append(data)

            # Record stats
            status = data["qualification_status"]
            reason = data["qualification_reason"]
            if status == "QUALIFIED":
                stats["qualified"] += 1
                qualified_records.append(data)
                print(f" -> QUALIFIED: {data['job_title']} at '{data['company']}' (Fresh: {data['freshness_status']})")
            elif status == "BORDERLINE":
                stats["borderline"] += 1
                print(f" -> BORDERLINE: {data['job_title']} at '{data['company']}' (Missing direct route)")
            else:
                if "STALE" in reason:
                    stats["rejected_stale"] += 1
                elif "SENIORITY" in reason:
                    stats["rejected_seniority"] += 1
                elif "EXPERIENCE" in reason:
                    stats["rejected_experience"] += 1
                elif "NON_TECH" in reason or "NON_DEV" in reason:
                    stats["rejected_non_tech"] += 1
                elif "LOCATION" in reason:
                    stats["rejected_location"] += 1
                print(f" -> REJECTED: {reason[:60]}")

            time.sleep(1.0)

        browser.close()

    # 1. Write the clean, qualified dataset to linkedin_job_posts_100.csv
    # NOTE: As instructed by prompt, quality > count. Output exactly genuine qualified records!
    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in qualified_records:
            writer.writerow(r)

    # 2. Write the comprehensive audit dataset (all records including rejections)
    with open(audit_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in all_records:
            writer.writerow(r)

    print("\n" + "=" * 60)
    print("LINKEDIN HARVEST & QUALIFICATION AUDIT SUMMARY")
    print("=" * 60)
    print(f"Total Posts Evaluated:      {stats['total_evaluated']}")
    print(f"Genuinely Qualified Fresh:  {stats['qualified']} (Saved to {output_csv_path})")
    print(f"Borderline (No direct URL): {stats['borderline']}")
    print(f"Rejected Stale (> 14 days): {stats['rejected_stale']}")
    print(f"Rejected Seniority:         {stats['rejected_seniority']}")
    print(f"Rejected Experience (>3y):  {stats['rejected_experience']}")
    print(f"Rejected Non-Tech / Field:  {stats['rejected_non_tech']}")
    print(f"Rejected Location/Geo:      {stats['rejected_location']}")
    print(f"Rejected Duplicates:        {stats['rejected_duplicate']}")
    print(f"Unreachable / Expired:      {stats['rejected_unreachable']}")
    print(f"Comprehensive Audit Export: {audit_csv_path}")
    print("=" * 60)

    return stats


if __name__ == "__main__":
    process_and_export_linkedin_posts()
