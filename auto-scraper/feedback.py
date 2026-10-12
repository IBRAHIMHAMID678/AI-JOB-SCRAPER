"""Manual feedback store (2026-10-09 P0).

Human verification must survive across sweeps. This module provides a
persistent, job-level feedback store separate from applied.json (which tracks
application attempts).

feedback.json structure:
{
  "jobs": {
    "<canonical_id>": {
      "company": ..., "title": ..., "url": ...,
      "decision": "applied|rejected|dead|unsuitable|useful|interview|offer",
      "decided_at": iso, "decided_by": "manual",
      "note": "...", "source": "sweep|digest|manual"
    }
  },
  "companies": {
    "<normalized_name>": {"decision": "blocked", "reason": ..., "decided_at": ...}
  }
}

Decisions:
- applied:    he applied (also mirrored in applied.json)
- rejected:   employer rejected
- dead:       posting is dead/gone — never surface again
- unsuitable: he judged it unsuitable — never surface again
- useful:     promising lead worth prioritizing
- interview / offer: positive pipeline outcomes
- companies.blocked: never surface this company (explicit choice only)

Canonical ID priority: ATS/stable job id > canonical URL > company|title.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
FEEDBACK_PATH = os.path.join(BASE, "feedback.json")

JOB_DECISIONS = {"applied", "rejected", "dead", "unsuitable", "useful",
                 "interview", "offer"}
# Decisions that suppress a job from future sweeps/digests
SUPPRESSING = {"dead", "unsuitable", "rejected"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_company(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _canonical_url(url: str) -> str:
    """Strip tracking params for a stable URL identity."""
    if not url:
        return ""
    url = url.split("#")[0]
    base, _, qs = url.partition("?")
    if not qs:
        return base.rstrip("/").lower()
    keep = []
    for part in qs.split("&"):
        k = part.split("=")[0].lower()
        if k.startswith(("utm_", "fbclid", "gclid", "msclkid", "ref", "source")):
            continue
        keep.append(part)
    canon = base.rstrip("/") + ("?" + "&".join(keep) if keep else "")
    return canon.lower()


def _norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip().lower()


def job_identity_keys(job: dict) -> dict:
    """All identity evidence for a job, as {kind: value}.

    Kinds: stable_id (ATS/board ID), url (canonical), ct (company|title).
    A job may have 1-3 keys depending on available data. Enrichment that
    adds a URL later must not break matching against records stored earlier
    with less information.
    """
    keys = {}
    jid = (job.get("id") or "").strip()
    if jid and re.match(r"^(gh|lv|as|sr|wad|li|arc|rj|hn)-", jid.lower()):
        keys["stable_id"] = jid.lower()
    url = _canonical_url(job.get("url") or job.get("apply_url") or "")
    if url:
        keys["url"] = f"url:{url}"
    comp = _norm_company(job.get("company") or "")
    title = _norm_title(job.get("title") or "")
    if comp and title:
        keys["ct"] = f"ct:{comp}|{title}"
    return keys


def canonical_job_id(job: dict) -> str:
    """Best single stable identity (backward compatible)."""
    keys = job_identity_keys(job)
    # priority: stable_id > url > ct
    for kind in ("stable_id", "url", "ct"):
        if kind in keys:
            return keys[kind]
    return ""


def load_feedback() -> dict:
    try:
        with open(FEEDBACK_PATH) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"jobs": {}, "companies": {}}
        data.setdefault("jobs", {})
        data.setdefault("companies", {})
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"jobs": {}, "companies": {}}


def save_feedback(data: dict):
    tmp = FEEDBACK_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, FEEDBACK_PATH)


def record_job_feedback(job: dict, decision: str, note: str = "",
                        source: str = "manual") -> str:
    """Record a manual decision for a job. Returns the canonical id used.

    Stores ALL available identity keys (stable_id, url, ct) so that later
    suppression works even when the sweep record has richer or different
    identity evidence than what was available at record time.
    """
    if decision not in JOB_DECISIONS:
        raise ValueError(f"unknown decision {decision!r}; want one of {sorted(JOB_DECISIONS)}")
    data = load_feedback()
    cid = canonical_job_id(job)
    keys = job_identity_keys(job)
    data["jobs"][cid] = {
        "company": job.get("company", ""),
        "title": job.get("title", ""),
        "url": job.get("url") or job.get("apply_url") or "",
        "identity_keys": keys,  # all evidence available at record time
        "decision": decision,
        "decided_at": _now_iso(),
        "decided_by": "manual",
        "note": note,
        "source": source,
    }
    save_feedback(data)
    return cid


def record_company_block(company: str, reason: str = "") -> str:
    data = load_feedback()
    key = _norm_company(company)
    data["companies"][key] = {
        "company": company,
        "decision": "blocked",
        "reason": reason,
        "decided_at": _now_iso(),
        "decided_by": "manual",
    }
    save_feedback(data)
    return key


def _record_keys(rec: dict, cid: str) -> dict:
    """Identity keys for a stored record. Backward compatible: legacy records
    without 'identity_keys' are reconstructed from company/title/url."""
    keys = rec.get("identity_keys")
    if isinstance(keys, dict) and keys:
        return keys
    # legacy record: reconstruct from stored fields
    return job_identity_keys({
        "company": rec.get("company", ""),
        "title": rec.get("title", ""),
        "url": rec.get("url", ""),
        "id": cid if not cid.startswith(("url:", "ct:")) else "",
    })


def job_suppressed(job: dict, data: dict | None = None) -> tuple[bool, str, str]:
    """Check whether manual feedback suppresses this job.

    Returns (suppressed, reason, matched_via). Matching is conservative:
    - stable_id or url match → suppress (high confidence)
    - ct (company|title) match → suppress ONLY if at least one side lacks a
      URL (prevents merging distinct postings that happen to share a title).
      If both have URLs and they differ, do NOT suppress on ct alone.
    - Missing values never become wildcards.

    The third return value explains which identity matched and why.
    """
    data = data or load_feedback()
    qkeys = job_identity_keys(job)
    if not qkeys:
        return False, "", ""
    for cid, rec in data["jobs"].items():
        if rec.get("decision") not in SUPPRESSING:
            continue
        rkeys = _record_keys(rec, cid)
        # Layer 1: stable_id exact match
        if "stable_id" in qkeys and qkeys["stable_id"] == rkeys.get("stable_id"):
            why = f"manual feedback: {rec['decision']} (stable_id {qkeys['stable_id']})"
            return True, why, f"stable_id:{qkeys['stable_id']}"
        # Layer 2: canonical URL exact match
        if "url" in qkeys and qkeys["url"] == rkeys.get("url"):
            why = f"manual feedback: {rec['decision']} (url match)"
            return True, why, f"url:{qkeys['url'][:60]}"
        # Layer 3: company|title — only if not both have differing URLs
        if "ct" in qkeys and qkeys["ct"] == rkeys.get("ct"):
            q_has_url = "url" in qkeys
            r_has_url = "url" in rkeys
            if q_has_url and r_has_url:
                # both have URLs and they differ → distinct postings, do not suppress
                continue
            why = (f"manual feedback: {rec['decision']} "
                   f"(company|title {qkeys['ct'][:50]})"
                   + (f" ({rec.get('note','')[:50]})" if rec.get("note") else ""))
            return True, why, f"ct:{qkeys['ct'][:50]}"
    # company-level block
    comp = _norm_company(job.get("company") or "")
    if comp and data["companies"].get(comp, {}).get("decision") == "blocked":
        return True, f"manual feedback: company blocked ({job.get('company')})", f"company:{comp}"
    return False, "", ""


def list_feedback(decision: str | None = None, limit: int = 50) -> list[dict]:
    data = load_feedback()
    out = []
    for cid, rec in data["jobs"].items():
        if decision and rec.get("decision") != decision:
            continue
        out.append({"id": cid, **rec})
    out.sort(key=lambda r: r.get("decided_at", ""), reverse=True)
    return out[:limit]
