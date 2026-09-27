import requests
import xml.etree.ElementTree as ET
import re
from log_manager import log

def _repair_xml(content):
    """Best-effort repair for feeds with unescaped '&' (e.g. nodesk.co/index.xml)."""
    text = content.decode("utf-8", errors="replace")
    text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)", "&amp;", text)
    return text.encode("utf-8")


def _split_title_company(raw_title):
    """
    Split an RSS item title into (title, company).
    Real Python.org format is "Title, Company" (e.g. 'Django Developer,
    The Developer Society'). Do NOT swap on " - " — titles like
    "Senior Backend Engineer - Remote" are not "Company - Title".
    """
    title = (raw_title or "").strip()
    company = "Remote Tech Employer"
    if ", " in title:
        # "Title, Company" — split on the LAST comma so titles containing
        # commas (e.g. "Engineer, Backend, Acme") keep working.
        title_part, company_part = title.rsplit(", ", 1)
        if title_part.strip() and company_part.strip():
            title, company = title_part.strip(), company_part.strip()
    elif " at " in title:
        parts = title.split(" at ", 1)
        title, company = parts[0].strip(), parts[1].strip() or company
    return title, company


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
                try:
                    root = ET.fromstring(response.content)
                except ET.ParseError:
                    # Fallback for malformed feeds (e.g. nodesk.co/index.xml
                    # has unescaped '&'); repair and retry before giving up.
                    log(f"  -> Strict XML parse failed for {src['name']}; trying repaired parse")
                    root = ET.fromstring(_repair_xml(response.content))
                items = root.findall("./channel/item")
                
                for item in items:
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    desc_elem = item.find("description")
                    
                    raw_title = title_elem.text if title_elem is not None else ""
                    job_url = link_elem.text if link_elem is not None else ""
                    raw_desc = desc_elem.text if desc_elem is not None else ""
                    
                    title, company = _split_title_company(raw_title)
                        
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
