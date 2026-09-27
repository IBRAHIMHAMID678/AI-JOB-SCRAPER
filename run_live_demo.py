import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import sync_playwright

job_url = "https://boards.greenhouse.io/figma/jobs/6158162004?gh_jid=6158162004"
cv_path = REPO_ROOT / "jobpilot" / "uploads" / "cvs" / "Ibrahim_Hamid_Resume.pdf"

print("=" * 65)
print("   JOBPILOT LIVE AUTO-APPLICATION DEMO")
print("=" * 65)
print(f"Candidate:  Ibrahim Hamid")
print(f"Email:      ibrahimhamid.2600@gmail.com")
print(f"Phone:      +92 318 0584128")
print(f"Resume:     {cv_path}")
print(f"Role:       Forward Deployed Engineer @ Figma")
print(f"Target URL: {job_url}")
print("-" * 65)

with sync_playwright() as p:
    print("[1/5] Launching visible browser window...")
    browser = p.chromium.launch(headless=False, slow_mo=120)
    context = browser.new_context(viewport={"width": 1280, "height": 880})
    page = context.new_page()

    print("[2/5] Navigating to Figma Greenhouse application page...")
    page.goto(job_url, timeout=35000, wait_until="domcontentloaded")
    time.sleep(2.0)

    print("[3/5] Inspecting & filling applicant details live...")
    # Scroll smoothly to form
    page.evaluate("window.scrollTo({ top: 350, behavior: 'smooth' })")
    time.sleep(1.0)

    # First Name
    fn = page.locator("input[aria-label*='First Name'], input[id*='first_name']")
    if fn.count() > 0:
        fn.first.click()
        fn.first.fill("Ibrahim")
        print("  -> Filled First Name: Ibrahim")
        time.sleep(0.5)

    # Last Name
    ln = page.locator("input[aria-label*='Last Name'], input[id*='last_name']")
    if ln.count() > 0:
        ln.first.click()
        ln.first.fill("Hamid")
        print("  -> Filled Last Name: Hamid")
        time.sleep(0.5)

    # Email
    em = page.locator("input[aria-label*='Email'], input[id*='email']")
    if em.count() > 0:
        em.first.click()
        em.first.fill("ibrahimhamid.2600@gmail.com")
        print("  -> Filled Email: ibrahimhamid.2600@gmail.com")
        time.sleep(0.5)

    # Phone
    ph = page.locator("input[aria-label*='Phone'], input[id*='phone'], input[type='tel']")
    if ph.count() > 0:
        ph.first.click()
        ph.first.fill("+923180584128")
        print("  -> Filled Phone: +923180584128")
        time.sleep(0.5)

    # Location
    loc = page.locator("input[aria-label*='Location'], input[id*='location'], input[placeholder*='city']")
    if loc.count() > 0:
        loc.first.click()
        loc.first.fill("Islamabad, Pakistan")
        print("  -> Filled Location: Islamabad, Pakistan")
        time.sleep(0.5)

    # Resume File Upload
    print("[4/5] Uploading Resume PDF...")
    file_inputs = page.locator("input[type='file']")
    if file_inputs.count() > 0:
        file_inputs.first.set_input_files(cv_path)
        print("  -> Attached Resume: Ibrahim_Hamid_Resume.pdf")
        time.sleep(1.0)

    # Scroll down to show filled values & resume section
    print("[5/5] Scrolling down to show all completed fields on screen...")
    for y in [600, 900, 1200]:
        page.evaluate(f"window.scrollTo({{ top: {y}, behavior: 'smooth' }})")
        time.sleep(1.2)

    # Take screenshot proof
    screenshot_dir = REPO_ROOT / "jobpilot" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    shot_path = str(screenshot_dir / "live_demo_figma.png")
    page.screenshot(path=shot_path)
    print(f"Captured live screenshot proof: {shot_path}")

    print("\nBrowser is open on your screen! Keeping it open for 20 seconds...")
    time.sleep(20.0)

    browser.close()
    print("=" * 65)
    print("   LIVE DEMO FINISHED SUCCESSFULLY")
    print("=" * 65)
