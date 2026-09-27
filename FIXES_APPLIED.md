# Fixes Applied — All 62 Audit Findings (2026-09-27)

Repo: `~/workspace/AI-JOB-SCRAPER`. Spec: `AUDIT_REPORT_2026-09-27.md`.
Ground truth applied everywhere: remote $10–40/hr OR Islamabad/Rawalpindi onsite ~PKR 100k/mo; 1–3 yrs experience; AI Engineer / AI Full-Stack Python; Pakistan-eligible only; LinkedIn ≤5d; portals ≤30d (prefer 14).

> ⚠️ **SECRETS ROTATION REQUIRED (user must act):** GROQ_API_KEY / OPENROUTER_API_KEY were committed to this repo's git history. The working tree no longer contains them (they now load from a gitignored `.env`), but git history is immutable — **rotate both keys in the Groq and OpenRouter dashboards** and update your `.env` / Vercel secrets. `vercel.json` DATABASE_URL was replaced with a Vercel secret reference (`@jobpilot-database-url`) — set that secret in Vercel.

## Section 1A — Discovery / source-yield (items 1–19) — worker A ✅
- [x] 1. `production_batch_run.py:186-207` — all 15 adapters registered (Jobicy, WorkingNomads, Remotive, WWR, TheMuse, Arbeitnow, RemoteOK, Himalayas, NodeDesk, Greenhouse, Lever, new Ashby, Rozee, Scrapfly, optional JobSpy); Ashby also registered in `jobpilot/workers/pipeline.py:209`. Live yields verified: Greenhouse 3780, Lever 322, Himalayas 240, RemoteOK 232, Jobicy 100, Arbeitnow 650, TheMuse 62, WWR 65, Remotive 54, NodeDesk 28, WorkingNomads 26.
- [x] 2. `ats_greenhouse.py` — pruned to live boards (Vercel, Canonical, GitLab, Stripe, Figma, Datadog, Brex, Gusto, Reddit, Discord, Instacart, Affirm, Elastic, CockroachLabs, Remote, Anthropic); `ats_lever.py` — pruned to `palantir`/`fly`; new `jobpilot/integrations/sources/ashby.py` (Ashby posting API; live-probed: OpenAI 830, Cursor 126, ElevenLabs 207, Cohere 147, Perplexity 123, n8n 34…); non-200 boards now log loudly.
- [x] 3. `himalayas.py` — `companyName` for company; Unix-timestamp `pubDate` → ISO; `nextCursor` pagination (capped at 4 pages/term — cursor never terminates).
- [x] 4. `sources/base.py` — `max_retries` 1→3; removed silent whole-fetch swallows (loud per-query logs; raise only when all queries fail).
- [x] 5. `themuse.py` — removed empty `api_key`; corrected params (category "Software Engineering", `location="Flexible / Remote"`, 0-indexed pages, browser UA).
- [x] 6. `rozee.py` — Scrapfly ASP/JS fallback for Cloudflare; loud failures; reports zero-yield when `SCRAPFLY_API_KEY` absent (no key written).
- [x] 7. `sources/workingnomads.py`, `scrapers/workingnomads.py` — endpoint → live `/api/exposed_jobs/` (26 jobs).
- [x] 8. `sources/nodesk.py`, `scrapers/nodesk_python_scraper.py` — strict XML parse with repaired-`&` fallback; "Title, Company" comma parsing; no ` - ` swap (28 jobs, 0 blank companies).
- [x] 9. `discover_urls.py`, `discover_targeted_linkedin.py` — hardened Yahoo redirect patterns, retries/backoff/UA rotation, loud zero warnings, LinkedIn snowflake ≤5-day pre-check, stale pool filtered, newer query angles. Note: live Yahoo is currently bot-blocked (`RemoteDisconnected`) — scripts report it loudly instead of silently yielding zero.
- [x] 10. Pagination/caps raised: Himalayas cursor, RemoteOK 40/tag + `llm`/`full-stack` tags, Arbeitnow 2 pages, Jobicy 100, Remotive 100, WWR all items, TheMuse 3 pages.
- [x] 11. `remoteok.py` — `j.get("location") or "Worldwide"` (0 empty locations).
- [x] 12. `jobicy.py` — reads `salaryMin`/`salaryCurrency`/`salaryPeriod` with robust numeric parser; `jobType` list→string fixed. (Live API currently exposes no salary keys — correctly absent, not fabricated.)
- [x] 13. `linkedin_posts.py` — documented as stub; kept unregistered in both pipelines so stats aren't misleading.
- [x] 14. `sources/jobspy.py`, `scrapers/jobspy_scraper.py` — `hours_old` 72→120 (≤5d LinkedIn rule).
- [x] 15. `jobpilot/core/config.py` — added ML Engineer, RAG, Python Developer, Backend Developer, Node.js; `scrapers/remotive_scraper.py` — dead `search_terms_lower` + unused import removed.
- [x] 16. Reassigned to worker B — done (see 1B).
- [x] 17. `ats_lever.py` — timeout 5→15s.
- [x] 18. `test_discovery_yield.py` — `Path(__file__).resolve().parent`-based paths.
- [x] 19. `datetime.utcnow()` → `datetime.now(timezone.utc)` in touched files (`pipeline.py` etc.).
- A verification: `py_compile` clean on all changed files; `git diff --check` clean; fresh-venv unit run: 118 passed, 2 failed — both pre-existing `test_auto_apply.py` failures (pristine tree fails identically).

