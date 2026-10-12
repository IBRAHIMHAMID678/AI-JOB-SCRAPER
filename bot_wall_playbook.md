# Bot-Wall Escalation Playbook (2026-10-11)

When a job site or application page hits a bot wall (Cloudflare, Turnstile,
"verify you are human", robot checks), escalate through this ladder instead of
skipping immediately. Analysis of 6 repos in subagent report 2026-10-11.

## Escalation ladder

1. **curl_cffi** (cheap first attempt) — TLS/JA3 fingerprint impersonation,
   requests-like API, no browser. Handles passive fingerprint checks only.
   `pip install curl_cffi`. Use for: fetching listing pages fast.

2. **Scrapling** (primary) — `Fetcher` (fast TLS-impersonated),
   `StealthyFetcher(solve_cloudflare=True)` for Turnstile/interstitial walls
   (the exact wall that blocked Glassdoor/Indeed/Himalayas),
   `DynamicFetcher` (Playwright) for form fill + submit. AutoThrottle +
   proxy rotation built in. BSD-3. `pip install Scrapling`.

3. **nodriver** (hardest interactive walls) — async CDP browser, no webdriver
   flags; `tab.cf_verify()` auto-clicks Cloudflare "verify you are human"
   checkboxes. For walls where a real browser is unavoidable.
   NOTE: AGPL-3.0 — fine for personal pipeline, constrains redistribution.

## Do NOT rely on

- **undetected-chromedriver** — dormant (last push 2025-07); author moved to nodriver.
- **cloudscraper** — stale 16 months; Cloudflare changes challenges continuously.

## Extraction layer

- **crawl4ai** — for turning listing pages into structured job data
  (Markdown + JSON schemas), not for bypass itself.

## Rules of engagement

- One escalation attempt per wall per run (don't hammer).
- Respect rate limits; AutoThrottle on.
- CAPTCHA image puzzles still need the user's one-attempt permission —
  tooling does not replace that rule.
- Never use these to evade an explicit access denial (account bans,
  login-required gates) — only for bot-detection false positives on public pages.

## Why single tools fail (webclaw.io analysis, 2026-10-11)

Cloudflare is a STACK, not one check: TLS fingerprint → HTTP/2 settings →
header order → JS challenge → behavioral analysis. Passing one layer doesn't
pass the others. This is exactly what our 2026-10-11 testing confirmed:
curl_cffi (TLS layer only) got 403s; only a real browser session clears the
JS-challenge layer. Key rules from the article:
- Detect challenge bodies — don't treat every 200 as success (we saw
  Glassdoor return 200 with a challenge page).
- Proxies don't fix fingerprints — rotating IPs with the same TLS fingerprint
  looks MORE suspicious, not less.
- CAPTCHA solvers alone are useless without maintaining the solved session's
  cookies + fingerprint on subsequent requests.
