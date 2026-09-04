import sys
import time

sys.path.insert(0, r"d:\Job Scraper")
from playwright.sync_api import sync_playwright

job_url = "https://boards.greenhouse.io/figma/jobs/6158162004?gh_jid=6158162004"
cv_path = r"d:\Job Scraper\jobpilot\uploads\cvs\Ibrahim_Hamid_Resume.pdf"

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
    page.screenshot(path=r"C:\Users\dell\.gemini\antigravity-ide\brain\4b5de1eb-7dd1-48bc-8e19-b10758268b46\screenshots\live_figma_form_proof.png")
    b.close()
    print("Focused form screenshot captured successfully!")
