"""
Outreach Agent & Technical Memo Generator.
Generates concise, hyper-personalized 3-sentence technical pitches tailored for:
1. Seed Founders (<15 headcount, closed round in last 60 days).
2. Boutique Agency Owners (Vapi, n8n, Clutch).
3. Fractional CTOs managing multiple startups.
Eliminates junior bias by leveraging proof-of-work, dynamic sandbox links, and the 1-Week Risk-Free Trial.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


class OutreachAgent:
    """Generates high-converting engineering memos and pitch drafts."""

    PORTFOLIO_BASE_URL = "https://ibrahimhamid.vercel.app"

    @classmethod
    def generate_pitch(
        cls,
        company_name: str,
        contact_name: Optional[str] = None,
        contact_title: Optional[str] = None,
        pitch_type: str = "seed_founder",
        tech_stack: Optional[list] = None,
        custom_angle: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Generates a 3-sentence technical pitch with dynamic sandbox link and trial offer.
        """
        name = (contact_name or "there").split()[0]
        stack = ", ".join(tech_stack[:3]) if tech_stack else "FastAPI, React, and LangChain"
        clean_client = company_name.lower().replace(" ", "").replace(".ai", "").replace(".com", "")
        demo_link = f"{cls.PORTFOLIO_BASE_URL}/demo?client={clean_client}"

        if pitch_type == "agency_owner":
            subject = f"Custom {tech_stack[0] if tech_stack else 'Python/FastAPI'} microservices for {company_name}'s client backlogs"
            body = f"""Hi {name},

Saw {company_name} delivers voice and workflow systems. Most client deployments hit a wall when they need custom async Python microservices, database bridges, or custom API webhooks.

I'm an AI Full-Stack Developer specializing in high-throughput FastAPI backends and interactive React frontends. Here is an interactive demo of my production RAG architecture: {demo_link}

If you have client feature requests or backend Jira tickets your core team doesn't have time to touch, I can execute them on a 1-week risk-free trial.

Best,
Ibrahim Hamid
AI/ML Engineer & Systems Architect"""

        elif pitch_type == "fractional_cto":
            subject = f"Contract engineering capacity for your portfolio teams ({company_name})"
            body = f"""Hi {name},

Saw you direct engineering for early-stage teams at {company_name}. I know a recurring headache for fractional technical leaders is finding reliable builders who can ship production FastAPI services and React MVPs without handholding.

I specialize in async Python backends and agentic workflows—recently shipped a forensic LLM guardrail system with AST safety parsing ({demo_link}).

If any of your portfolio startups need immediate feature execution without the friction or overhead of US hiring, I'm available for a 1-week risk-free trial sprint via Wise/Deel.

Best,
Ibrahim Hamid"""

        else:  # seed_founder
            subject = f"FastAPI + React execution for {company_name} (congrats on the round)"
            body = f"""Hi {name},

Congratulations on {company_name}'s recent funding round. 

I saw you're building with {stack}. I'm an AI Full-Stack Developer who specializes in production RAG systems and high-throughput async backends—recently launched a live forensic LLM guardrail harness and real-time agent demos ({demo_link}).

I know shipping your MVP endpoints fast without burning runway is priority #1. If you need someone who can take immediate ownership of your feature backlog without handholding, let's do a 1-week risk-free trial sprint. If you aren't thrilled with the code quality, you owe $0.

Best,
Ibrahim Hamid
AI/ML Engineer & Systems Architect"""

        return {
            "subject": subject,
            "body": body,
            "demo_link": demo_link,
            "recipient_name": name,
            "company": company_name
        }
