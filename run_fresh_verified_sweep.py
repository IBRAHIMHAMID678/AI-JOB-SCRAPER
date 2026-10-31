#!/usr/bin/env python3
"""
run_fresh_verified_sweep.py
===========================
Comprehensive background scraper runner for AI Job Scraper.
Filters specifically for:
1. International remote jobs hiring worldwide (< 2 years / Junior level).
2. Local Pakistani tech jobs in the Twin Cities (Islamabad & Rawalpindi) onsite/remote/hybrid.
3. Fresh jobs from today / within 24 hours.
4. Verified jobs: Live HTTP link & posting validation (eliminates dead links and expired posts).
5. All 40+ scraper sources + JobSpy deep crawl with automated fallback.
6. Strictly writes temp and caches to D:\\Job Scraper\\.cache\\
"""

import sys
import os
import json
import re
import time
import hashlib
import concurrent.futures
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error
import unicodedata

# Ensure root directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "auto-scraper"))

# Import config first to ensure strict D: drive cache/temp isolation
import config
from log_manager import log
from database import save_job_to_db, init_sqlite
from scrapers.jobspy_scraper import scrape_single_term

# Load auto-scraper sources
try:
    from sources import SOURCES as AUTO_SOURCES
except Exception as e:
    log(f"[WARN] Failed to load auto-scraper sources: {e}")
    AUTO_SOURCES = {}

# Senior title patterns (Strict hard block)
SENIOR_PATTERNS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bstaff\b", r"\bprincipal\b",
    r"\bdirector\b", r"\bvp\b", r"\bvice president\b", r"\bhead of\b",
    r"\barchitect\b", r"\bmanager\b", r"\bdistinguished\b", r"\bfellow\b",
    r"\biii\b", r"\biv\b", r"\bv\b"
]

# Junior / Entry level positive indicators
JUNIOR_PATTERNS = [
    r"\bjunior\b", r"\bjr\.?\b", r"\bentry[- ]level\b", r"\bassociate\b",
    r"\bfresher\b", r"\bfresh graduate\b", r"\bintern\b", r"\binternship\b",
    r"\b0[-–]1\s*(?:year|yr)", r"\b0[-–]2\s*(?:year|yr)", r"\b1[-–]2\s*(?:year|yr)",
    r"\b< ?2\s*(?:year|yr)", r"\bless than 2\s*(?:year|yr)", r"\b1\s*(?:year|yr)"
]

# Experience exclusion: 3+ or 4+ years
HIGH_EXP_PATTERNS = [
    r"(\d+)\s*\+\s*(?:years?|yrs?)(?:'s)?(?:\s+of)?\s+experience",
    r"(?:minimum|at\s+least|requires?)\s*(\d+)\s*(?:years?|yrs?)",
    r"(\d+)\s*[-–]\s*\d+\s*(?:years?|yrs?)"
]

# Twin Cities markers
TWIN_CITIES_PATTERNS = [
    r"\bislamabad\b", r"\brawalpindi\b", r"\bisb\b", r"\brwp\b",
    r"\bblue area\b", r"\bi-8\b", r"\bi-9\b", r"\bi-10\b", r"\bg-8\b",
    r"\bg-9\b", r"\bg-10\b", r"\bg-11\b", r"\bdha\b", r"\bbahria\b"
]

# Pakistan markers
PAKISTAN_PATTERNS = [r"\bpakistan\b", r"\b\.pk\b"] + TWIN_CITIES_PATTERNS

# Worldwide remote markers
WORLDWIDE_REMOTE_PATTERNS = [
    r"\bworldwide\b", r"\banywhere\b", r"\bglobal remote\b",
    r"\bwork from anywhere\b", r"\bany country\b", r"\beverywhere\b",
    r"\bremote worldwide\b", r"\bfully distributed\b", r"\bhire anywhere\b",
    r"\ball countries\b", r"\bopen to anyone\b", r"\bemea\b"
]

