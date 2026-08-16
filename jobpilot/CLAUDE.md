# JOBPILOT — Project Status

## How to Run Locally

```bash
cd d:\AI-JOB-SCRAPER-main\jobpilot

# First time only — install packages
# On Python 3.14 Windows use --only-binary for pandas/jobspy:
pip install -r requirements.txt
pip install pandas python-jobspy --only-binary=:all:

# Run
python run.py
# Open: http://localhost:8000
```

## Deployment
- **Frontend + API**: Netlify (auto-deploys on git push to master)
- **Live URL**: https://singular-pasca-851777.netlify.app
- **GitHub**: https://github.com/Uswarooj/ai-job-scraper.git (master branch)
- Netlify function: `netlify/functions/api/api.py` (Mangum wraps FastAPI)

## What's Working ✅
- Multi-user auth (register/login/logout/forgot-password with OTP)
- Per-user data isolation — every query scoped to user_id
- CV upload + auto-parse (skills, roles, keywords extracted)
- CV-based job matching (uses YOUR CV, not hardcoded profile)
- Pipeline auto-triggers after CV upload
- Job scraping: Himalayas, Remotive, RemoteOK, WeWorkRemotely, Arbeitnow, TheMuse, NodeDesk, Rozee
- JobSpy (LinkedIn + Indeed) — optional, serial with jitter to avoid bot detection
- India job filter — excluded automatically
- Location-aware: remote UK/USA/Germany + user's city for on-site
- Last 24 hours only
- Per-user Telegram notifications
- Password eye toggle on all fields
- Onboarding toast after first login
- Data leakage fixed: outerjoin → inner join, analytics scoped to user

## Pending (credentials only)
- Set `GROQ_API_KEY` in settings for AI-powered matching
- Set Telegram Bot Token + Chat ID per user (in Settings tab)
- Set LinkedIn/Indeed credentials per user (in Settings tab)
- Playwright for browser auto-apply: `pip install playwright && playwright install chromium`

## Key Files
- Entry point: `run.py`
- Config: `core/config.py`
- Pipeline: `workers/pipeline.py`
- Matching: `agents/matching/agent.py` (CV-based, not hardcoded)
- Dashboard: `static/index.html`
- Auth: `api/routes/auth.py` + `services/auth_service.py`
- Netlify function: `../netlify/functions/api/api.py`

## DB Schema Notes
Uses SQLAlchemy `create_all` (no migrations). If you change model columns
or constraints, delete `jobpilot.db` and restart — it recreates automatically.

## Python Version
Python 3.11 or 3.12 recommended. Python 3.14 works but needs:
`pip install pandas python-jobspy --only-binary=:all:`
