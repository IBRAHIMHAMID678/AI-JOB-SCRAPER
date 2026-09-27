import pandas as pd
from scrapers.jobspy_scraper import get_jobspy_jobs
from scrapers.himalayas_scraper import get_himalayas_jobs
from evaluator import evaluate_job_single as evaluate_job  # item 35: evaluate_job does not exist; evaluate_job_single updates the job dict in place and returns job/None

def main():
    print("Starting Remote Job Scraper & AI Matcher...")
    
    # 1. Extraction
    print("\n--- Phase 1: Data Extraction ---")
    jobspy_jobs = get_jobspy_jobs()
    himalayas_jobs = get_himalayas_jobs()
    
    all_raw_jobs = jobspy_jobs + himalayas_jobs
    print(f"Total raw jobs found: {len(all_raw_jobs)}")
    
    # Deduplicate by URL
    unique_jobs = {job["url"]: job for job in all_raw_jobs if job["url"]}.values()
    jobs_list = list(unique_jobs)
    print(f"Total unique jobs after deduplication: {len(jobs_list)}")
    
    if not jobs_list:
        print("No jobs found. Exiting.")
        return
        
    # 2. Evaluation
    print("\n--- Phase 2: AI Evaluation ---")
    evaluated_jobs = []
    
    for i, job in enumerate(jobs_list):
        print(f"Evaluating job {i+1}/{len(jobs_list)}: {job['title']} at {job['company']}")
        eval_result = evaluate_job(job)
        
        if eval_result:
            # Merge evaluation results into the job dictionary
            job.update(eval_result)
            evaluated_jobs.append(job)
            print(f"  -> Score: {job['match_score']}, Junior Friendly: {job['is_junior_friendly']}")
            
    # 3. Filtering and Exporting
    print("\n--- Phase 3: Filtering and Export ---")
    if not evaluated_jobs:
        print("No jobs were successfully evaluated. Exiting.")
        return
        
    # Filter for match_score >= 50
    high_match_jobs = [job for job in evaluated_jobs if job.get('match_score', 0) >= 50]
    print(f"Found {len(high_match_jobs)} jobs with a match score >= 50.")
    
    if not high_match_jobs:
        print("No high match jobs found.")
        return
        
    # Convert to DataFrame, sort by score descending
    df = pd.DataFrame(high_match_jobs)
    df = df.sort_values(by="match_score", ascending=False)
    
    # Export to CSV
    output_file = "remote_junior_jobs.csv"
    df.to_csv(output_file, index=False)
    print(f"Success! Exported {len(df)} matching jobs to {output_file}")

if __name__ == "__main__":
    main()
