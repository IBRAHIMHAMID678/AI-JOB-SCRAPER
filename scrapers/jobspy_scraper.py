import pandas as pd
from jobspy import scrape_jobs
import config
from log_manager import log

def get_jobspy_jobs():
    """
    Scrapes jobs using python-jobspy for LinkedIn, Indeed, and ZipRecruiter.
    Returns a list of standardized job dictionaries.
    """
    log(f"Scraping JobSpy for {len(config.SEARCH_TERMS)} terms...")
    
    all_jobs = []
    
    for term in config.SEARCH_TERMS:
        log(f"  -> Scraping JobSpy for '{term}'...")
        try:
            jobs_df = scrape_jobs(
                site_name=["linkedin", "indeed", "zip_recruiter"],
                search_term=term,
                location="Remote",
                results_wanted=config.RESULTS_PER_TERM,
                hours_old=72, 
                country_alice="usa",
                is_remote=True
            )
            
            if jobs_df is not None and not jobs_df.empty:
                for _, row in jobs_df.iterrows():
                    # Normalize to our standard schema
                    job = {
                        "title": str(row.get("title", "")),
                        "company": str(row.get("company", "")),
                        "url": str(row.get("job_url", "")),
                        "description": str(row.get("description", "")) if pd.notna(row.get("description")) else "No description available",
                        "location": str(row.get("location", "Remote")),
                        "source": f"JobSpy - {str(row.get('site', 'Unknown'))}"
                    }
                    if job["url"] and job["url"] != "nan":
                        all_jobs.append(job)
        except Exception as e:
            log(f"  -> Error scraping JobSpy for '{term}': {e}")
            
    log(f"JobSpy scraping complete. Found {len(all_jobs)} jobs.")
    return all_jobs

if __name__ == "__main__":
    jobs = get_jobspy_jobs()
    print(f"Sample job: {jobs[0] if jobs else 'No jobs found'}")
