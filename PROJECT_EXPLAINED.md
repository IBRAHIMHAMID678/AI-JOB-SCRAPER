# AI Job Scraper — Simple Explanation

## What is this project?

**AI Job Scraper** — a tool that automatically finds remote software jobs from the internet, scores them based on your profile, and shows you only the best matches.

---

## How it works — Step by Step

### Step 1: Collecting Jobs (Scrapers)

The app visits **8 different job websites** automatically and pulls job listings:

| Website | File |
|---|---|
| LinkedIn, Indeed, Glassdoor (via JobSpy) | `scrapers/jobspy_scraper.py` |
| Himalayas | `scrapers/himalayas_scraper.py` |
| Remotive | `scrapers/remotive_scraper.py` |
| RemoteOK | `scrapers/remoteok_scraper.py` |
| WeWorkRemotely | `scrapers/weworkremotely_scraper.py` |
| NoDesk | `scrapers/nodesk_python_scraper.py` |
| The Muse | `scrapers/themuse_scraper.py` |

---

### Step 2: Scoring Jobs (Evaluator)

Every job gets a **score out of 100** based on:

| Criteria | Max Points |
|---|---|
| Job title match (AI Engineer, Full Stack, Python Dev) | +40 |
| Skills match (Python, FastAPI, React, LangChain, RAG, MongoDB) | +40 |
| Junior / entry-level role | +20 |
| USD pay mentioned | +5 to +10 |

Then it checks: **Is this job accessible from Pakistan?**
It automatically skips jobs that say "US-only" or "US citizens only".

---

### Step 3: Auto-Decision

| Result | What Happens |
|---|---|
| Score >= 40% + Pakistan-eligible | Auto-approved, shown on dashboard |
| Borderline score | Placed in "Pending Review" queue for manual check |
| Score < 30% | Silently skipped |

---

### Step 4: View Results

- Run `python server.py` → opens a **live web dashboard** at `http://localhost:8000`
- Run `python main.py` → saves results to a **CSV file**
- From the dashboard you can also export results as a **Word document (DOCX)**

---

## Key Files Summary

| File | Purpose |
|---|---|
| `main.py` | Simple CLI runner — scrape → score → save CSV |
| `server.py` | Web dashboard with live updates |
| `evaluator.py` | The brain — scores each job |
| `database.py` | Saves results to MongoDB (or memory if MongoDB is off) |
| `config.py` | Settings (API keys, preferences) |
| `log_manager.py` | Handles all console/dashboard logs |
| `scrapers/` | Folder containing one scraper per job website |
| `static/` | Frontend files for the web dashboard |

---

## Setup in 3 Steps

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Create a `.env` file**
```env
GROQ_API_KEY=your_groq_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=job_scraper_db
```

**3. Run it**
```bash
# Web dashboard (recommended)
python server.py

# Or CLI only
python main.py
```

---

## In One Sentence

This tool **automatically searches 8 job websites, scores each job based on your skills (Python, FastAPI, React, AI/LLM), filters out US-only jobs, and shows you the best remote jobs you can apply to from Pakistan.**
