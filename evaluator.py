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

# Item 31: code version baked into the cache key so eval_cache.json can never
# re-emit scores computed by older (buggy) filter logic.
_EVAL_CODE_VERSION = "2"

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
    # Item 31: include a description content hash so description edits
    # (added US-only restriction, removed pay) invalidate the cache entry.
    desc_hash = hashlib.md5(str(job.get('description', ''))[:2000].encode('utf-8')).hexdigest()[:16]
    raw = f"v{_EVAL_CODE_VERSION}:{url}:{title}:{company}:{desc_hash}"
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
        r'\b(north\s+america\s+only|us/canada\s+only)\b',
        # Item 21 parity: bare-US remote scopes ("Remote, US" / "Remote - US")
        r'\bremote[\s,\-–(]*us\b',
        r'\bremote[\s,\-–(]*usa\b',
        r'\b(us|usa)\s+only\b',
    ]
    
    for pattern in us_restriction_patterns:
        if re.search(pattern, loc) or re.search(pattern, desc):
            return True
            
    state_match = re.search(r'\b(al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|ia|ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy)\b', loc)
    if state_match and "remote" not in loc and "worldwide" not in loc:
        token = state_match.group(1).lower()
        # Item 22: "in" is the English word ("Developer in Dubai") and ca/de/pa/in/md/al/ar/...
        # are ISO country codes ("Toronto, CA", "Berlin, DE", "Mumbai, IN") — require
        # corroborating US context before treating as a US state.
        _iso_collisions = {"al", "ar", "ca", "co", "de", "ga", "id", "il", "in", "ky", "la",
                           "md", "me", "mo", "ms", "mt", "ne", "pa", "sc", "sd", "tn", "va"}
        _us_hints = ("usa", "u.s.", "united states", "america")
        if token in _iso_collisions and not any(h in loc or h in desc for h in _us_hints):
            pass  # ambiguous — not treated as US-only
        else:
            return True
        
    return False

