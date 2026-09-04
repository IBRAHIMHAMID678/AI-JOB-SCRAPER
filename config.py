# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Scraping Settings
SEARCH_TERMS = [
    "AI Engineer",
    "LLM Engineer",
    "RAG Engineer",
    "Python AI Developer",
    "AI Full Stack Developer",
    "Full Stack Developer",
    "FastAPI Developer",
    "Python Backend Developer",
    "Remote Developer UK",
    "Software Engineer Remote"
]
RESULTS_PER_TERM = 15

# AI Evaluation Settings
OPENROUTER_MODEL = "google/gemini-2.5-flash"
RATE_LIMIT_DELAY = 1

# Disk Cache Settings
EVAL_CACHE_FILE = "eval_cache.json"

# Target Profile Details
CANDIDATE_PROFILE = """
Computer Science graduate (2026), Junior Software Engineer / AI Engineer skilled in 
Python (FastAPI, Django, Flask), React, Next.js, Node.js, NestJS, LangChain, RAG, vector databases (MongoDB Atlas), 
and LLM integration. Looking for Remote, USD/GBP pay, 0-2 years experience roles, 
specifically AI Engineer, AI Full Stack Developer, Full Stack Developer, or Backend Engineer.
Candidate is based in Pakistan and accepts Worldwide Remote / Work from Anywhere / Remote in Pakistan / UK Remote.
"""
