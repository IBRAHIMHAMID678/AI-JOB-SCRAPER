import time
import re
from log_manager import log, emit_job
import concurrent.futures

def evaluate_job_single(job):
    """
    Evaluates a job locally using a deterministic keyword matcher based on the user's resume.
    Avoids all API limits, credits, and network errors.
    """
    try:
        title = str(job.get('title', '')).lower()
        desc = str(job.get('description', '')).lower()
        full_text = f"{title} {desc}"
        
        score = 0
        match_reasons = []
        
        # 1. Core Skills (Max 50 points)
        core_skills = {
            'python': 15,
            'react': 10,
            'next.js': 10,
            'node': 10,
            'node.js': 10,
            'fastapi': 10,
            'typescript': 5,
            'javascript': 5,
            'django': 5,
            'postgresql': 5,
            'mongodb': 5
        }
        
        core_score = 0
        found_core = []
        for skill, points in core_skills.items():
            if re.search(r'\b' + re.escape(skill) + r'\b', full_text):
                core_score += points
                found_core.append(skill)
        
        if core_score > 50:
            core_score = 50
            
        score += core_score
        if found_core:
            match_reasons.append(f"Core skills: {', '.join(found_core)}")

        # 2. AI / Data Skills (Max 30 points)
        ai_skills = {
            'ai': 10,
            'machine learning': 10,
            'langchain': 15,
            'rag': 15,
            'llm': 10,
            'artificial intelligence': 10,
            'data science': 5
        }
        
        ai_score = 0
        found_ai = []
        for skill, points in ai_skills.items():
            if re.search(r'\b' + re.escape(skill) + r'\b', full_text):
                ai_score += points
                found_ai.append(skill)
                
        if ai_score > 30:
            ai_score = 30
            
        score += ai_score
        if found_ai:
            match_reasons.append(f"AI skills: {', '.join(found_ai)}")

        # 3. Junior / Entry Level Fit (Max 20 points)
        junior_keywords = ['junior', 'entry level', '0-2 years', 'graduate', 'intern', 'associate']
        is_junior_friendly = False
        for kw in junior_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', full_text):
                is_junior_friendly = True
                score += 20
                match_reasons.append(f"Level fit: {kw}")
                break
                
        # Look for explicit senior requirements to penalize
        senior_keywords = ['senior', 'staff', 'lead', 'principal', '5+ years', '7+ years', '10+ years']
        for kw in senior_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', title):
                score -= 30 # Heavy penalty if title says senior
                match_reasons.append(f"Senior level title ({kw})")
                break
            elif re.search(r'\b' + re.escape(kw) + r'\b', desc):
                score -= 10
                match_reasons.append(f"Senior requirements mentioned")
                break

        # Ensure score stays in bounds
        if score < 0: score = 0
        if score > 100: score = 100
        
        # Estimate Pay extraction (naive regex approach)
        pay_match = re.search(r'\$\d{2,3}[kK]?(?:\s*-\s*\$\d{2,3}[kK]?)?', desc)
        estimated_pay = pay_match.group(0) if pay_match else "Not Disclosed"
        
        reason = " | ".join(match_reasons) if match_reasons else "No specific keyword matches."
        
        job_result = {
            "match_score": score,
            "is_junior_friendly": is_junior_friendly,
            "estimated_pay": estimated_pay,
            "match_reason": reason
        }
        
        # Merge result into job
        job.update(job_result)
        
        if score >= 50:
            log(f"  -> High match found: {job.get('title')} ({score}/100)")
            emit_job(job) # Send to frontend table
            
        return job
        
    except Exception as e:
        log(f"Error evaluating job '{job.get('title')}': {e}")
        return None

def evaluate_jobs_parallel(jobs):
    log(f"Starting local evaluation of {len(jobs)} jobs...")
    evaluated_jobs = []
    
    # Local evaluation is instantaneous, no need for throttling
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_job = {executor.submit(evaluate_job_single, job): job for job in jobs}
        for i, future in enumerate(concurrent.futures.as_completed(future_to_job)):
            job = future_to_job[future]
            try:
                res = future.result()
                if res:
                    evaluated_jobs.append(res)
            except Exception as exc:
                log(f"Job {job.get('title')} generated an exception: {exc}")
                
    return evaluated_jobs
