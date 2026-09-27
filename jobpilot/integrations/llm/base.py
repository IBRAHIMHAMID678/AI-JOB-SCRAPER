"""
LLM provider abstraction.
Swap providers by changing LLM_PROVIDER in config — no code changes needed.
All prompts must request structured JSON output.
All LLM responses are validated against schemas.
"""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from ...core.config import settings
from ...core.logging import get_logger

logger = get_logger(__name__)


class LLMError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(ABC):
    """Base for all LLM backends."""

    provider_name: str = "base"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        """Return raw text response."""
        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        tokens = max_tokens or settings.LLM_MAX_TOKENS

        for attempt in range(1, settings.LLM_MAX_RETRIES + 1):
            try:
                result = self._call(system_prompt, user_prompt, temp, tokens)
                logger.debug("[LLM:%s] Success on attempt %d", self.provider_name, attempt)
                return result
            except LLMError as exc:
                if not exc.retryable or attempt >= settings.LLM_MAX_RETRIES:
                    raise
                delay = 2 ** attempt
                logger.warning("[LLM:%s] Attempt %d failed, retrying in %ds: %s", self.provider_name, attempt, delay, exc)
                time.sleep(delay)

        raise LLMError(f"All {settings.LLM_MAX_RETRIES} retries exhausted", retryable=False)

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Type[BaseModel],
        temperature: float = None,
    ) -> Optional[BaseModel]:
        """
        Call LLM and parse the result into a Pydantic model.
        Retries with correction prompt if JSON is invalid.
        Returns None on total failure — never raises in normal usage.
        """
        full_system = (
            system_prompt
            + "\n\nIMPORTANT: Respond ONLY with valid JSON matching the required schema. No markdown. No explanation."
        )
        # Item 38: 3 attempts before falling back to rule-based (was 2)
        for attempt in range(1, 4):
            try:
                raw = self.complete(full_system, user_prompt, temperature=temperature)
                parsed = _extract_json(raw)
                return schema.model_validate(parsed)
            except Exception as exc:
                if attempt < 3:
                    logger.warning("[LLM:%s] JSON parse failed (attempt %d/3), retrying with correction: %s", self.provider_name, attempt, exc)
                    user_prompt = user_prompt + "\n\nYour previous response was not valid JSON. Please respond with ONLY valid JSON."
                else:
                    logger.error("[LLM:%s] JSON validation failed after 3 attempts: %s", self.provider_name, exc)
                    return None
        return None

    @abstractmethod
    def _call(self, system: str, user: str, temperature: float, max_tokens: int) -> str:
        """Implement the actual API call."""


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM output that may contain markdown fences."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown code fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # Find first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"No JSON found in LLM response: {text[:200]}")


# ── Provider registry ─────────────────────────────────────────────────────────

_REGISTRY: Dict[str, Type[LLMProvider]] = {}


def register_provider(name: str, cls: Type[LLMProvider]) -> None:
    _REGISTRY[name] = cls


def get_provider() -> LLMProvider:
    name = settings.LLM_PROVIDER
    cls = _REGISTRY.get(name)
    if cls is None:
        available = list(_REGISTRY.keys())
        raise LLMError(f"LLM provider '{name}' not found. Available: {available}", retryable=False)
    return cls()
