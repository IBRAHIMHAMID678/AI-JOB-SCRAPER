import queue

# Queues for SSE streaming
log_queue = queue.Queue()
job_queue = queue.Queue()

def log(msg):
    print(msg)
    log_queue.put(msg)

def emit_job(job):
    job_queue.put(job)
