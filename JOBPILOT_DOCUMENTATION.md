# JOBPILOT — Complete Project Documentation

> AI-powered career automation platform that discovers jobs 24/7, scores them against your profile, prepares tailored applications, and tracks everything through a professional dashboard.

---

## Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [How to Run Locally](#4-how-to-run-locally)
5. [Environment Variables](#5-environment-variables)
6. [How the Pipeline Works](#6-how-the-pipeline-works)
7. [Agents](#7-agents)
8. [Job Scoring System](#8-job-scoring-system)
9. [Application State Machine](#9-application-state-machine)
10. [API Reference](#10-api-reference)
11. [Dashboard Features](#11-dashboard-features)
12. [Security Features](#12-security-features)
13. [Running Tests](#13-running-tests)
14. [Docker Deployment](#14-docker-deployment)
15. [Vercel Deployment](#15-vercel-deployment)
16. [Integrations](#16-integrations)
17. [Feature Status](#17-feature-status)
18. [Known Limitations](#18-known-limitations)
19. [Roadmap](#19-roadmap)

---

## 1. What This Project Does

JOBPILOT automates the job search process end-to-end:

- **Discovers** fresh jobs from 8 sources (LinkedIn, Indeed, Glassdoor, Himalayas, Remotive, RemoteOK, WeWorkRemotely, Arbeitnow, TheMuse)
- **Normalizes** raw data into a clean canonical schema
- **Deduplicates** using URL hash + content hash + fuzzy title/company matching
- **Analyzes** each job with a hybrid rule-based + LLM system (extracts skills required, red flags, Pakistan/remote eligibility)
- **Scores** jobs 0–100 against your candidate profile across 8 dimensions
- **Prepares** ATS-optimized resumes and cover letters tailored per job
- **Tracks** applications through a 14-state machine (from discovered → offer/rejected)
- **Notifies** via WhatsApp and Email (pending credentials)
- **Streams** everything live to a dark-mode dashboard in real time

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI |
| Database | SQLite (default) / PostgreSQL (production) |
| ORM | SQLAlchemy 2.0 + Alembic migrations |
| Config | Pydantic Settings (all from `.env`) |
| LLM | Groq (llama3-8b-8192) / OpenRouter (Gemini 2.5 Flash) |
| Job Sources | python-jobspy, direct APIs, HTML scraping |
| Scheduling | APScheduler |
| Real-time | SSE (Server-Sent Events) |
| Queue | In-memory (Redis-ready) |
| Frontend | Vanilla HTML/CSS/JS (no build step) |
| Testing | pytest, pytest-asyncio |
| Deployment | Vercel (serverless) / Docker |
| CI/CD | GitHub Actions → Vercel CLI |

---

## 3. Project Structure

```
AI-JOB-SCRAPER-main/
│
├── jobpilot/                       # Main application package
│   ├── core/
│   │   ├── config.py               # All settings via pydantic-settings
│   │   ├── database.py             # SQLAlchemy engine, session, init_db
│   │   ├── models.py               # 15 ORM tables
│   │   ├── schemas.py              # Pydantic request/response schemas
│   │   ├── logging.py              # Structured JSON logging + SSE queues
│   │   ├── security.py             # SSRF prevention, prompt injection detection
│   │   ├── events.py               # In-process pub/sub event bus
│   │   └── state_machine.py        # 14-state application state machine
│   │
│   ├── agents/
│   │   ├── base.py                 # Agent base class (retry, DB tracking, observability)
│   │   ├── normalization/          # Raw → canonical job schema
│   │   ├── deduplication/          # URL + content + fuzzy dedup
│   │   ├── analysis/               # Skill extraction, red flags, LLM hybrid
│   │   ├── matching/               # 8-dimension candidate scoring
│   │   ├── resume/                 # ATS resume optimization per job
│   │   └── cover_letter/           # Tailored cover letter generation
│   │
│   ├── integrations/
│   │   ├── sources/                # Job source adapters
│   │   │   ├── base.py             # JobSourceAdapter interface
│   │   │   ├── jobspy.py           # LinkedIn, Indeed, Glassdoor (via JobSpy)
│   │   │   ├── himalayas.py        # Himalayas.app API
│   │   │   ├── remotive.py         # Remotive API
│   │   │   ├── remoteok.py         # RemoteOK API
│   │   │   ├── weworkremotely.py   # WeWorkRemotely RSS
│   │   │   ├── arbeitnow.py        # Arbeitnow API
│   │   │   ├── themuse.py          # The Muse API
│   │   │   └── nodesk.py           # NoDesk scraper
│   │   ├── llm/
│   │   │   ├── base.py             # LLM provider interface
│   │   │   ├── groq_provider.py    # Groq implementation
│   │   │   └── openrouter_provider.py  # OpenRouter implementation
│   │   ├── email/
│   │   │   └── oauth.py            # Gmail OAuth integration
│   │   └── whatsapp/
│   │       └── client.py           # Meta WhatsApp Business API
│   │
│   ├── api/
│   │   ├── main.py                 # FastAPI app, lifespan, SSE stream, dashboard
│   │   └── routes/
│   │       ├── jobs.py             # /api/jobs/*
│   │       ├── applications.py     # /api/applications/*
│   │       ├── analytics.py        # /api/analytics/*
│   │       ├── agents.py           # /api/agents/*
│   │       ├── notifications.py    # /api/notifications/*
│   │       ├── profile.py          # /api/profile/*
│   │       ├── email.py            # /api/email/*
│   │       ├── whatsapp.py         # /api/whatsapp/*
│   │       └── system.py           # /api/system/*
│   │
│   ├── workers/
│   │   ├── pipeline.py             # Parallel job pipeline orchestrator
│   │   └── scheduler.py            # APScheduler for recurring runs
│   │
│   ├── prompts/
│   │   ├── job_analysis.txt        # LLM prompt for job analysis
│   │   ├── resume.txt              # LLM prompt for resume tailoring
│   │   └── cover_letter.txt        # LLM prompt for cover letter
│   │
│   ├── static/
│   │   ├── index.html              # Full dashboard (single file)
│   │   └── support.js              # Dashboard JS helpers
│   │
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── test_security.py       # 10+ tests
│   │   │   ├── test_state_machine.py  # 9 tests
│   │   │   ├── test_deduplication.py  # 5 tests
│   │   │   ├── test_normalization.py  # 8 tests
│   │   │   └── test_matching.py       # 9 tests
│   │   └── integration/
│   │       └── test_api.py
│   │
│   ├── run.py                      # Entry point
│   ├── requirements.txt
│   ├── .env.example
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── api/
│   ├── index.py                    # Vercel serverless entry point
│   └── requirements.txt            # Vercel build dependencies
│
├── .github/
│   └── workflows/
│       └── deploy.yml              # GitHub Actions → Vercel auto-deploy
│
├── vercel.json                     # Vercel build + routing config
└── .env.example                    # Root-level env template
```

---

## 4. How to Run Locally

### Prerequisites
- Python 3.11+
- pip

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/Uswarooj/ai-job-scraper.git
cd ai-job-scraper/jobpilot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment
copy .env.example .env
# Open .env and set GROQ_API_KEY at minimum

# 4. Run
python run.py

# 5. Open browser
# http://localhost:8000
```

The app auto-creates the SQLite database on first run. No database setup required.

### Minimum required `.env` setting

```env
GROQ_API_KEY=your_key_from_console.groq.com
```

Everything else has sensible defaults.

---

## 5. Environment Variables

### Core

| Variable | Default | Description |
|---|---|---|
| `DEBUG` | `false` | Enable debug mode |
| `SECRET_KEY` | *(change this)* | App secret key |
| `DATABASE_URL` | `sqlite:///./jobpilot.db` | SQLite or PostgreSQL URL |
| `LOG_LEVEL` | `INFO` | Logging level |

### LLM

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `groq` | `groq` or `openrouter` |
| `LLM_MODEL` | `llama3-8b-8192` | Model name |
| `GROQ_API_KEY` | — | **Required for AI features** |
| `OPENROUTER_API_KEY` | — | Alternative LLM provider |
| `OPENROUTER_MODEL` | `google/gemini-2.5-flash` | OpenRouter model |

### Candidate Profile

| Variable | Default | Description |
|---|---|---|
| `CANDIDATE_NAME` | `Ibrahim Hamid` | Your full name |
| `CANDIDATE_EMAIL` | `ibrahimhamid.2600@gmail.com` | Your email |
| `CANDIDATE_LOCATION` | `Islamabad, Pakistan` | Your location |
| `CANDIDATE_TIMEZONE` | `Asia/Karachi` | Your timezone |
| `CANDIDATE_REMOTE_PREFERENCE` | `worldwide_remote` | Remote work preference |

### Scoring

| Variable | Default | Description |
|---|---|---|
| `SCORE_HIGH_PRIORITY` | `90` | Auto-approve threshold |
| `SCORE_GOOD_MATCH` | `75` | Good match threshold |
| `SCORE_POSSIBLE_MATCH` | `60` | Possible match threshold |
| `SCORE_MIN_THRESHOLD` | `30` | Minimum to store job |

### Application Control

| Variable | Default | Description |
|---|---|---|
| `APPLICATION_MODE` | `manual` | `manual` / `approval` / `controlled` |
| `MAX_APPLICATIONS_PER_DAY` | `10` | Daily limit |
| `AUTO_APPLICATION_ENABLED` | `false` | Enable auto-apply |

### Integrations

| Variable | Description |
|---|---|
| `WHATSAPP_API_TOKEN` | Meta WhatsApp Business API token |
| `WHATSAPP_PHONE_NUMBER_ID` | Your WhatsApp Business phone ID |
| `WHATSAPP_TO_NUMBER` | Your personal WhatsApp number |
| `EMAIL_OAUTH_CLIENT_ID` | Google OAuth client ID |
| `EMAIL_OAUTH_CLIENT_SECRET` | Google OAuth client secret |

---

## 6. How the Pipeline Works

```
[Trigger: manual or scheduled every 6h]
         │
         ▼
┌─────────────────────────────────────────┐
│  Source Adapters (parallel, 8 sources)  │
│  JobSpy · Himalayas · Remotive          │
│  RemoteOK · WeWorkRemotely · Arbeitnow  │
│  TheMuse · NoDesk                       │
└─────────────┬───────────────────────────┘
              │ raw jobs
              ▼
    ┌──────────────────┐
    │ Normalization    │  salary parsing, remote type,
    │ Agent            │  date parsing, canonical schema
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ Deduplication    │  URL hash + content hash +
    │ Agent            │  fuzzy title/company match
    └────────┬─────────┘
             │ unique jobs only
             ▼
    ┌──────────────────────────────────────┐
    │  Analysis Agent (parallel per job)   │
    │  · Extracts required skills          │
    │  · Detects red flags                 │
    │  · Checks Pakistan/remote eligibility│
    │  · Senior role pre-filter (no LLM)   │
    │  · LLM structured JSON analysis      │
    └────────┬─────────────────────────────┘
             │
             ▼
    ┌──────────────────┐
    │ Matching Agent   │  8-dimension score 0–100
    │                  │  with full breakdown
    └────────┬─────────┘
             │ score >= 30
             ▼
    ┌──────────────────┐
    │ Saved to DB      │  streamed live to dashboard
    │ + SSE broadcast  │  via /api/stream
    └──────────────────┘
```

---

## 7. Agents

### Base Agent (`agents/base.py`)
All agents inherit from `BaseAgent`. Provides:
- Input/output validation
- Automatic retry with exponential backoff
- Database run tracking (start time, end time, status, error)
- Structured logging with correlation IDs
- Observability hooks

### Normalization Agent
- Parses salary ranges (hourly/annual, various formats)
- Standardizes remote type (remote/hybrid/on-site)
- Standardizes employment type (full-time/contract/part-time)
- Parses and normalizes posted dates
- Outputs canonical `NormalizedJob` schema

### Deduplication Agent
Three-signal deduplication:
1. **URL hash** — exact URL match
2. **Content hash** — same title + company + location fingerprint
3. **Fuzzy match** — similar title at same company (catches reposts with slight wording changes)

### Analysis Agent
Hybrid rule-based + LLM:
- Rule-based pre-filter: rejects senior/principal roles instantly (no LLM cost)
- LLM analysis: extracts required skills, experience level, red flags
- Pakistan/remote eligibility detection
- All job text wrapped and sanitized before LLM submission (prompt injection defense)

### Matching Agent
Scores jobs across 8 dimensions:

| Dimension | Weight |
|---|---|
| Skills overlap | High |
| Role title match | High |
| Remote compatibility | High |
| Location/work authorization | High |
| Experience level fit | Medium |
| Salary range overlap | Medium |
| Employment type preference | Low |
| Company size preference | Low |

### Resume Agent
- Takes job description + candidate profile
- Outputs ATS-optimized tailored resume
- Facts-only policy — never fabricates experience
- Uses versioned prompt from `prompts/resume.txt`

### Cover Letter Agent
- Generates professional, specific cover letters
- References actual job requirements
- Non-generic — tailored per job
- Uses versioned prompt from `prompts/cover_letter.txt`

---

## 8. Job Scoring System

| Score | Label | Dashboard Action |
|---|---|---|
| 90–100 | HIGH PRIORITY | Auto-approved, highlighted |
| 75–89 | GOOD MATCH | Auto-approved |
| 60–74 | POSSIBLE MATCH | Pending review queue |
| 40–59 | LOW PRIORITY | Pending review queue |
| < 30 | — | Silently dropped |

Each score includes a full breakdown by dimension, visible in the job detail view.

---

## 9. Application State Machine

14 states with validated transitions:

```
DISCOVERED → ANALYZED → MATCHED → PENDING_REVIEW
    → APPROVED → RESUME_GENERATING → COVER_LETTER_GENERATING
    → APPLICATION_READY → SUBMITTED → INTERVIEW_SCHEDULED
    → OFFER_RECEIVED → ACCEPTED

Dead ends: REJECTED, WITHDRAWN, EXPIRED
```

Every transition is logged with timestamp, reason, and user/system actor. Invalid transitions raise an error — state can never go backward except to terminal states.

---

## 10. API Reference

### Jobs

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/jobs/discover` | Start pipeline (triggers scrape + analyze + match) |
| `GET` | `/api/jobs` | List all jobs (filter by score, status, source) |
| `GET` | `/api/jobs/{id}` | Full job detail with analysis + match breakdown |
| `POST` | `/api/jobs/{id}/shortlist` | Move to shortlist |
| `POST` | `/api/jobs/{id}/reject` | Reject job |

### Applications

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/applications` | List all applications |
| `POST` | `/api/applications/{id}/approve` | Approve for application |
| `POST` | `/api/applications/{id}/submit` | Mark as submitted |
| `GET` | `/api/applications/{id}/status` | Current state + history |

### Analytics

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/analytics/summary` | Total jobs, matches, applications, response rate |
| `GET` | `/api/analytics/scores` | Score distribution histogram |
| `GET` | `/api/analytics/sources` | Per-source job count and quality |
| `GET` | `/api/download/csv` | Export all data as CSV |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/system/health` | Health check (DB, scheduler, LLM status) |
| `GET` | `/api/system/status` | Full system status |
| `GET` | `/api/stream` | SSE real-time event stream |
| `GET` | `/api/docs` | Swagger interactive API docs |

---

## 11. Dashboard Features

The dashboard (`static/index.html`) is a single-file dark-mode UI with no build step.

### Pages

| Page | What It Shows |
|---|---|
| **Pipeline** | Live console, start button, source status, real-time log stream |
| **Jobs** | Scored job feed with score circles, match details, approve/reject |
| **Review** | Pending jobs awaiting manual review |
| **Applications** | Kanban tracker (7 columns: Discovered → Accepted) |
| **Analytics** | Stats cards, score distribution chart, source performance |
| **Settings** | Scoring thresholds, application limits, notification toggles |

### Real-time Updates
All pipeline activity streams live via SSE to the dashboard — log lines appear as they happen, new jobs appear in the feed the moment they are scored.

---

## 12. Security Features

| Feature | Implementation |
|---|---|
| SSRF prevention | All URLs validated — private IPs, localhost, and internal ranges blocked |
| Prompt injection defense | All scraped job text wrapped in delimiters and sanitized before LLM |
| No stored passwords | Email integration uses OAuth 2.0 only |
| No hardcoded secrets | All credentials from `.env`, never in source code |
| Audit logging | Every application state transition logged with actor + timestamp |
| Input validation | All API inputs validated by Pydantic schemas |
| SQL injection | Parameterized queries via SQLAlchemy ORM |

---

## 13. Running Tests

```bash
cd jobpilot
pytest tests/unit/ -v
```

### Test Coverage

| File | What It Tests | Count |
|---|---|---|
| `test_security.py` | URL validation, SSRF, prompt injection, hashing | 10+ |
| `test_state_machine.py` | All valid transitions, terminals, happy path | 9 |
| `test_deduplication.py` | URL hash, content hash, fuzzy match signals | 5 |
| `test_normalization.py` | Salary parsing, remote type detection, batch | 8 |
| `test_matching.py` | Scoring dimensions, full matching, math | 9 |

---

## 14. Docker Deployment

```bash
cd jobpilot
docker-compose up
```

### What `docker-compose.yml` runs

| Service | Description |
|---|---|
| `app` | JOBPILOT FastAPI app on port 8000 |
| `postgres` | PostgreSQL (for production use) |
| `redis` | Redis (for distributed workers) |

### To use PostgreSQL instead of SQLite

In your `.env`:
```env
DATABASE_URL=postgresql://jobpilot:password@localhost:5432/jobpilot
```

---

## 15. Vercel Deployment

The app is deployed to Vercel as a Python serverless function.

### How it works

```
GitHub push to master
        │
        ▼
GitHub Actions (.github/workflows/deploy.yml)
        │
        ▼
Vercel CLI (vercel deploy --prod)
        │
        ▼
Vercel builds api/index.py → serverless lambda
        │  (includes jobpilot/ package via includeFiles)
        ▼
Live at your Vercel URL
```

On Vercel:
- Database → SQLite in `/tmp` (ephemeral, resets on cold start)
- APScheduler → disabled (use Vercel Cron or external scheduler for recurring runs)
- Static files → served through the FastAPI route

### Required GitHub Secrets

Add at `github.com/Uswarooj/ai-job-scraper/settings/secrets/actions`:

| Secret | Where to Get It |
|---|---|
| `VERCEL_TOKEN` | vercel.com/account/tokens → Create Token |
| `VERCEL_ORG_ID` | `.vercel/repo.json` → `orgId` value |
| `VERCEL_PROJECT_ID` | `.vercel/repo.json` → `id` value |

Your values:
- `VERCEL_ORG_ID` = `team_l8WWwHqW0hExonwBgFz4NGHZ`
- `VERCEL_PROJECT_ID` = `prj_xcdrUfqF4MN3LkuBhHM4hd4TjImw`

### Manual Deploy Trigger

`github.com/Uswarooj/ai-job-scraper/actions` → Deploy to Vercel → Run workflow

---

## 16. Integrations

### LLM Providers

| Provider | Config | Models |
|---|---|---|
| Groq | `LLM_PROVIDER=groq` + `GROQ_API_KEY` | llama3-8b-8192 (default), llama3-70b |
| OpenRouter | `LLM_PROVIDER=openrouter` + `OPENROUTER_API_KEY` | Gemini 2.5 Flash, Claude, GPT-4, 100+ others |

Free tier available on both. Get Groq key at [console.groq.com](https://console.groq.com).

### WhatsApp (Pending Setup)

Sends notifications for:
- New high-score job discovered
- Application ready to submit
- Recruiter response received
- Interview scheduled

**To activate:**
1. Create Meta Business account at [developers.facebook.com](https://developers.facebook.com)
2. Apply for WhatsApp Business API access
3. Set `WHATSAPP_API_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_TO_NUMBER` in `.env`

### Email OAuth (Pending Setup)

Monitors inbox for:
- Recruiter replies
- Interview invitations
- Rejection emails
- Offer letters

**To activate:**
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → Enable Gmail API → Create OAuth 2.0 credentials
3. Set `EMAIL_OAUTH_CLIENT_ID`, `EMAIL_OAUTH_CLIENT_SECRET` in `.env`

---

## 17. Feature Status

| Feature | Status |
|---|---|
| Multi-source job discovery (8 sources) | ✅ Working |
| Job normalization | ✅ Working |
| Deduplication | ✅ Working |
| AI job analysis (rule-based + LLM) | ✅ Working |
| Candidate matching with score breakdown | ✅ Working |
| Application state machine (14 states) | ✅ Working |
| ATS resume optimization | ✅ Working |
| Cover letter generation | ✅ Working |
| Dark-mode dashboard | ✅ Working |
| Real-time SSE streaming | ✅ Working |
| SQLite (zero setup) | ✅ Working |
| PostgreSQL | ✅ Ready (change DATABASE_URL) |
| Analytics + CSV export | ✅ Working |
| Kanban application tracker | ✅ Working |
| Unit tests (41+ tests) | ✅ Passing |
| Docker deployment | ✅ Ready |
| Vercel serverless deployment | ✅ Ready (needs secrets) |
| GitHub Actions CI/CD | ✅ Ready (needs secrets) |
| WhatsApp notifications | ⚙️ Pending Meta API credentials |
| Email OAuth monitoring | ⚙️ Pending Google OAuth credentials |
| Redis distributed queue | ⚙️ Set REDIS_URL to activate |

---

## 18. Known Limitations

- **Vercel SQLite is ephemeral** — database resets on each cold start. Use PostgreSQL for persistent data on Vercel.
- **No CAPTCHA solving** — by design. Manual application submission required for sites with CAPTCHA.
- **Browser automation not included** — form-based job applications are not automated.
- **WhatsApp and Email require external API approval** — code is complete, credentials are not.
- **Python 3.14 on Windows** — `python-jobspy` requires numpy which needs a C compiler on Python 3.14. Use Python 3.11 or 3.12 to avoid the build error.

---

## 19. Roadmap

### Immediate (credentials only)
- [ ] Set `GROQ_API_KEY` → enables AI analysis and resume/cover letter generation
- [ ] Add GitHub secrets → enables auto-deploy to Vercel
- [ ] Meta WhatsApp API approval → enables WhatsApp notifications
- [ ] Google OAuth credentials → enables email monitoring

### Short Term
- [ ] Switch Vercel database to PostgreSQL (persistent across cold starts)
- [ ] Set `REDIS_URL` to enable distributed worker queue
- [ ] Add Vercel Cron job for scheduled pipeline runs (replaces APScheduler on serverless)

### Long Term
- [ ] Multi-user support (each user has their own profile, CVs, job feed)
- [ ] CV versioning and per-job CV selection
- [ ] Browser automation for one-click apply (Playwright)
- [ ] Mobile app or Telegram bot interface
- [ ] Interview preparation agent

---

*Generated: August 2026 | Repository: github.com/Uswarooj/ai-job-scraper*
