"""
LinkedIn post URL discovery via Yahoo search.

Hardened 2026-09-27:
- Yahoo actively bot-blocks (RemoteDisconnected); extraction now tries several
  redirect-URL patterns plus encoded/bare fallbacks, retries with backoff and
  rotated user agents, and logs LOUDLY when a query yields zero results.
- Posted <=5d pre-check at discovery: LinkedIn activity IDs are snowflakes —
  decode the post timestamp and drop posts older than 5 days (user rule)
  instead of letting the harvester nuke the whole pool later.
- Fresher query angles (pay/urgency/2026 signals) rotated in.
"""
import urllib.request
import urllib.parse
import re
import time
import random
from datetime import datetime, timezone

MAX_POST_AGE_DAYS = 5  # user rule: LinkedIn freshness <= 5 days

queries = [
    # Variations of tech + hiring
    'site:linkedin.com/posts "hiring" "remote" "python"',
    'site:linkedin.com/posts "we are hiring" "full stack" remote',
    'site:linkedin.com/posts "looking for" "developer" Islamabad',
    'site:linkedin.com/posts "hiring" "ai engineer" USD',
    'site:linkedin.com/posts "remote developer needed" python',
    'site:linkedin.com/posts "send your CV" "developer" remote',
    'site:linkedin.com/posts "apply here" "react" remote',
    'site:linkedin.com/posts "we are hiring" "Islamabad" developer',
    'site:linkedin.com/posts "looking for a" "fastapi" remote',
    'site:linkedin.com/posts "hiring" "software engineer" "USD"',
    'site:linkedin.com/posts "talent acquisition" "python" remote',
    'site:linkedin.com/posts "recruiter" "ai engineer" remote',
    'site:linkedin.com/posts "we are hiring" "frontend developer" remote',
    'site:linkedin.com/posts "hiring" "fullstack" GBP remote',
    'site:linkedin.com/posts "send your resume" "software engineer" remote',
    'site:linkedin.com/posts "looking for a developer" remote',
    'site:linkedin.com/posts "hiring" "LLM" remote',
    'site:linkedin.com/posts "we are hiring" "Rawalpindi" software',
    'site:linkedin.com/posts "hiring" "backend developer" remote',
    'site:linkedin.com/posts "open position" "python developer" remote',
    'site:linkedin.com/posts "we\'re hiring" "junior developer" remote',
    'site:linkedin.com/posts "hiring" "nextjs" remote',
    'site:linkedin.com/posts "hiring" "django" remote',
    'site:linkedin.com/posts "hiring" "machine learning" remote',
    'site:linkedin.com/posts "immediate joining" "developer" remote',
    'site:linkedin.com/posts "looking for" "intern" "software" remote',
    'site:linkedin.com/posts "hiring" "Pakistan" remote software',
    # ── Fresher angles (pay/urgency/recency signals beat index lag) ──
    'site:linkedin.com/posts "hiring" "AI Engineer" remote "$" "per hour"',
    'site:linkedin.com/posts "hiring" "ML Engineer" remote "apply"',
    'site:linkedin.com/posts "we are hiring" "RAG" OR "LLM" remote',
    'site:linkedin.com/posts "immediate joiner" "python developer" remote',
    'site:linkedin.com/posts "urgent hiring" "backend developer" remote',
    'site:linkedin.com/posts "hiring" "prompt engineer" remote',
    'site:linkedin.com/posts "hiring" "GenAI" OR "generative ai" remote',
    'site:linkedin.com/posts "looking for" "AI engineer" remote "$"',
    'site:linkedin.com/posts "hiring" "fastapi" OR "django" remote "2026"',
    'site:linkedin.com/posts "we are hiring" "software engineer" "Pakistan" "remote"',
    'site:linkedin.com/posts "hiring" "node.js" OR "nodejs" developer remote',
    'site:linkedin.com/posts "hiring" "data engineer" "python" remote',
    'site:linkedin.com/posts "contract" "AI engineer" remote "$"',
    'site:linkedin.com/posts "hiring" "full stack developer" remote "immediate"',
]

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


def get_linkedin_snowflake_datetime(url):
    """Decode a LinkedIn activity-N snowflake to its creation datetime (ground truth)."""
    m = re.search(r"activity-(\d+)", url)
    if not m:
        return None
    try:
        ts_ms = int(m.group(1)) >> 22
        return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    except Exception:
        return None


