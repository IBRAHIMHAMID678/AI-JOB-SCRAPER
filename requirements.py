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
    "rag pipeline", "vector database", "vibe coder",
]

# Priority sources: listings here fill or die fastest (verified by churn analysis
# 2026-10-07 — direct ATS boards, LinkedIn, and these aggregators had the most
# postings vanish between sweeps). Leads from these sources get a rank bonus
# and a live-verification pass before the email digest goes out.
PRIORITY_SOURCES = {
    "ats:greenhouse", "ats:lever", "ats:ashby",
    "linkedin", "wearedistributed", "wwr", "jobicy",
}
# Titles that are hard-blocked (QA/SDET/test automation — never his targets,
# even when the description mentions AI/LLM). Checked on the title only, so a
# dev posting that merely mentions "testing" in its description is NOT caught.
# "vibe coder" titles are NOT in this list — they stay in the sweep.
QA_TITLE_PATTERNS = [
    "qa engineer", "qa analyst", "qa tester", "qa automation",
    "quality assurance", "sdet", "test automation", "automation tester",
    "test engineer", "software tester", "manual tester",
]

# Titles that are never his target roles, even if the description mentions AI.
# Checked before role relevance so "AI" in a sales job's description can't qualify it.
NON_DEV_TITLE_PATTERNS = [
    "sales", "sdr", "account executive", "business development", "consultant",
    "consulting", "analyst", "recruiter", "recruitment", "talent acquisition",
    "marketing", "seo", "designer", "writer", "content writer", "accountant",
    "bookkeeper", "finance", "customer success", "customer support",
    "support specialist", "technical support", "support engineer",
    "support analyst", "help desk", "helpdesk",
    "tutor", "teacher", "instructor", "driver",
    "security", "devops", "sre", "site reliability", "platform engineer",
    "android", "ios developer", "mobile developer",
    # non-software engineering (2026-10-08: embedded/mechanical/aerospace
    # roles were reaching the digest email despite being outside his field)
    "embedded", "firmware", "mechanical", "electrical", "aerospace",
    "civil engineer", "chemical engineer", "propulsion",
]

# Titles that are hard-blocked (senior-only)
SENIOR_TITLE_PATTERNS = [
    "senior", "sr.", "staff", "principal", "lead", "architect",
    "manager", "director", "head of", "vp ", "vice president",
    "distinguished", "fellow",
]

# ---- Company-level visa-sponsorship walls -------------------------------------
# Companies that auto-rejected his applications with an explicit "no visa
# sponsorship" policy. The employer has already decided, so re-applying only
# burns application slots — fail these at the filter, don't surface them again.
# gitlab: 5 rejections within one minute on 2026-10-05 ("GitLab does not offer
# visa sponsorships") — Forward Deployed Engineer AI/Agentic SDLC, Backend
# Engineer AI Duo Chat, Fullstack Engineer (TypeScript) Duo Client SDK,
# Backend Engineer (Python) Agent Foundations, Senior AI Engineer.
COMPANY_VISA_WALL = [
    "gitlab",
]

# ---- Strictness: legal gates vs geographic preferences ---------------------------
# FAIL (no honest path): citizenship, clearance, domicile, work authorization.
# REVIEW (his call — timezone preference vs legal block is ambiguous in prose):
# "only candidates in X", "must be based in X". Structured hiring-region
# metadata (applicantLocationRequirements) that excludes Pakistan still fails —
# that is the employer's explicit geo setting, not prose.
CITIZENSHIP_HARD_GATE_PATTERNS = [
    r"u\.?s\.?\s*citizenship\s+(is\s+)?required",
    r"citizenship\s+(is\s+)?required",
    r"u\.?s\.?\s*citizens?\s+(is\s+)?required",
    r"must\s+be\s+a\s+u\.?s\.?\s*citizen",
    r"national\s+id\s+(is\s+)?required",
    r"security\s+clearance",
    r"top\s+secret",
    r"\bts/sci\b",
    r"eligible\s+for\s+(a\s+)?security\s+clearance",
    r"must\s+be\s+domiciled\s+in\s+(the\s+)?(u\.?s\.?|united\s+states)",
    r"domiciled\s+in\s+the\s+u\.?s\.?",
    r"green\s*card\s+holders?\s+(only|required)",
    r"work\s+authorization\s+(in|for)\s+(the\s+)?[\w\s\.]+\s+required",
    r"(u\.?s\.?|united\s+states)\s+work\s+authorization\s+required",
    r"must\s+have\s+(the\s+)?(legal\s+)?right\s+to\s+work\s+in",
    r"right\s+to\s+work\s+in\s+(the\s+)?[\w\s\.]+\s+required",
    # region-exclusion gates (caught via detail-page enrichment)
    r"applications?\s+from\s+outside\s+[\w\s]+\s+will\s+not\s+be\s+considered",
]

