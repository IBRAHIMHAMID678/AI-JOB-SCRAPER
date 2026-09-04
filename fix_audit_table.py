import sqlite3

conn = sqlite3.connect('D:/Job Scraper/jobpilot.db')
c = conn.cursor()
c.execute("""
    UPDATE application_submission_audit 
    SET previous_status = 'SUBMITTED', classification = 'FAILED' 
    WHERE audited_status = 'SUBMISSION_UNVERIFIED'
""")
conn.commit()

c.execute("""
    SELECT previous_status, audited_status, classification, count(*) 
    FROM application_submission_audit 
    GROUP BY previous_status, audited_status, classification
""")
for row in c.fetchall():
    print(row)
conn.close()
