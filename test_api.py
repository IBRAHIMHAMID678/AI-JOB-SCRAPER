import requests
import time

print("Starting pipeline...")
res = requests.post('http://localhost:8000/api/start')
print(res.json())

# Stream events
res = requests.get('http://localhost:8000/api/stream', stream=True)
for line in res.iter_lines():
    if line:
        line_str = line.decode('utf-8')
        print(line_str)
        if "DONE" in line_str:
            break

print("Pipeline finished. Attempting to download CSV...")
time.sleep(1)
csv_res = requests.get('http://localhost:8000/api/download')
print("Status Code:", csv_res.status_code)
print("Headers:", csv_res.headers)
print("Content:", csv_res.text[:200])
