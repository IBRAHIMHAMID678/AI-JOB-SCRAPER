"""Filter: applies Ibrahim's requirements to a normalized job dict.

Returns a structured verdict dict:
    {
        "verdict": "pass" | "review" | "fail",
        "reason_codes": [...],      # stable machine-readable codes
        "evidence_fields": {...},   # what evidence each decision rested on
        "missing_fields": [...],    # facts that were needed but absent
        "confidence": "high"|"medium"|"low",  # explainable, not calibrated
        "ruleset_version": RULESET_VERSION,
        "reasons": [...],           # human-readable (backward compatible)
    }

Design principles (2026-10-09 P0 repair):
- A verdict of "pass" requires POSITIVE evidence, never the absence of a
  disqualifier. "Remote" alone is not worldwide; empty location is not proof.
- A verdict of "fail" requires a DECISIVE reason (senior title, 4+ mandatory
  years, citizenship gate, confirmed dead). Uncertainty -> "review".
- Never auto-pass when the description is missing/empty — eligibility gates
  that depend on JD text cannot be verified.
- Local (Isb/Rwp) roles have their own pass path and are never forced
  through remote-country verification.

Normalized job dict fields used:
    source, id, title, company, description, description_status,
    url, apply_url, apply_email, location, remote,
    salary_min, salary_max, salary_unit, posted_at, tags
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from requirements import (
    ROLE_KEYWORDS, SENIOR_TITLE_PATTERNS, NON_DEV_TITLE_PATTERNS,
    QA_TITLE_PATTERNS,
    MAX_EXP_QUALIFY, CITIZENSHIP_HARD_GATE_PATTERNS, REGION_PREFERENCE_PATTERNS,
    FOREIGN_CITY_MARKERS, FOREIGN_COUNTRY_MARKERS,
    LOCAL_CITIES, ACCEPTABLE_CITIES, PAKISTAN_MARKERS,
    MAX_AGE_DAYS_PORTAL, PREFERRED_AGE_DAYS, BLOCKED_ROUTE_MARKERS,
    COMPANY_VISA_WALL,
)

RULESET_VERSION = "2026-10-09-p0"

# ---- compiled patterns -------------------------------------------------------
_EXP_PATTERNS = [
    re.compile(r"(\d+)\s*\+\s*(?:years?|yrs?)(?:'s)?(?:\s+of)?\s+experience", re.I),
    re.compile(r"(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)", re.I),
    re.compile(r"(\d+)\s*(?:years?|yrs?)(?:'s)?(?:\s+of)?(?:\s+[\w-]+){0,3}\s+experience", re.I),
    re.compile(r"experience\s*[:\-]?\s*(\d+)\s*[-–+]?\s*(?:years?|yrs?)", re.I),
]
# "minimum 4 years", "at least 3 years", "4+ years required" -> mandatory floor
_MANDATORY_FLOOR_RE = re.compile(
    r"(?:minimum|at least|atleast|minimum of|require[sd]?|must have|need)\s+"
    r"(?:at\s+least\s+)?(\d+)\s*(?:\+)?\s*(?:years?|yrs?)", re.I)
# "preferred 3+ years", "nice to have 2 years" -> preferred, not mandatory
_PREFERRED_RE = re.compile(
    r"(?:prefer(?:red|ably)?|nice to have|bonus|ideal(?:ly)?|desired)\b"
    r"[^.]{0,60}?(\d+)\s*(?:\+)?\s*(?:years?|yrs?)", re.I)
_SENIOR_RE = re.compile("|".join(re.escape(p) for p in SENIOR_TITLE_PATTERNS), re.I)
_NON_DEV_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in NON_DEV_TITLE_PATTERNS) + r")\b", re.I)
_QA_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in QA_TITLE_PATTERNS) + r")\b", re.I)
_CITIZEN_RE = re.compile("|".join(f"(?:{p})" for p in CITIZENSHIP_HARD_GATE_PATTERNS), re.I)
_REGION_PREF_RE = re.compile("|".join(f"(?:{p})" for p in REGION_PREFERENCE_PATTERNS), re.I)
_CITY_RE = re.compile("|".join(re.escape(c) for c in FOREIGN_CITY_MARKERS), re.I)
_COUNTRY_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in FOREIGN_COUNTRY_MARKERS) + r")\b", re.I)
# Explicit Pakistan eligibility: the employer names Pakistan as a hiring location
_PK_EXPLICIT_RE = re.compile(
    r"\b(hiring|hire|open to|welcome|eligible|based)\b[^.]{0,50}?\bpakistan\b"
    r"|\bpakistan\b[^.]{0,30}?\b(eligible|welcome|based|remote)\b", re.I)
# Negations that override positive Pakistan mentions
_PK_NEGATION_RE = re.compile(
    r"\b(cannot|can't|not|never|no longer|unable to)\b[^.]{0,30}?\b(hire|hiring|eligible)\b[^.]{0,30}?\bpakistan\b"
    r"|\bpakistan\b[^.]{0,30}?\b(is\s+not|not\s+an?)\b[^.]{0,20}?\b(eligible|supported)\b", re.I)
# Authoritative worldwide hiring policy (not marketing fluff)
_WORLDWIDE_AUTH_RE = re.compile(
    r"\b(work from anywhere|remote worldwide|hiring worldwide|"
    r"anywhere in the world|fully distributed|remote-first company|"
    r"hire (from )?anywhere|open to candidates (worldwide|globally))\b"
    r"|\b(hiring|location|based|eligible|we hire)\b.{0,40}\b(worldwide|anywhere)\b",
    re.I)
_DEV_TITLE_RE = re.compile(r"\b(engineer|developer)\b", re.I)
_JUNIOR_HINTS = re.compile(r"\b(junior|entry[- ]level|fresher|fresh graduates?|0[-–]2|1[-–]3|0[-–]3)\b", re.I)
_ONSITE_DESC_RE = re.compile(
    r"(based in our .{0,40} office|in-office \d+ days? per week|full-time onsite|"
    r"on-site \d+ days?|hybrid .{0,30}office|work from our .{0,40} office)",
    re.I)
_PAK_LOCAL_RE = re.compile(r"\b(pakistan|islamabad|rawalpindi|rwp|\bisb\b|karachi|lahore)\b", re.I)
_INTERN_RE = re.compile(r"\bintern(ship)?\b", re.I)


# ---- structured result builder ------------------------------------------------
def _new_result() -> dict:
    return {
        "verdict": "review",
        "reason_codes": [],
        "evidence_fields": {},
        "missing_fields": [],
        "confidence": "low",
        "ruleset_version": RULESET_VERSION,
        "reasons": [],
    }


def _add(res: dict, code: str, reason: str, evidence: dict | None = None):
    res["reason_codes"].append(code)
    res["reasons"].append(reason)
    if evidence:
        res["evidence_fields"].update(evidence)


def _missing(res: dict, field: str):
    if field not in res["missing_fields"]:
        res["missing_fields"].append(field)


# ---- experience parsing -------------------------------------------------------
def _exp_assessment(text: str) -> dict:
    """Return {mandatory_min, mandatory_max, preferred, ambiguous, none_found}.

    - mandatory: "4+ years required", "minimum 3 years" -> hard floor
    - range "2-4 years" -> ambiguous (review, not fail)
    - preferred: "preferred 3+ years" -> soft, review at most
    - company-age phrasing ("5+ years in business") is excluded by patterns
    - a "preferred/nice-to-have" qualifier near the match demotes it to soft
    """
    out = {"mandatory_min": None, "mandatory_max": None, "preferred": None,
           "ambiguous": False, "none_found": True}
    # preferred-context: if the whole experience mention sits inside preferred
    # language, it is soft, not a hard floor
    pref_ctx = re.compile(
        r"(?:prefer(?:red|ably)?|nice to have|bonus|ideal(?:ly)?|desired|"
        r"open to)\b[^.]{0,80}?\d+\s*(?:\+)?\s*(?:years?|yrs?)", re.I)
    is_preferred_context = bool(pref_ctx.search(text))
    lows, highs = [], []
    for pat in _EXP_PATTERNS:
        for m in pat.finditer(text):
            groups = [g for g in m.groups() if g is not None]
            if len(groups) == 2:
                lo, hi = int(groups[0]), int(groups[1])
                lows.append(lo); highs.append(hi)
                if lo <= MAX_EXP_QUALIFY < hi:
                    out["ambiguous"] = True  # e.g. 2-4 years
            else:
                lows.append(int(groups[0])); highs.append(int(groups[0]))
    if is_preferred_context and lows:
        # the experience mention is aspirational, not a gate
        out["preferred"] = max(highs) if highs else max(lows)
        out["none_found"] = False
        return out
    # mandatory floor: "minimum X years", "X+ years required"
    mf = _MANDATORY_FLOOR_RE.search(text)
    if mf:
        out["mandatory_min"] = int(mf.group(1))
    # preferred (soft)
    pf = _PREFERRED_RE.search(text)
    if pf:
        out["preferred"] = int(pf.group(1))
    if lows:
        out["none_found"] = False
        out["mandatory_min"] = min(lows) if out["mandatory_min"] is None else min(out["mandatory_min"], min(lows))
        out["mandatory_max"] = max(highs)
    elif mf or pf:
        out["none_found"] = False
    return out


def _role_relevant(title: str, desc: str) -> bool:
    if _DEV_TITLE_RE.search(title):
        return True
    blob = f"{title} {desc}".lower()
    return any(k in blob for k in ROLE_KEYWORDS)


def _desc_status(job: dict) -> str:
    """How complete is the description? Never trust length alone."""
    st = str(job.get("description_status") or "").lower()
    if st in ("full", "partial", "empty", "unavailable", "blocked"):
        return st
    # fallback for jobs scraped before the extraction pipeline existed
    dlen = len((job.get("description") or "").strip())
    if dlen >= 800:
        return "full"
    if dlen >= 200:
        return "partial"
    return "empty" if dlen == 0 else "partial"


def _location_assessment(job: dict, desc: str, res: dict) -> tuple[str, str]:
    """Return (geo_class, detail). geo_class: local | pk_remote | worldwide |
    remote_unverified | out_of_scope."""
    loc = (job.get("location") or "").lower()
    blob = f"{loc} {desc or ''}".lower()
    remote = bool(job.get("remote"))

    def _has_any(words) -> bool:
        return bool(re.search(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", blob))

    if _has_any(LOCAL_CITIES):
        return "local", "Islamabad/Rawalpindi area"
    if _has_any(["karachi"]):
        return "local", "Karachi"
    if not remote:
        return "out_of_scope", "not remote and not a Pakistan city"

    # Remote: check explicit Pakistan eligibility first (positive evidence)
    # Negations override: "cannot hire in Pakistan" must NOT grant eligibility
    if _PK_NEGATION_RE.search(blob):
        return "out_of_scope", "explicit Pakistan exclusion"
    if _PK_EXPLICIT_RE.search(blob):
        return "pk_remote", "employer explicitly names Pakistan"
    # structured hiring-region metadata from detail enrichment
    loc_req = job.get("_loc_requirements") or []
    if loc_req:
        req_blob = " ".join(loc_req).lower()
        if "pakistan" in req_blob:
            return "pk_remote", f"hiring region includes Pakistan: {', '.join(loc_req)}"
        pak_ok_words = ["worldwide", "global", "anywhere", "apac", "emea"]
        if not any(w in req_blob for w in pak_ok_words):
            return "out_of_scope", f"hiring region excludes Pakistan: {', '.join(loc_req)}"
    # foreign city/country in location -> hiring region excludes Pakistan
    # Explicit country in location field takes precedence over generic
    # "worldwide" marketing copy in description. "Remote (Canada)" means
    # Canada, not worldwide.
    cm = _CITY_RE.search(loc)
    if cm:
        return "out_of_scope", f"foreign hiring location ({cm.group(0)})"
    cn = _COUNTRY_RE.search(loc)
    if cn:
        return "out_of_scope", f"hiring country ({cn.group(0)})"
    # authoritative worldwide policy
    if _WORLDWIDE_AUTH_RE.search(blob):
        return "worldwide", "authoritative worldwide hiring policy"
    # "Remote" alone, or empty location, is NOT evidence of eligibility
    _missing(res, "hiring_country")
    return "remote_unverified", "remote but Pakistan eligibility unverified"


def _route_assessment(job: dict) -> tuple[str, str]:
    """Return (route_class, detail). route_class: ok | blocked | unverified."""
    blob = f"{job.get('apply_url') or ''} {job.get('description') or ''}".lower()
    for marker in BLOCKED_ROUTE_MARKERS:
        if marker in blob:
            return "blocked", f"blocked route ({marker.strip()})"
    if job.get("apply_email"):
        return "ok", "direct email"
    url = (job.get("apply_url") or "").lower()
    if "docs.google.com/forms" in url:
        return "ok", "google form"
    if "linkedin.com/jobs" in url and "apply" not in url:
        # LinkedIn job VIEW page (not Easy Apply) — apply path is the
        # employer's external site; verifiable, not blocked
        return "ok", "linkedin listing with external apply path"
    if job.get("source") == "linkedin":
        return "unverified", "linkedin route — verify apply path"
    if url:
        return "ok", "career page / apply link"
    return "blocked", "no usable apply route"


# ---- main filter --------------------------------------------------------------
def filter_job(job: dict) -> dict:
    res = _new_result()
    title = job.get("title") or ""
    desc = job.get("description") or ""
    text = f"{title}\n{desc}"
    dstatus = _desc_status(job)
    res["evidence_fields"]["description_status"] = dstatus

    # ---- hard fails: title gates (no JD needed) ----
    if _SENIOR_RE.search(title):
        _add(res, "senior_title", f"senior-only title: {title!r}",
             {"title": title})
        res["verdict"] = "fail"; res["confidence"] = "high"
        return res
    if _NON_DEV_RE.search(title):
        _add(res, "non_dev_title", f"non-dev role: {title!r}", {"title": title})
        res["verdict"] = "fail"; res["confidence"] = "high"
        return res
    if _QA_RE.search(title):
        _add(res, "qa_title", f"QA/test-automation role: {title!r}", {"title": title})
        res["verdict"] = "fail"; res["confidence"] = "high"
        return res
    if (job.get("company") or "").strip().lower() in COMPANY_VISA_WALL:
        _add(res, "visa_wall_company",
             f"company visa-sponsorship wall ({job.get('company')})",
             {"company": job.get("company")})
        res["verdict"] = "fail"; res["confidence"] = "high"
        return res

    # ---- role relevance ----
    if not _role_relevant(title, desc):
        _add(res, "role_irrelevant", "role not in target set (AI/Python/full-stack)")
        res["verdict"] = "fail"; res["confidence"] = "medium"
        return res
    _add(res, "role_relevant", "role in target set")

    # ---- legal gates (need JD text; if JD missing, cannot verify -> review) ----
    if dstatus in ("empty", "unavailable", "blocked"):
        _missing(res, "job_description")
        _add(res, "desc_missing_for_gates",
             "description missing — legal/experience gates unverifiable")
    else:
        if _CITIZEN_RE.search(text):
            _add(res, "citizenship_gate",
                 "citizenship/clearance/work-auth/domicile gate in posting")
            res["verdict"] = "fail"; res["confidence"] = "high"
            return res
        pref = _REGION_PREF_RE.search(text)
        if pref:
            _add(res, "region_preference",
                 f"region preference per posting ({pref.group(0).strip()[:60]}) — his call",
                 {"matched": pref.group(0).strip()[:80]})
            res["verdict"] = "review"; res["confidence"] = "medium"
            # region preference is decisive enough to stop here
            res["evidence_fields"]["stopped_at"] = "region_preference"
            return res
        # on-site-abroad signals in description
        if _ONSITE_DESC_RE.search(desc) and not _PAK_LOCAL_RE.search(f"{job.get('location') or ''} {desc}"):
            _add(res, "onsite_abroad", "on-site abroad per posting description")
            res["verdict"] = "fail"; res["confidence"] = "medium"
            return res

    # ---- experience ----
    exp = _exp_assessment(text)
    if dstatus in ("empty", "unavailable", "blocked"):
        _add(res, "exp_unverifiable", "experience requirements unverifiable — no description")
        # cannot fail on experience without evidence; stays review
    elif exp["mandatory_min"] is not None and exp["mandatory_min"] > MAX_EXP_QUALIFY:
        _add(res, "exp_exceeds_cap",
             f"mandatory minimum {exp['mandatory_min']} years exceeds {MAX_EXP_QUALIFY} yr junior cap",
             {"mandatory_min": exp["mandatory_min"]})
        res["verdict"] = "fail"; res["confidence"] = "high"
        return res
    elif exp["mandatory_max"] is not None and exp["mandatory_max"] > MAX_EXP_QUALIFY:
        if exp["ambiguous"]:
            _add(res, "exp_ambiguous_range",
                 f"experience range {exp['mandatory_min']}-{exp['mandatory_max']} yrs straddles cap — his call",
                 {"range": [exp["mandatory_min"], exp["mandatory_max"]]})
            res["verdict"] = "review"; res["confidence"] = "medium"
            res["evidence_fields"]["stopped_at"] = "exp_ambiguous_range"
            return res
        _add(res, "exp_exceeds_cap",
             f"experience {exp['mandatory_min']}-{exp['mandatory_max']} yrs exceeds 0-3 cap",
             {"range": [exp["mandatory_min"], exp["mandatory_max"]]})
        res["verdict"] = "fail"; res["confidence"] = "high"
        return res
    elif exp["preferred"] is not None and exp["preferred"] >= 4:
        # "preferred 4+ years" with no mandatory floor -> soft signal, review
        # (none_found is always False when preferred is set; the mandatory
        # floor check above already ran, so reaching here means no hard gate)
        _add(res, "exp_preferred_high",
             f"preferred (not mandatory) {exp['preferred']}+ years — his call",
             {"preferred": exp["preferred"]})
        res["verdict"] = "review"; res["confidence"] = "low"
        res["evidence_fields"]["stopped_at"] = "exp_preferred_high"
        return res
    elif not exp["none_found"]:
        _add(res, "exp_ok",
             f"experience within 0-3 cap",
             {"mandatory_min": exp["mandatory_min"], "mandatory_max": exp["mandatory_max"]})
    else:
        _add(res, "exp_unspecified", "no explicit experience requirement found")

    # ---- freshness ----
    posted = job.get("posted_at")
    if posted:
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - posted).days
        if age_days > MAX_AGE_DAYS_PORTAL:
            _add(res, "stale_posting", f"stale: {age_days}d old (>30d)",
                 {"age_days": age_days})
            res["verdict"] = "fail"; res["confidence"] = "high"
            return res
        _add(res, "freshness_ok", f"posted {age_days}d ago", {"age_days": age_days})
    else:
        _missing(res, "posted_at")
        _add(res, "date_unknown", "post date unknown — verify freshness manually")

    # ---- geography ----
    geo_class, geo_detail = _location_assessment(job, desc, res)
    res["evidence_fields"]["geo_class"] = geo_class
    if geo_class == "out_of_scope":
        _add(res, "location_out_of_scope", geo_detail)
        res["verdict"] = "fail"; res["confidence"] = "medium"
        return res
    if geo_class in ("pk_remote", "worldwide"):
        _add(res, "geo_eligible", geo_detail, {"geo_class": geo_class})
    elif geo_class == "local":
        _add(res, "geo_eligible", geo_detail, {"geo_class": geo_class})
    else:  # remote_unverified
        _add(res, "geo_unverified", geo_detail + " — manual check needed")
        res["verdict"] = "review"; res["confidence"] = "low"
        res["evidence_fields"]["stopped_at"] = "geo_unverified"
        return res

    # ---- apply route ----
    route_class, route_detail = _route_assessment(job)
    if route_class == "blocked":
        _add(res, "route_blocked", route_detail)
        res["verdict"] = "fail"; res["confidence"] = "high"
        return res
    if route_class == "unverified":
        _add(res, "route_unverified", route_detail)
        res["verdict"] = "review"; res["confidence"] = "low"
        res["evidence_fields"]["stopped_at"] = "route_unverified"
        return res
    _add(res, "route_ok", f"route: {route_detail}")

    # ---- junior hints / intern ----
    if _JUNIOR_HINTS.search(text):
        _add(res, "junior_friendly", "junior-friendly language in posting")
    if _INTERN_RE.search(title):
        _add(res, "intern_title", "intern-titled role: needs his call")
        res["verdict"] = "review"; res["confidence"] = "medium"
        res["evidence_fields"]["stopped_at"] = "intern_title"
        return res

    # ---- pass requires: description present, date known, geo eligible ----
    if dstatus in ("empty", "unavailable", "blocked"):
        _add(res, "no_pass_without_desc",
             "cannot auto-pass: description missing")
        res["verdict"] = "review"; res["confidence"] = "low"
        return res
    if not posted:
        _add(res, "no_pass_without_date",
             "cannot auto-pass: post date unknown")
        res["verdict"] = "review"; res["confidence"] = "low"
        return res

    res["verdict"] = "pass"; res["confidence"] = "high"
    _add(res, "all_checks_passed", "role, experience, freshness, geography, route all verified")
    return res


# Backward-compatible wrapper: some callers unpack (verdict, reasons).
def filter_job_tuple(job: dict) -> tuple[str, list[str]]:
    r = filter_job(job)
    return r["verdict"], r["reasons"]
