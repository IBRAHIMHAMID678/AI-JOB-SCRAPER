import urllib.request
import urllib.parse
import re
import time
import os

queries = [
    # AI / ML / LLM
    'site:linkedin.com/posts "AI Engineer" "hiring"',
    'site:linkedin.com/posts "Machine Learning Engineer" "hiring"',
    'site:linkedin.com/posts "Generative AI" "hiring"',
    'site:linkedin.com/posts "LLM Engineer" "hiring"',
    'site:linkedin.com/posts "RAG" "AI" "hiring"',
    'site:linkedin.com/posts "AI Developer" "hiring"',
    # Python / Backend
    'site:linkedin.com/posts "Python Developer" "hiring" remote',
    'site:linkedin.com/posts "FastAPI" "hiring"',
    'site:linkedin.com/posts "Backend Developer" "Python" "hiring"',
    'site:linkedin.com/posts "Django" "FastAPI" "hiring"',
    # Full Stack / Frontend
    'site:linkedin.com/posts "Full Stack Developer" "hiring" remote',
    'site:linkedin.com/posts "Next.js" "hiring" remote',
    'site:linkedin.com/posts "React Developer" "hiring" remote',
    'site:linkedin.com/posts "MERN Developer" "hiring"',
    # Location / Pakistan / Islamabad
    'site:linkedin.com/posts "Software Engineer" hiring "Islamabad"',
    'site:linkedin.com/posts "AI Engineer" hiring "Pakistan"',
    'site:linkedin.com/posts "Python Developer" hiring "Rawalpindi"',
    'site:linkedin.com/posts "Full Stack" hiring "Islamabad"',
    'site:linkedin.com/posts "developer" hiring "Pakistan" remote',
]

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
discovered = set()

# Load existing discovered URLs first
txt_path = "discovered_linkedin_urls.txt"
if os.path.exists(txt_path):
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and "linkedin.com/posts/" in line:
                discovered.add(line)
print(f"Loaded {len(discovered)} existing URLs from {txt_path}")

for q in queries:
    url = 'https://search.yahoo.com/search?p=' + urllib.parse.quote(q)
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            ru_matches = re.findall(r'RU=([^/]+)/RK', html)
            for ru in ru_matches:
                unquoted = urllib.parse.unquote(ru)
                if 'linkedin.com/posts/' in unquoted:
                    clean = unquoted.split('?')[0].rstrip('/')
                    discovered.add(clean)
        print(f"Query: {q[:32]}... -> Total unique: {len(discovered)}")
    except Exception as e:
        print(f"Query error '{q[:32]}': {e}")
    time.sleep(1.2)

# Save merged discovered URLs
with open(txt_path, "w", encoding="utf-8") as f:
    for u in sorted(discovered):
        f.write(u + "\n")

print(f"\nFinal saved discovered URLs count: {len(discovered)} into {txt_path}")
