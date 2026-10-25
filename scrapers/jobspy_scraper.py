import pandas as pd
import concurrent.futures
from jobspy import scrape_jobs
import config
from log_manager import log

def scrape_single_term(term):
    term_jobs = []
    
    hours_target = getattr(config, 'HOURS_OLD', 24)
    
    # 1. Scrape LinkedIn and Indeed Remote (Worldwide remote)
    log(f"  -> Scraping Remote Job Boards for '{term}' (past {hours_target}h)...")
    try:
        jobs_df = scrape_jobs(
            site_name=["linkedin", "indeed"],
            search_term=term,
            location="Remote",
            results_wanted=config.RESULTS_PER_TERM,
            hours_old=hours_target,
            is_remote=True
        )
        if jobs_df is not None and not jobs_df.empty:
            for _, row in jobs_df.iterrows():
                site_src = str(row.get("site", "JobSpy Remote"))
                job = {
                    "title": str(row.get("title", "")),
                    "company": str(row.get("company", "")),
                    "url": str(row.get("job_url", "")),
                    "description": str(row.get("description", "")) if pd.notna(row.get("description")) else "No description available",
                    "location": str(row.get("location", "Remote")),
                    "estimated_pay": str(row.get("min_amount", "")) + " - " + str(row.get("max_amount", "")) if pd.notna(row.get("min_amount")) else "Not Disclosed",
                    "source": f"JobSpy - {site_src.capitalize()}"
                }
                if job["url"] and job["url"] != "nan":
                    term_jobs.append(job)
    except Exception as e:
        log(f"  -> Error scraping Remote Job Boards for '{term}': {e}")
        
    # 2. Scrape Twin Cities Local (Islamabad & Rawalpindi, Pakistan - remote, onsite, hybrid)
    twin_cities = ["Islamabad, Pakistan", "Rawalpindi, Pakistan"]
    for city in twin_cities:
        try:
            jobs_df = scrape_jobs(
                site_name=["linkedin"],
                search_term=term,
                location=city,
                results_wanted=config.RESULTS_PER_TERM,
                hours_old=hours_target
            )
            if jobs_df is not None and not jobs_df.empty:
                for _, row in jobs_df.iterrows():
                    job = {
                        "title": str(row.get("title", "")),
                        "company": str(row.get("company", "")),
                        "url": str(row.get("job_url", "")),
                        "description": str(row.get("description", "")) if pd.notna(row.get("description")) else "No description available",
                        "location": str(row.get("location", city)),
                        "estimated_pay": "Not Disclosed",
                        "source": f"JobSpy - {city.split(',')[0]} Local"
                    }
                    if job["url"] and job["url"] != "nan":
                        term_jobs.append(job)
        except Exception as e:
            log(f"  -> Error scraping {city} for '{term}': {e}")

    return term_jobs

def get_jobspy_jobs():
    """
    Scrapes jobs using python-jobspy in parallel across all target search terms.
    Targets global remote roles and local remote/onsite/hybrid roles in Islamabad/Rawalpindi, Pakistan.
    Returns a list of standardized job dictionaries.
    """
    log(f"Scraping JobSpy in parallel across {len(config.SEARCH_TERMS)} search terms...")
    
    all_jobs = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(scrape_single_term, term) for term in config.SEARCH_TERMS]
        for future in concurrent.futures.as_completed(futures):
            try:
                jobs = future.result()
                if jobs:
                    all_jobs.extend(jobs)
            except Exception as e:
                log(f"  -> Exception scraping term in JobSpy: {e}")
            
    # Deduplicate by URL
    unique_jobs = {job["url"]: job for job in all_jobs if job["url"]}.values()
    all_jobs = list(unique_jobs)
    
    log(f"JobSpy parallel scraping complete. Found {len(all_jobs)} unique jobs.")
    return all_jobs

if __name__ == "__main__":
    jobs = get_jobspy_jobs()
    print(f"Total jobs found: {len(jobs)}")
    if jobs:
        print(f"Sample job: {jobs[0]}")
