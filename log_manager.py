import queue

# Queues for SSE streaming
log_queue = queue.Queue()
job_queue = queue.Queue()
pending_job_queue = queue.Queue()

def log(msg):
    msg_str = str(msg)
    try:
        # Avoid UnicodeEncodeError on Windows CP1252 console and force flush
        print(msg_str.encode('cp1252', errors='replace').decode('cp1252'), flush=True)
    except Exception:
        try:
            print(msg_str.encode('ascii', errors='replace').decode('ascii'), flush=True)
        except Exception:
            pass
    log_queue.put(msg_str)

def emit_job(job):
    job_queue.put(job)

def emit_pending_job(job):
    pending_job_queue.put(job)
