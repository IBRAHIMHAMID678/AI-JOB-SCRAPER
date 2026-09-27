"""OpenRouter LLM provider (access to many models via one API)."""
from __future__ import annotations

import requests

from ...core.config import settings
from ...core.logging import get_logger
from .base import LLMError, LLMProvider, register_provider

logger = get_logger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(LLMProvider):
    provider_name = "openrouter"

    def __init__(self) -> None:
        if not settings.OPENROUTER_API_KEY:
            raise LLMError("OPENROUTER_API_KEY not set", retryable=False)
        self._model = settings.OPENROUTER_MODEL

    def _call(self, system: str, user: str, temperature: float, max_tokens: int) -> str:
        try:
            resp = requests.post(
                _BASE_URL,
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://jobpilot.local",
                    "X-Title": "JOBPILOT",
                },
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    # Item 38: force JSON output where the API supports it
                    "response_format": {"type": "json_object"},
                },
                timeout=settings.LLM_TIMEOUT,
            )
            if resp.status_code == 429:
                raise LLMError("OpenRouter rate limit", retryable=True)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"] or ""
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"OpenRouter error: {exc}", retryable=True)


register_provider("openrouter", OpenRouterProvider)
