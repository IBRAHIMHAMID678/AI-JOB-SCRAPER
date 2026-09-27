import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
from playwright.sync_api import sync_playwright

job_url = "https://boards.greenhouse.io/figma/jobs/6158162004?gh_jid=6158162004"
cv_path = REPO_ROOT / "jobpilot" / "uploads" / "cvs" / "Ibrahim_Hamid_Resume.pdf"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={"width": 1280, "height": 850})
    page.goto(job_url, timeout=30000)

    # Fill fields with exact IDs
    page.locator("#first_name").fill("Ibrahim")
    page.locator("#last_name").fill("Hamid")
    page.locator("#email").fill("ibrahimhamid.2600@gmail.com")
    page.locator("#phone").fill("+923180584128")

    # Upload Resume
    f = page.locator("input[type='file']")
    if f.count() > 0:
        f.first.set_input_files(cv_path)

    time.sleep(1.0)
    page.locator("#first_name").scroll_into_view_if_needed()
    time.sleep(1.0)
    screenshot_dir = REPO_ROOT / "jobpilot" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot_dir / "live_figma_form_proof.png"))
    b.close()
    print("Focused form screenshot captured successfully!")