def is_fresh_post(url, max_days=MAX_POST_AGE_DAYS):
    """Pre-check: keep the URL unless its snowflake proves it is older than max_days."""
    dt = get_linkedin_snowflake_datetime(url)
    if dt is None:
        return True  # cannot prove stale — keep it for the harvester to judge
    return (datetime.now(timezone.utc) - dt).days <= max_days


def extract_linkedin_urls(html):
    """Hardened Yahoo redirect extraction: several patterns + encoded/bare fallbacks."""
    found = []
    patterns = [
        r'/RU=([^"\']+?)/RK[=;&]',  # Yahoo redirect: /RU=<pct-encoded>/RK=...
        r'RU=([^"\']+?)/RK=',       # variant without leading slash
    ]
    for pat in patterns:
        for ru in re.findall(pat, html):
            try:
                unquoted = urllib.parse.unquote(ru)
            except Exception:
                continue
            if 'linkedin.com/posts/' in unquoted:
                found.append(unquoted.split('?')[0].rstrip('/'))
    # Fallback: percent-encoded linkedin post URLs embedded in markup
    # (activity IDs are digits-only — stop there, never swallow trailing junk)
    for enc in re.findall(
        r'https?%3A%2F%2F(?:www\.)?linkedin\.com%2Fposts%2Factivity-\d+',
        html, re.IGNORECASE,
    ):
        try:
            unquoted = urllib.parse.unquote(enc)
        except Exception:
            continue
        if 'linkedin.com/posts/' in unquoted:
            found.append(unquoted.split('?')[0].rstrip('/'))
    # Last resort: bare linkedin post URLs visible in markup
    for bare in re.findall(r'https?://(?:www\.)?linkedin\.com/posts/activity-\d+[\w\-/]*', html):
        found.append(bare.split('?')[0].rstrip('/'))
    # Dedupe, preserve order
    seen, out = set(), []
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def fetch_yahoo(query):
    """Fetch one Yahoo query with retries, backoff, rotated UA. Returns (urls, error)."""
    url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}"
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': random.choice(USER_AGENTS)})
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
            return extract_linkedin_urls(html), None
        except Exception as e:
            last_err = e
            time.sleep(2.0 * (attempt + 1) + random.uniform(0, 1.0))
    return [], last_err


def main():
    all_found = set()
    stale_dropped = 0
    zero_result_queries = 0

    for idx, q in enumerate(queries):
        if len(all_found) >= 120:
            break
        urls, err = fetch_yahoo(q)
        if err is not None:
            zero_result_queries += 1
            print(f"[{idx+1}/{len(queries)}] Query '{q[:35]}...' -> YAHOO BLOCKED/FAILED after retries: {err}")
        elif not urls:
            zero_result_queries += 1
            # LOUD: zero results are never normal here — Yahoo markup changed or bot-blocked
            print(f"[{idx+1}/{len(queries)}] Query '{q[:35]}...' -> WARNING: 0 URLs extracted (Yahoo markup change or bot block?)")
        else:
            new_in_query = 0
            for u in urls:
                if u in all_found:
                    continue
                if not is_fresh_post(u):
                    stale_dropped += 1
                    continue
                all_found.add(u)
                new_in_query += 1
            print(f"[{idx+1}/{len(queries)}] Query '{q[:35]}...' -> +{new_in_query} fresh (Total: {len(all_found)})")
        time.sleep(2.0 + random.uniform(0, 1.5))

    print(f"\nDiscovered {len(all_found)} unique fresh LinkedIn post URLs.")
    print(f"Dropped {stale_dropped} URLs as >{MAX_POST_AGE_DAYS}d old (snowflake pre-check).")
    if zero_result_queries:
        print(f"WARNING: {zero_result_queries}/{len(queries)} queries yielded zero results — "
              f"Yahoo is likely bot-blocking; the pool may go stale.")
    with open("discovered_linkedin_urls.txt", "w", encoding="utf-8") as f:
        for u in sorted(all_found):
            f.write(u + "\n")
    print("Saved to discovered_linkedin_urls.txt")


if __name__ == "__main__":
    main()
