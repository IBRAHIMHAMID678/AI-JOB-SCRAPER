# AI-JOB-SCRAPER — Deep Code Audit Report
**Date:** 2026-09-27 · **Repo:** `~/workspace/AI-JOB-SCRAPER` (~153 Python files)
**Method:** Three parallel auditors read the actual source (discovery, matching, application flow) and verified key bugs empirically (live endpoint probes, reproduced regex/parsing bugs). Parent agent additionally checked requirements, config, exception patterns, and deploy wiring.
**User's requirements (ground truth):** remote $10–40/hr **or** Islamabad/Rawalpindi onsite ~PKR 100k/mo; 1–3 yrs experience (junior→mid); AI Engineer / AI Full-Stack Python; Pakistan-eligible only; LinkedIn ≤5 days fresh; portals ≤30 days (prefer 14).

**Headline:** The system has two divergent pipelines (the `jobpilot/` package pipeline via `workers/pipeline.py`, and the legacy root path via `evaluator.py`/`server.py`/`production_batch_run.py`) that disagree on thresholds, freshness, and eligibility. Of ~15 discovery sources, roughly half silently return zero. The production batch path doesn't call 8 of the 15 adapters. The application path contains stub submitters that fabricate "submitted" results, misroutes every email-apply job to a browser, and permanently blacklists any attempt it couldn't verify. Almost nothing that fails logs loudly enough to notice.

---

## Section 1 — Scraping / Discovery / Matching Issues

### 1A. Discovery & source-yield bugs

**1. [CRITICAL] Production batch discovery ignores 8 of 15 sources**
- `production_batch_run.py` → `discover_raw_jobs()` (~lines 128–190) calls only: Greenhouse, Lever, Jobicy, Remotive, WorkingNomads, WeWorkRemotely, LinkedIn CSV.
- Never called: `RemoteOKAdapter`, `ArbeitnowAdapter`, `HimalayasAdapter`, `NodeDeskAdapter`, `RozeeAdapter`, `TheMuseAdapter`, `JobSpyAdapter`, `LinkedInPostsAdapter`.
- Why it matters: a live probe found RemoteOK alone returning 101 live jobs for one tag; the batch run sees zero of them. This is the single largest structural yield loss.
- Fix: mirror `_fetch_all_sources()` from `jobpilot/workers/pipeline.py:148-220` into `discover_raw_jobs()`.

**2. [CRITICAL] ATS board targeting is ~94% dead — the exact AI companies the user wants are gone**
- `jobpilot/integrations/sources/ats_greenhouse.py:24-31` (40 targets), `ats_lever.py:26-31` (20 targets). Live probes:
  - Greenhouse: 16 of 17 AI targets 404 (`openai, cursor, mistral, elevenlabs, runway, deepgram, baseten, octoai, qdrant, huggingface, groq, cohere, pinecone, weaviate, scale, perplexity` — only `anthropic` works); plus 7 more 404s (`postman, hashicorp, automattic, zapier, sourcegraph, writer, retool`).
  - Lever: 18 of 20 targets 404 — only `palantir` and `fly` work (`netflix, shopify, coursera, docker, airtable, dbtlabs, n8n, replit, supabase, synthesia, modal, resend, railway, convex, prisma, cal, clerk` all dead — moved to Ashby/own boards).
- `fetch_company_jobs` does `if res.status_code != 200: return []` — silent. `fetch()` in `ats_greenhouse.py` also wraps per-board failures in `except Exception: pass`.
- Why it matters: the user wants AI Engineer roles; the adapter's AI-company list is nearly all dead air, silently.
- Fix: delete dead tokens; add an Ashby adapter (`https://api.ashbyhq.com/posting-api/job-board/{company}`) for OpenAI, Cursor, Mistral, ElevenLabs, Runway, Replit, Supabase, Railway, etc.

