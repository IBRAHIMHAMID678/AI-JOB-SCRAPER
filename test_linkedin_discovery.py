import urllib.request
import urllib.parse
import re

queries = [
    'site:linkedin.com/posts "hiring" "remote" "python"',
    'site:linkedin.com/posts "we are hiring" "full stack" remote',
    'site:linkedin.com/posts "looking for" "developer" Islamabad',
    'site:linkedin.com/posts "hiring" "ai engineer" USD',
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

all_found = set()

for q in queries:
    url = f"https://search.yahoo.com/search?p={urllib.parse.quote(q)}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            # Yahoo search results have r.search.yahoo.com/RU=.../RK=2/RS=...
            # inside RU is the target URL URL-encoded
            ru_matches = re.findall(r'RU=([^/]+)/RK', html)
            for ru in ru_matches:
                unquoted = urllib.parse.unquote(ru)
                if 'linkedin.com/posts/' in unquoted:
                    # Clean URL: strip tracking params
                    clean_url = unquoted.split('?')[0].rstrip('/')
                    all_found.add(clean_url)
    except Exception as e:
        print(f"Error querying Yahoo: {e}")

print(f"Total unique LinkedIn post URLs discovered: {len(all_found)}")
for u in list(all_found)[:10]:
    print(" -", u)
