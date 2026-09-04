import requests
from log_manager import log

def fetch_jobicy_jobs(count_limit=30):
    """
    Fetches remote software/AI engineering jobs from Jobicy public REST API.
    API endpoint: https://jobicy.com/api/v2/remote-jobs
    """
    jobs = []
    log("  -> Fetching Jobicy Remote Jobs API...")
    try:
        url = "https://jobicy.com/api/v2/remote-jobs?count=50&industry=dev"
        resp = requests.get(url, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            raw_jobs = data.get("jobs", [])
            for item in raw_jobs:
                title = item.get("jobTitle", "").strip()
                company = item.get("companyName", "").strip()
                job_url = item.get("url", "").strip()
                location = item.get("jobGeo", "Worldwide Remote").strip()
                desc = item.get("jobDescription", "") or item.get("jobExcerpt", "")
                pay = item.get("annualSalaryMin", "")
                pay_str = f"${pay} USD" if pay else "Not Disclosed"

                if title and job_url:
                    jobs.append({
                        "title": title,
                        "company": company or "Jobicy Partner",
                        "location": location or "Worldwide Remote",
                        "url": job_url,
                        "description": desc,
                        "estimated_pay": pay_str,
                        "source": "Jobicy API"
                    })
                if len(jobs) >= count_limit:
                    break
            log(f"Jobicy API fetching complete. Found {len(jobs)} jobs.")
        else:
            log(f"Jobicy API returned HTTP {resp.status_code}")
    except Exception as e:
        log(f"Error scraping Jobicy API: {e}")
    
    return jobs
