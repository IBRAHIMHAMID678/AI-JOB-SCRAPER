# JOBPILOT — Claude Checkpoint

## Status: COMPLETE (pending credential configuration)

## Completed
- [x] core/ — config, models (15 tables), schemas, database, logging, security, events, state_machine
- [x] agents/ — base, normalization, deduplication, analysis, matching, resume, cover_letter
- [x] integrations/sources/ — jobspy, himalayas, remotive, remoteok, weworkremotely, arbeitnow, themuse, nodesk
- [x] integrations/llm/ — base, groq_provider, openrouter_provider
- [x] integrations/whatsapp/client.py — Meta official API (pending credentials)
- [x] integrations/email/oauth.py — Gmail OAuth (pending credentials)
- [x] workers/pipeline.py — parallel orchestrator (8 sources, parallel analysis)
- [x] api/main.py — FastAPI + SSE stream
- [x] api/routes/ — jobs, applications, analytics, agents, notifications, system
- [x] static/index.html — full dark-mode dashboard (no build step)
- [x] tests/unit/ — 5 test files, 41+ unit tests
- [x] conftest.py + tests/conftest.py — pytest env setup
- [x] prompts/ — job_analysis.txt, resume.txt, cover_letter.txt
- [x] run.py, requirements.txt, .env.example, Dockerfile, docker-compose.yml
- [x] README.md, PROJECT_STATUS.md

## Pending (credentials only, not code)
- [ ] Set GROQ_API_KEY in .env for LLM features
- [ ] Set WHATSAPP_API_TOKEN + Meta Business approval for WhatsApp
- [ ] Set EMAIL_OAUTH_CLIENT_ID/SECRET + Google OAuth for email monitoring

## To Run
```bash
cd jobpilot
pip install -r requirements.txt
cp .env.example .env   # then set GROQ_API_KEY
python run.py
# http://localhost:8000
```

## To Test
```bash
cd jobpilot
pytest tests/unit/ -v
```

## Key Files
- Entry point: `run.py`
- Config: `core/config.py` (all settings from .env)
- Pipeline: `workers/pipeline.py`
- Dashboard: `static/index.html`
- Tests: `tests/unit/`