# Geographic preference phrasing -> REVIEW, not fail. Timezone is never his
# constraint; whether "only candidates in Europe" is a timezone wish or a
# legal block is his call once he sees the posting.
REGION_PREFERENCE_PATTERNS = [
    r"only\s+candidates?\s+(based\s+)?in\s+(the\s+)?(u\.?s\.?|united\s+states|canada|u\.?k\.?|europe|e\.?u\.?|colombia|australia)",
    r"must\s+be\s+(based|located)\s+in\s+(the\s+)?(u\.?s\.?|united\s+states|canada|u\.?k\.?|europe|e\.?u\.?|colombia|australia)",
    r"(u\.?s\.?|europe|u\.?k\.?|canada)[-\s]?only\s+(role|position|applicants|candidates)",
]

# ---- Strictness: on-site-abroad detection ------------------------------------
# City names that prove a role is on-site abroad when the location string names
# them WITHOUT the word "remote". Country/region names (USA, Poland, APAC) are
# deliberately NOT here — those stay as review (eligibility unverified).
FOREIGN_CITY_MARKERS = [
    "san francisco", "san jose", "sunnyvale", "palo alto", "mountain view",
    "menlo park", "cupertino", "fremont", "santa clara", "los angeles",
    "san diego", "new york", "nyc", "boston", "cambridge", "seattle", "bellevue",
    "austin", "chicago", "denver", "boulder", "ann arbor", "pittsburgh",
    "san mateo",
    "london", "dublin", "berlin", "munich", "paris", "amsterdam",
    "zurich", "stockholm", "copenhagen", "oslo", "helsinki", "vienna",
    "prague", "warsaw", "krakow", "barcelona", "madrid", "milan", "lisbon",
    "toronto", "vancouver", "montreal", "waterloo",
    "bangalore", "bengaluru", "hyderabad", "chennai", "pune", "mumbai",
    "delhi", "gurgaon", "noida",
    "singapore", "sydney", "melbourne", "auckland", "tokyo", "osaka",
    "seoul", "shanghai", "beijing", "shenzhen", "hong kong", "taipei",
    "jakarta", "kuala lumpur", "manila", "tel aviv", "dubai", "abu dhabi",
    "riyadh", "doha", "istanbul", "mexico city", "sao paulo", "buenos aires",
    "santiago", "johannesburg", "lagos", "nairobi", "cairo", "christchurch",
]

# Country names that prove a hiring region excludes Pakistan when the location
# string names them WITHOUT any Pakistan/worldwide marker. The detail-page
# enrichment appends these (e.g. "Seoul [South Korea]"); the filter must act
# on them, not wave them through as "unverified".
FOREIGN_COUNTRY_MARKERS = [
    "united states", "usa", "u.s.a", "u.s", "us", "canada", "united kingdom", "uk", "eu",
    "ireland", "germany", "france", "netherlands", "spain", "portugal",
    "italy", "sweden", "norway", "denmark", "finland", "switzerland",
    "austria", "belgium", "poland", "czech republic", "czechia", "estonia",
    "lithuania", "latvia", "romania", "hungary", "greece", "croatia",
    "ukraine", "turkey", "israel", "uae", "united arab emirates",
    "saudi arabia", "qatar", "india", "china", "hong kong", "taiwan",
    "japan", "south korea", "korea", "singapore", "malaysia", "indonesia",
    "philippines", "thailand", "vietnam", "australia", "new zealand", "new zealand",
    "brazil", "mexico", "colombia", "argentina", "chile", "peru",
    "south africa", "nigeria", "kenya", "egypt",
    # region labels that exclude Pakistan
    "latam", "namer", "amer", "north america",
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
