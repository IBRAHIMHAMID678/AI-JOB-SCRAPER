import urllib.request
import urllib.parse
import re
import time

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
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

all_found = set()

for idx, q in enumerate(queries):
    if len(all_found) >= 120:
        break
    url = f"https://search.yahoo.com/search?p={urllib.parse.quote(q)}"
    success = False
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                ru_matches = re.findall(r'RU=([^/]+)/RK', html)
                new_in_query = 0
                for ru in ru_matches:
                    unquoted = urllib.parse.unquote(ru)
                    if 'linkedin.com/posts/' in unquoted:
                        clean_url = unquoted.split('?')[0].rstrip('/')
                        if clean_url not in all_found:
                            all_found.add(clean_url)
                            new_in_query += 1
                print(f"[{idx+1}/{len(queries)}] Query '{q[:35]}...' -> +{new_in_query} (Total: {len(all_found)})")
                success = True
                break
        except Exception as e:
            time.sleep(2.0)
    if not success:
        print(f"[{idx+1}/{len(queries)}] Query '{q[:35]}...' -> Failed after retries")
    time.sleep(2.0)

print(f"\nDiscovered {len(all_found)} unique LinkedIn post URLs.")
with open("discovered_linkedin_urls.txt", "w", encoding="utf-8") as f:
    for u in all_found:
        f.write(u + "\n")
print("Saved to discovered_linkedin_urls.txt")
