# config.py

import os
import sys
import tempfile
from dotenv import load_dotenv

load_dotenv()

# Explicitly isolate all caches, temp files, and browser data to D: drive (.cache)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, ".cache")
TEMP_DIR = os.path.join(CACHE_DIR, "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

# OS Temp redirection (stops C:\Users\...\AppData\Local\Temp writes)
os.environ["TEMP"] = TEMP_DIR
os.environ["TMP"] = TEMP_DIR
os.environ["TMPDIR"] = TEMP_DIR
tempfile.tempdir = TEMP_DIR

# Playwright & Browser cache redirection
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(CACHE_DIR, "ms-playwright")

# AI / ML library cache redirection away from C: drive
os.environ["XDG_CACHE_HOME"] = CACHE_DIR
os.environ["HF_HOME"] = os.path.join(CACHE_DIR, "huggingface")
os.environ["TORCH_HOME"] = os.path.join(CACHE_DIR, "torch")

# Prevent writing .pyc files to disk
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

# API Keys (loaded from environment — see .env.example; never commit real values)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Scraping Settings
# Item 15: junk terms "Remote Developer UK" / "Software Engineer Remote" removed;
# missing terms added.
SEARCH_TERMS = [
    "Junior AI Engineer",
    "Junior Python Developer",
    "Junior Backend Developer",
    "Junior Full Stack Developer",
    "AI Engineer",
    "LLM Engineer",
    "RAG Engineer",
    "RAG",
    "ML Engineer",
    "Python AI Developer",
    "Python Developer",
    "Backend Developer",
    "Node.js",
    "AI Full Stack Developer",
    "Full Stack Developer",
    "FastAPI Developer",
    "Python Backend Developer",
]
RESULTS_PER_TERM = 15
HOURS_OLD = 24  # Freshness: jobs posted within the last 24 hours

# AI Evaluation Settings
OPENROUTER_MODEL = "google/gemini-2.5-flash"
RATE_LIMIT_DELAY = 1

# Disk Cache Settings
EVAL_CACHE_FILE = os.path.join(CACHE_DIR, "eval_cache.json")

# Target Profile Details
CANDIDATE_PROFILE = """
Computer Science graduate (2026), Junior Software Engineer / AI Engineer skilled in 
Python (FastAPI, Django, Flask), React, Next.js, Node.js, NestJS, LangChain, RAG, vector databases (MongoDB Atlas), 
and LLM integration. Looking for Remote, USD/GBP pay, 1-3 years experience roles,
specifically AI Engineer, AI Full Stack Developer, Full Stack Developer, or Backend Engineer.
Candidate is based in Pakistan and accepts Worldwide Remote / Work from Anywhere / Remote in Pakistan / UK Remote.
"""
