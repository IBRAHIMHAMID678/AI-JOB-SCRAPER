# New Job-Board Sources — 2026-10-14

2 new working sources added to the scraper (`sources_extra.py`, registered in
`sources.py` SOURCES, added to `run.py --sources` default list).

## Added

### talenthubsol (tested: 100 jobs)
- What: TalentHubSol (talenthubsol.com) — Pakistan job portal on WordPress.
- How: public WP REST API, `noo_job` post type, `?per_page=100` (no auth).
- Coverage: mostly Lahore/Islamabad onsite + some remote; company parsed from
  titles ("Role required at Company"); city detection for 12 PK cities; PKR
  salary parsed from descriptions (monthly).
- Sample: "Graphic Designer plus Video editor" @ Giga Sol, Lahore, posted today.

### indeed_pk (tested: 90 jobs)
- What: Indeed Pakistan listings via jobspy (same pattern as existing `linkedin` source).
- How: 5 search terms, 7-day freshness, `country_indeed="Pakistan"`.
- Note: upstream `apis.indeed.com` is flaky (one ReadTimeout seen); per-term
  try/except returns [] on error, never crashes the run.
- Sample: "AI/ML Engineer" @ Kwick High Tech & Solutions, Islamabad, posted today.

## Probe results (dropped candidates)

~45 endpoints probed from `job-boards.md`. Dropped with reasons:
- **No public feed/API found**: rozee.pk, mustakbil.com (Angular SPAs), brightspyre
  (also account-gated), dynamitejobs.com, jobgether.com, skipthedrive.com,
  simplify.jobs, underdog.io, stillhiring.today, remote_rocketship.com, cord,
  otta, producthunt (OAuth), role_rasta (signup + paid pass).
- **Bot walls / errors**: paperpk.com (403), indiehackers (403), betalist (403),
  web3.career (403), cryptocurrencyjobs.co (403), nodesk.co (403), curaiz (403),
  remotehub.com (refused), remote.co (timeouts), flexjobs (paywall/timeout).
- **Blog feeds, no job items**: trulyremote.co RSS, authenticjobs.com RSS,
  euremotejobs, gun.io RSS, smashingmagazine jobs RSS.
- **Empty feeds**: jobspresso.co (0 items), startup.jobs (404), techstars (404).
- **Stale data**: career_vault.io API works but newest listing is 2026-07-30.
- **Subset of existing sources**: wwr category RSS, himalayas RSS.
- **glassdoor via jobspy**: "Glassdoor is not available for PAKISTAN".

## Files changed
- `sources_extra.py` (new) — the 2 adapters + dropped-candidate notes in docstring.
- `sources.py` — registers `sources_extra.FETCHERS` into SOURCES.
- `run.py` — added `talenthubsol,indeed_pk` to `--sources` default.

## Notes
- No changes to filter/rank/dedup. `applied.json` and `results/` untouched.
- Smoke-tested through `run.scrape()`: 190 jobs, 0 errors, schema valid.
- No git repo exists under the workspace — changes left in working tree (no commit possible).
