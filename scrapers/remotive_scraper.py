import requests
import config
from log_manager import log

def get_remotive_jobs():
    """
    Fetches software development jobs from Remotive public API.
    Returns a list of standardized job dictionaries.
    """
    log("Scraping Remotive API for software development jobs...")
    url = "https://remotive.com/api/remote-jobs?category=software-dev"
    
    all_jobs = []
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            jobs = data.get("jobs", [])
            
            # Filter based on search keywords
            search_terms_lower = [t.lower() for t in config.SEARCH_TERMS]
            
            for job_data in jobs:
                title = str(job_data.get("title", ""))
                loc_req = str(job_data.get("candidate_required_location", "")).lower()
                
                # Pre-filter by location: skip if it's restricted to areas outside Pakistan/Worldwide
                # If location specifies things like "usa", "us only", "canada", "europe", "uk"
                # but doesn't mention "worldwide", "anywhere", or "pakistan", skip it.
                is_restricted = False
                restricted_keywords = ["us ", "us only", "usa", "canada", "europe", "uk only", "united kingdom", "germany", "latam"]
                
                # Check if it has a restricted location and DOES NOT contain anywhere/worldwide/pakistan
                has_restriction = any(rk in loc_req for rk in restricted_keywords)
                has_allowance = any(ak in loc_req for ak in ["worldwide", "anywhere", "pakistan", "global"])
                
                if has_restriction and not has_allowance:
                    is_restricted = True
                    
                if is_restricted:
                    continue
                
                # Check if the title matches any of our target terms
                # E.g. check if title contains words like "developer", "engineer", "programmer"
                # and doesn't contain "senior", "lead", "director", etc.
                title_lower = title.lower()
                
                # Target junior/entry/software terms
                keywords = ["ai", "python", "full stack", "react", "next", "node", "software", "developer", "engineer", "frontend", "backend", "web"]
                matches_kw = any(kw in title_lower for kw in keywords)
                
                if matches_kw:
                    job = {
                        "title": title,
                        "company": job_data.get("company_name", ""),
                        "url": job_data.get("url", ""),
                        "description": job_data.get("description", "No description available"),
                        "location": job_data.get("candidate_required_location", "Remote"),
                        "source": "Remotive"
                    }
                    if job["url"]:
                        all_jobs.append(job)
        else:
            log(f"  -> Remotive API returned status code: {response.status_code}")
    except Exception as e:
        log(f"  -> Error fetching from Remotive API: {e}")
        
    log(f"Remotive API fetching complete. Found {len(all_jobs)} jobs after initial filter.")
    return all_jobs

if __name__ == "__main__":
    jobs = get_remotive_jobs()
    print(f"Total jobs: {len(jobs)}")
    if jobs:
        print(f"Sample job: {jobs[0]}")
