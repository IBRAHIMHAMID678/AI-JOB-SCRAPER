from playwright.sync_api import sync_playwright
import urllib.parse
import re

queries = [
    'site:linkedin.com/posts "we are hiring" remote python',
    'site:linkedin.com/posts "hiring" "remote" "ai engineer"',
    'site:linkedin.com/posts "looking for" "developer" Islamabad',
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    for q in queries:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(q)}"
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        links = page.query_selector_all("li.b_algo h2 a")
        print(f"Query '{q}': found {len(links)} links")
        for l in links[:3]:
            href = l.get_attribute("href")
            txt = l.inner_text()
            print("  Href:", href[:80], "| Title:", txt[:60])
    browser.close()
