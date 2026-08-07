import requests
import config
from log_manager import log

def get_himalayas_jobs():
    """
    Fetches jobs from Himalayas public REST API.
    Returns a list of standardized job dictionaries.
    """
    log(f"Scraping Himalayas API for {len(config.SEARCH_TERMS)} terms...")
    
    base_url = "https://himalayas.app/jobs/api"
    all_jobs = []
    
    try:
        # Himalayas API doesn't easily support arbitrary search terms via a single endpoint without pagination over all jobs
        # For this demo, we'll hit the main endpoint and filter.
        # Note: They have a /jobs endpoint that returns recent jobs.
        log("  -> Fetching jobs from Himalayas...")
        response = requests.get(f"{base_url}", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            jobs = data.get("jobs", [])
            
            # Filter jobs based on search terms
            # Convert terms to lower for easy matching
            search_terms_lower = [t.lower() for t in config.SEARCH_TERMS]
            
            for job_data in jobs:
                title = job_data.get("title", "")
                
                # Check if the title matches any of our terms
                # For a broader search, we check if any word from our terms is in the title
                # E.g. "AI", "Engineer", "Python", "React", "Full Stack"
                keywords = ["ai", "python", "full stack", "react", "next.js", "junior", "entry"]
                
                if any(kw in title.lower() for kw in keywords):
                    job = {
                        "title": title,
                        "company": job_data.get("companyName", ""),
                        "url": job_data.get("jobUrl", ""),
                        "description": job_data.get("description", "No description available"),
                        "location": job_data.get("location", "Remote"),
                        "source": "Himalayas"
                    }
                    
                    if job["url"]:
                        all_jobs.append(job)
                        
                        # Stop if we hit a generous limit to avoid taking too much time
                        if len(all_jobs) >= config.RESULTS_PER_TERM * len(config.SEARCH_TERMS):
                            break
                            
    except Exception as e:
        log(f"  -> Error fetching from Himalayas API: {e}")
        
    log(f"Himalayas API fetching complete. Found {len(all_jobs)} jobs.")
    return all_jobs

if __name__ == "__main__":
    jobs = get_himalayas_jobs()
    print(f"Sample job: {jobs[0] if jobs else 'No jobs found'}")
