import requests
import config
from log_manager import log

def get_himalayas_jobs():
    """
    Fetches remote jobs from Himalayas search endpoint (worldwide friendly).
    Returns a list of standardized job dictionaries.
    """
    log("Scraping Himalayas API for worldwide-friendly jobs...")
    base_url = "https://himalayas.app/jobs/api/search"
    
    all_jobs = []
    
    # We will search Himalayas using a few keywords to get a broad list of candidates
    keywords_to_search = ["python", "react", "full stack", "software", "node"]
    
    for kw in keywords_to_search:
        log(f"  -> Fetching Himalayas for '{kw}'...")
        params = {
            "q": kw,
            "worldwide": "true",
            "limit": 20
        }
        
        try:
            response = requests.get(base_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                jobs = data.get("jobs", [])
                
                for job_data in jobs:
                    title = job_data.get("title", "")
                    
                    # Normalize location restrictions to string
                    loc_restrictions = job_data.get("locationRestrictions", [])
                    
                    # If locationRestrictions has entries, check if Pakistan is allowed.
                    # Since we requested worldwide=true, most will have empty restrictions, meaning anywhere.
                    if loc_restrictions:
                        loc_restrictions_lower = [str(loc).lower() for loc in loc_restrictions]
                        if not any(x in loc_restrictions_lower for x in ["pakistan", "worldwide", "anywhere"]):
                            # Pakistan is not explicitly allowed in restricted list, skip
                            continue
                            
                    location_str = ", ".join(loc_restrictions) if loc_restrictions else "Worldwide / Remote"
                    
                    job = {
                        "title": title,
                        "company": job_data.get("companyName", ""),
                        "url": job_data.get("applicationLink", ""),
                        "description": job_data.get("description", "No description available"),
                        "location": location_str,
                        "source": "Himalayas"
                    }
                    
                    if job["url"]:
                        all_jobs.append(job)
                        
            else:
                log(f"  -> Himalayas API returned status: {response.status_code} for keyword '{kw}'")
        except Exception as e:
            log(f"  -> Error fetching from Himalayas API for '{kw}': {e}")
            
    # Deduplicate by URL
    unique_jobs = {job["url"]: job for job in all_jobs if job["url"]}.values()
    all_jobs = list(unique_jobs)
    
    log(f"Himalayas API fetching complete. Found {len(all_jobs)} unique jobs.")
    return all_jobs

if __name__ == "__main__":
    jobs = get_himalayas_jobs()
    print(f"Total jobs: {len(jobs)}")
    if jobs:
        print(f"Sample job: {jobs[0]}")
