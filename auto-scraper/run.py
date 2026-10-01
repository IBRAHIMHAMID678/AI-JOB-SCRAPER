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


def scrape(sources: list[str]) -> list[dict]:
    jobs, errors = [], []
    for name in sources:
        try:
            batch = SOURCES[name]()
            jobs.extend(batch)
            print(f"  {name}: {len(batch)} raw", flush=True)
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"  {name}: ERROR {e}", flush=True)
    return jobs, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--sources", default="remoteok,remotive,hn_hiring,linkedin,workingnomads,jobicy,himalayas,wwr")
    ap.add_argument("--out", default=os.path.join(BASE, "results"))
    ap.add_argument("--drafts", type=int, default=0,
                    help="create Gmail drafts for top-N email-route leads")
    ap.add_argument("--targets", default=os.path.join(BASE, "targets.yaml"),
                    help="YAML file of arbitrary websites/portals to scrape "
                         "(empty string disables)")
    args = ap.parse_args()

    src_names = [s for s in args.sources.split(",") if s in SOURCES]
    print(f"Scraping {len(src_names)} sources...")
    jobs, errors = scrape(src_names)

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
    print(f"Raw total: {len(jobs)}")

    applied = load_applied()
    seen_run = set()
    passed, review, failed = [], [], []
    for j in jobs:
        key = f"{j['company']}|{j['title']}".lower()
        if key in applied or key in seen_run:
            continue
        seen_run.add(key)
        verdict, reasons = filter_job(j)
        sc, notes = score(j, reasons)
        rec = {"job": j, "verdict": verdict, "reasons": reasons,
               "score": round(sc, 1), "score_notes": notes}
        # make posted_at JSON-safe later
        if verdict == "pass":
            passed.append(rec)
        elif verdict == "review":
            review.append(rec)
        else:
            failed.append(rec)
    print(f"pass={len(passed)} review={len(review)} fail={len(failed)}")

    passed.sort(key=lambda r: -r["score"])
    review.sort(key=lambda r: -r["score"])
    top = (passed + review)[:args.top]

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    outdir = os.path.join(args.out, day)
    os.makedirs(outdir, exist_ok=True)

    def _ser(r):
        j = dict(r["job"])
        p = j.get("posted_at")
        j["posted_at"] = p.isoformat() if p else None
        # trim huge descriptions
        if len(j.get("description") or "") > 4000:
            j["description"] = j["description"][:4000] + "…"
        return {"score": r["score"], "score_notes": r["score_notes"],
                "verdict": r["verdict"], "reasons": r["reasons"], "job": j}

    with open(os.path.join(outdir, "leads.json"), "w") as f:
        json.dump([_ser(r) for r in top], f, indent=1)

    lines = [f"# Auto-scraper report — {day}", "",
             f"Scraped {len(jobs)} raw listings from {', '.join(src_names)}.",
             f"Passed: {len(passed)} | Review: {len(review)} | Failed: {len(failed)}",
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
