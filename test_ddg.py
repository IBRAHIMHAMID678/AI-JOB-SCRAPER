import urllib.request
import urllib.parse
import re

query = 'site:linkedin.com/posts "AI Engineer" hiring remote'
url = 'https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(query)
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        uddg_matches = re.findall(r'uddg=([^&]+)', html)
        found = []
        for u in uddg_matches:
            target = urllib.parse.unquote(u)
            if 'linkedin.com/posts/' in target:
                clean = target.split('?')[0].rstrip('/')
                found.append(clean)
        print(f"DDG found {len(found)} LinkedIn posts:")
        for f in found[:10]:
            print(" -", f)
except Exception as e:
    print("DDG Error:", e)
