"""Live-browser apply-route verification for the job scraper.

The egress proxy rejects Chromium's own CONNECT requests
(ERR_TUNNEL_CONNECTION_FAILED), but plain Python sockets tunnel fine — so
headless Chromium runs through a local relay
(~/workspace/job_hunt/browser-relay/relay.py on 127.0.0.1:18924) which
forwards the browser's CONNECT via Python through $https_proxy.

This module manages the relay's lifecycle (spawns it if it isn't running),
renders each URL in headless Chromium, and classifies the page:

  live_apply  — an actionable apply button/link/form or a known ATS apply page
  dead        — 404 / "no longer available" / "position filled" style text
  signin_wall — apply requires sign-in / account creation
  bot_wall    — Cloudflare / CAPTCHA / "verify you are human" challenge
  uncertain   — anything else (never raises on a single bad URL)

Stdlib + playwright only. Import-safe: nothing runs until verify() or main().
"""

import os
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

RELAY_HOST = "127.0.0.1"
RELAY_PORT = 18924
RELAY_SCRIPT = os.path.expanduser("~/workspace/job_hunt/browser-relay/relay.py")

NAV_TIMEOUT_MS = 30000      # per-page navigation cap
SETTLE_S = 3                # wait for JS render after load
PAGE_BUDGET_S = 60          # worst-case per URL
MAX_WORKERS = 3

APPLY_TEXT_RE = re.compile(r"apply|submit application|submit your application", re.I)
ATS_DOMAINS = (
    "workable.com", "greenhouse.io", "boards.greenhouse.io", "lever.co",
    "ashbyhq.com", "careers-page.com", "workday", "myworkdayjobs.com",
    "icims.com", "jobvite.com", "breezy.hr", "recruitee.com", "teamtailor.com",
    "smartrecruiters.com", "jobs.ashbyhq.com",
)
DEAD_RE = re.compile(
    r"404|not found|no longer available|position (has been )?filled|"
    r"job (has |is )?(expired|closed|no longer)|this job (is |has been )?(closed|filled|expired)|"
    r"we couldn't find|page not found", re.I)
SIGNIN_RE = re.compile(
    r"sign in to apply|log ?in to apply|create an account to apply|"
    r"please (sign|log) in before applying", re.I)
LISTING_RE = re.compile(
    r"\d[\d,]*\s+(remote\s+)?(ai engineer|developer|engineering|software|design|marketing)\s+jobs?\s+(available|found)|"
    r"jobs?\s+available|browse\s+(all\s+)?jobs|job\s+(listings?|board)|"
    r"find\s+(your\s+)?(next|remote)\s+job", re.I)
BOTWALL_RE = re.compile(
    r"cloudflare|checking your browser|verify you are human|"
    r"attention required|captcha|access denied|are you a robot|"
    r"just a moment|performing security verification|ray id|"
    r"security service to protect against malicious bots|"
    r"verifying (you are|that you are) (human|not a bot)", re.I)


def relay_running() -> bool:
    """True if something is listening on 127.0.0.1:18924."""
    try:
        s = socket.create_connection((RELAY_HOST, RELAY_PORT), timeout=2)
        s.close()
        return True
    except OSError:
        return False


_relay_proc = None


