"""Layered job deduplication (2026-10-09 P1).

Identity layers, in order of reliability:
  1. Stable ATS / board job ID (gh-*, lv-*, as-*, wad-*, li-*, arc-*)
  2. Canonical job URL (tracking params stripped)
  3. Normalized (company, title, location)
  4. Conservative fuzzy title match + corroborating evidence
     (same company + same location + overlapping title tokens)

Never merge distinct requisitions: different ATS ids, different locations,
or materially different titles stay separate. Every merge records its reason.
Thresholds are configurable module constants.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# Fuzzy-match threshold: conservative. Two titles must be very similar AND
# share company + location to merge at layer 4.
FUZZY_TITLE_THRESHOLD = 0.88
FUZZY_MIN_TOKEN_OVERLAP = 3


def _norm_company(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _norm_title(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # drop seniority noise that boards append inconsistently
    t = re.sub(r"\b(jr|sr|junior|senior|i{1,3}|iv|v)\b\.?", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _norm_location(loc: str) -> str:
    l = (loc or "").lower()
    l = re.sub(r"[^\w\s]", " ", l)
    return re.sub(r"\s+", " ", l).strip()


def canonical_url(url: str) -> str:
    if not url:
        return ""
    url = url.split("#")[0]
    base, _, qs = url.partition("?")
    if not qs:
        return base.rstrip("/").lower()
    keep = []
    for part in qs.split("&"):
        k = part.split("=")[0].lower()
        if k.startswith(("utm_", "fbclid", "gclid", "msclkid", "fb_", "ref",
                         "source", "srsltid", "mc_cid", "mc_eid")):
            continue
        keep.append(part)
    return (base.rstrip("/") + ("?" + "&".join(sorted(keep)) if keep else "")).lower()


def _stable_id(job: dict) -> str | None:
    jid = (job.get("id") or "").strip()
    if jid and re.match(r"^(gh|lv|as|sr|wad|li|arc|rj|hn)-", jid.lower()):
        return jid.lower()
    return None


def _title_tokens(title: str) -> set[str]:
    stop = {"and", "the", "a", "an", "of", "for", "with", "remote", "hybrid", "onsite", "on-site"}
    return {t for t in _norm_title(title).split() if t not in stop and len(t) > 1}


def dedup_key_layers(job: dict) -> dict:
    """Return the identity keys for each layer."""
    return {
        "stable_id": _stable_id(job),
        "url": canonical_url(job.get("url") or job.get("apply_url") or ""),
        "company": _norm_company(job.get("company")),
        "title": _norm_title(job.get("title")),
        "location": _norm_location(job.get("location")),
    }


def _merge_job_fields(kept: dict, dropped: dict):
    """Merge dropped into kept. Completeness wins for descriptive fields;
    safety-critical evidence is preserved conservatively (most restrictive)."""
    # Descriptive: longer/more complete wins
    dropped_longer = len(dropped.get("description") or "") > len(kept.get("description") or "")
    if dropped_longer:
        for k in ("description", "description_full"):
            if dropped.get(k):
                kept[k] = dropped[k]
        # the more complete record likely has the better apply_url too
        if dropped.get("apply_url"):
            kept["apply_url"] = dropped["apply_url"]
    # description_status: most informative wins (full > partial > empty/unavailable/blocked)
    _status_rank = {"full": 4, "partial": 3, "empty": 1, "unavailable": 1, "blocked": 0}
    ks = _status_rank.get((kept.get("description_status") or "").lower(), 0)
    ds = _status_rank.get((dropped.get("description_status") or "").lower(), 0)
    if ds > ks and dropped.get("description_status"):
        kept["description_status"] = dropped["description_status"]
    # Scalar fields: fill gaps, prefer non-empty (apply_url handled above)
    for k in ("location", "salary_min", "salary_max", "salary_unit",
              "company", "title"):
        if not kept.get(k) and dropped.get(k):
            kept[k] = dropped[k]
    # apply_url: fill gap if not set by longer-record rule
    if not kept.get("apply_url") and dropped.get("apply_url"):
        kept["apply_url"] = dropped["apply_url"]
    # Safety-critical: preserve negative evidence (most restrictive wins).
    # _loc_requirements: union (if either says Canada-only, the merged record knows)
    for k in ("_loc_requirements", "_dead_markers", "_gate_hits"):
        kv, dv = kept.get(k), dropped.get(k)
        if dv and not kv:
            kept[k] = dv
        elif kv and dv and isinstance(kv, list) and isinstance(dv, list):
            kept[k] = sorted(set(kv) | set(dv))
    # reason_codes / missing_fields: union (don't lose fail evidence)
    for k in ("reason_codes", "missing_fields"):
        kv, dv = kept.get(k) or [], dropped.get(k) or []
        if dv:
            kept[k] = sorted(set(kv) | set(dv))


def dedup_key_layers(job: dict) -> dict:
    """Return the identity keys for each layer."""
    return {
        "stable_id": _stable_id(job),
        "url": canonical_url(job.get("url") or job.get("apply_url") or ""),
        "company": _norm_company(job.get("company")),
        "title": _norm_title(job.get("title")),
        "location": _norm_location(job.get("location")),
    }


def deduplicate(jobs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Deduplicate a job list. Returns (unique_jobs, merge_log).

    Each unique job gets:
      _dedup_sources: list of sources that carried this job
      _dedup_merged:  count of duplicates merged into it
    merge_log entries: {kept_id, dropped_id, layer, reason}
    """
    unique: list[dict] = []
    # indexes per layer
    by_id: dict[str, dict] = {}
    by_url: dict[str, dict] = {}
    by_ctl: dict[tuple, dict] = {}
    merge_log: list[dict] = []
    # Layer-4 fuzzy index: (company, location) -> [(job, layers, tokens)]
    # Built lazily on first layer-4 use; avoids O(n²) with per-pair recomputation
    l4_groups: dict[tuple, list] = {}
    l4_built = False

    def _register(u: dict, layers: dict):
        if layers["stable_id"]:
            by_id[layers["stable_id"]] = u
        if layers["url"]:
            by_url[layers["url"]] = u
        ctl = (layers["company"], layers["title"], layers["location"])
        if layers["company"] and layers["title"]:
            by_ctl[ctl] = u

    for job in jobs:
        layers = dedup_key_layers(job)
        match = None
        reason = ""

        # Layer 1: stable id
        if layers["stable_id"] and layers["stable_id"] in by_id:
            match = by_id[layers["stable_id"]]
            reason = f"layer1 stable_id={layers['stable_id']}"
        # Layer 2: canonical URL — merge unless stable IDs prove different requisitions
        # (different IDs from the SAME source with different numeric parts)
        elif layers["url"] and layers["url"] in by_url:
            cand = by_url[layers["url"]]
            cand_id = _stable_id(cand)
            # Only block if both have IDs from the same source prefix and they differ
            # e.g., gh-123 vs gh-456 = different; gh-123 vs as-789 = same posting, different source
            block = False
            if layers["stable_id"] and cand_id:
                lp, _, _ = layers["stable_id"].partition("-")
                cp, _, _ = cand_id.partition("-")
                if lp == cp and layers["stable_id"] != cand_id:
                    block = True
            if not block:
                match = cand
                reason = f"layer2 url={layers['url'][:60]}"
        # Layer 3: company + normalized title + location
        # Block only if same-source stable IDs differ (distinct requisitions)
        elif layers["company"] and layers["title"]:
            ctl = (layers["company"], layers["title"], layers["location"])
            if ctl in by_ctl:
                cand = by_ctl[ctl]
                cand_id = _stable_id(cand)
                block = False
                if layers["stable_id"] and cand_id:
                    lp, _, _ = layers["stable_id"].partition("-")
                    cp, _, _ = cand_id.partition("-")
                    if lp == cp and layers["stable_id"] != cand_id:
                        block = True
                if not block:
                    match = cand
                    reason = f"layer3 company+title+location"
        # Layer 4: fuzzy title + same company + same location — not if stable_ids differ
        # PERFORMANCE: Group by (company, location); precompute layers/tokens;
        # cheap token-overlap check before expensive SequenceMatcher.
        if not match and layers["company"] and layers["title"]:
            if not l4_built:
                for u in unique:
                    ul = dedup_key_layers(u)
                    key = (ul["company"], ul["location"])
                    l4_groups.setdefault(key, []).append(
                        (u, ul, _title_tokens(u.get("title"))))
                l4_built = True
            groups = l4_groups
            job_tokens = _title_tokens(job.get("title"))
            candidates = groups.get((layers["company"], layers["location"]), [])
            for u, ul, u_tokens in candidates:
                # Cheap check first: token overlap
                overlap = len(u_tokens & job_tokens)
                if overlap < FUZZY_MIN_TOKEN_OVERLAP:
                    continue
                # distinct requisitions: same-source stable IDs that differ → never fuzzy-merge
                uid = _stable_id(u)
                if layers["stable_id"] and uid:
                    lp, _, _ = layers["stable_id"].partition("-")
                    cp, _, _ = uid.partition("-")
                    if lp == cp and layers["stable_id"] != uid:
                        continue
                # Expensive check only if cheap check passes
                sim = SequenceMatcher(None, ul["title"], layers["title"]).ratio()
                if sim >= FUZZY_TITLE_THRESHOLD:
                    match = u
                    reason = (f"layer4 fuzzy sim={sim:.2f} overlap={overlap} "
                              f"('{u.get('title')[:40]}' ~ '{job.get('title')[:40]}')")
                    break
            # Add this job to groups for future comparisons (if not matched)
            if not match:
                key = (layers["company"], layers["location"])
                groups.setdefault(key, []).append((job, layers, job_tokens))

        if match:
            srcs = match.setdefault("_dedup_sources", [match.get("source")])
            if job.get("source") not in srcs:
                srcs.append(job.get("source"))
            match["_dedup_merged"] = match.get("_dedup_merged", 0) + 1
            # Merge: prefer more complete data, but NEVER discard safety evidence.
            # Safety-critical fields are preserved conservatively (most restrictive wins).
            _merge_job_fields(match, job)
            merge_log.append({"kept_id": match.get("id"), "dropped_id": job.get("id"),
                              "layer": reason.split()[0], "reason": reason})
        else:
            job["_dedup_sources"] = [job.get("source")]
            job["_dedup_merged"] = 0
            unique.append(job)
            _register(job, layers)

    return unique, merge_log
