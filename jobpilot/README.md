# JOBPILOT — AI Career Command Center

A production-grade, multi-agent AI career automation platform.

## Quick Start

```bash
cd jobpilot

# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env → set GROQ_API_KEY at minimum

# 3. Run
python run.py

# 4. Open dashboard
# http://localhost:8000
```

## What It Does

| Feature | Status |
|---|---|
| Multi-source job discovery (8 sources) | ✅ Working |
| Job normalization | ✅ Working |
| Deduplication (URL + content + fuzzy) | ✅ Working |
| AI job analysis (rule-based + LLM) | ✅ Working |
| Candidate matching with score breakdown | ✅ Working |
| Application state machine | ✅ Working |
| ATS resume optimization | ✅ Working |
| Cover letter generation | ✅ Working |
| Professional dark-mode dashboard | ✅ Working |
| Real-time SSE pipeline streaming | ✅ Working |
| SQLite database (no setup) | ✅ Working |
| PostgreSQL support | ✅ Ready (change DATABASE_URL) |
| Analytics & CSV export | ✅ Working |
| Kanban application tracker | ✅ Working |
| WhatsApp notifications | ⚙️ Pending Meta API credentials |
| Email OAuth monitoring | ⚙️ Pending Google OAuth credentials |
| Docker deployment | ✅ Dockerfile provided |

## Architecture

```
JOBPILOT
├── core/           — Config, DB, schemas, security, events, state machine
├── agents/         — Specialized agents (normalization, dedup, analysis, matching, resume, cover letter)
├── integrations/   — Source adapters, LLM providers, WhatsApp, Email
├── api/            — FastAPI routes (jobs, applications, analytics, agents, system)
├── workers/        — Pipeline orchestrator
├── prompts/        — Versioned LLM prompts
├── static/         — Professional dashboard (HTML/CSS/JS)
└── tests/          — Unit + integration tests
```

## Agents

| Agent | Purpose |
|---|---|
| Normalization | Converts raw scraped data → canonical schema |
| Deduplication | URL hash + content hash + fuzzy title/company match |
| Analysis | Extracts skills, experience, red flags, Pakistan eligibility |
| Matching | Scores jobs 0-100 with full breakdown |
| Resume | ATS-optimized tailored resume per job (facts-only, no fabrication) |
| Cover Letter | Professional, specific, non-generic letters |

## Score System

| Score | Label | Action |
|---|---|---|
| 90–100 | HIGH PRIORITY | Auto-approved |
| 75–89 | GOOD MATCH | Auto-approved |
| 60–74 | POSSIBLE MATCH | Pending review |
| 40–59 | LOW PRIORITY | Pending review |
| <40 | — | Silently skipped |

## Security Features

- URL validation (SSRF prevention — blocks private IPs, localhost)
- Prompt injection detection on all external job content
- All job descriptions sanitized before LLM submission
- No raw passwords stored (OAuth only)
- No secrets in source code
- Audit logging for all state transitions

## API

```
POST /api/jobs/discover         — Start pipeline
GET  /api/jobs                  — List jobs
GET  /api/jobs/{id}             — Job details + analysis + match
POST /api/applications/{id}/approve   — Approve application
POST /api/applications/{id}/submit    — Mark submitted
GET  /api/analytics/summary     — Stats
GET  /api/download/csv          — Export CSV
GET  /api/stream                — SSE live updates
GET  /api/system/status         — System health
```

## Running Tests

```bash
cd jobpilot
pytest tests/unit/ -v
```

## Configuration

All settings in `.env`. Key settings:

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | — | Required for LLM features |
| `DATABASE_URL` | `sqlite:///./jobpilot.db` | Database connection |
| `APPLICATION_MODE` | `manual` | `manual` / `approval` / `controlled` |
| `SCORE_AUTO_APPROVE` | `40` | Minimum score for auto-approval |
| `MAX_APPLICATIONS_PER_DAY` | `10` | Daily application limit |

## Docker

```bash
docker-compose up
```
