"""
End-to-End Test Suite for the Founder Radar & Side-Door Machine.
Tests:
1. Zero-Cost Email Verifier & Pattern Derivation.
2. Hacker News Algolia Live Sniper & Filter Invariants.
3. SEC Form D Edgar & Agency Partner Radar.
4. Startup App Teardown Studio (REA-inspired decompiler).
5. Outreach Agent Pitch Generator (1-Week Risk-Free Trial).
6. FastAPI Radar API Endpoints.
7. Dashboard HTML Rendering & Legacy Exclusion Invariants.
"""
import pytest
from fastapi.testclient import TestClient

from jobpilot.api.main import app
from jobpilot.services.email_verifier import EmailVerifier
from jobpilot.services.hn_sniper import HNSniper
from jobpilot.services.underground_radar import UndergroundRadar
from jobpilot.services.app_teardown import AppTeardownEngine
from jobpilot.agents.outreach_agent import OutreachAgent


@pytest.fixture
def client():
    return TestClient(app)


# ── 1. Email Verifier Tests ───────────────────────────────────────────────────

def test_candidate_email_patterns():
    candidates = EmailVerifier.generate_candidate_emails("Alex", "Vance", "neuralflow.ai")
    assert "alex@neuralflow.ai" in candidates
    assert "alex.vance@neuralflow.ai" in candidates
    assert "avance@neuralflow.ai" in candidates
    assert len(candidates) >= 4


async def test_email_verifier_resolve():
    res = await EmailVerifier.resolve_verified_email("Dan", "Miller", "example.com")
    assert res is not None
    assert "verified_email" in res
    assert "@example.com" in res["verified_email"]
    assert res["confidence"] >= 70


# ── 2. Hacker News Sniper Tests ───────────────────────────────────────────────

def test_hn_comment_parser_valid():
    raw_comment = {
        "objectID": "9998881",
        "author": "techfounder",
        "created_at": "2026-10-10T12:00:00Z",
        "comment_text": "NeuralStream | Remote (Worldwide) | Full-Stack AI Engineer | Python, FastAPI, React. Email founder@neuralstream.ai to apply."
    }
    parsed = HNSniper.parse_hiring_comment(raw_comment)
    assert parsed is not None
    assert parsed["company"] == "NeuralStream"
    assert parsed["contact_email"] == "founder@neuralstream.ai"
    assert parsed["is_worldwide"] is True
    assert "fastapi" in parsed["matched_skills"]


def test_hn_comment_parser_disqualifies_us_only():
    raw_comment = {
        "objectID": "9998882",
        "author": "usrecruiter",
        "created_at": "2026-10-10T12:00:00Z",
        "comment_text": "US Only | Must reside in North America | Python Engineer. Email us@company.com"
    }
    parsed = HNSniper.parse_hiring_comment(raw_comment)
    assert parsed is None, "Should disqualify jobs with explicit US Only geofences"


# ── 3. SEC Form D & Agency Radar Tests ────────────────────────────────────────

async def test_underground_agencies():
    agencies = await UndergroundRadar.fetch_boutique_agencies()
    assert len(agencies) >= 3
    for agency in agencies:
        assert agency["source"] == "agency_partner_network"
        assert "@" in agency["verified_email"]
        assert "pitch_angle" in agency


async def test_sec_form_d_fallback_resilience():
    leads = await UndergroundRadar.fetch_sec_form_d_leads(limit=3)
    assert len(leads) >= 2
    for lead in leads:
        assert lead["source"] == "sec_form_d_edgar"
        assert lead["company"]


# ── 4. App Teardown Studio Tests ──────────────────────────────────────────────

async def test_app_teardown_analysis():
    findings = await AppTeardownEngine.analyze_target_app("https://example.com")
    assert findings is not None
    assert findings["domain"] == "example.com"
    assert "teardown_memo" in findings
    assert "Ibrahim Hamid" in findings["teardown_memo"]
    assert "1-week risk-free trial" in findings["teardown_memo"]
    assert "recommended_fix" in findings
    assert "FastAPI" in findings["recommended_fix"]


# ── 5. Outreach Pitch Generator Tests ─────────────────────────────────────────

def test_outreach_pitch_generator_seed():
    pitch = OutreachAgent.generate_pitch(
        company_name="ApexAI",
        contact_name="Marcus",
        contact_title="CTO",
        pitch_type="seed_founder",
        tech_stack=["FastAPI", "React", "vLLM"]
    )
    assert "ApexAI" in pitch["subject"]
    assert "1-week risk-free trial" in pitch["body"]
    assert "https://ibrahimhamid.vercel.app/demo?client=apexai" in pitch["demo_link"]
    assert "FastAPI, React, vLLM" in pitch["body"]


def test_outreach_pitch_generator_agency():
    pitch = OutreachAgent.generate_pitch(
        company_name="VocalFlow",
        contact_name="Sarah",
        contact_title="Agency Partner",
        pitch_type="agency_owner",
        tech_stack=["Python", "Vapi", "FastAPI"]
    )
    assert "VocalFlow" in pitch["subject"]
    assert "microservices" in pitch["subject"]
    assert "1-week risk-free trial" in pitch["body"]


# ── 6. FastAPI Radar API Endpoints End-to-End ─────────────────────────────────

def test_api_radar_feed(client):
    resp = client.get("/api/radar/feed?stream=agency&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["leads"]) >= 3
    assert data["counts"]["boutique_agencies"] >= 3


def test_api_verify_email(client):
    resp = client.post("/api/radar/verify-email", json={
        "first_name": "Alex",
        "last_name": "Vance",
        "domain": "neuralflow.ai"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "verified_email" in data["result"]
    assert "@neuralflow.ai" in data["result"]["verified_email"]


def test_api_teardown(client):
    resp = client.post("/api/radar/teardown", json={
        "url": "https://example.com"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "findings" in data
    assert "teardown_memo" in data["findings"]


def test_api_generate_pitch(client):
    resp = client.post("/api/radar/generate-pitch", json={
        "company_name": "NeuralFlow AI",
        "contact_name": "Alex Vance",
        "contact_title": "CTO",
        "pitch_type": "seed_founder",
        "tech_stack": ["FastAPI", "React", "LangChain"]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "NeuralFlow AI" in data["pitch"]["subject"]
    assert "1-week risk-free trial" in data["pitch"]["body"]


# ── 7. Dashboard HTML Invariants ──────────────────────────────────────────────

def test_dashboard_html_contains_radar(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    # Must have Founder Radar components
    assert "Founder Radar" in html
    assert "id=\"page-radar\"" in html
    assert "id=\"radar-teardown-box\"" in html
    assert "id=\"radar-verify-box\"" in html
    assert "id=\"pitch-modal\"" in html
    assert "Apollo.io Seed Discovery" in html
    # Must NOT have legacy Telegram section in settings
    assert "s-tg-token" not in html
    assert "testTelegram" not in html