**3. [CRITICAL] Himalayas adapter reads fields that don't exist → 100% of its jobs dropped**
- `jobpilot/integrations/sources/himalayas.py:33-40`: uses `j.get("company", {}).get("name", "")` and `j.get("requiredSkills", [])`. Live API has **no** `company`/`requiredSkills` keys — it's `companyName` (a string).
- Every job gets `company=""`, and `filter_qualify_deduplicate` does `if not title or not company: continue` (`production_batch_run.py`) → silently discarded. Also ignores the real `pubDate` field and `nextCursor` pagination.
- Why it matters: an entire source yields zero, with no error.
- Fix: `company=j.get("companyName","")`, drop `requiredSkills`, add `posting_date=j.get("pubDate")`, paginate on `nextCursor`. Also wire it into `discover_raw_jobs()` (see #1).

**4. [CRITICAL] Retry logic is decorative — `max_retries = 1`, exceptions swallowed inside every `fetch()`**
- `jobpilot/integrations/sources/base.py:20`: `max_retries = 1` → the retry loop can never retry.
- Nearly every adapter wraps its whole body in `try/except: log; return []` (e.g. `arbeitnow.py:18-32`, `jobicy.py:38`, `remotive.py:42`, `himalayas.py:42`), so `get_jobs()`'s backoff path is unreachable. One 429 or timeout zeroes that source for the run.
- Why it matters: transient failures become permanent zero-yield sources; nothing retries.
- Fix: `max_retries = 3`; remove inner swallows (re-raise after logging) so `get_jobs()` retries with its `2 ** attempt` backoff.

**5. [HIGH] TheMuse adapter crippled by empty `api_key`**
- `jobpilot/integrations/sources/themuse.py:24`: `params={"category": cat, "level": "Entry Level", "page": 1, "api_key": ""}`. Live probe: with empty `api_key=` → `{"total": 12}` (one attempt timed out); **without** the param → `{"total": 99836}`. The root `scrapers/themuse_scraper.py` omits `api_key` and works.
- Why it matters: ~0 results instead of ~99k searchable, failure hidden by swallowed exception.
- Fix: delete `"api_key": ""` from params. One-line quick win.

**6. [HIGH] Rozee adapter fully Cloudflare-blocked**
- `jobpilot/integrations/sources/rozee.py:19` — both the API URL and the listing-scrape fallback return **HTTP 403 "Just a moment..."** (verified live). This is the user's Pakistan-local source — dead, silently returning `[]`.
- Fix: route Rozee through Scrapfly/Playwright, or drop it from the active set so stats aren't misleading.

**7. [HIGH] Root WorkingNomads scraper hits a 404 endpoint**
- `scrapers/workingnomads.py:15`: `url = "https://www.workingnomads.com/api/v1/jobs/"` → verified HTTP 404. The adapter (`sources/workingnomads.py:15`) uses the correct `https://www.workingnomads.com/api/exposed_jobs/` (verified 200).
- Fix: point the scraper at `/api/exposed_jobs/`.

**8. [HIGH] NoDesk adapter dead; Python.org feed misparsed**
- `jobpilot/integrations/sources/nodesk.py:34`: `ET.fromstring(resp.content)` on `https://nodesk.co/index.xml` raises `ParseError: not well-formed` → whole feed yields 0.
- The Python.org feed works (20 items) but the parser assumes `"Title at Company"` / `"Company - Title"` while the real format is `"Title, Company"` (verified: `'Django Developer, The Developer Society'`); titles containing `" - "` get company/title **swapped**, then fail the tech-keyword filter. Same bug in `scrapers/nodesk_python_scraper.py`.
- Fix: parse the comma format; don't swap on `" - "`.

**9. [HIGH] LinkedIn discovery pipeline yields ~0: Yahoo scraping + stale pool**
- `discover_urls.py` / `discover_targeted_linkedin.py` scrape `search.yahoo.com` with regex `RU=([^/]+)/RK` — fragile against Yahoo markup changes, zero results fail silently.
- 5 sampled URLs from `discovered_linkedin_urls.txt` decode (via the snowflake logic, verified sane/monotonic) to **24–82 days old** — search-index lag means the pool is stale on arrival, and the harvester's ≤14d STALE-reject then nukes nearly all of it.
- Fix: re-verify the Yahoo regex against current markup; add a `posted ≤5d` pre-check at discovery; rotate fresher query angles.

**10. [MEDIUM] No pagination anywhere that matters**
- Himalayas ignores `nextCursor`; RemoteOK takes `[:15]`/tag of ~101 available (`sources/remoteok.py:40`); Arbeitnow `[:30]` (`arbeitnow.py:19`); Jobicy single `count=50` page; Remotive `limit=20` single page; WWR `[:20]`/feed; TheMuse 1 page `[:15]`.
- Fix: paginate per API (cursor/page params) or at least raise per-tag caps.

**11. [MEDIUM] RemoteOK empty-location leak**
- `jobpilot/integrations/sources/remoteok.py`: `location=j.get("location", "Worldwide")` — returns `""` when the key exists with an empty value (RemoteOK commonly has empty location), so location is `""` not `"Worldwide"`. Downstream eligibility parsing sees an empty string.
- Fix: `j.get("location") or "Worldwide"`.

**12. [MEDIUM] Jobicy salary fields don't exist**
- `jobpilot/integrations/sources/jobicy.py`: reads `annualSalaryMin` (doesn't exist; real keys are `salaryMin`/`salaryCurrency`/`salaryPeriod`) → salary always None. Also `str(x).isdigit()` rejects floats/decimals.
- Fix: use the real keys; parse robustly.

**13. [MEDIUM] `LinkedInPostsAdapter.fetch()` always returns `[]`**
- `jobpilot/integrations/sources/linkedin_posts.py:117-123` — stub; also not wired into `workers/pipeline.py`, so social leads never flow.
- Fix: implement or remove.

**14. [MEDIUM] JobSpy windows stricter than the user's rule; tiny result cap**
- `jobpilot/integrations/sources/jobspy.py:91,112`: `hours_old=24`; root `scrapers/jobspy_scraper.py`: `hours_old=72`. User rule: ≤5 days (120h) for LinkedIn. `_LINKEDIN_RESULTS_PER_TERM = 8`.
- Fix: `hours_old=120`, raise per-term caps.

**15. [MEDIUM] Search-term gaps and junk terms**
- `jobpilot/core/config.py` `SEARCH_TERMS` lacks "ML Engineer", "RAG", "Python Developer", "Backend Developer", "Node.js"; RemoteOK `_TAGS` lacks "llm"/"full-stack". Root `config.py` has junk terms "Remote Developer UK" / "Software Engineer Remote" (UK term wastes quota and pulls UK-geo jobs). `scrapers/remotive_scraper.py:21` computes `search_terms_lower` but never uses it (dead code).
- Fix: add the missing terms; remove the UK junk term.

**16. [MEDIUM] Harvester misclassifies WFH posts as onsite**
- `harvest_linkedin_posts.py`: `work_arrangement` defaults to `"Onsite"` unless the body literally contains "remote"/"hybrid" — "WFH"/"work from home" not detected → `location="Onsite"`, `country="International"` → geo-rejected.
- Fix: detect WFH variants.

**17. [LOW] Lever `timeout=5`** (`ats_lever.py:58`) — slow boards silently drop. Raise to 15.
**18. [LOW] `test_discovery_yield.py` hardcodes `d:/Job Scraper`** — dead on Linux.
**19. [LOW] `datetime.utcnow()` naive datetimes** — deprecation noise only.

### 1B. Matching / scoring / filtering bugs (why good jobs get dropped, bad ones pass)

**20. [CRITICAL] Seniority false-positive via raw substring match — drops legit junior jobs**
- `jobpilot/agents/analysis/agent.py:58, 95-101`: `_SENIOR_KEYWORDS` matched with `any(k in text ...)` where `text = title + " " + description[:500]` — plain substring, no word boundaries.
- Verified: `("Junior AI Engineer", "Join a leading AI startup…")` → flagged "senior" ("lead" in "leading"; also "manager", "architecture"→"architect"). Result: `_experience_score("senior")` → **0 pts instead of 12–15** (`matching/agent.py:112-119`) → real junior AI roles pushed below the 30-point persist cutoff (`pipeline.py:309`) and silently discarded. The whole-word `check_seniority()` in `eligibility.py` exists but is never called here.
- Fix: whole-word match on the **title only** (reuse `eligibility.check_seniority`).

**21. [CRITICAL] `_location_score` always returns 10/10 "Worldwide remote" — US-only remote slips through**
- `jobpilot/agents/matching/agent.py:129`: `if any(k in loc for k in ["worldwide", "anywhere", "pakistan", "global", ""]):` — `""` is **always** a substring, so this is always True; the `elif` is dead code.
- Compounding: `_is_us_only` (`analysis/agent.py:78-90`) doesn't catch `"Remote, US"` / `"Remote - US"` — "us" alone matches neither the compiled patterns nor `_US_STATES`. And `pipeline.py:process_job` never calls `eligibility.py`, which *would* catch these.
- Result: US-only remote jobs get `pakistan_eligible=True` + 10/10 "Worldwide remote".
- Fix: remove `""` from the list; add bare-US patterns (`remote[\s,\-–(]*us\b`, `\bus only\b`); or call `evaluate_job_eligibility` in the pipeline.

**22. [HIGH] US-state regex treats ISO country codes as US states — drops legit international jobs**
- `jobpilot/agents/analysis/agent.py:48-51,88`: bare 2-letter abbreviation search. Verified: `"Toronto, CA"`, `"Berlin, DE"`, `"Panama City, PA"`, `"Chisinau, MD"`, `"Tirana, AL"`, `"Mumbai, IN"`, `"Buenos Aires, AR"` → all `us_only=True` → `[SKIP] US-only`.
- Root `evaluator.py:80-112` has the same list **plus** `\bin\b` matching the English word "in" in locations like "Developer in Dubai".
- Fix: drop the bare-abbreviation heuristic or require corroborating US context; never match 2-letter tokens that are also ISO country codes without it.

**23. [HIGH] Remote-type default + negation-blind scan — onsite jobs classified "remote"**
- `jobpilot/agents/normalization/agent.py:38-48`: scans `location + description` for remote keywords, final `return "remote"  # default assumption for job boards`. "This is NOT a remote position. Office in Berlin." → `remote_type="remote"`; the onsite-city filter (`pipeline.py:~270`) never fires.
- Fix: handle negations ("not a remote", "no remote", "onsite only"); default to `"unknown"` when location names a physical city.

**24. [HIGH] Over-aggressive dedup: canonical ID = company+title only, permanent across runs**
- `jobpilot/agents/normalization/agent.py:108-111`: `canon_id = sha256(f"{norm_co}::{norm_ti}")` — ignores location, salary, description, URL, source.
- `jobpilot/agents/deduplication/agent.py:47-52, 90-106`: loads **all** historical IDs from DB → a reposted/fresh listing is dropped forever. Fuzzy match additionally strips seniority words ("Senior AI Engineer" ≡ "AI Engineer" at same company). In `production_batch_run.py`, `generate_canonical_job_id(company, title)` has the same flaw, and dedup runs *before* eligibility — a "Senior X" seen first can cause "Junior X" at the same company to be dropped.
- "AI Engineer @ X (remote)" vs "AI Engineer @ X (onsite Islamabad)" — the user wants both; the second is dropped.
- Fix: include location + salary/description hash in the canonical ID; only suppress reposts within the freshness window; run eligibility before dedup.

**25. [HIGH] Role keyword map misses core AI title variants — "ML Engineer" scores 12 vs "AI Engineer" 25**
- `jobpilot/agents/matching/agent.py:52-67` (`_build_role_map`); same gap in `evaluator.py:166`. Missing: "ml engineer", "machine learning engineer", "genai"/"generative ai engineer", "rag engineer", "ai/ml engineer", "nlp engineer", "prompt engineer", "fastapi developer", "django developer".
- Fix: add the variants to both maps.

**26. [HIGH] Experience scorer contradicts the approved 1–3 yr range**
- `jobpilot/agents/matching/agent.py:112-119`: `years_min <= 2 → 12 pts` else 5 pts. A job requiring exactly **3 years** (explicitly in-range per the user's approved rule, `pipeline.py`'s own `> 3` skip, and `eligibility.py`) gets a 7-point penalty.
- Fix: `years_min <= 3`.

**27. [HIGH] No upper-bound experience exclusion — 5+ year roles keep full points**
- `evaluator.py:196-237`: no pattern rejects "5+ years"/"8 years" descriptions; `analysis/agent.py:99-112` pattern 1 requires "experience|exp" immediately after "years", so "5 years of hands-on experience building APIs" → `years_min=None` → pipeline's `> 3` skip never fires, full 12 pts awarded.
- Fix: allow `(\d+)\s*(?:years?|yrs?)\s+of\s+[\w\s]{0,30}?experience` with intervening words.

**28. [MEDIUM] Salary parsing broken: single values never parse; PKR mislabeled as USD; no period detection**
- `jobpilot/agents/normalization/agent.py:61-73`: `_SALARY_PATTERN` requires a two-number range. Verified: `'$30/hr'` → `(None,None,None)`; `'$150000'` → None; `'$60,000/year'` → None → scored "not disclosed" (2 pts).
- `'Rs. 100,000 - 150,000'` → `(100000, 150000, 'USD')` — `_CURRENCY_MAP` lacks PKR/Rs/₨ and defaults to `"USD"`, so PKR 100k (~$350/mo) is scored/labeled as a USD six-figure salary. No hourly/monthly/annual distinction.
- Root `evaluator.py` pay regex also never enforces the $10–40/hr range (a $200/hr role gets the same +10), and never detects PKR/month — Islamabad onsite roles get no pay signal.
- Fix: optional second number; add PKR/Rs/₨; capture `/hr|/mo|/yr` period; enforce the 10–40 band.

**29. [MEDIUM] Bare `"india"` substring rejects worldwide-remote jobs that merely mention India**
- `jobpilot/core/eligibility.py:127-168`: `restricted_keywords` includes `"india"`, matched against `location + description[:800]`. "team across India and Europe" on a worldwide posting → `LOCATION_INELIGIBLE`. (Hit by `harvest_linkedin_posts.py:412` and `auto_apply.py:1205`.)
- Fix: anchor to location/remote-scope phrasing ("remote - india", "india only", "must be based in india").

**30. [MEDIUM] EMEA jobs hard-rejected though Pakistan is often eligible**
- `jobpilot/core/eligibility.py:check_geographic_eligibility` includes `"remote - emea"` in restricted keywords, and the fallback rejects any location lacking pakistan/islamabad/rawalpindi/worldwide/anywhere/global/remote — `location="EMEA"` (the standard Himalayas/Jobicy/Remotive value) → `LOCATION_INELIGIBLE`.
- Fix: treat EMEA as eligible unless the description excludes Pakistan.

**31. [MEDIUM] Stale eval cache bypasses filters and never invalidates**
- `evaluator.py:238-268`: cache-hit returns **before** the senior/non-tech/US pre-filters; key is `md5(url:title:company)` so description edits (added US-only restriction, removed pay) never invalidate; `eval_cache.json` persists across code fixes → stale scores re-emitted.
- Fix: run pre-filters before cache lookup; include a content hash + code-version in the key.

**32. [MEDIUM] Freshness gates don't match the user's rule**
- `production_batch_run.py` `filter_qualify_deduplicate`: `age_days > 14 → STALE` — drops valid 15–30-day portal jobs (user allows ≤30d). Conversely LinkedIn uses 14d where the user wants ≤5d (`harvest_linkedin_posts.py` FRESH ≤14d).
- `harvest_linkedin_posts.py` `evaluate_freshness` year-branch bug: `if "y" in token or "year" in token:` runs first and `"y" in "2 days"` is True ("days" contains "y") → `"2 days"`, `"1 day"`, `"14 days"`, `"daily"` all classified STALE. Reproduced.
- `production_batch_run.py` `parse_iso_datetime` truncates tz: `dt_str[:25]` turns `"2026-09-26T11:15:22+00:00"` into `"...+00:0"` → parse fails → None → job stamped "FRESH/now" → stale jobs pass the gate.
- Fix: ≤5d LinkedIn / ≤30d portals; reorder day-check before year-check (or `\byears?\b`); use `datetime.fromisoformat`.

**33. [MEDIUM] LinkedIn harvester rewrites location to "Worldwide Remote"**
- `harvest_linkedin_posts.py:343-360`: any post containing "remote" → `location="Worldwide Remote"` before `evaluate_job_eligibility()` sees it. "Remote - LATAM" / "Remote - India" lose their qualifier.
- Fix: pass raw location text to eligibility.

**34. [MEDIUM] Swallowed exceptions silently drop jobs mid-pipeline**
- `normalization/agent.py:94-99`: per-job try/except → warning log, job dropped. `pipeline.py:process_job` broad except → None. `evaluator.py:196-204`: except → `match_score=0, is_pakistan_eligible=False`. `agents/base.py:77-82` `run()` returns None on failure.
- Fix: dead-letter record for dropped jobs instead of a log line.

**35. [MEDIUM] Threshold/label inconsistencies + dead entry point**
- `SCORE_AUTO_APPROVE=40` (`core/config.py:77`) but `get_score_label(40..59)` = `"LOW_PRIORITY"` — auto-approved/auto-applied jobs display as LOW_PRIORITY. Root: `evaluator.py:242` `AUTO_APPROVE_THRESHOLD=60` vs `server.py:164` hardcoded `>= 40`.
- `main.py:4` does `from evaluator import evaluate_job` — **no such function exists** (`evaluator.py` defines only `evaluate_job_local`/`evaluate_job_single`) → `main.py` crashes on import.

**36. [MEDIUM] Config values contradict documented user requirements**
- `config.py:38` `CANDIDATE_PROFILE` and `application_engine.py:224-229`: "0-2 years experience" vs approved **1–3**.
- `jobpilot/core/candidate.py`: `"salary_range": "$30 - $50 per hour"`, `"desired_salary": "$60,000 / year or $30 / hour"` vs **$10–40/hr** (used by form fillers — over-quoting can auto-reject).
- `jobpilot/core/unified_model.py` `RoleInfo.experience_required_max = 2.0` vs 3.
- `matching/agent.py:45-46` + `pipeline.py:249-250`: `min_hourly_usd=15, max_hourly_usd=60` vs 10–40.
- `harvest_linkedin_posts.py` FRESH ≤14d vs **≤5d**.
- Fix: sync all to the approved values.

**37. [LOW] `_is_local_pk` false positive** (`analysis/agent.py:73-76`): `"isb"`/`"pindi"` substrings — "Brisbane" contains "isb".
**38. [LOW] LLM providers don't set `response_format: json_object`** (`groq_provider.py`, `openrouter_provider.py`); `complete_json` gives up after 2 attempts → None (analysis falls back to rule-based). Single provider, no fallback chain.
**39. [LOW] `server.py:112-117` dedup**: jobs with empty URL are silently discarded entirely.
**40. [LOW] `_JUNIOR_KEYWORDS` hardcodes "0-2 years"** (`analysis/agent.py:59`, `evaluator.py:186`) — stale vs 1–3.

---

## Section 2 — Application Flow Issues

**41. [CRITICAL] Legacy `application_engine.py` LinkedIn/Indeed submitters are stubs that fabricate "submitted" results**
- `application_engine.py:100-165`: `LinkedInSubmitter.submit_application` and `IndeedSubmitter` build `application_result = {"status": "submitted", ...}`, `await asyncio.sleep(3)` ("Simulate LinkedIn submission" — no browser, no HTTP request), then fabricate `confirmation.reference_id = f"LI-{datetime.now().timestamp()}"` and log "Successfully applied to ...".
- `job_application_orchestrator.py:72` counts `status == "submitted"` as success and sends the user a confirmation email. If this orchestrator path runs (it's the documented "main orchestrator"), **every reported success is fake** — zero applications leave the machine.
- Fix: delete the stubs (or raise `NotImplementedError`); route the orchestrator through `jobpilot.services.auto_apply.apply_to_job`.

**42. [CRITICAL] `mailto:` application URLs are fed to Playwright instead of the email flow — router is dead code**
- `production_batch_run.py:216` builds `application_url = u or f"mailto:{em}"` for LinkedIn-post jobs that only have an apply email.
- `jobpilot/services/auto_apply.py:1272-1304`: `if apply_url:` — `mailto:` is truthy → falls into `_generic_apply(apply_url, ...)` → `page.goto("mailto:...")` fails (unknown scheme) → every email-apply job recorded as `SUBMISSION_UNCONFIRMED`/`FAILED`.
- The email path only runs `if not applied_ok and not apply_url:` — unreachable for mailto:. `router.py:classify_application_url` correctly classifies `mailto:` as `EMAIL` but **has zero callers**.
- Fix: at the top of the URL dispatch, route `mailto:` to the SMTP email flow; actually call `classify_application_url` in `apply_to_job`.

**43. [CRITICAL] `run_frozen_batch_apply.py` crashes immediately on Linux**
- `run_frozen_batch_apply.py:7,16`: `sys.path.insert(0, r"d:\Job Scraper")`; `batch_file = r"d:\Job Scraper\batches\AUTO_APPLY_BATCH_20260905_181243.json"` → on Linux this is a relative path → instant `FileNotFoundError`. Same disease in `capture_focused_form.py`, `run_live_demo.py`, `live_demo.py` (also `headless=False`, needs a display).
- Fix: resolve paths from repo root; take the batch file as a CLI arg.

**44. [HIGH] `SUBMISSION_UNCONFIRMED` jobs are permanently blacklisted — no retry ever**
- `jobpilot/services/auto_apply.py:1175-1187`: any existing app with status in `("SUBMITTED","CONFIRMED","SUBMISSION_UNVERIFIED","SUBMISSION_UNCONFIRMED")` → `return False  # IDEMPOTENCY BLOCKED`. A job whose confirmation wasn't detected (network hiccup, slow page, verifier false-negative) is treated identically to a confirmed submission and excluded from every future batch forever. Combined with #42, every mailto: job fails once and is locked out permanently.
- Fix: idempotency blocks only `SUBMITTED`/`CONFIRMED`; allow retry for `SUBMISSION_UNCONFIRMED`/`FAILED`.

**45. [HIGH] Resume/cover-letter agents never invoked — applications go out with generic filler**
- `grep` for `ResumeAgent|CoverLetterAgent` outside their own files → zero hits. `production_batch_run.py`/`run_workflow_a.py` never pass `cover_letter` into `apply_to_job`.
- `auto_apply.py:254`: every unmatched textarea gets `cover_letter or candidate["about_me"]` — "Why do you want to work here?" gets the generic about-me paragraph. The resume agent outputs markdown saved to DB, never rendered to PDF or uploaded.
- Fix: wire `CoverLetterAgent` and a real resume-PDF render pipeline into `apply_to_job`, or delete the dead agents.

**46. [HIGH] Tailored-resume data contradicts the canonical profile**
- `jobpilot/agents/resume/agent.py:90`: `university="NUST (National University of Sciences and Technology)"` vs canonical CUST (`candidate.py`).
- `auto_apply.py` hardcoded answers: `degree_result` "Expected graduation July 2026, GPA 3.4/4.0" vs canonical graduated July 2026, GPA 3.6/4.0; `currently_employed → "No"` + `current_company: "Freelance / Independent Projects"` vs Brandlya Group AI Engineer (Jul 2026–present).
- Salary `$60,000 / year or $30 / hour` vs user's $10–40/hr — over-quoting on salary filters can auto-reject.
- Fix: single-source everything from `get_canonical_candidate_profile()`; delete hardcoded strings in `_classify_and_resolve_field`.

**47. [HIGH] Bare `except Exception: pass` throughout the apply agents**
- `jobpilot/agents/application/greenhouse_agent.py`: lines 187-188, 399-400, 427-428, 445-446, 448-449. `lever_agent.py`: 164-165, 175-176, 185-186, 222-223. `application/base.py:70-71`. Failures during form fill/submit vanish without a trace — no way to distinguish "applied" from "crashed".
- Fix: log the exception with context and mark the attempt `FAILED` with a reason.

**48. [MEDIUM] `_send_email_application` returns `True` ("sent") when SMTP isn't even configured**
- `jobpilot/services/auto_apply.py:172-175`: `if not all([smtp_host, smtp_user, smtp_pass]): logger.warning(...); return True`. Currently guarded at the call site (line 1304), but any future caller gets a false success for an unsent email.
- Fix: return `False` (or raise) when SMTP is unconfigured.

**49. [MEDIUM] State machine bypassed — statuses written directly, transitions never validated**
- `jobpilot/services/auto_apply.py:1330-1400` writes `app.status = "SUBMITTED"` / `final_status` with plain `db.commit()`; the `TRANSITIONS` map in `state_machine.py` is enforced nowhere in the production flow. `api/routes/applications.py:121-127` allows manually marking "submitted" without evidence.
- Fix: route all status writes through `state_machine.transition()`.

**50. [MEDIUM] Verification screenshot path is a hardcoded Windows path**
- `jobpilot/core/submission_verifier.py:144`: `screenshot_dir: str = r"d:\Job Scraper\jobpilot\screenshots"` → on Linux creates a literal garbage-named directory; "proof" screenshots unfindable.
- Fix: repo-root-relative default.

**51. [MEDIUM] Resume resolution is cwd-dependent and Windows-first**
- `jobpilot/core/candidate.py:resolve_resume_path` — first candidates are `d:\Job Scraper\...` (dead on Linux), then `pathlib.Path("jobpilot/uploads/cvs/Ibrahim_Hamid_Resume.pdf").resolve()` depends on process cwd → "Resume file not found" aborts whole runs.
- Fix: resolve relative to `Path(__file__)`.

**52. [MEDIUM] Router defines routes no handler implements (WORKDAY, GOOGLE_FORM)**
- `router.py` returns WORKDAY (requires_login=True), GOOGLE_FORM, EMAIL — but `apply_to_job` only special-cases greenhouse/lever; everything else goes to `_generic_apply`, which bails on any password wall and can't handle Google Forms' structure or Workday login.
- Fix: use `classify_application_url` in the dispatcher; explicitly record WORKDAY/GOOGLE_FORM as unsupported instead of doomed browser attempts.

**53. [MEDIUM] `_click_submit_button` false-negative via `div:has-text('required')`** (`auto_apply.py:~915`): helper text like "* indicates required field" matches → `has_error=True` → returns False even when submit succeeded; can trigger spurious "Next"-clicks after a real submission.
- Fix: scope to visible error-styled elements; drop the bare `:has-text('required')`.

**54. [LOW] `fact_checker.py:48` iterates a string as skill list** — `candidate_profile["skills"]` is a comma-separated string; `set(...)` becomes a set of characters → spurious "unverified skill" warnings. Fix: split on commas.
**55. [LOW] Work-authorization answers are unconditional `"Yes"`** (`auto_apply.py:~330`) for any country question — submits false claims on restricted postings.
**56. [LOW] Daily-limit/tier logic (`can_apply`) never called** by `production_batch_run`/`run_workflow_a` — limits are decorative in the production path.
**57. [LOW] `_greenhouse_apply`/`_lever_apply` wrappers (`auto_apply.py:1098/1112`) are dead code** — never called; logic duplicated inline.
**58. [LOW] No CAPTCHA solving exists** (`application/base.py:check_safety_triggers` only detects + pauses). Correct conservative behavior, but any Cloudflare/Turnstile board stalls the batch.

---

## Cross-cutting

**59. [HIGH] Root `requirements.txt` is missing ~20 dependencies**
- Root `requirements.txt` has 12 unpinned entries. Code imports `playwright`, `sqlalchemy`, `pydantic_settings`, `httpx`, `beautifulsoup4`, `APScheduler`, `python-docx`, `python-multipart`, `bcrypt`, `cryptography`, `alembic`, `psycopg2-binary`, `mangum`, `sse_starlette`… none declared. Anyone installing from the root requirements (README path / legacy scripts) breaks at import time. `jobpilot/requirements.txt` is the fuller one (used by the Dockerfile), but the root one is what `main.py`/`server.py`/`production_batch_run.py` users hit.
- Fix: consolidate into one requirements file (or make the root one include the jobpilot one).

**60. [HIGH] Secrets committed to the repo**
- `config.py`: hardcoded `GROQ_API_KEY` and `OPENROUTER_API_KEY` in plaintext. `vercel.json`: `DATABASE_URL` committed. These are live credentials in a git repo.
- Fix: move to `.env` (gitignored), rotate the keys.

**61. [MEDIUM] Windows paths hardcoded in 6+ files** — `run_frozen_batch_apply.py`, `capture_focused_form.py`, `run_live_demo.py`, `live_demo.py`, `submission_verifier.py`, `candidate.py`, `test_discovery_yield.py`. All break on Linux (the deploy/VM environment).
- Fix: `pathlib.Path(__file__).resolve().parent` based paths.

**62. [MEDIUM] Two parallel pipelines with divergent rules** — `jobpilot/workers/pipeline.py` (thresholds 30/40/60/75/90, `TIER2_SCORE_MIN=40`) vs legacy `evaluator.py`/`server.py`/`production_batch_run.py` (threshold 60, blanket 14d freshness, different eligibility). `jobpilot/agents/discovery/` is **empty** (only `__init__.py`) — discovery lives in two different orchestrators. Behavior depends on which entry point you run; fixes must be applied twice or the legacy path retired.
- Fix: retire one path; make `production_batch_run.py` delegate to `workers/pipeline.py`.

---

## Quick wins (small fix → big effect, ranked)

1. `production_batch_run.py:discover_raw_jobs` — wire in the 8 missing adapters (mirror `workers/pipeline.py:_fetch_all_sources`). Largest single yield gain.
2. `jobpilot/integrations/sources/themuse.py:24` — delete `"api_key": ""` → TheMuse ~0 → ~99k searchable.
3. `jobpilot/integrations/sources/himalayas.py:33-40` — `companyName`/`pubDate` field fix → Himalayas 0 → jobs.
4. `ats_greenhouse.py` / `ats_lever.py` — delete ~34 dead board tokens; add Ashby adapter for the AI companies.
5. `jobpilot/agents/analysis/agent.py:95-101` — seniority: whole-word match on title only (biggest recall win in matching).
6. `jobpilot/agents/matching/agent.py:129` — remove `""` from the location list (+ bare-US patterns in `_is_us_only`).
7. `matching/agent.py:52-67` + `evaluator.py:166` — add missing role variants (ml engineer, genai, rag, nlp, prompt, fastapi/django).
8. `matching/agent.py:116` — `years_min <= 2` → `<= 3`.
9. `normalization/agent.py:110` — canonical ID: include location + description hash.
10. `jobpilot/integrations/sources/base.py:20` — `max_retries = 1` → `3`; stop swallowing in `fetch()`.
11. `harvest_linkedin_posts.py` — fix `"y" in token` year-branch ordering; FRESH ≤14d → ≤5d.
12. `production_batch_run.py` — freshness ≤30d for portals; fix `parse_iso_datetime` tz truncation (`datetime.fromisoformat`).
13. `jobpilot/services/auto_apply.py:1272/1304` — route `mailto:` to the SMTP email flow (~5 lines); unblocks an entire apply channel.
14. `jobpilot/services/auto_apply.py:1175-1187` — allow retry of `SUBMISSION_UNCONFIRMED`/`FAILED`.
15. `run_frozen_batch_apply.py:7,16` + `submission_verifier.py:144` + `candidate.py` — repo-root-relative paths.
16. Sync stale constants: "0-2 years"→"1-3" (`config.py`, `application_engine.py`, `unified_model.py`); salary →$10–40/hr (`candidate.py`, `matching/agent.py`, `pipeline.py`); PKR/Rs currency mapping (`normalization/agent.py`); EMEA/India eligibility scoping (`eligibility.py`).
17. Delete the stub `LinkedInSubmitter`/`IndeedSubmitter` in `application_engine.py` (or raise `NotImplementedError`) — stops fake "submitted" results.
18. Consolidate requirements; move secrets to `.env` and rotate the keys.
