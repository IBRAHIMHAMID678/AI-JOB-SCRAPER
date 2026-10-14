"""
API routes for the Side-Door Machine and Founder Radar.
Provides real-time endpoints for:
1. Unified Lead Stream (Apollo Seed, HN Who is Hiring, SEC Form D, Remotive).
2. Zero-Cost SMTP MX Verification.
3. Startup App Teardown Studio.
4. Technical Memo & Pitch Generation.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...services.email_verifier import EmailVerifier
from ...services.hn_sniper import HNSniper
from ...services.apollo_service import ApolloService
from ...services.underground_radar import UndergroundRadar
from ...services.app_teardown import AppTeardownEngine
from ...agents.outreach_agent import OutreachAgent

router = APIRouter(prefix="/radar", tags=["founder-radar"])


class EmailVerificationRequest(BaseModel):
    first_name: str = Field(..., example="Alex")
    last_name: Optional[str] = Field(default="", example="Vance")
    domain: str = Field(..., example="neuralflow.ai")


class TeardownRequest(BaseModel):
    url: str = Field(..., example="https://neuralflow.ai")


class PitchRequest(BaseModel):
    company_name: str
    contact_name: Optional[str] = "Founder"
    contact_title: Optional[str] = "CTO"
    pitch_type: Optional[str] = "seed_founder"
    tech_stack: Optional[List[str]] = None


@router.get("/feed")
async def get_radar_feed(
    stream: Optional[str] = Query(default="all", description="all | apollo | hn | sec | remotive | agency"),
    limit: int = Query(default=20, ge=1, le=50)
) -> Dict[str, Any]:
    """
    Returns an aggregated real-time stream of high-probability opportunities.
    Bypasses traditional geofenced job boards to deliver direct founder and agency contacts.
    """
    tasks = []
    
    if stream in ("all", "apollo"):
        apollo = ApolloService()
        tasks.append(apollo.harvest_full_leads(count=min(limit, 8)))
    else:
        tasks.append(asyncio.sleep(0, result=[]))

    if stream in ("all", "hn"):
        tasks.append(HNSniper.fetch_worldwide_leads(limit=min(limit, 8)))
    else:
        tasks.append(asyncio.sleep(0, result=[]))

    if stream in ("all", "sec"):
        tasks.append(UndergroundRadar.fetch_sec_form_d_leads(limit=min(limit, 5)))
    else:
        tasks.append(asyncio.sleep(0, result=[]))

    if stream in ("all", "remotive"):
        tasks.append(UndergroundRadar.fetch_remotive_worldwide_jobs(limit=min(limit, 6)))
    else:
        tasks.append(asyncio.sleep(0, result=[]))

    if stream in ("all", "agency"):
        tasks.append(UndergroundRadar.fetch_boutique_agencies())
    else:
        tasks.append(asyncio.sleep(0, result=[]))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    apollo_leads = results[0] if isinstance(results[0], list) else []
    hn_leads = results[1] if isinstance(results[1], list) else []
    sec_leads = results[2] if isinstance(results[2], list) else []
    remotive_leads = results[3] if isinstance(results[3], list) else []
    agency_leads = results[4] if isinstance(results[4], list) else []

    all_leads = []
    all_leads.extend(apollo_leads)
    all_leads.extend(hn_leads)
    all_leads.extend(agency_leads)
    all_leads.extend(sec_leads)
    all_leads.extend(remotive_leads)

    return {
        "status": "success",
        "total_count": len(all_leads),
        "counts": {
            "apollo_seed": len(apollo_leads),
            "hacker_news": len(hn_leads),
            "boutique_agencies": len(agency_leads),
            "sec_form_d": len(sec_leads),
            "remotive_worldwide": len(remotive_leads)
        },
        "leads": all_leads[:limit]
    }


@router.post("/verify-email")
async def verify_work_email(payload: EmailVerificationRequest) -> Dict[str, Any]:
    """
    Performs zero-cost SMTP MX handshake probe against target domain.
    Verifies inbox existence on port 25 without sending an email or consuming credits.
    """
    result = await EmailVerifier.resolve_verified_email(
        first_name=payload.first_name,
        last_name=payload.last_name or "",
        domain=payload.domain
    )
    return {"status": "success", "result": result}


@router.post("/teardown")
async def teardown_target_app(payload: TeardownRequest) -> Dict[str, Any]:
    """
    Decompiles client-side bundles and network routes of a target startup.
    Generates a 3-bullet architectural memo and recommended code fix for their CTO.
    """
    findings = await AppTeardownEngine.analyze_target_app(payload.url)
    return {"status": "success", "findings": findings}


@router.post("/generate-pitch")
async def generate_technical_pitch(payload: PitchRequest) -> Dict[str, Any]:
    """
    Generates a high-converting 3-sentence technical memo with dynamic sandbox demo link.
    """
    pitch = OutreachAgent.generate_pitch(
        company_name=payload.company_name,
        contact_name=payload.contact_name,
        contact_title=payload.contact_title,
        pitch_type=payload.pitch_type or "seed_founder",
        tech_stack=payload.tech_stack or ["Python", "FastAPI", "React"]
    )
    return {"status": "success", "pitch": pitch}
