"""Auto-scraper: scrape -> filter by Ibrahim's requirements -> rank -> top N.

Usage:
    python3 run.py [--top 20] [--sources remoteok,remotive,hn_hiring] [--out results]
    python3 run.py --drafts N   # also create Gmail drafts for top-N email-route leads

Outputs: <out>/<YYYY-MM-DD>/leads.json and report.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sources import SOURCES
from filter import filter_job
from rank import score

try:
    import generic as _generic
except ImportError:
    _generic = None

BASE = os.path.dirname(os.path.abspath(__file__))
APPLIED_PATH = os.path.join(BASE, "applied.json")

RESUME = os.path.expanduser("~/workspace/user/files/Ibrahim_Hamid_Resume.pdf")

COVER_TEMPLATE = """Dear HR,

I am writing to express my interest in the {role} position. With my background in building robust {domain} and my experience incorporating artificial intelligence, I am confident in my ability to contribute effectively to your engineering team.

{stack_para}

Portfolio: github.com/IBRAHIMHAMID678 - including Job Pilot (github.com/IBRAHIMHAMID678/AI-JOB-SCRAPER), a full-stack AI job application platform with scraping, matching, and automation pipelines; plus Chatbot-Agent and Auto Market.

I have attached my resume for your review, which provides further details on my technical skills and project experience. I would welcome the opportunity to discuss how my background aligns with the needs of your team.

Thank you for your time and consideration.

