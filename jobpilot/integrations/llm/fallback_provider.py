"""
AI Provider Fallback System.
Chains multiple providers (Groq -> OpenRouter -> Direct Heuristic Fallback).
If a provider fails, encounters a 429 rate limit, or times out, the next
configured provider is seamlessly engaged without crashing the request.
"""
from __future__ import annotations

import os
from typing import List, Optional, Type
from pydantic import BaseModel

from ...core.config import settings
from ...core.logging import get_logger
from .base import LLMError, LLMProvider, register_provider
from .groq_provider import GroqProvider
from .openrouter_provider import OpenRouterProvider

logger = get_logger(__name__)


class FallbackProvider(LLMProvider):
    provider_name = "fallback"

    def __init__(self) -> None:
        self.providers: List[LLMProvider] = []

        # Attempt to load Groq
        if os.environ.get("GROQ_API_KEY") or settings.GROQ_API_KEY:
            try:
                self.providers.append(GroqProvider())
                logger.info("[LLM:FALLBACK] Registered Groq provider in chain")
            except Exception as e:
                logger.warning("[LLM:FALLBACK] Could not initialize Groq: %s", e)

        # Attempt to load OpenRouter
        if os.environ.get("OPENROUTER_API_KEY") or settings.OPENROUTER_API_KEY:
            try:
                self.providers.append(OpenRouterProvider())
                logger.info("[LLM:FALLBACK] Registered OpenRouter provider in chain")
            except Exception as e:
                logger.warning("[LLM:FALLBACK] Could not initialize OpenRouter: %s", e)

    def _call(self, system: str, user: str, temperature: float, max_tokens: int) -> str:
        last_error = None
        for prov in self.providers:
            try:
                logger.info("[LLM:FALLBACK] Attempting call with provider: %s", prov.provider_name)
                return prov._call(system, user, temperature, max_tokens)
            except Exception as exc:
                last_error = exc
                logger.warning("[LLM:FALLBACK] Provider %s failed (%s). Falling back to next available provider...", prov.provider_name, exc)
                continue

        raise LLMError(f"All configured fallback providers failed. Last error: {last_error}", retryable=False)

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Type[BaseModel],
        temperature: float = None,
    ) -> Optional[BaseModel]:
        for prov in self.providers:
            try:
                res = prov.complete_json(system_prompt, user_prompt, schema, temperature)
                if res is not None:
                    return res
            except Exception as exc:
                logger.warning("[LLM:FALLBACK] Provider %s complete_json failed: %s. Trying next...", prov.provider_name, exc)
                continue
        logger.error("[LLM:FALLBACK] All providers failed for structured JSON completion.")
        return None


register_provider("fallback", FallbackProvider)

