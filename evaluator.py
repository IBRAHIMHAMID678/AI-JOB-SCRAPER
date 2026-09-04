import os
import re
import time
import json
import hashlib
import threading
import concurrent.futures
from groq import Groq
import requests
import config
from log_manager import log, emit_job, emit_pending_job

# Concurrency semaphore for API calls
api_semaphore = threading.Semaphore(5)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Global Evaluation Cache with Re-entrant Lock to prevent deadlocks
EVAL_CACHE = {}
cache_lock = threading.RLock()

def get_cache_filepath():
    cache_name = getattr(config, 'EVAL_CACHE_FILE', 'eval_cache.json')
    return os.path.join(BASE_DIR, cache_name)

def load_eval_cache():
    global EVAL_CACHE
    cache_file = get_cache_filepath()
    if os.path.exists(cache_file):
        try:
            with cache_lock:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    EVAL_CACHE = json.load(f)
            log(f"Loaded {len(EVAL_CACHE)} cached job evaluations from {cache_file}.")
        except Exception as e:
            log(f"Could not load evaluation cache: {e}")
            EVAL_CACHE = {}

def save_eval_cache():
    cache_file = get_cache_filepath()
    try:
        with cache_lock:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(EVAL_CACHE, f, indent=2)
    except Exception as e:
        log(f"Could not save evaluation cache: {e}")

def clear_all_scraped_data():
    global EVAL_CACHE
    try:
        with cache_lock:
            EVAL_CACHE = {}
            save_eval_cache()
        from database import delete_all_jobs_from_db
        delete_all_jobs_from_db()
        log("[EVALUATOR] All scraped data and evaluation caches cleared successfully.")
        return True
    except Exception as e:
        log(f"[EVALUATOR] Error clearing scraped data: {e}")
        return False

def clean_html_text(raw_text):
    if not raw_text:
        return ""
    # Strip HTML tags
    clean = re.sub(r'<[^>]+>', ' ', str(raw_text))
    # Replace multiple whitespaces/newlines
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def get_job_hash(job):
    url = str(job.get('url', '')).strip()
    title = str(job.get('title', '')).strip()
    company = str(job.get('company', '')).strip()
    raw = f"{url}:{title}:{company}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()

load_eval_cache()

def is_us_only_restricted(job):
    """
    Checks if a job is strictly restricted to US candidates and does not allow worldwide remote work.
    """
    title = str(job.get('title', '')).lower()
    desc = str(job.get('description', '')).lower()
    loc = str(job.get('location', 'Remote')).lower()
    source = str(job.get('source', '')).lower()
    
    if any(x in loc for x in ["pakistan", "islamabad", "rawalpindi"]):
        return False
        
    allowance_keywords = ["worldwide", "anywhere", "pakistan", "global remote", "work from anywhere", "work from home anywhere", "any country", "everywhere"]
    if any(ak in loc or ak in desc for ak in allowance_keywords):
        return False
        
    us_restriction_patterns = [
        r'\b(us|usa)\s*(-only|only)\b',
        r'\b(us|usa)\s+(citizens?|citizenship|residents?|residency|based\s+only)\b',
        r'\b(must\s+reside\s+in\s+the\s+us|must\s+be\s+located\s+in\s+the\s+us|authorized\s+to\s+work\s+in\s+the\s+us)\b',
        r'\b(us\s+work\s+authorization|us\s+citizenship\s+required)\b',
        r'\b(north\s+america\s+only|us/canada\s+only)\b'
    ]
    
    for pattern in us_restriction_patterns:
        if re.search(pattern, loc) or re.search(pattern, desc):
            return True
            
    state_match = re.search(r'\b(al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy)\b', loc)
    if state_match and "remote" not in loc and "worldwide" not in loc:
        return True
        
    return False

