import pandas as pd
jobs = [{'title': 'Embedded Systems Engineer', 'match_score': 55}]
df = pd.DataFrame(jobs)
df.to_csv('remote_junior_jobs.csv', index=False)
print("CSV generated successfully")
