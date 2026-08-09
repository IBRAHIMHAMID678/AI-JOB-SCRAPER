import requests
from log_manager import log

def get_themuse_jobs():
    """
    Fetches remote jobs from The Muse Public API.
    Returns a list of standardized job dictionaries.
    """
    log("Scraping The Muse API for remote Software Engineering jobs...")
    base_url = "https://www.themuse.com/api/public/jobs"
    
    all_jobs = []
    
    # We will fetch the first 2 pages to get a good batch of active jobs
    for page in range(2):
        log(f"  -> Fetching The Muse API page {page}...")
        params = {
            "category": "Software Engineering",
            "location": "Flexible / Remote",
            "page": page,
            "descending": "true"
        }
        
        try:
            response = requests.get(base_url, params=params, timeout=12)
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                
                for job_data in results:
                    title = job_data.get("name", "")
                    
                    # Extract location names
                    locations = job_data.get("locations", [])
                    location_names = [loc.get("name", "") for loc in locations]
                    location_str = ", ".join(location_names) if location_names else "Flexible / Remote"
                    
                    # Get company details
                    company_name = job_data.get("company", {}).get("name", "Unknown Company")
                    
                    # Get direct landing page URL
                    job_url = job_data.get("refs", {}).get("landing_page", "")
                    
                    # Standardize job dict
                    job = {
                        "title": title,
                        "company": company_name,
                        "url": job_url,
                        "description": job_data.get("contents", "No description available"),
                        "location": location_str,
                        "source": "The Muse"
                    }
                    
                    if job["url"]:
                        all_jobs.append(job)
            else:
                log(f"  -> The Muse API returned status: {response.status_code} on page {page}")
        except Exception as e:
            log(f"  -> Error fetching from The Muse API on page {page}: {e}")
            
    # Deduplicate by URL
    unique_jobs = {job["url"]: job for job in all_jobs if job["url"]}.values()
    all_jobs = list(unique_jobs)
    
    log(f"The Muse API fetching complete. Found {len(all_jobs)} unique jobs.")
    return all_jobs

if __name__ == "__main__":
    jobs = get_themuse_jobs()
    print(f"Total jobs: {len(jobs)}")
    if jobs:
        print(f"Sample job: {jobs[0]['title']} at {jobs[0]['company']}")