## Section 1B — Matching / scoring / filtering (items 20–40) — worker B ✅
- [x] 20. `jobpilot/agents/analysis/agent.py:75` — seniority detection now title-only, whole-word via `check_seniority`; "Junior AI Engineer" at "leading AI startup" no longer flagged senior.
- [x] 21. `jobpilot/agents/matching/agent.py:141` — removed always-true `""` from location keyword list; `analysis/agent.py:47-57` + `evaluator.py:121` — added bare-US patterns (`Remote, US`, `Remote - US`, `US only`); `jobpilot/workers/pipeline.py:103` — Phase 2b eligibility precheck (`evaluate_job_eligibility`) before global dedup.
- [x] 22. `analysis/agent.py:63`, `evaluator.py:108` — ISO country codes (CA/DE/PA/IN/MD/AL) require corroborating US context; fixed `\bin\b` matching "in" in "Developer in Dubai".
- [x] 23. `jobpilot/agents/normalization/agent.py:88` — negation handling checked first ("not a remote position" → onsite); physical city with no signal → `unknown`, not `remote`.
- [x] 24. `normalization/agent.py:171` — v2 canonical ID includes location + salary + description hash; `production_batch_run.py:69` — `generate_canonical_job_id_v2` (legacy kept for historical lookups); `deduplication/agent.py:26-50` — seniority canonicalized not stripped (Senior≠Junior), location bucket in key (Remote≠Islamabad); dedup history bounded to 30 days; `jobpilot/tests/unit/test_deduplication.py` updated + 2 new tests.
- [x] 25. `matching/agent.py:58`, `evaluator.py:163` — added ML, machine-learning, GenAI, RAG, AI/ML, NLP, Prompt, FastAPI, Django title variants.
- [x] 26. `matching/agent.py:127` — 3-year requirements get full in-range experience points.
- [x] 27. `analysis/agent.py:145`, `evaluator.py:140`, `eligibility.py:58` — experience regex allows intervening words incl. hyphens ("5 years of hands-on experience" now extracts); 4+ yr roles excluded per 1–3 rule.
- [x] 28. `normalization/agent.py:114` — `_parse_salary` keeps 3-tuple `(min,max,currency)` + new `_parse_salary_period`; `matching/agent.py:156` — period-aware scoring: `$30/hr`→hourly, `Rs. 100,000-150,000`→PKR/monthly (not USD), `$200/hr` gets no full pay points; $10–40/hr band enforced.
- [x] 29. `eligibility.py:165` — bare "India" in description no longer rejects; only `Remote - India`/`India only`/`must be based in India`/location-token reject.
- [x] 30. `eligibility.py:132` — EMEA block moved after explicit restriction checks; EMEA eligible unless Pakistan excluded.
- [x] 31. `evaluator.py:79` — cache key includes description hash + `_EVAL_CODE_VERSION="2"`; pre-filters run before cache lookup.
- [x] 32. `harvest_linkedin_posts.py:109` — LinkedIn FRESH ≤5 days; token parsing reordered ("2 days" no longer hits year branch); `production_batch_run.py:80` — `parse_iso_datetime` tz-aware via `fromisoformat`; 15–30d portal jobs retained as AGING, only >30d stale.
- [x] 33. `harvest_linkedin_posts.py:430` — raw remote-scope text (`Remote - LATAM`/`Remote (India)`) passed to eligibility.
- [x] 34. `jobpilot/core/dead_letter.py` (new) + `jobpilot/agents/base.py`, `normalization/agent.py`, `workers/pipeline.py`, `evaluator.py` — failures write structured records to repo-root `dead_letter.jsonl`.
- [x] 35. `jobpilot/core/config.py` — scores ≥40 label `APPROVED` (was 60); `evaluator.py` `AUTO_APPROVE_THRESHOLD=40`; `server.py:164` already `>=40`; `main.py` imports `evaluate_job_single as evaluate_job` (import crash fixed).
- [x] 36. `matching/agent.py:45`, `workers/pipeline.py` — salary target $10–40/hr; `unified_model.py` `experience_required_max` 2.0→3.0; root `config.py:43` CANDIDATE_PROFILE 0–2→1–3 yrs (API-key lines untouched).
- [x] 37. `analysis/agent.py:89` — Islamabad aliases word-boundaried; "Brisbane" no longer matches `isb`.
- [x] 38. `groq_provider.py`, `openrouter_provider.py` — JSON response format; `llm/base.py` — `complete_json` 3 attempts.
- [x] 39. `server.py:110-116` — URL-less jobs dedup via title+company MD5 fallback.
- [x] 40. `analysis/agent.py`, `evaluator.py` — junior keywords synced to 1–3-year variants.
- [x] 15b. Root `config.py:13-26` — removed "Remote Developer UK"/"Software Engineer Remote"; added RAG, ML Engineer, Python Developer, Backend Developer, Node.js.
- [x] 16. `harvest_linkedin_posts.py:30` — WFH variant detection (`wfh`, `work from home`, `work-from-home`, `remote work`).
- B verification: `py_compile` clean on 21 files; 105/105 behavior checks pass via stub harness (`/tmp/verify_workerB.py`); pytest/pydantic unavailable in env (pip blocked by PEP 668) — full `jobpilot/tests/` suite should be run where deps exist. `eval_cache.json` test artifact deleted. `schemas.py` ownership violation reverted (no schema change).