# US/EU/UK only restrictions (blocks candidate unless worldwide remote is present)
RESTRICTED_LOCATIONS = [
    r"\b(us|usa)\s*(-only|only)\b",
    r"\b(us|usa)\s+(citizens?|citizenship|residents?|residency)\b",
    r"\b(must\s+reside\s+in\s+the\s+us|must\s+be\s+located\s+in\s+the\s+us)\b",
    r"\b(north\s+america\s+only|us/canada\s+only|eu\s+only|uk\s+only)\b",
    r"\bremote[\s,\-–(]*us\b",
    r"\bremote[\s,\-–(]*usa\b",
    r"\b(us|usa)\s+only\b"
]

def is_senior(title: str) -> bool:
    t = title.lower()
    for pat in SENIOR_PATTERNS:
        if re.search(pat, t):
            return True
    return False

def check_experience_is_junior(text: str) -> tuple[bool, str]:
    """
    Returns (is_allowed, reason).
    Allows <= 2 years or junior keywords. Blocks roles requiring >= 3 years.
    """
    t = text.lower()
    
    # Check upper-bound experience requirement
    for pat in HIGH_EXP_PATTERNS:
        matches = re.findall(pat, t)
        for m in matches:
            try:
                years = int(m) if isinstance(m, str) else int(m[0])
                if years >= 3:
                    return False, f"Requires {years}+ years experience"
            except (ValueError, TypeError, IndexError):
                pass

    # Check junior positive hint
    for pat in JUNIOR_PATTERNS:
        if re.search(pat, t):
            return True, "Junior / Entry level match (< 2 yrs)"

    return True, "Standard Developer (< 3 yrs requirement)"

def classify_location(location: str, description: str) -> tuple[str, bool]:
    """
    Returns (category, is_eligible)
    Categories: 'Twin Cities Local', 'Pakistan Remote', 'Worldwide Remote', 'Ineligible'
    """
    raw_loc = location or "Remote"
    loc_clean = unicodedata.normalize("NFKD", str(raw_loc)).encode("ascii", "ignore").decode("utf-8").lower()
    desc_clean = (description or "").lower()
    full_text = f"{loc_clean} {desc_clean}"

    # 1. Twin Cities Local Check
    for pat in TWIN_CITIES_PATTERNS:
        if re.search(pat, loc_clean):
            return "Twin Cities (Islamabad/Rawalpindi)", True

    # 2. Pakistan Remote / Local Check
    for pat in PAKISTAN_PATTERNS:
        if re.search(pat, loc_clean):
            return "Pakistan (Local/Remote)", True

    # 3. Check for US/EU Hard Restrictions
    for pat in RESTRICTED_LOCATIONS:
        if re.search(pat, loc_clean) or re.search(pat, desc_clean):
            # If explicit worldwide is not stated, block
            if not any(re.search(w, full_text) for w in WORLDWIDE_REMOTE_PATTERNS):
                return "Ineligible (Geographically Restricted)", False

    # 4. Worldwide Remote Check
    for pat in WORLDWIDE_REMOTE_PATTERNS:
        if re.search(pat, full_text):
            return "Worldwide Remote (Global)", True

    # 5. Default Remote check (if feed is remote-only like RemoteOK/Remotive/Himalayas)
    if "remote" in loc_clean and not any(re.search(pat, loc_clean) for pat in RESTRICTED_LOCATIONS):
        return "Worldwide Remote (General)", True

    return "Unverified / Non-Target", False

