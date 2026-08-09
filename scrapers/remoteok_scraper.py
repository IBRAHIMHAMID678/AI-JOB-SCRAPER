import requests
import config
from log_manager import log

def get_remoteok_jobs():
    """
    Fetches remote jobs from Remote OK public API.
    Returns a list of standardized job dictionaries.
    """
    log("Scraping Remote OK API...")
    url = "https://remoteok.com/api"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    all_jobs = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            
            # Skip the first element if it's metadata (doesn't contain position/job details)
            if data and isinstance(data, list):
                job_listings = data[1:] if len(data) > 1 else []
                
                for job_data in job_listings:
                    title = str(job_data.get("position", ""))
                    loc_req = str(job_data.get("location", "")).lower()
                    
                    # Pre-filter by location: skip if it's restricted to areas outside Pakistan/Worldwide
                    is_restricted = False
                    restricted_keywords = ["us ", "us only", "usa", "canada", "europe", "uk only", "united kingdom", "germany", "latam"]
                    
                    has_restriction = any(rk in loc_req for rk in restricted_keywords)
                    has_allowance = any(ak in loc_req for ak in ["worldwide", "anywhere", "pakistan", "global"])
                    
                    if has_restriction and not has_allowance:
                        is_restricted = True
                        
                    if is_restricted:
                        continue
                    
                    # Filter by tech keywords
                    title_lower = title.lower()
                    keywords = ["ai", "python", "full stack", "react", "next", "node", "software", "developer", "engineer", "frontend", "backend", "web"]
                    matches_kw = any(kw in title_lower for kw in keywords)
                    
                    if matches_kw:
                        # Use apply_url or url
                        job_url = job_data.get("apply_url") or job_data.get("url")
                        if job_url and not job_url.startswith("http"):
                            # Normalize URL
                            if job_url.startswith("/"):
                                job_url = "https://remoteok.com" + job_url
                            else:
                                job_url = "https://remoteok.com/" + job_url
                                
                        job = {
                            "title": title,
                            "company": job_data.get("company", ""),
                            "url": job_url,
                            "description": job_data.get("description", "No description available"),
                            "location": job_data.get("location", "Remote"),
                            "source": "Remote OK"
                        }
                        if job["url"]:
                            all_jobs.append(job)
        else:
            log(f"  -> Remote OK API returned status code: {response.status_code}")
    except Exception as e:
        log(f"  -> Error fetching from Remote OK API: {e}")
        
    log(f"Remote OK API fetching complete. Found {len(all_jobs)} jobs after initial filter.")
    return all_jobs

if __name__ == "__main__":
    jobs = get_remoteok_jobs()
    print(f"Total jobs: {len(jobs)}")
    if jobs:
        print(f"Sample job: {jobs[0]}")