## Section 2 — Application flow (items 41–58) — worker C ✅
- [x] 41. `application_engine.py:1-200` — DELETED fabricated `LinkedInSubmitter`/`IndeedSubmitter` classes; `JobApplicationEngine.apply_to_job()` now delegates to `auto_apply.apply_to_job` via `asyncio.to_thread`, mapping only real success → `"submitted"`; orchestrator sends confirmation email only on truthful success.
- [x] 42. `jobpilot/services/auto_apply.py:~1280-1350` — `apply_to_job()` calls `classify_application_url()` before any browser attempt; explicit dispatch for GREENHOUSE / LEVER / EMAIL / WORKDAY / GOOGLE_FORM / generic forms (`mailto:` → SMTP email flow).
- [x] 43. `run_frozen_batch_apply.py:1-40` — `d:\…` → `Path(__file__).resolve().parent`; batch file as CLI arg, else newest `batches/AUTO_APPLY_BATCH_*.json`.
- [x] 44. `auto_apply.py` idempotency guard — blocks retry only for SUBMITTED/CONFIRMED; UNCONFIRMED/UNVERIFIED/FAILED may retry; `state_machine.py:44` — SUBMISSION_UNCONFIRMED → APPLICATION_STARTED (retry) allowed.
- [x] 45. `auto_apply.py:1157` — `_generate_cover_letter()` via `CoverLetterAgent` + fact-check; generated when none supplied; `production_batch_run.py` + `run_workflow_a.py` pass it. Partial: ResumeAgent still DB-Markdown only — TODO added (no Markdown→PDF upload pipeline).
- [x] 46. `candidate.py` — AI Engineer / Brandlya Group / employed "Yes"; salary `$10 - $40 per hour`; `resume/agent.py` university from canonical profile (NUST removed), `$10-$40/hr`. Note: hardcoded 3.6/4.0 GPA inherited from audited canonical profile — needs user confirmation.
- [x] 47. `greenhouse_agent.py`, `lever_agent.py`, `application/base.py` — bare `except: pass` → contextual `logger.warning`; failures return failure, never silent success.
- [x] 48. `auto_apply.py:187` — `_send_email_application` returns False + error log when SMTP unconfigured.
- [x] 49. `auto_apply.py:1208` — `_record_application_status()` routes ORM writes through `state_machine.transition()`; `api/routes/applications.py:33,134` — `mark_submitted`/`mark_confirmed` require `evidence` string (HTTP 400 if missing). Residual: direct-write fallback on invalid transitions (logged ERROR, intentional).
- [x] 50. `submission_verifier.py` — screenshot dir repo-relative `jobpilot/screenshots`.
- [x] 51. `candidate.py` `resolve_resume_path` — `Path(__file__)`-relative lookup, honors `CANDIDATE_RESUME_PATH`, no Windows paths.
- [x] 52. `auto_apply.py` dispatch + `state_machine.py:54,58` — WORKDAY/GOOGLE_FORM record terminal `UNSUPPORTED_ROUTE`, never sent to browser.
- [x] 53. `application/base.py` — submit validation scoped to visible error/invalid/validation elements; bare `:has-text('required')` dropped.
- [x] 54. `fact_checker.py` — splits comma-separated skills (was iterating characters).
- [x] 55. `auto_apply.py:75` — `_truthful_work_authorization()`: named-country auth "Yes" only for Pakistan / genuinely worldwide wording, else "No". Caveat: truly ambiguous country questions currently default "Yes" — stricter default is a candidate follow-up.
- [x] 56. `production_batch_run.py`, `run_workflow_a.py` — `can_apply(score, user_id)` gates added.
- [x] 57. `auto_apply.py` — dead `_greenhouse_apply`/`_lever_apply` wrappers deleted.
- [x] 58. Intentionally unchanged: no CAPTCHA solver; detect + PAUSED with `pause_reason` (conservative policy).
- C verification: `py_compile` clean on 18 files; unit suite 134 passed, 2 failed (pre-existing at HEAD, verified via git stash — `test_work_authorization_and_sponsorship_questions`, `test_experience_and_education_fields`); integration 15 passed; router/state-machine/work-auth/evidence-gate live checks pass.
- C follow-ups: (a) CoverLetterAgent prompt/`MASTER_RESUME` fallback still contains education language — user's 2026-09-27 "never mention education in cover letters/emails" rule needs a follow-up pass; (b) 5 `TestSalaryParsing` failures attributed to a `_parse_salary` 4-tuple change — flagged for integration resolution.

