"""Groq LLM provider (fast inference, Llama models)."""
from __future__ import annotations

from ...core.config import settings
from ...core.logging import get_logger
from .base import LLMError, LLMProvider, register_provider

logger = get_logger(__name__)


class GroqProvider(LLMProvider):
    provider_name = "groq"

    def __init__(self) -> None:
        if not settings.GROQ_API_KEY:
            raise LLMError("GROQ_API_KEY not set", retryable=False)
        from groq import Groq
        self._client = Groq(api_key=settings.GROQ_API_KEY)
        self._model = settings.LLM_MODEL or "llama3-8b-8192"

    def _call(self, system: str, user: str, temperature: float, max_tokens: int) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=settings.LLM_TIMEOUT,
                # Item 38: force JSON output where the API supports it
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            msg = str(exc)
            retryable = "rate_limit" in msg.lower() or "timeout" in msg.lower() or "503" in msg
            raise LLMError(f"Groq API error: {msg}", retryable=retryable)


register_provider("groq", GroqProvider)
