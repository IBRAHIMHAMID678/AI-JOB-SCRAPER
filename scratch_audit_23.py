import csv
with open('linkedin_job_posts_100.csv', encoding='utf-8') as f:
    for i, r in enumerate(csv.DictReader(f)):
        fr = r.get('freshness_status')
        co = r.get('company')
        ti = r.get('job_title')
        loc = r.get('location')
        app_url = r.get('application_url') or r.get('application_email')
        fp = r.get('opportunity_fingerprint')
        print(f"{i+1:2d}. [{fr}] {co} -- {ti} -- {loc} -- {app_url} -- FP: {fp}")