Best regards,
Ibrahim Hamid"""

STACK_PARAS = {
    "backend": ("backend systems and REST APIs",
                "In addition to my core expertise in Python, FastAPI, and PostgreSQL, I have hands-on experience with AI integration. Specifically, I have worked on implementing Retrieval-Augmented Generation (RAG) pipelines and utilizing Ollama for local language model deployment and integration. This allows me to bridge the gap between traditional backend development and modern, AI-driven application features."),
    "ai": ("AI-powered applications",
           "In addition to my core expertise in Python (PyTorch, Transformers, and production ML systems), I have hands-on experience with AI integration. Specifically, I have worked on implementing Retrieval-Augmented Generation (RAG) pipelines, embeddings and vector databases, and utilizing Ollama for local language model deployment and integration. This allows me to bridge the gap between traditional software development and modern, AI-driven application features."),
    "fullstack": ("web applications",
                  "In addition to my core expertise across the MERN stack (MongoDB, Express.js, React, and Node.js), I have hands-on experience with AI integration. Specifically, I have worked on implementing Retrieval-Augmented Generation (RAG) pipelines and utilizing Ollama for local language model deployment and integration. This allows me to bridge the gap between traditional full-stack development and modern, AI-driven application features."),
}


def _profile(title: str) -> str:
    t = title.lower()
    if "backend" in t:
        return "backend"
    if any(k in t for k in ("ai", "ml", "llm", "rag", "nlp", "prompt")):
        return "ai"
    return "fullstack"


def load_applied() -> set[str]:
    try:
        with open(APPLIED_PATH) as f:
            data = json.load(f)
        return {
            f"{a.get('company', '')}|{a.get('title') or a.get('role', '')}".lower()
            for a in data
        }
    except FileNotFoundError:
        return set()


def save_applied(entries: list[dict]):
    try:
        with open(APPLIED_PATH) as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []
    seen = {f"{a['company']}|{a['title']}".lower() for a in data}
    for e in entries:
        key = f"{e['company']}|{e['title']}".lower()
        if key not in seen:
            data.append(e); seen.add(key)
    with open(APPLIED_PATH, "w") as f:
        json.dump(data, f, indent=1)


def scrape(sources: list[str]) -> tuple[list[dict], list[str], dict]:
    """Returns (jobs, errors, per_source_stats). A source error is recorded
    in per_source_stats and never aborts other sources."""
    jobs, errors = [], []
    stats: dict[str, dict] = {}
    for name in sources:
        st = {"raw": 0, "ok": False, "error": ""}
        try:
            batch = SOURCES[name]()
            jobs.extend(batch)
            st["raw"] = len(batch)
            st["ok"] = True
            print(f"  {name}: {len(batch)} raw", flush=True)
        except Exception as e:
            st["error"] = f"{type(e).__name__}: {str(e)[:150]}"
            errors.append(f"{name}: {e}")
            print(f"  {name}: ERROR {e}", flush=True)
        stats[name] = st
    return jobs, errors, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--sources", default="remoteok,remotive,hn_hiring,linkedin,workingnomads,jobicy,himalayas,wwr,yc_jobs,reddit_rss,wearedistributed,nocommute,justremote,pythonorg,arc,remotecom,dailyremote,techjobsforgood,remote4africa,builtin,jobsbylevel,arbeitnow,rj_ai_curator,tg_remotejobs,tg_remote_python,berlinstartupjobs,getinit,dice")
    ap.add_argument("--out", default=os.path.join(BASE, "results"))
    ap.add_argument("--drafts", type=int, default=0,
                    help="create Gmail drafts for top-N email-route leads")
    ap.add_argument("--targets", default=os.path.join(BASE, "targets.yaml"),
                    help="YAML file of arbitrary websites/portals to scrape "
                         "(empty string disables)")
    ap.add_argument("--verify", type=int, default=0,
                    help="after ranking, live-verify the apply routes of the "
                         "top-N leads in headless Chromium via verify_live.py "
                         "(default 0 = off)")
    args = ap.parse_args()

    src_names = [s for s in args.sources.split(",") if s in SOURCES]
    print(f"Scraping {len(src_names)} sources...")
    jobs, errors, src_stats = scrape(src_names)

    # Universal targets: any website or portal listed in targets.yaml
    if args.targets and _generic:
        try:
            import yaml
            with open(args.targets) as f:
                tcfg = yaml.safe_load(f) or {}
            tjobs = []
            for t in tcfg.get("targets", []):
                url = t.get("url", "").strip()
                if not url:
                    continue
                try:
                    if t.get("kind") == "list":
                        batch = _generic.fetch_list_page(
                            url, t.get("link_re", r"/jobs?/"),
                            int(t.get("max_items", 20)))
                        print(f"  target [list] {url[:60]}: {len(batch)} raw", flush=True)
                    else:
                        method, batch = _generic.fetch_target(url)
                        print(f"  target [{method}] {url[:60]}: {len(batch)} raw", flush=True)
                    tjobs.extend(batch)
                except Exception as e:
                    errors.append(f"target {url}: {e}")
                    print(f"  target {url[:60]}: ERROR {e}", flush=True)
            jobs.extend(tjobs)
        except FileNotFoundError:
            print("  (no targets.yaml — skipping universal scrape)")
        except ImportError:
            print("  (pyyaml missing — skipping universal scrape)")
    print(f"Raw total: {len(jobs)}", flush=True)
    raw_total = len(jobs)  # capture before dedup (for honest metrics)

    # Layered deduplication (2026-10-09 P1): stable ATS id > canonical URL >
    # company+title+location > conservative fuzzy match. Replaces the old
    # fragile company|title-only check.
    from dedup import deduplicate
    jobs, merge_log = deduplicate(jobs)
    print(f"dedup: {len(merge_log)} duplicates merged, {len(jobs)} unique", flush=True)
    for m in merge_log[:5]:
        print(f"  merged [{m['layer']}] {m['dropped_id']} -> {m['kept_id']}")

    applied = load_applied()
    seen_run = set()
    passed, review, failed = [], [], []
    from extract import enrich_description
    from feedback import load_feedback, job_suppressed
    fb_data = load_feedback()
    fb_suppressed_n = 0
    for j in jobs:
        key = f"{j['company']}|{j['title']}".lower()
        if key in applied or key in seen_run:
            continue
        seen_run.add(key)
        # Manual feedback suppresses dead/unsuitable/rejected jobs (2026-10-09 P0)
        suppressed, why, _matched_via = job_suppressed(j, fb_data)
        if suppressed:
            fb_suppressed_n += 1
            failed.append({"job": j, "verdict": "fail", "reasons": [why],
                           "reason_codes": ["manual_feedback_suppressed"],
                           "evidence_fields": {}, "missing_fields": [],
                           "confidence": "high",
                           "ruleset_version": "2026-10-09-p0",
                           "score": 0.0, "score_notes": []})
            continue
        # Cheap pre-filter classification: set description_status from what the
        # source provided (no network). Full detail-page enrichment happens
        # later, only for pass/review candidates.
        enrich_description(j, pre_classify_only=True)
        fr = filter_job(j)
        verdict, reasons = fr["verdict"], fr["reasons"]
        sc, notes = score(j, reasons)
        rec = {"job": j, "verdict": verdict, "reasons": reasons,
               "reason_codes": fr["reason_codes"],
               "evidence_fields": fr["evidence_fields"],
               "missing_fields": fr["missing_fields"],
               "confidence": fr["confidence"],
               "ruleset_version": fr["ruleset_version"],
               "score": round(sc, 1), "score_notes": notes}
        # make posted_at JSON-safe later
        if verdict == "pass":
            passed.append(rec)
        elif verdict == "review":
            review.append(rec)
        else:
            failed.append(rec)
    print(f"pass={len(passed)} review={len(review)} fail={len(failed)} "
          f"(feedback-suppressed={fb_suppressed_n})")

    # Description extraction pipeline (2026-10-09 P0): for jobs reaching
    # pass/review, ensure description_status is set and attempt to recover
    # complete JDs from official detail pages via source-specific adapters.
    # Bounded to keep the sweep fast; API-complete sources skip fetching.
    try:
        from extract import enrich_description
        cands = sorted(passed + review, key=lambda r: -r["score"])
        enriched_n = 0
        ENRICH_CAP = 60
        for rec in cands:
            j = rec["job"]
            if j.get("description_status") in ("full",):
                continue  # already complete, no fetch needed
            if enriched_n >= ENRICH_CAP:
                # mark the rest as not-attempted rather than leaving stale state
                if not j.get("description_status"):
                    from extract import set_description
                    set_description(j, j.get("description") or "", "partial",
                                    "enrich_cap_reached", j.get("url", ""),
                                    error="enrichment cap reached; completeness unverified")
                continue
            enrich_description(j)
            enriched_n += 1
            # re-filter on the enriched record so new JD text feeds the gates
            fr = filter_job(j)
            sc, notes = score(j, fr["reasons"])
            rec.update({"verdict": fr["verdict"], "reasons": fr["reasons"],
                        "reason_codes": fr["reason_codes"],
                        "evidence_fields": fr["evidence_fields"],
                        "missing_fields": fr["missing_fields"],
                        "confidence": fr["confidence"],
                        "ruleset_version": fr["ruleset_version"],
                        "score": round(sc, 1), "score_notes": notes})
        # re-bucket after re-filtering
        passed = [r for r in cands if r["verdict"] == "pass"]
        review = [r for r in cands if r["verdict"] == "review"]
        refiltered = [r for r in cands if r["verdict"] == "fail"]
        failed.extend(refiltered)
        print(f"description enrichment: {enriched_n} jobs processed; "
              f"{len(refiltered)} newly failed after enrichment")
    except Exception as e:
        print(f"description enrichment skipped: {e}")

    # Legacy WAD detail-page enrichment is now handled by extract.adapt_wad
    # via the pipeline above; the old enrich.py path is retired.

    passed.sort(key=lambda r: -r["score"])
    review.sort(key=lambda r: -r["score"])

    # Hiring lanes (2026-10-09 P2): separate ranked shortlists so one
    # category never crowds out the others.
    def _lane(r) -> str:
        j, ev = r["job"], r.get("evidence_fields", {})
        geo = ev.get("geo_class", "")
        if geo == "local":
            return "C"  # Islamabad–Rawalpindi local
        unit = (j.get("salary_unit") or "")
        desc = ((j.get("description_full") or j.get("description")) or "").lower()
        is_contract = unit == "hourly" or any(
            k in desc for k in ("contract", "freelance", "hourly", "$/hr", "per hour"))
        if r["verdict"] == "pass" and geo in ("pk_remote", "worldwide"):
            return "B" if is_contract else "A"
        if r["verdict"] == "review":
            return "D"  # stretch / needs manual assessment
        return "A" if geo in ("pk_remote", "worldwide") else "D"

    lanes: dict[str, list] = {"A": [], "B": [], "C": [], "D": []}
    for r in passed + review:
        lanes[_lane(r)].append(r)
    lane_names = {
        "A": "Pakistan-eligible international remote (employment)",
        "B": "USD hourly contracts / freelance",
        "C": "Islamabad–Rawalpindi local",
        "D": "Stretch — needs manual assessment",
    }

    top = (passed + review)[:args.top]

    # Live apply-route verification (2026-10-14): render each top lead's
    # apply URL in headless Chromium and classify it. Off by default.
    verified_map = {}
    if args.verify and args.verify > 0:
        try:
            import verify_live
            vurls, vkeys = [], []
            for r in top[:args.verify]:
                j = r["job"]
                u = j.get("apply_url") or j.get("url")
                if u:
                    vurls.append(u)
                    vkeys.append((j.get("company"), j.get("title")))
            print(f"Live-verifying {len(vurls)} apply routes...")
            vres = verify_live.verify(vurls)
            for u, key in zip(vurls, vkeys):
                verified_map[u] = vres.get(u, {})
            n_live = sum(1 for v in verified_map.values()
                         if v.get("verdict") == "live_apply")
            print(f"Verification: {n_live}/{len(vurls)} live apply routes")
        except Exception as e:
            print(f"Live verification skipped: {e}")

    # Per-source health metrics (2026-10-09 P1): description extraction
    # success + verdict distribution per source, recorded every run.
    try:
        from monitor import record_run
        # Collect job IDs per source for unique-evidence tracking in learning.
        # Uses stable IDs where available, else canonical URL, else content hash.
        # Also tracks which IDs were eligible (pass/review) for accurate yield,
        # and per-job description status for consistent description rates.
        # Identity aliases: store all layers so enrichment transitions
        # (title-only → URL → ATS ID) can be reconciled to one canonical ID.
        from dedup import dedup_key_layers
        source_job_ids: dict[str, set[str]] = {}
        source_eligible_ids: dict[str, set[str]] = {}
        source_desc_status: dict[str, dict[str, str]] = {}
        source_identity_aliases: dict[str, dict[str, str]] = {}
        source_unambiguous_ids: dict[str, set[str]] = {}
        for r in passed + review + failed:
            job = r["job"]
            src = job.get("source", "?")
            s = src_stats.setdefault(src, {})
            s[r["verdict"]] = s.get(r["verdict"], 0) + 1
            ds = (job.get("description_status") or "unknown")
            s[f"desc_{ds}"] = s.get(f"desc_{ds}", 0) + 1
            # ID for cross-run deduplication (strongest available)
            layers = dedup_key_layers(job)
            jid = layers["stable_id"] or layers["url"] or f"ct:{layers['company']}|{layers['title']}"
            if jid:
                source_job_ids.setdefault(src, set()).add(jid)
                source_desc_status.setdefault(src, {})[jid] = ds
                # Store all layers as aliases for reconciliation
                aliases = {}
                if layers["stable_id"]:
                    aliases["stable_id"] = layers["stable_id"]
                if layers["url"]:
                    aliases["url"] = layers["url"]
                aliases["ct"] = f"ct:{layers['company']}|{layers['title']}"
                source_identity_aliases.setdefault(src, {})[jid] = aliases
                # Unambiguous attribution: single contributing source only
                contrib = job.get("_dedup_sources", [src])
                if len(contrib) == 1:
                    source_unambiguous_ids.setdefault(src, set()).add(jid)
                if r["verdict"] in ("pass", "review"):
                    source_eligible_ids.setdefault(src, set()).add(jid)
        record_run(src_stats, errors, {
            "raw": raw_total, "unique": len(passed) + len(review) + len(failed),
            "pass": len(passed), "review": len(review), "fail": len(failed),
            "duplicates_merged": len(merge_log),
        }, source_job_ids, source_eligible_ids, source_desc_status,
            source_identity_aliases, source_unambiguous_ids)
        print(f"health recorded for {len(src_stats)} sources")
    except Exception as e:
        print(f"health recording skipped: {e}")

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = os.path.join(args.out, day)
    os.makedirs(outdir, exist_ok=True)

    # store lane on each record for downstream consumers
    for lid, recs in lanes.items():
        for r in recs:
            r["lane"] = lid

    def _ser(r):
        j = dict(r["job"])
        p = j.get("posted_at")
        j["posted_at"] = p.isoformat() if p else None
        # Preserve the complete description for filters/downstream processing.
        # Only the display copy is truncated; description_full is never cut.
        full = j.get("description_full") or j.get("description") or ""
        j["description_full"] = full
        if len(j.get("description") or "") > 4000:
            j["description"] = j["description"][:4000] + "…"
        return {"score": r["score"], "score_notes": r["score_notes"],
                "verdict": r["verdict"], "reasons": r["reasons"],
                "reason_codes": r.get("reason_codes", []),
                "evidence_fields": r.get("evidence_fields", {}),
                "missing_fields": r.get("missing_fields", []),
                "confidence": r.get("confidence", "low"),
                "ruleset_version": r.get("ruleset_version", "?"),
                "lane": r.get("lane", "D"),
                "verified": verified_map.get(
                    j.get("apply_url") or j.get("url"), {}),
                "job": j}

    with open(os.path.join(outdir, "leads.json"), "w") as f:
        json.dump([_ser(r) for r in top], f, indent=1)

    lines = [f"# Auto-scraper report — {day}", "",
             f"Scraped {len(jobs)} raw listings from {', '.join(src_names)}.",
             f"Passed: {len(passed)} | Review: {len(review)} | Failed: {len(failed)}",
             f"Lanes: " + " | ".join(
                 f"{lid} ({lane_names[lid].split(' —')[0].split(' (')[0]}): {len(recs)}"
                 for lid, recs in lanes.items()),
             f"Errors: {'; '.join(errors) if errors else 'none'}", "",
             f"## Top {len(top)}", ""]
    for i, r in enumerate(top, 1):
        j = r["job"]
        pay = ""
        if j.get("salary_min") or j.get("salary_max"):
            unit = "/hr" if j.get("salary_unit") == "hourly" else "/yr"
            pay = f" — ${j.get('salary_min') or '?'}–${j.get('salary_max') or '?'}{unit}"
        lines.append(f"### {i}. {j['title']} — {j['company']}{pay}")
        lines.append(f"- Source: {j['source']} | Location: {j['location']}"
                     f" | Remote: {j['remote']}")
        lines.append(f"- Score: {r['score']} ({', '.join(r['score_notes'])})")
        lines.append(f"- Why: {'; '.join(r['reasons'])}")
        if j.get("apply_email"):
            lines.append(f"- Apply: email {j['apply_email']}")
        elif j.get("apply_url"):
            lines.append(f"- Apply: {j['apply_url']}")
        lines.append(f"- Listing: {j['url']}")
        lines.append("")
    if review:
        lines += ["## Review (needs his call)", ""]
        for r in review[:10]:
            j = r["job"]
            lines.append(f"- {j['title']} — {j['company']} ({j['source']}): {'; '.join(r['reasons'])}")
    if verified_map:
        lines += ["", "## Verified apply routes (live Chromium check)", ""]
        for i, r in enumerate(top[:args.verify], 1):
            j = r["job"]
            v = verified_map.get(j.get("apply_url") or j.get("url"), {})
            verdict = v.get("verdict", "not run")
            au = v.get("apply_url") or ""
            au_s = f" → {au}" if au and au != (j.get("apply_url") or j.get("url")) else ""
            lines.append(f"- {i}. {j['title']} — {j['company']}: **{verdict}**{au_s}"
                         f" ({v.get('notes', 'n/a')})")
    with open(os.path.join(outdir, "report.md"), "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote {outdir}/leads.json and report.md")

    # Draft mode: Gmail drafts for email-route leads (no approval needed for drafts)
    if args.drafts:
        n = 0
        for r in top[:args.drafts]:
            j = r["job"]
            if not j.get("apply_email"):
                continue
            prof = _profile(j["title"])
            domain, stack_para = STACK_PARAS[prof]
            body = COVER_TEMPLATE.format(role=j["title"], domain=domain,
                                         stack_para=stack_para)
            cmd = ["hatch_gws_cli", "gmail", "+draft", "--to", j["apply_email"],
                   "--subject", f"Application for {j['title']} - Ibrahim Hamid",
                   "--body", body, "--attach", RESUME]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=120)
                n += 1
                print(f"  draft -> {j['apply_email']} ({j['company']})")
            except Exception as e:
                print(f"  draft FAILED for {j['company']}: {e}")
        print(f"Created {n} drafts")


if __name__ == "__main__":
    main()