def evaluate_job_local(job):
    """
    Upgraded Smart Local Evaluator running deterministically with weighted CV skill scoring,
    UK & Worldwide Remote location verification, 2-skill minimum gate, and 60% threshold.
    """
    try:
        title = str(job.get('title', '')).lower()
        desc = clean_html_text(job.get('description', '')).lower()
        loc = str(job.get('location', '')).lower()
        full_text = f"{title} {desc}"
        
        score = 0
        match_reasons = []
        
        # 1. Seniority Check (Hard exclusion if senior title)
        senior_keywords = ['senior', 'lead', 'staff', 'principal', 'director', 'vp', 'head', 'architect', 'manager', 'sr.', 'sr ', 'iii', 'iv', 'v']
        if any(re.search(r'\b' + re.escape(kw) + r'\b', title) for kw in senior_keywords):
            return {
                "match_score": 0,
                "is_junior_friendly": False,
                "is_pakistan_eligible": False,
                "estimated_pay": "Not Disclosed",
                "match_reason": "Skipped: Senior/Lead role."
            }

        # 2. Title Fit Scoring (Max 40 points)
        if any(term in title for term in ["ai engineer", "ai developer", "ai full stack", "llm engineer", "rag engineer"]):
            score += 40
            match_reasons.append("Primary Title Fit (AI / LLM)")
        elif any(term in title for term in ["full stack", "python developer", "fastapi", "backend"]):
            score += 35
            match_reasons.append("Core Stack Developer Fit")
        elif any(term in title for term in ["software engineer", "developer", "react", "web", "node"]):
            score += 25
            match_reasons.append("General Software Engineer Role")
            
        # 3. Core Skills Verification (Minimum 2 matching skills required for > 50%)
        skills = {
            'python': 10,
            'fastapi': 10,
            'react': 8,
            'next.js': 8,
            'node': 6,
            'node.js': 6,
            'nestjs': 6,
            'langchain': 10,
            'rag': 10,
            'mongodb': 5,
            'llm': 10,
            'typescript': 5,
            'django': 7,
            'flask': 7
        }
        
        found_skills = []
        skill_score = 0
        for skill, pts in skills.items():
            if re.search(r'\b' + re.escape(skill) + r'\b', full_text):
                skill_score += pts
                if skill not in found_skills:
                    found_skills.append(skill)
                    
        score += min(skill_score, 40)
        if found_skills:
            match_reasons.append(f"Skills ({len(found_skills)}): {', '.join(found_skills[:5])}")

        # Gate Rule: If fewer than 2 core skills matched, cap score at 45%
        if len(found_skills) < 2:
            score = min(score, 45)
            match_reasons.append("Capped: Fewer than 2 core skills matched")

        # 4. Experience Fit
        junior_keywords = ['junior', 'entry level', '0-2 years', 'graduate', 'associate', 'intern', 'entry']
        is_junior_friendly = False
        if any(kw in full_text for kw in junior_keywords):
            is_junior_friendly = True
            score += 15
            match_reasons.append("Junior Level Fit")
        else:
            is_junior_friendly = True
            score += 10
            
        # 5. Pay Rate Detection (USD / GBP)
        usd_hourly_match = re.search(r'[\$\£]\d{2,3}(?:\.\d{2})?\s*(?:-\s*[\$\£]\d{2,3}(?:\.\d{2})?)?\s*(?:/\s*hr|\s*per hour|\s*/\s*hour|\s*hourly|\s*/\s*h\b)', desc, re.IGNORECASE)
        usd_salary_match = re.search(r'[\$\£]\d{2,3}[kK](?:\s*-\s*[\$\£]\d{2,3}[kK])?', desc) or re.search(r'[\$\£]\d{2,3},\d{3}', desc)
        
        estimated_pay = "Not Disclosed"
        if usd_hourly_match:
            estimated_pay = usd_hourly_match.group(0) + " Hourly"
            score += 10
            match_reasons.append(f"Pay: {estimated_pay}")
        elif usd_salary_match:
            estimated_pay = usd_salary_match.group(0) + " Salary"
            score += 5
            match_reasons.append(f"Pay: {estimated_pay}")
        elif job.get('estimated_pay') and job.get('estimated_pay') != "Not Disclosed":
            estimated_pay = job.get('estimated_pay')

        # 6. Location Eligibility Check
        is_pakistan_eligible = True
        if is_us_only_restricted(job):
            is_pakistan_eligible = False

        reason = " | ".join(match_reasons) if match_reasons else "Strict local evaluator matching."
        if not is_pakistan_eligible:
            reason += " (Location restriction detected)"
            
        return {
            "match_score": min(score, 100),
            "is_junior_friendly": is_junior_friendly,
            "is_pakistan_eligible": is_pakistan_eligible,
            "estimated_pay": estimated_pay,
            "match_reason": f"[Strict Match] {reason}"
        }
    except Exception as e:
        log(f"Error in local evaluation: {e}")
        return {
            "match_score": 0,
            "is_junior_friendly": False,
            "is_pakistan_eligible": False,
            "estimated_pay": "Not Disclosed",
            "match_reason": f"Evaluation error: {e}"
        }

