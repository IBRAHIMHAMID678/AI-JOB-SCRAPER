"""
Matcha-Grade Company Intelligence & Metadata Enrichment Engine.
Attaches venture funding, key investors, company size, and logos to jobs.
"""
from __future__ import annotations

import os
import json
import sqlite3
from typing import Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEED_PATH = os.path.join(BASE_DIR, "companies_seed.json")
SQLITE_DB_PATH = os.path.join(BASE_DIR, "jobpilot.db")

class CompanyEnricher:
    def __init__(self):
        self.companies: Dict[str, Dict[str, Any]] = {}
        self.init_db()
        self.load_seed_data()

    def init_db(self):
        """Creates companies table non-destructively in SQLite."""
        try:
            conn = sqlite3.connect(SQLITE_DB_PATH)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id TEXT PRIMARY KEY,
                    slug TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    domain TEXT,
                    logo_url TEXT,
                    funding_total TEXT,
                    funding_stage TEXT,
                    key_investors TEXT, -- JSON array
                    company_size INTEGER,
                    company_summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[CompanyEnricher] DB Init Error: {e}")

    def load_seed_data(self):
        """Loads cached and seed company metadata into memory."""
        # 1. Load from companies_seed.json if exists
        if os.path.exists(SEED_PATH):
            try:
                with open(SEED_PATH, "r", encoding="utf-8") as f:
                    self.companies = json.load(f)
            except Exception as e:
                print(f"[CompanyEnricher] Seed load error: {e}")

        # 2. Sync into SQLite
        try:
            conn = sqlite3.connect(SQLITE_DB_PATH)
            c = conn.cursor()
            for slug, comp in self.companies.items():
                c.execute("""
                    INSERT INTO companies (id, slug, name, domain, logo_url, funding_total, funding_stage, key_investors, company_size, company_summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(slug) DO UPDATE SET
                        logo_url=excluded.logo_url,
                        funding_total=excluded.funding_total,
                        funding_stage=excluded.funding_stage,
                        key_investors=excluded.key_investors,
                        company_size=excluded.company_size,
                        company_summary=excluded.company_summary
                """, (
                    comp.get("id") or slug,
                    slug,
                    comp.get("name", slug.title()),
                    comp.get("domain", f"{slug}.com"),
                    comp.get("logo_url", ""),
                    comp.get("funding_total", ""),
                    comp.get("funding_stage", ""),
                    json.dumps(comp.get("key_investors", [])),
                    comp.get("company_size") or 0,
                    comp.get("company_summary", "")
                ))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[CompanyEnricher] SQLite sync error: {e}")

    def get_company(self, slug_or_name: str) -> Dict[str, Any]:
        """Resolves company metadata by slug or name."""
        if not slug_or_name:
            return self._default_company("Unknown")
        key = slug_or_name.lower().replace(" ", "").replace("-", "")
        for k, v in self.companies.items():
            if k.lower().replace(" ", "").replace("-", "") == key or v.get("name", "").lower() == slug_or_name.lower():
                return v

        # Fallback with default domain favicon
        clean_slug = slug_or_name.lower().replace(" ", "-")
        return {
            "id": clean_slug,
            "name": slug_or_name.title(),
            "domain": f"{clean_slug}.com",
            "logo_url": f"https://www.google.com/s2/favicons?domain={clean_slug}.com&sz=128",
            "funding_total": "Venture Backed",
            "funding_stage": "Growth",
            "key_investors": [],
            "company_size": 100,
            "company_summary": f"{slug_or_name.title()} is a high-growth technology company."
        }

    def _default_company(self, name: str) -> Dict[str, Any]:
        return {
            "id": "unknown",
            "name": name,
            "domain": "",
            "logo_url": "",
            "funding_total": "",
            "funding_stage": "",
            "key_investors": [],
            "company_size": 0,
            "company_summary": ""
        }

    def enrich_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Attaches full company metadata to a job dictionary."""
        co_slug = job.get("company_slug") or job.get("company", "")
        comp_info = self.get_company(co_slug)
        job["companies"] = comp_info
        job["company_summary"] = comp_info.get("company_summary") or job.get("company_summary", "")
        job["company_size"] = comp_info.get("company_size") or 0
        job["logo_url"] = comp_info.get("logo_url") or ""
        job["funding_total"] = comp_info.get("funding_total") or ""
        job["key_investors"] = comp_info.get("key_investors") or []
        return job

if __name__ == "__main__":
    enricher = CompanyEnricher()
    sample = {"company": "Together AI", "company_slug": "togetherai", "title": "AI Engineer"}
    enriched = enricher.enrich_job(sample)
    print("Sample enriched job:", json.dumps(enriched, indent=2))
