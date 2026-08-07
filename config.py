# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Scraping Settings
SEARCH_TERMS = [
    "Junior AI Engineer",
    "Junior Full Stack Developer",
    "Junior Python Engineer"
]
RESULTS_PER_TERM = 10 # Limiting to 10 per term per platform for demo/rate limiting purposes

# AI Evaluation Settings
OPENROUTER_MODEL = "google/gemini-2.5-flash"  # Using a highly capable model
RATE_LIMIT_DELAY = 1  # OpenRouter handles concurrency much better

# Target Profile Details
CANDIDATE_PROFILE = """
Computer Science graduate (2026), Junior Software Engineer / AI Engineer skilled in 
Python (FastAPI), React, Next.js, Node.js, NestJS, LangChain, RAG, vector databases (MongoDB Atlas), 
and LLM integration. Looking for Remote, USD pay, 0-2 years experience roles, 
specifically AI Engineer or Full Stack Developer.
"""
