import urllib.request
import urllib.parse
import re
import time

queries = [
    'site:linkedin.com/posts "AI Engineer" hiring remote',
    'site:linkedin.com/posts "Python Developer" hiring remote',
    'site:linkedin.com/posts "FastAPI" hiring',
    'site:linkedin.com/posts "Machine Learning Engineer" hiring Pakistan',
    'site:linkedin.com/posts "Full Stack Developer" hiring Islamabad',
    'site:linkedin.com/posts "Next.js" hiring remote',
]

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
found = set()

for q in queries:
    url = f"https://search.yahoo.com/search?p={urllib.parse.quote(q)}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            ru_matches = re.findall(r'RU=([^/]+)/RK', html)
            for ru in ru_matches:
                unquoted = urllib.parse.unquote(ru)
                if 'linkedin.com/posts/' in unquoted:
                    clean = unquoted.split('?')[0].rstrip('/')
                    found.add(clean)
        print(f"Query '{q[:35]}' -> total unique so far: {len(found)}")
    except Exception as e:
        print(f"Query error '{q[:35]}': {e}")
    time.sleep(1)

print(f"\nTotal discovered: {len(found)}")
for u in list(found)[:10]:
    print("  ", u)
