import requests
from log_manager import log

def get_arbeitnow_jobs():
    """
    Fetches remote jobs from Arbeitnow Public Job Board API.
    Returns a list of standardized job dictionaries.
    """
    log("Scraping Arbeitnow API...")
    url = "https://www.arbeitnow.com/api/job-board-api"
    
    all_jobs = []
    try:
        response = requests.get(url, timeout=12)
        if response.status_code == 200:
            data = response.json()
            job_listings = data.get("data", [])
            
            for job_data in job_listings:
                title = str(job_data.get("title", ""))
                is_remote = job_data.get("remote", False)
                location = str(job_data.get("location", "Remote"))
                
                # We want remote-friendly jobs
                if not is_remote and "remote" not in location.lower():
                    continue
                    
                # Basic tech keyword filter to limit processing overhead
                title_lower = title.lower()
                tech_keywords = ["ai", "python", "full stack", "react", "next", "node", "software", "developer", "engineer", "frontend", "backend", "web", "fastapi", "django"]
                matches_kw = any(kw in title_lower for kw in tech_keywords)
                
                if matches_kw:
                    job = {
                        "title": title,
                        "company": job_data.get("company_name", "Unknown Company"),
                        "url": job_data.get("url", ""),
                        "description": job_data.get("description", "No description available"),
                        "location": location if location else "Remote",
                        "source": "Arbeitnow"
                    }
                    if job["url"]:
                        all_jobs.append(job)
        else:
            log(f"  -> Arbeitnow API returned status code: {response.status_code}")
    except Exception as e:
        log(f"  -> Error fetching from Arbeitnow API: {e}")
        
    # Deduplicate by URL
    unique_jobs = {job["url"]: job for job in all_jobs if job["url"]}.values()
    all_jobs = list(unique_jobs)
    
    log(f"Arbeitnow API fetching complete. Found {len(all_jobs)} jobs after initial filtering.")
    return all_jobs

if __name__ == "__main__":
    jobs = get_arbeitnow_jobs()
    print(f"Total jobs: {len(jobs)}")
    if jobs:
        print(f"Sample: {jobs[0]['title']} at {jobs[0]['company']}")