def evaluate_job_single(job):
    """
    Fast evaluation engine with strict 60% threshold, pre-filtering, and deduplication.
    """
    AUTO_APPROVE_THRESHOLD = 60
    title = str(job.get('title', ''))
    company = str(job.get('company', ''))
    desc = clean_html_text(job.get('description', ''))
    loc = str(job.get('location', 'Remote'))
    source = str(job.get('source', 'Unknown'))
    
    # 1. Check Disk Cache
    job_hash = get_job_hash(job)
    job["job_hash"] = job_hash
    with cache_lock:
        if job_hash in EVAL_CACHE:
            cached_res = EVAL_CACHE[job_hash]
            job.update(cached_res)
            if job.get("requires_manual_verification", False):
                emit_pending_job(job)
            elif job.get("match_score", 0) >= AUTO_APPROVE_THRESHOLD and job.get("is_pakistan_eligible", False):
                log(f"  -> Matched Job (Cache): {title} ({job['match_score']}%) at {company}")
                emit_job(job)
            return job

    # 2. Senior / Non-tech Pre-Filtering
    title_lower = title.lower()
    senior_keywords = ['senior', 'lead', 'staff', 'principal', 'director', 'vp', 'head', 'architect', 'manager', 'sr.', 'sr ', 'iii', 'iv', 'v']
    for kw in senior_keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', title_lower):
            log(f"  -> Skipping senior role: {title} at {company}")
            return None
            
    tech_keywords = ["ai", "python", "react", "next", "node", "software", "developer", "engineer", "programmer", "frontend", "backend", "web", "data", "tech", "fastapi", "django", "flask"]
    if not any(kw in title_lower for kw in tech_keywords):
        log(f"  -> Skipping non-tech role: {title} at {company}")
        return None
        
    if is_us_only_restricted(job):
        log(f"  -> Skipping US-restricted remote job: {title} at {company} (Location: {loc})")
        return None

    # 3. High-Speed Smart Evaluator
    eval_result = evaluate_job_local(job)
    if eval_result["match_score"] < 40:
        log(f"  -> Skipping low match role: {title} at {company} (Score: {eval_result['match_score']}/100)")
        return None

    # Determine auto-approval: Score >= 60% and Location Eligible
    if eval_result["match_score"] >= AUTO_APPROVE_THRESHOLD and eval_result["is_pakistan_eligible"]:
        eval_result["requires_manual_verification"] = False
    else:
        eval_result["requires_manual_verification"] = True

    job.update(eval_result)
    
    # Save to disk cache safely
    with cache_lock:
        EVAL_CACHE[job_hash] = eval_result
    save_eval_cache()

    # Emit to frontend
    if not job.get("requires_manual_verification", False) and job.get("match_score", 0) >= AUTO_APPROVE_THRESHOLD and job.get("is_pakistan_eligible", False):
        log(f"  -> [MATCH] Auto-Approved (Score {job['match_score']}%): {title} at {company}")
        emit_job(job)
    elif job.get("requires_manual_verification", False):
        log(f"  -> Borderline Job (Pending Verification): {title} at {company}")
        emit_pending_job(job)
        
    return job

def evaluate_jobs_parallel(jobs):
    log(f"Starting parallel evaluation of {len(jobs)} jobs...")
    evaluated_jobs = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_job = {executor.submit(evaluate_job_single, job): job for job in jobs}
        for future in concurrent.futures.as_completed(future_to_job):
            job = future_to_job[future]
            try:
                res = future.result()
                if res:
                    evaluated_jobs.append(res)
            except Exception as exc:
                log(f"Job {job.get('title')} generated an exception during evaluation: {exc}")
                
    return evaluated_jobs
