import os
import json
import asyncio
import pandas as pd
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from scrapers.jobspy_scraper import get_jobspy_jobs
from scrapers.himalayas_scraper import get_himalayas_jobs
from evaluator import evaluate_jobs_parallel
from log_manager import log_queue, job_queue, log

app = FastAPI()

# Mount static files for the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

global_evaluated_jobs = []
is_running = False

def run_pipeline():
    global is_running, global_evaluated_jobs
    is_running = True
    global_evaluated_jobs = []
    
    log("--- Phase 1: Data Extraction ---")
    jobspy_jobs = get_jobspy_jobs()
    himalayas_jobs = get_himalayas_jobs()
    
    all_raw_jobs = jobspy_jobs + himalayas_jobs
    log(f"Total raw jobs found: {len(all_raw_jobs)}")
    
    # Deduplicate by URL
    unique_jobs = {job["url"]: job for job in all_raw_jobs if job["url"]}.values()
    jobs_list = list(unique_jobs)
    log(f"Total unique jobs after deduplication: {len(jobs_list)}")
    
    if not jobs_list:
        log("No jobs found. Pipeline complete.")
        is_running = False
        return
        
    log("--- Phase 2: AI Evaluation (Parallel) ---")
    results = evaluate_jobs_parallel(jobs_list)
    
    # Store globally for download
    global_evaluated_jobs = [job for job in results if job.get('match_score', 0) >= 50]
    
    log("--- Phase 3: Complete ---")
    log(f"Pipeline finished! Found {len(global_evaluated_jobs)} highly matched jobs.")
    log("DONE")
    is_running = False

@app.get("/")
def serve_index():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.post("/api/start")
def start_scraping(background_tasks: BackgroundTasks):
    global is_running
    if is_running:
        return {"status": "Already running"}
    background_tasks.add_task(run_pipeline)
    return {"status": "Started"}

@app.get("/api/stream")
async def sse_stream():
    async def event_generator():
        while True:
            # Check for new logs
            while not log_queue.empty():
                msg = log_queue.get()
                yield {"event": "log", "data": json.dumps({"message": msg})}
                
            # Check for new evaluated jobs
            while not job_queue.empty():
                job = job_queue.get()
                try:
                    job_json = json.dumps(job, default=str)
                    yield {"event": "job", "data": job_json}
                except Exception as e:
                    log(f"Error serializing job: {e}")
                
            await asyncio.sleep(0.5)
            
    return EventSourceResponse(event_generator())

@app.get("/api/download")
def download_csv():
    if not global_evaluated_jobs:
        return {"error": "No jobs available for download"}
        
    df = pd.DataFrame(global_evaluated_jobs)
    df = df.sort_values(by="match_score", ascending=False)
    
    output_file = "remote_junior_jobs.csv"
    df.to_csv(output_file, index=False)
    return FileResponse(path=output_file, filename="remote_junior_jobs.csv", media_type="text/csv")