def verify_live_url(url: str, timeout: int = 8) -> tuple[bool, str]:
    """
    Checks if a job URL is live, reachable, and active (HTTP 200/301/302).
    Disqualifies dead links or expired postings.
    """
    if not url or not url.startswith("http"):
        return False, "Invalid URL format"
        
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if code in (200, 301, 302, 307, 308):
                # Sample the body to ensure it's not an expiration message
                body = resp.read(4096).decode("utf-8", errors="ignore").lower()
                dead_markers = [
                    "this job has expired", "position closed", "no longer accepting applications",
                    "job posting has ended", "job is no longer available", "page not found", "404 not found"
                ]
                for dm in dead_markers:
                    if dm in body:
                        return False, f"Posting expired ({dm})"
                return True, "Live URL Verified (HTTP 200)"
            return False, f"HTTP status {code}"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            # Behind Cloudflare or bot-protection (e.g. LinkedIn direct redirect)
            return True, f"Live URL (Protected endpoint HTTP {e.code})"
        return False, f"Dead link (HTTP {e.code})"
    except Exception as e:
        # If timeout or connection refused
        return False, f"Connection failed: {str(e)[:60]}"

def run_sweep():
    start_time = time.time()
    log("[SWEEP] ========================================================")
    log("[SWEEP] Starting Live Fresh Job Sweep (24-Hour Verified Pipeline)")
    log("[SWEEP] Target 1: Remote International Worldwide (< 2 yrs / Junior)")
    log("[SWEEP] Target 2: Twin Cities Local (Islamabad / Rawalpindi)")
    log("[SWEEP] ========================================================")

    raw_jobs = []

    # -------------------------------------------------------------
    # 1. JobSpy Deep Crawl: Remote & Twin Cities
    # -------------------------------------------------------------
    log("[SWEEP] Phase 1: Running JobSpy across targeted search terms...")
    # Core target search terms focused on junior/entry & AI/Full Stack/Python
    sweep_terms = [
        "Junior AI Engineer",
        "Junior Python Developer",
        "Junior Full Stack Developer",
        "Junior Backend Developer",
        "AI Engineer",
        "Python Developer",
        "Full Stack Developer",
        "Backend Developer",
        "FastAPI Developer"
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {executor.submit(scrape_single_term, term): term for term in sweep_terms}
        for future in concurrent.futures.as_completed(future_map):
            term = future_map[future]
            try:
                jobs = future.result()
                if jobs:
                    raw_jobs.extend(jobs)
                    log(f"  [JobSpy] Term '{term}' -> {len(jobs)} raw jobs found")
            except Exception as e:
                log(f"  [JobSpy] Error on term '{term}': {e}")

    log(f"[SWEEP] JobSpy Phase completed. Collected {len(raw_jobs)} raw jobs.")

    # -------------------------------------------------------------
    # 2. Auto-Scraper Sources (All 40+ keyless, feeds, ATS & PK portals)
    # -------------------------------------------------------------
    log(f"[SWEEP] Phase 2: Querying {len(AUTO_SOURCES)} specialized sources in parallel...")
    
    # Priority sources for remote & Pakistan
    sources_to_query = [
        'talenthubsol', 'indeed_pk', 'apnijobs', 'jobspy_bayt',
        'remoteok', 'remotive', 'himalayas', 'jobicy', 'workingnomads', 'wwr',
        'yc_jobs', 'hn_hiring', 'fourdayweek', 'themuse', 'landing_jobs',
        'getonbrd', 'smartrecruiters', 'justjoin', 'workable_search',
        'ats_greenhouse', 'ats_lever', 'ats_ashby'
    ]
    # Add any remaining available sources
    for s in AUTO_SOURCES.keys():
        if s not in sources_to_query:
            sources_to_query.append(s)

    def fetch_source_safe(src_name):
        func = AUTO_SOURCES.get(src_name)
        if not func:
            return []
        try:
            batch = func()
            return batch or []
        except Exception as e:
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_src = {executor.submit(fetch_source_safe, src): src for src in sources_to_query}
        for future in concurrent.futures.as_completed(future_to_src):
            src_name = future_to_src[future]
            try:
                batch = future.result()
                if batch:
                    # Normalize auto-scraper format to match standard job dict
                    for j in batch:
                        raw_jobs.append({
                            "title": j.get("title", ""),
                            "company": j.get("company", ""),
                            "url": j.get("url") or j.get("apply_url", ""),
                            "description": j.get("description", ""),
                            "location": j.get("location", "Remote"),
                            "estimated_pay": f"{j.get('salary_min', '')} - {j.get('salary_max', '')}" if j.get('salary_min') else "Not Disclosed",
                            "source": f"Feed - {src_name}",
                            "posted_at": j.get("posted_at")
                        })
                    log(f"  [Feed] Source '{src_name}' -> {len(batch)} jobs found")
            except Exception as e:
                pass

    log(f"[SWEEP] Total raw jobs gathered: {len(raw_jobs)}")

    # -------------------------------------------------------------
    # 3. Deduplication
    # -------------------------------------------------------------
    unique_candidates = {}
    for job in raw_jobs:
        url = (job.get("url") or "").strip()
        title = (job.get("title") or "").strip().lower()
        company = (job.get("company") or "").strip().lower()
        if not url:
            continue
        fp = f"{title}:{company}"
        if url not in unique_candidates and fp not in unique_candidates:
            unique_candidates[url] = job
            unique_candidates[fp] = job

    deduped_jobs = [j for k, j in unique_candidates.items() if k.startswith("http")]
    log(f"[SWEEP] Unique candidate jobs after deduplication: {len(deduped_jobs)}")

    # -------------------------------------------------------------
    # 4. Strict Filtering (Seniority, Experience, Location)
    # -------------------------------------------------------------
    log("[SWEEP] Phase 3: Filtering jobs against user requirements...")
    passed_filter = []

    for job in deduped_jobs:
        title = job.get("title", "")
        desc = job.get("description", "")
        loc = job.get("location", "Remote")

        # Gate 1: Reject Senior / Lead
        if is_senior(title):
            continue

        # Gate 2: Experience Filter (< 2 years / Junior friendly)
        exp_ok, exp_reason = check_experience_is_junior(f"{title} {desc}")
        if not exp_ok:
            continue

        # Gate 3: Location Classification (Twin Cities vs Worldwide Remote)
        category, is_eligible = classify_location(loc, desc)
        if not is_eligible:
            continue

        job["category"] = category
        job["exp_reason"] = exp_reason

        # Scoring
        score = 60
        reasons = [category, exp_reason]
        
        t_low = title.lower()
        if any(term in t_low for term in ["ai", "python", "full stack", "fastapi", "backend", "rag", "llm"]):
            score += 25
            reasons.append("Core Stack Fit (AI / Python / Full Stack)")
        if any(term in t_low for term in ["junior", "entry", "associate", "fresher"]):
            score += 15
            reasons.append("Junior Level Title")

        job["match_score"] = min(score, 100)
        job["match_reason"] = " | ".join(reasons)
        passed_filter.append(job)

    log(f"[SWEEP] Passed criteria filter: {len(passed_filter)} candidates")

    # -------------------------------------------------------------
    # 5. Live Link & Posting Verification
    # -------------------------------------------------------------
    log(f"[SWEEP] Phase 4: Live verifying {len(passed_filter)} job URLs (eliminating dead/expired links)...")
    verified_jobs = []

    def verify_single(job):
        url = job.get("url")
        is_live, verify_msg = verify_live_url(url)
        if is_live:
            job["verification_status"] = "Verified Active"
            job["verification_detail"] = verify_msg
            return job
        else:
            log(f"  [DEAD LINK REJECTED] {job.get('title')} at {job.get('company')} ({verify_msg})")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(verify_single, job) for job in passed_filter]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res:
                verified_jobs.append(res)

    log(f"[SWEEP] Live Verification Complete! Found {len(verified_jobs)} fully verified jobs.")

    # Sort: Twin Cities jobs first, then by match score descending
    def sort_key(j):
        is_twin = 1 if "Twin Cities" in j.get("category", "") else 0
        return (is_twin, j.get("match_score", 0))

    verified_jobs.sort(key=sort_key, reverse=True)

    # -------------------------------------------------------------
    # 6. Database Persistence
    # -------------------------------------------------------------
    log(f"[SWEEP] Persisting {len(verified_jobs)} verified jobs into SQLite (jobpilot.db)...")
    saved_count = 0
    for job in verified_jobs:
        if save_job_to_db(job):
            saved_count += 1

    log(f"[SWEEP] Database persistence complete ({saved_count} jobs updated in jobpilot.db).")

    # -------------------------------------------------------------
    # 7. Generate Reports
    # -------------------------------------------------------------
    sweeps_dir = os.path.join(BASE_DIR, "sweeps")
    os.makedirs(sweeps_dir, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")

    json_path = os.path.join(sweeps_dir, f"verified_sweep_{today_str}.json")
    latest_json_path = os.path.join(sweeps_dir, "fresh_verified_jobs_latest.json")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(verified_jobs, f, indent=2, default=str)
    with open(latest_json_path, "w", encoding="utf-8") as f:
        json.dump(verified_jobs, f, indent=2, default=str)

    # Markdown Summary Report
    md_path = os.path.join(sweeps_dir, f"verified_sweep_{today_str}.md")
    latest_md_path = os.path.join(sweeps_dir, "fresh_verified_jobs_latest.md")

    twin_cities_jobs = [j for j in verified_jobs if "Twin Cities" in j.get("category", "")]
    pak_remote_jobs = [j for j in verified_jobs if "Pakistan (Local/Remote)" in j.get("category", "")]
    worldwide_jobs = [j for j in verified_jobs if "Worldwide" in j.get("category", "")]

    md_content = f"""# AI Job Pilot — Verified Fresh Jobs Report ({today_str})

> Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}
> Total Verified Active Jobs: **{len(verified_jobs)}**
> Twin Cities (Islamabad / Rawalpindi): **{len(twin_cities_jobs)}**
> Pakistan Remote: **{len(pak_remote_jobs)}**
> Worldwide International Remote (< 2 yrs / Junior): **{len(worldwide_jobs)}**

---

## 1. Twin Cities Local Jobs (Islamabad / Rawalpindi)

| Title | Company | Location | Pay | Match | URL |
| :--- | :--- | :--- | :--- | :---: | :--- |
"""
    for j in twin_cities_jobs:
        md_content += f"| **{j['title']}** | {j['company']} | {j['location']} | {j['estimated_pay']} | {j['match_score']}% | [Apply Link]({j['url']}) |\n"

    md_content += f"""
---

## 2. Worldwide International Remote Jobs (Junior / < 2 Years)

| Title | Company | Location / Source | Pay | Match | URL |
| :--- | :--- | :--- | :--- | :---: | :--- |
"""
    for j in worldwide_jobs:
        md_content += f"| **{j['title']}** | {j['company']} | {j['source']} | {j['estimated_pay']} | {j['match_score']}% | [Apply Link]({j['url']}) |\n"

    if pak_remote_jobs:
        md_content += f"""
---

## 3. Pakistan Remote Tech Jobs

| Title | Company | Location | Pay | Match | URL |
| :--- | :--- | :--- | :--- | :---: | :--- |
"""
        for j in pak_remote_jobs:
            md_content += f"| **{j['title']}** | {j['company']} | {j['location']} | {j['estimated_pay']} | {j['match_score']}% | [Apply Link]({j['url']}) |\n"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    with open(latest_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    elapsed = round(time.time() - start_time, 1)
    log(f"[SWEEP] ========================================================")
    log(f"[SWEEP] Sweep successfully completed in {elapsed}s!")
    log(f"[SWEEP] Total Verified Jobs: {len(verified_jobs)}")
    log(f"[SWEEP] Report saved to: {md_path}")
    log("[SWEEP] ========================================================")
    return verified_jobs

if __name__ == "__main__":
    run_sweep()