def ensure_relay() -> None:
    """Start the relay as a child process if it isn't already listening.

    Keeps a single handle; safe to call repeatedly (never spawns duplicates).
    """
    global _relay_proc
    if relay_running():
        return
    if _relay_proc is not None and _relay_proc.poll() is None:
        return
    if not os.path.exists(RELAY_SCRIPT):
        raise RuntimeError(f"relay script not found: {RELAY_SCRIPT}")
    _relay_proc = subprocess.Popen(
        [sys.executable, RELAY_SCRIPT],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    for _ in range(50):  # wait up to ~5s for the port
        if relay_running():
            return
        time.sleep(0.1)
    raise RuntimeError("relay did not come up on 127.0.0.1:18924")


def _launch_browser(pw):
    return pw.chromium.launch(
        headless=True,
        args=[
            f"--proxy-server=http://{RELAY_HOST}:{RELAY_PORT}",
            "--ignore-certificate-errors",
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
        ])


def _check_one(url: str, pw) -> dict:
    """Verify a single URL inside the shared playwright instance."""
    started = time.time()
    browser = None
    try:
        browser = _launch_browser(pw)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"),
            viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        nav_err = None
        try:
            page.goto(url, wait_until="domcontentloaded",
                      timeout=NAV_TIMEOUT_MS)
        except Exception as e:
            # Navigation itself failed (timeout, reset). Don't bail: the page
            # may still hold partial content (e.g. a Cloudflare challenge
            # that never reaches domcontentloaded). Analyze what we have.
            nav_err = f"{type(e).__name__}"
        time.sleep(SETTLE_S)

        text = ""
        try:
            text = (page.inner_text("body") or "")[:20000]
        except Exception:
            pass
        final_url = page.url

        notes = []
        verdict = "uncertain"

        # 1. Known ATS apply page in the final URL?
        if any(d in final_url for d in ATS_DOMAINS):
            verdict = "live_apply"
            notes.append(f"ATS apply page: {final_url}")

        # 2. Bot wall?
        if BOTWALL_RE.search(text):
            return {"url": url, "verdict": "bot_wall",
                    "apply_url": final_url,
                    "notes": "bot/CAPTCHA challenge detected"}

        # 3. Dead page?
        if DEAD_RE.search(text):
            return {"url": url, "verdict": "dead",
                    "apply_url": final_url,
                    "notes": "dead-page markers in page text"}

        # 4. Sign-in wall?
        if SIGNIN_RE.search(text):
            return {"url": url, "verdict": "signin_wall",
                    "apply_url": final_url,
                    "notes": "apply requires sign-in/account"}

        # Second-chance re-read: bot walls sometimes render late. If nothing
        # matched, wait a bit more and re-analyze the text once.
        if verdict == "uncertain":
            time.sleep(5)
            try:
                text2 = (page.inner_text("body") or "")[:20000]
            except Exception:
                text2 = ""
            if text2 and text2 != text:
                text = text2
                if BOTWALL_RE.search(text):
                    return {"url": url, "verdict": "bot_wall",
                            "apply_url": page.url,
                            "notes": "bot/CAPTCHA challenge detected (late render)"}
                if DEAD_RE.search(text):
                    return {"url": url, "verdict": "dead",
                            "apply_url": page.url,
                            "notes": "dead-page markers in page text (late render)"}
                if SIGNIN_RE.search(text):
                    return {"url": url, "verdict": "signin_wall",
                            "apply_url": page.url,
                            "notes": "apply requires sign-in/account (late render)"}
        apply_url = None
        try:
            loc = page.locator("a, button, input[type=submit], input[type=button]")
            n = loc.count()
            for i in range(min(n, 60)):
                el = loc.nth(i)
                try:
                    label = (el.inner_text() or "") + " " + (el.get_attribute("aria-label") or "")
                    if APPLY_TEXT_RE.search(label):
                        href = el.get_attribute("href")
                        apply_url = href or final_url
                        notes.append(f"apply control: {label.strip()[:60]!r}")
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # Application form markers (file upload for resume)?
        has_file_input = False
        try:
            has_file_input = page.locator("input[type=file]").count() > 0
        except Exception:
            pass
        if has_file_input:
            notes.append("resume file-upload field present")

        if apply_url or (has_file_input and verdict == "uncertain"):
            verdict = "live_apply"
        if verdict == "live_apply" and not apply_url:
            apply_url = final_url

        if verdict == "uncertain":
            if not text.strip():
                notes.append(f"no page content (nav: {nav_err or 'ok'})")
            elif LISTING_RE.search(text):
                notes.append("live job-listing index page, not a direct apply route")
            else:
                notes.append("no apply control, form, or dead/wall markers found")
        elif nav_err:
            notes.append(f"partial load after nav {nav_err}")
        return {"url": url, "verdict": verdict,
                "apply_url": apply_url or (final_url if verdict == "live_apply" else None),
                "notes": "; ".join(notes) or "n/a"}
    except Exception as e:
        return {"url": url, "verdict": "uncertain",
                "apply_url": None, "notes": f"error: {type(e).__name__}: {e}"}
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        # hard per-URL budget guard (informational; executor moves on anyway)
        _ = time.time() - started


def verify(urls: list) -> dict:
    """Render each URL in headless Chromium and classify its apply route.

    Returns {url: {url, verdict, apply_url, notes}}. Never raises on a
    single bad URL — records 'uncertain' and continues.
    """
    urls = [u for u in urls if u]
    if not urls:
        return {}
    ensure_relay()
    from playwright.sync_api import sync_playwright

    results = {}

    def worker(url):
        with sync_playwright() as pw:
            return url, _check_one(url, pw)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for url, res in ex.map(worker, urls, timeout=len(urls) * PAGE_BUDGET_S):
            results[url] = res
    return results


def main(argv):
    urls = [a for a in argv if a.startswith("http")]
    if not urls:
        print("usage: verify_live.py <url> [url ...]")
        return 1
    out = verify(urls)
    for u in urls:
        r = out.get(u, {})
        print(f"[{r.get('verdict', '?')}] {u}")
        if r.get("apply_url") and r["apply_url"] != u:
            print(f"    apply: {r['apply_url']}")
        print(f"    notes: {r.get('notes', 'n/a')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
