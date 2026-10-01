"""Ibrahim's encoded job requirements — the rules engine for the auto-scraper.

Mirrors his standing rules (as of 2026-09-28). Update here when he changes them.
"""
from __future__ import annotations

# ---- Role matching -----------------------------------------------------------
ROLE_KEYWORDS = [
    "ai engineer", "artificial intelligence engineer", "ml engineer",
    "machine learning engineer", "llm engineer", "rag engineer",
    "genai engineer", "generative ai engineer", "prompt engineer",
    "nlp engineer", "ai developer", "ml developer", "ai/ml engineer",
    "python developer", "python engineer", "backend developer",
    "full stack developer", "full-stack developer", "fullstack",
    "software engineer", "software developer", "ai agent",
    "agentic ai", "langchain", "llama", "retrieval-augmented",
    "rag pipeline", "vector database",
]

# Titles that are never his target roles, even if the description mentions AI.
# Checked before role relevance so "AI" in a sales job's description can't qualify it.
NON_DEV_TITLE_PATTERNS = [
    "sales", "sdr", "account executive", "business development", "consultant",
    "consulting", "analyst", "recruiter", "recruitment", "talent acquisition",
    "marketing", "seo", "designer", "writer", "content writer", "accountant",
    "bookkeeper", "finance", "customer success", "customer support",
    "support specialist", "tutor", "teacher", "instructor", "driver",
    "security", "devops", "sre", "site reliability", "platform engineer",
    "android", "ios developer", "mobile developer",
]

# Titles that are hard-blocked (senior-only)
SENIOR_TITLE_PATTERNS = [
    "senior", "sr.", "staff", "principal", "lead", "architect",
    "manager", "director", "head of", "vp ", "vice president",
    "distinguished", "fellow",
]

# ---- Experience --------------------------------------------------------------
# 0-3 years qualifies; 4+ years and senior-only are excluded.
MIN_EXP_QUALIFY = 0
MAX_EXP_QUALIFY = 3

# ---- Locations ---------------------------------------------------------------
LOCAL_CITIES = [
    "islamabad", "rawalpindi", "rwp", "isb", "dha", "bahria",
    "gulberg", "g-13", "g-8", "blue area",
]
ACCEPTABLE_CITIES = LOCAL_CITIES + ["karachi"]  # Karachi ok for the right role
PAKISTAN_MARKERS = ["pakistan", "pk"] + ACCEPTABLE_CITIES

# ---- Remote pay --------------------------------------------------------------
# Target $10-40/hr. Roles paying above are fine (bonus); far below are flagged.
PAY_TARGET_MIN = 10
PAY_TARGET_MAX = 40

# ---- Freshness ----------------------------------------------------------------
# Portal/career-page listings: no older than 30 days (prefer 14).
MAX_AGE_DAYS_PORTAL = 30
PREFERRED_AGE_DAYS = 14

# ---- Apply routes -------------------------------------------------------------
# Allowed: direct email, Google Forms, official career pages.
# Blocked: LinkedIn Easy Apply, LinkedIn DMs, account-gated flows (unless he approves).
BLOCKED_ROUTE_MARKERS = ["easy apply", "dm ", "direct message", "linkedin.com/jobs/apply"]

# ---- Application rules ---------------------------------------------------------
# - Application contact email: ibrahimhamid.2600@gmail.com (never the other one)
# - NEVER state salary expectation unless the employer explicitly asks.
# - NEVER mention education in emails/cover letters.
# - Never frame him as student / "fresh graduate".
APPLY_EMAIL = "ibrahimhamid.2600@gmail.com"
