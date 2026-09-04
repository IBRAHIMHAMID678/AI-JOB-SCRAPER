import sys
from playwright.sync_api import sync_playwright

test_url = "https://www.linkedin.com/posts/farid-ullah-mahsud_i-am-looking-for-a-passionate-developer-to-activity-7398266306518716416-4EOZ"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    try:
        page.goto(test_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)
        title = page.title()
        content = page.inner_text("body")
        print(f"Page Title: {title}")
        print(f"Body length: {len(content)}")
        print("First 500 characters:")
        print(content[:500])
    except Exception as e:
        print(f"Playwright error: {e}")
    finally:
        browser.close()
