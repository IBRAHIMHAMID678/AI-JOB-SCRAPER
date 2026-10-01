"""Assemble a top-20 job shortlist: pass/review first, then near-misses with caveats."""
import json, re, sys, datetime
sys.path.insert(0, '.')
from filter import filter_job
from rank import score
from run import load_applied
import sources, generic

DEV_TITLE = re.compile(r'\b(engineer|developer|programmer|full[\s-]?stack|backend|frontend|front[\s-]?end|back[\s-]?end|fullstack|software|swe|ai\b|ml\b|machine learning|data engineer|devops|sdet|qa automation)\b', re.I)
SENIOR = re.compile(r'\b(senior|sr\.?|staff|principal|lead|head of|director|vp|architect|manager)\b', re.I)
NONDEV = re.compile(r'\b(sales|marketing|support|customer|success|engagement|representative|designer|design engineer|electrical|mechanical|civil|account|hr|recruit|teacher|nurse|doctor|security|secops|detection|iam\b)\b', re.I)
REGION_LOCK = re.compile(r'\b(USA-only|US-only|US only|United States only|EU-only|Europe only|Canada only|UK only|Australia only)\b', re.I)
EXP = re.compile(r'(\d+)\s*\+?\s*(?:-|to|–)\s*(\d+)?\s*(?:years|yrs)', re.I)
EXP1 = re.compile(r'(\d+)\s*\+\s*(?:years|yrs)', re.I)

def near_miss(j):
    """Return (ok, caveats) for fail-pile salvage."""
    title = j.get('title') or ''
    desc = (j.get('description') or '')[:3000]
    loc = j.get('location') or ''
    if not DEV_TITLE.search(title): return False, []
    if SENIOR.search(title): return False, []
    if NONDEV.search(title): return False, []
    caveats = []
    # region
    if REGION_LOCK.search(loc + ' ' + desc[:500]): return False, []
    if re.search(r'\b(Portugal|Canada|Singapore|Ireland|Philippines|Malaysia)\b', loc) and 'remote' not in loc.lower():
        return False, []
    if j.get('remote') and not re.search(r'pakistan', loc + desc[:500], re.I):
        caveats.append('PK eligibility unverified')
    # experience
    exp = None
    m = EXP.search(title + ' ' + desc[:1500]) or EXP1.search(title + ' ' + desc[:1500])
    if m:
        lo = int(m.group(1)); hi = int(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else lo
        exp = (lo, hi)
        if lo >= 4: return False, []
        if hi and hi > 3: caveats.append(f'{lo}-{hi} yrs asked')
    # freshness
    posted = j.get('posted_at')
    if posted:
        try:
            dt = datetime.datetime.fromisoformat(str(posted))
            age = (datetime.datetime.now(datetime.timezone.utc) - dt).days
            if age > 30: return False, []
            if age > 14: caveats.append(f'posted {age}d ago')
        except Exception: pass
    else:
        caveats.append('posted date unknown')
    if re.search(r'\bexpert\b', title, re.I):
        caveats.append('title suggests senior level — verify')
    if re.search(r'\bmobile\b|\bios\b|\bandroid\b', title, re.I):
        return False, []
    # route
    if not (j.get('apply_email') or j.get('apply_url')):
        caveats.append('apply route needs check')
    return True, caveats

def collect_raw():
    jobs = []
    for name, fn in sources.SOURCES.items():
        try:
            for j in fn(): jobs.append(j)
        except Exception as e:
            print(f'  {name}: ERROR {e}', flush=True)
    import yaml
    tg = yaml.safe_load(open('targets.yaml'))
    for t in tg.get('targets', []):
        try:
            for j in generic.scrape_target(t): jobs.append(j)
        except Exception as e:
            print(f'  target {t.get("url")}: ERROR {e}', flush=True)
    return jobs

def main():
    applied = load_applied()
    raw = collect_raw()
    print(f'raw: {len(raw)}', flush=True)
    seen, cands, misses = set(), [], []
    for j in raw:
        key = f"{j.get('company')}|{j.get('title')}".lower()
        if key in applied or key in seen: continue
        seen.add(key)
        verdict, reasons = filter_job(j)
        sc, _ = score(j, reasons)
        if verdict in ('pass', 'review'):
            cands.append({'job': j, 'verdict': verdict, 'score': round(sc,1),
                          'reasons': reasons, 'caveats': []})
        else:
            ok, cav = near_miss(j)
            if ok:
                misses.append({'job': j, 'verdict': 'near-miss', 'score': round(sc,1),
                               'reasons': reasons, 'caveats': cav})
    # merge linkedin (expanded if ready, else earlier 5-term scrape)
    li = None
    for p in ('results/2026-09-28/linkedin_recs2.json', 'results/2026-09-28/linkedin_recs.json'):
        try:
            li = json.load(open(p)); print(f'linkedin from {p}', flush=True); break
        except FileNotFoundError:
            continue
    if li:
        for r in li:
            j = r['job']
            key = f"{j.get('company')}|{j.get('title')}".lower()
            if key in applied or key in seen: continue
            seen.add(key)
            if r['verdict'] in ('pass', 'review'):
                cands.append({'job': j, 'verdict': r['verdict'], 'score': r['score'],
                              'reasons': r['reasons'], 'caveats': []})
            else:
                ok, cav = near_miss(j)
                if ok:
                    cav = cav + ['check apply route on LinkedIn']
                    misses.append({'job': j, 'verdict': 'near-miss', 'score': r['score'],
                                   'reasons': r['reasons'], 'caveats': cav})
    else:
        print('no linkedin recs file ready', flush=True)
    # rank: pass/review by score, then near-miss by score
    cands.sort(key=lambda x: -x['score'])
    misses.sort(key=lambda x: -x['score'])
    final = cands + misses
    final = final[:20]
    json.dump(final, open('results/2026-09-28/top20.json', 'w'), indent=1, default=str)
    print(f'\nTOP {len(final)} (solid={len(cands)}, near-miss={len([f for f in final if f["verdict"]=="near-miss"])})', flush=True)
    for i, r in enumerate(final, 1):
        j = r['job']
        tag = 'SOLID' if r['verdict'] in ('pass','review') else 'NEAR-MISS'
        print(f"{i}. [{tag}] {j['title'][:52]} @ {j['company'][:26]}", flush=True)
        print(f"   {j['source']} | {(j['location'] or '')[:38]} | {j['url'][:80]}", flush=True)
        if r['caveats']: print(f"   caveats: {'; '.join(r['caveats'])}", flush=True)

if __name__ == '__main__':
    main()
