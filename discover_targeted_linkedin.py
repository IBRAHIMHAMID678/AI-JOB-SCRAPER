"""
Targeted LinkedIn post URL discovery via Yahoo search (AI/ML/Python angles).

Hardened 2026-09-27:
- Same Yahoo hardening as discover_urls.py: multiple redirect-URL patterns,
  retries with backoff + rotated user agents, LOUD warnings on zero results.
- Posted <=5d pre-check at discovery via LinkedIn activity snowflake decode —
  applied to BOTH newly discovered URLs and the existing pool
  (discovered_linkedin_urls.txt was 24-82 days stale on 2026-09-27).
- Fresher query angles added.
"""
import urllib.request
import urllib.parse
import re
import time
import random
import os
from datetime import datetime, timezone

MAX_POST_AGE_DAYS = 5  # user rule: LinkedIn freshness <= 5 days

queries = [
    # AI / ML / LLM
    'site:linkedin.com/posts "AI Engineer" "hiring"',
    'site:linkedin.com/posts "Machine Learning Engineer" "hiring"',
    'site:linkedin.com/posts "Generative AI" "hiring"',
    'site:linkedin.com/posts "LLM Engineer" "hiring"',
    'site:linkedin.com/posts "RAG" "AI" "hiring"',
    'site:linkedin.com/posts "AI Developer" "hiring"',
    # Python / Backend
    'site:linkedin.com/posts "Python Developer" "hiring" remote',
    'site:linkedin.com/posts "FastAPI" "hiring"',
    'site:linkedin.com/posts "Backend Developer" "Python" "hiring"',
    'site:linkedin.com/posts "Django" "FastAPI" "hiring"',
    # Full Stack / Frontend
    'site:linkedin.com/posts "Full Stack Developer" "hiring" remote',
    'site:linkedin.com/posts "Next.js" "hiring" remote',
    'site:linkedin.com/posts "React Developer" "hiring" remote',
    'site:linkedin.com/posts "MERN Developer" "hiring"',
    # Location / Pakistan / Islamabad
    'site:linkedin.com/posts "Software Engineer" hiring "Islamabad"',
    'site:linkedin.com/posts "AI Engineer" hiring "Pakistan"',
    'site:linkedin.com/posts "Python Developer" hiring "Rawalpindi"',
    'site:linkedin.com/posts "Full Stack" hiring "Islamabad"',
    'site:linkedin.com/posts "developer" hiring "Pakistan" remote',
    # ── Fresher angles (pay/urgency/recency signals beat index lag) ──
    'site:linkedin.com/posts "hiring" "AI Engineer" remote "$" "per hour"',
    'site:linkedin.com/posts "hiring" "ML Engineer" remote "apply now"',
    'site:linkedin.com/posts "urgent hiring" "python developer" remote',
    'site:linkedin.com/posts "hiring" "prompt engineer" remote',
    'site:linkedin.com/posts "immediate joiner" "AI" OR "ML" remote',
    'site:linkedin.com/posts "we are hiring" "backend developer" "Pakistan" remote',
    'site:linkedin.com/posts "hiring" "software engineer" remote "2026" "apply"',
    'site:linkedin.com/posts "looking for" "full stack" remote "contract" "$"',
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
        r'/RU=([^"\']+?)/RK[=;&]',
        r'RU=([^"\']+?)/RK=',
    ]
    for pat in patterns:
        for ru in re.findall(pat, html):
            try:
                unquoted = urllib.parse.unquote(ru)
            except Exception:
                continue
            if 'linkedin.com/posts/' in unquoted:
                found.append(unquoted.split('?')[0].rstrip('/'))
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
    for bare in re.findall(r'https?://(?:www\.)?linkedin\.com/posts/activity-\d+[\w\-/]*', html):
        found.append(bare.split('?')[0].rstrip('/'))
    seen, out = set(), []
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def fetch_yahoo(query):
    """Fetch one Yahoo query with retries, backoff, rotated UA. Returns (urls, error)."""
    url = 'https://search.yahoo.com/search?p=' + urllib.parse.quote(query)
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': random.choice(USER_AGENTS)})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
            return extract_linkedin_urls(html), None
        except Exception as e:
            last_err = e
            time.sleep(2.0 * (attempt + 1) + random.uniform(0, 1.0))
    return [], last_err


def main():
    txt_path = "discovered_linkedin_urls.txt"
    discovered = set()
    stale_dropped = 0

    # Load existing pool — and re-verify freshness (the pool was 24-82d stale)
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "linkedin.com/posts/" in line:
                    if is_fresh_post(line):
                        discovered.add(line)
                    else:
                        stale_dropped += 1
        print(f"Loaded pool from {txt_path}: kept {len(discovered)} fresh, "
              f"dropped {stale_dropped} as >{MAX_POST_AGE_DAYS}d old")

    zero_result_queries = 0
    for q in queries:
        urls, err = fetch_yahoo(q)
        if err is not None:
            zero_result_queries += 1
            print(f"Query: {q[:32]}... -> YAHOO BLOCKED/FAILED after retries: {err}")
        elif not urls:
            zero_result_queries += 1
            print(f"Query: {q[:32]}... -> WARNING: 0 URLs extracted (Yahoo markup change or bot block?)")
        else:
            new_in_query = 0
            for u in urls:
                if u in discovered:
                    continue
                if not is_fresh_post(u):
                    stale_dropped += 1
                    continue
                discovered.add(u)
                new_in_query += 1
            print(f"Query: {q[:32]}... -> +{new_in_query} fresh (Total unique: {len(discovered)})")
        time.sleep(1.2 + random.uniform(0, 1.0))

    if zero_result_queries:
        print(f"WARNING: {zero_result_queries}/{len(queries)} queries yielded zero results — "
              f"Yahoo is likely bot-blocking; the pool may go stale.")

    # Final freshness sweep before saving
    final = {u for u in discovered if is_fresh_post(u)}
    dropped_final = len(discovered) - len(final)
    with open(txt_path, "w", encoding="utf-8") as f:
        for u in sorted(final):
            f.write(u + "\n")

    print(f"\nFinal saved discovered URLs count: {len(final)} into {txt_path} "
          f"(dropped {dropped_final} stale in final sweep)")


if __name__ == "__main__":
    main()
