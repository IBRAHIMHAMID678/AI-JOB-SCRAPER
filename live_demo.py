import os
import sys
import time

sys.path.insert(0, r"d:\Job Scraper")

from playwright.sync_api import sync_playwright
from jobpilot.services.auto_apply import _candidate, _fill_all_form_fields

job_url = "https://boards.greenhouse.io/figma/jobs/6158162004?gh_jid=6158162004"
candidate = _candidate()
cv_path = r"d:\Job Scraper\jobpilot\uploads\cvs\Ibrahim_Hamid_Resume.pdf"

print("=" * 60)
print("  LAUNCHING LIVE VISIBLE BROWSER FOR AUTO-APPLY DEMO")
print("=" * 60)
print(f"Target Role: Forward Deployed Engineer @ Figma")
print(f"Candidate:   {candidate['full_name']} ({candidate['email']})")
print(f"Resume:      {cv_path}")
print(f"URL:         {job_url}")
print("-" * 60)

with sync_playwright() as p:
    # Launch Chromium in non-headless mode so the window pops up on your screen
    print("[1/5] Launching visible browser window on your desktop...")
    browser = p.chromium.launch(headless=False, slow_mo=100)
    context = browser.new_context(viewport={"width": 1280, "height": 850})
    page = context.new_page()

    print("[2/5] Navigating to Greenhouse job application form...")
    page.goto(job_url, timeout=30000, wait_until="domcontentloaded")
    time.sleep(2.0)

    print("[3/5] Starting intelligent form inspection and field filling...")
    # Scroll smoothly to form
    page.evaluate("window.scrollTo(0, 400)")
    time.sleep(1.0)

    filled = _fill_all_form_fields(page, candidate, cv_path)
    print(f"[4/5] Successfully filled {filled} form fields live on screen!")

    # Scroll down to show completed fields and attached resume
    print("Scrolling down to show completed fields...")
    for offset in [600, 1000, 1400]:
        page.evaluate(f"window.scrollTo(0, {offset})")
        time.sleep(1.5)

    print("[5/5] Keeping the browser window open for 15 seconds so you can see it...")
    time.sleep(15.0)

    browser.close()
    print("=" * 60)
    print("  LIVE DEMO COMPLETED SUCCESSFULLY")
    print("=" * 60)
