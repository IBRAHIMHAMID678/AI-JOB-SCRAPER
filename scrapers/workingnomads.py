import requests
from log_manager import log

def fetch_workingnomads_jobs(count_limit=30):
    """
    Fetches remote jobs from Working Nomads API.
    API endpoint: https://www.workingnomads.com/api/v1/jobs/
    """
    jobs = []
    log("  -> Fetching Working Nomads API...")
    try:
        url = "https://www.workingnomads.com/api/v1/jobs/"
        resp = requests.get(url, timeout=12)
        if resp.status_code == 200:
            raw_jobs = resp.json()
            for item in raw_jobs:
                category = str(item.get("category_name", "")).lower()
                if "development" not in category and "sysadmin" not in category:
                    continue
                
                title = item.get("title", "").strip()
                company = item.get("company_name", "").strip()
                job_url = item.get("url", "").strip()
                location = item.get("location", "Worldwide Remote").strip()
                desc = item.get("description", "")

                if title and job_url:
                    jobs.append({
                        "title": title,
                        "company": company or "Working Nomads Partner",
                        "location": location or "Worldwide Remote",
                        "url": job_url,
                        "description": desc,
                        "estimated_pay": "Not Disclosed",
                        "source": "Working Nomads API"
                    })
                if len(jobs) >= count_limit:
                    break
            log(f"Working Nomads API fetching complete. Found {len(jobs)} jobs.")
        else:
            log(f"Working Nomads API returned HTTP {resp.status_code}")
    except Exception as e:
        log(f"Error scraping Working Nomads API: {e}")
    
    return jobs