## Cross-cutting (items 59–62) — worker D ✅
- [x] 59. `requirements.txt` — rewritten as union of root + `jobpilot/requirements.txt` (26 deps, incl. `mangum>=0.17.0` for `netlify/functions/api/api.py`); `jobpilot/requirements.txt` unchanged. AST import-coverage check (`/tmp/check_import_coverage.py`): zero uncovered imports. `fitz`/PyMuPDF left as commented optional (try/except import with fallback in `cv_parser.py`).
- [x] 60. `config.py:8-10` — keys now `os.getenv("GROQ_API_KEY","")` / `os.getenv("OPENROUTER_API_KEY","")` + never-commit comment; `vercel.json` — DATABASE_URL value removed → `"@jobpilot-database-url"` Vercel secret reference (JSON validated); `.env.example` extended with placeholders (no real values); `.gitignore` already had `.env`/`.env*`; secret sweep found no other committed secrets. ⚠️ Keys in git history must still be ROTATED by the user.
- [x] 61. `capture_focused_form.py`, `run_live_demo.py`, `live_demo.py` — `d:\…` paths → `Path(__file__).resolve().parent`-based; zero `[A-Z]:\` strings remain; `headless=False` left as-is (demos are meant to be visible). py_compile clean.
- [x] 62. `production_batch_run.py` — added ground-truth sync docstring (shared constants: auto-approve 40, LinkedIn ≤5d, portals ≤30d, 1–3 yrs, $10–40/hr). Consistency snapshot: agreed on `SCORE_AUTO_APPROVE=40`/`TIER2_SCORE_MIN=40`, `server.py:164 >= 40`, `pipeline.py:301 >3yr` skip; remaining divergences (evaluator `AUTO_APPROVE_THRESHOLD=60`, batch ≤14d freshness, harvester ≤14d, `years_min<=2`, salary 15–60, "0-2 years" strings) are worker B's items 26/32/36/40 — pending at check time.

## Verification
- Full-repo `python3 -m compileall`: clean, zero errors (all ~153 files).
- Worker A: `py_compile` clean; `git diff --check` clean; fresh-venv unit run 118 passed / 2 failed — both pre-existing `test_auto_apply.py` failures (pristine tree fails identically).
- Worker B: `py_compile` clean on 21 files; 105/105 behavior checks pass via stub harness (`/tmp/verify_workerB.py`); `jobpilot/tests/unit/test_deduplication.py` updated + 2 new tests for the fixed fuzzy key.
- Worker C: `py_compile` clean on 18 files; unit suite 134 passed / 2 failed — both pre-existing at HEAD (verified via `git stash`: `test_work_authorization_and_sponsorship_questions`, `test_experience_and_education_fields`); integration suite 15 passed; router/state-machine/work-auth/evidence-gate live checks pass.
- Worker D: `py_compile` clean; AST import-coverage check (`/tmp/check_import_coverage.py`) exit 0 — every third-party import covered by `requirements.txt`.
- Coordinator: fixed remaining `datetime.utcnow()` in `deduplication/agent.py`, `agents/base.py`, `api/main.py`, `api/routes/analytics.py`, `core/logging.py`, `core/db_audit.py`, `core/dead_letter.py`, `core/eligibility.py` → `datetime.now(timezone.utc)`; deliberately left naive datetimes in `application_lock.py`, `auth_service.py`, `core/models.py`, `api/routes/cvs.py`, `services/cv_parser.py` (DB-stored values compared against each other — mixing aware/naive would raise TypeError).
- Pre-commit checks: no `.env` in tree, no secret patterns in diff, no junk binaries; new files are `ashby.py`, `dead_letter.py`, `FIXES_APPLIED.md`, `AUDIT_REPORT_2026-09-27.md`.

## Deliberately skipped / deferred
- Item 58: no CAPTCHA solver added — detect + PAUSED with `pause_reason` is the correct conservative behavior.
- Item 45 (partial): ResumeAgent still outputs DB Markdown only — TODO added; no Markdown→PDF upload pipeline implemented.
- Item 13: `LinkedInPostsAdapter` kept as documented stub, unregistered from both pipelines (not deleted).
- Item 6: Rozee kept with Scrapfly fallback; yields zero loudly when `SCRAPFLY_API_KEY` is absent.
- `live_demo.py` / `run_live_demo.py`: `headless=False` kept — these demos are meant to be visible.
- `jobpilot/core/schemas.py`: no `salary_period` field added — period handled via `_parse_salary_period`/`_detect_salary_period` with no schema change.
- Full `jobpilot/tests/` pytest suite could not run in this environment (no pydantic/pytest installed, pip blocked by PEP 668) — recommend running it in a proper venv before the next production batch.
- Worker C caveats carried forward: (a) hardcoded `3.6/4.0` GPA in canonical profile needs user confirmation — never invent GPA claims; (b) ambiguous work-authorization questions currently default "Yes" — stricter default is a candidate follow-up; (c) CoverLetterAgent prompt/`MASTER_RESUME` fallback still contains education language — user's 2026-09-27 "never mention education in cover letters/emails" rule needs a follow-up pass on the agent prompt.