def evaluate_job_local(job):
    """
    Upgraded Smart Local Evaluator running deterministically with weighted CV skill scoring,
    UK & Worldwide Remote location verification, 2-skill minimum gate, and 40% auto-approve threshold.
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
        # Item 25: AI title variants — "ML Engineer" etc. must score like "AI Engineer"
        if any(term in title for term in [
            "ai engineer", "ai developer", "ai full stack", "llm engineer", "rag engineer",
            "ml engineer", "machine learning engineer", "generative ai engineer", "genai",
            "ai/ml engineer", "nlp engineer", "prompt engineer",
        ]):
            score += 40
            match_reasons.append("Primary Title Fit (AI / LLM)")
        elif any(term in title for term in [
            "full stack", "python developer", "fastapi", "django developer", "backend",
        ]):
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
        # Item 40: approved range is 1-3 years (was stale "0-2 years")
        junior_keywords = ['junior', 'entry level', '1-3 years', '1-3 yrs', '0-3 years', 'graduate', 'associate', 'intern', 'entry']
        is_junior_friendly = False
        if any(kw in full_text for kw in junior_keywords):
            is_junior_friendly = True
            score += 15
            match_reasons.append("Junior Level Fit")
        else:
            is_junior_friendly = True
            score += 10
            
        # 5. Pay Rate Detection (USD / GBP)
        # Item 28: enforce the $10-40/hr ground-truth band; detect PKR/month.
        usd_hourly_match = re.search(r'[\$\£]\s*(\d{2,3}(?:\.\d{2})?)\s*(?:-\s*[\$\£]\s*(\d{2,3}(?:\.\d{2})?))?\s*(?:/\s*hr|\s*per hour|\s*/\s*hour|\s*hourly|\s*/\s*h\b)', desc, re.IGNORECASE)
        usd_salary_match = re.search(r'[\$\£]\d{2,3}[kK](?:\s*-\s*[\$\£]\d{2,3}[kK])?', desc) or re.search(r'[\$\£]\d{2,3},\d{3}', desc)
        pkr_month_match = re.search(r'(?:pkr|rs\.?|₨)\s*\d[\d,]*(?:\s*(?:-|to|–)\s*(?:pkr|rs\.?)?\s*\d[\d,]*)?\s*(?:/\s*mo|per\s+month|monthly)', desc, re.IGNORECASE)

        estimated_pay = "Not Disclosed"
        if usd_hourly_match:
            estimated_pay = usd_hourly_match.group(0).strip() + " Hourly"
            try:
                rate = float(usd_hourly_match.group(1))
            except (ValueError, TypeError):
                rate = 0
            if 10 <= rate <= 40:
                score += 10
                match_reasons.append(f"Pay in $10-40/hr band: {estimated_pay}")
            else:
                score += 2
                match_reasons.append(f"Pay outside $10-40/hr band: {estimated_pay} (no full pay points)")
        elif pkr_month_match:
            estimated_pay = pkr_month_match.group(0).strip() + " PKR/month"
            score += 4
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
        # Item 34: dead-letter record instead of silently returning score 0
        try:
            _write_dead_letter(
                str(job.get('url') or job.get('title') or 'unknown'),
                stage="evaluator:evaluate_job_local",
                error=e,
                extra={"title": job.get('title'), "company": job.get('company')},
            )
        except Exception:
            pass
        log(f"Error in local evaluation: {e}")
        return {
            "match_score": 0,
            "is_junior_friendly": False,
            "is_pakistan_eligible": False,
            "estimated_pay": "Not Disclosed",
            "match_reason": f"Evaluation error: {e}"
        }


def _write_dead_letter(job_id, stage, error, extra=None):
    """Item 34: durable dead-letter record (evaluator.py is standalone; no jobpilot import)."""
    try:
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "job_id": str(job_id or "unknown"),
            "stage": stage,
            "error": str(error)[:2000],
        }
        if extra:
            record["extra"] = extra
        with open(os.path.join(BASE_DIR, "dead_letter.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass

def evaluate_job_single(job):
    """
    Fast evaluation engine with strict 40% auto-approve threshold, pre-filtering,
    and deduplication. Pre-filters ALWAYS run before the cache lookup (item 31):
    a cache hit must never bypass senior/non-tech/US/experience filters.
    """
    # Item 35: sync to 40 per ground-truth auto-approve (was 60)
    AUTO_APPROVE_THRESHOLD = 40
    title = str(job.get('title', ''))
    company = str(job.get('company', ''))
    desc = clean_html_text(job.get('description', ''))
    loc = str(job.get('location', 'Remote'))
    source = str(job.get('source', 'Unknown'))

    job_hash = get_job_hash(job)
    job["job_hash"] = job_hash

    # 1. Senior / Non-tech / US-restriction / Experience Pre-Filtering (before cache)
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

    # Item 27: upper-bound experience exclusion — reject 4+ year roles per the 1-3 rule.
    # Allows intervening words: "5 years of hands-on experience building APIs".
    _exp_upper = None
    for _pat in (
        r"(\d+)\s*(?:years?|yrs?)\s+of\s+[\w\s-]{0,30}?(?:experience|exp)",
        r"(\d+)\s*[-–+]\s*(?:\d+\s*)?(?:years?|yrs?)",
        r"(?:minimum|min|at\s+least|requires?|requirement|seeking)\s*(\d+)\s*(?:years?|yrs?)",
    ):
        _m = re.search(_pat, desc, re.IGNORECASE)
        if _m:
            _exp_upper = int(_m.group(1))
            break
    if _exp_upper is not None and _exp_upper >= 4:
        log(f"  -> Skipping role requiring {_exp_upper} years (exceeds 1-3 yr range): {title} at {company}")
        return None

    # 2. Check Disk Cache (pre-filters already applied; key includes content hash + code version)
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
