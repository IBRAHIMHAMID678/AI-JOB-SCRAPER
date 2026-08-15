import requests
import xml.etree.ElementTree as ET
import re
from log_manager import log

def get_nodesk_python_jobs():
    """
    Fetches remote jobs from Python.org Jobs RSS and NoDesk RSS feeds.
    Returns a list of standardized job dictionaries.
    """
    log("Scraping Python.org and NoDesk RSS feeds...")
    sources_to_scrape = [
        {"name": "Python.org Jobs", "url": "https://www.python.org/jobs/feed/rss/"},
        {"name": "NoDesk Jobs", "url": "https://nodesk.co/index.xml"}
    ]
    
    all_jobs = []
    
    for src in sources_to_scrape:
        try:
            response = requests.get(src["url"], timeout=12)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                items = root.findall("./channel/item")
                
                for item in items:
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    desc_elem = item.find("description")
                    
                    raw_title = title_elem.text if title_elem is not None else ""
                    job_url = link_elem.text if link_elem is not None else ""
                    raw_desc = desc_elem.text if desc_elem is not None else ""
                    
                    company = "Remote Tech Employer"
                    title = raw_title
                    if " at " in raw_title:
                        parts = raw_title.split(" at ", 1)
                        title = parts[0].strip()
                        company = parts[1].strip()
                    elif " - " in raw_title:
                        parts = raw_title.split(" - ", 1)
                        company = parts[0].strip()
                        title = parts[1].strip()
                        
                    title_lower = title.lower()
                    tech_keywords = ["ai", "python", "full stack", "react", "next", "node", "software", "developer", "engineer", "frontend", "backend", "web", "fastapi", "django"]
                    if not any(kw in title_lower for kw in tech_keywords):
                        continue
                        
                    pay_match = re.search(r'\$\d{2,3}(?:,\d{3})*(?:\s*-\s*\$\d{2,3}(?:,\d{3})*)?(?:\s*/\s*hr|\s*per hour|\s*/\s*year|\s*/\s*yr)?', raw_desc, re.IGNORECASE)
                    estimated_pay = pay_match.group(0) if pay_match else "Not Disclosed"
                    
                    job = {
                        "title": title,
                        "company": company,
                        "url": job_url,
                        "description": raw_desc if raw_desc else "No description available",
                        "location": "Worldwide Remote",
                        "estimated_pay": estimated_pay,
                        "source": src["name"]
                    }
                    if job["url"]:
                        all_jobs.append(job)
        except Exception as e:
            log(f"  -> Error reading RSS feed for {src['name']} ({src['url']}): {e}")
            
    unique_jobs = {job["url"]: job for job in all_jobs if job["url"]}.values()
    all_jobs = list(unique_jobs)
    
    log(f"Python.org & NoDesk scraping complete. Found {len(all_jobs)} jobs.")
    return all_jobs

if __name__ == "__main__":
    jobs = get_nodesk_python_jobs()
    print(f"Total jobs: {len(jobs)}")
    if jobs:
        print(f"Sample: {jobs[0]['title']} at {jobs[0]['company']}")
