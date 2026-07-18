"""Model provider abstraction (minimal v1).

v1 keeps this deliberately small: `complete(prompt)` (single-shot) + a
`max_context_tokens` attribute so the ContextAssembler can cap by tokens.
Streaming / tool-use / multi-turn are phase 2 (see plan).

The `NullProvider` is deterministic (echoes the prompt) so the engine is
fully testable with zero tokens. `OpenRouterProvider` talks to the
OpenRouter chat completions endpoint via stdlib `urllib` (no SDK dep).
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Optional

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class ModelProvider(ABC):
    max_context_tokens: int = 8192

    @abstractmethod
    def complete(self, prompt: str, model: Optional[str] = None) -> str:
        ...


class NullProvider(ModelProvider):
    """Deterministic echo stub — no network, no tokens.

    Echoes the prompt so tests can assert round-trip behavior of the
    assembly pipeline without a model.
    """

    max_context_tokens = 8192

    def complete(self, prompt: str, model: Optional[str] = None) -> str:
        return f"[null-provider-echo]\n{prompt}"


class OpenRouterProvider(ModelProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "openai/gpt-4o-mini",
        max_context_tokens: int = 128000,
        base_url: str = OPENROUTER_URL,
    ):
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OpenRouterProvider requires api_key or OPENROUTER_API_KEY")
        self.api_key = key
        self.model = model
        self.base_url = base_url
        self.max_context_tokens = max_context_tokens

    def complete(self, prompt: str, model: Optional[str] = None) -> str:
        payload = {
            "model": model or self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise PermissionError("OpenRouter auth failed (401)") from exc
            raise
