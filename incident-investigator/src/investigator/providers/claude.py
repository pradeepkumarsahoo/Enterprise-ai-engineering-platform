"""Claude provider, via the official Anthropic Python SDK.

One structured-output request per investigation. The model gets no tools: it
cannot query, change or notify anything. Evidence is gathered by code before
the call and every citation is checked by code after it.

Choices:
- Model claude-opus-5-5 at effort "high": investigation is reasoning-heavy and
  a wrong lead costs on-call time. Thinking is adaptive by default on this model.
- output_config.format with a JSON schema, so the reply always parses.
- Server-side refusal fallbacks ("default") so a safety decline is retried on a
  fallback model inside the same call instead of failing the investigation.
- Non-streaming with max_tokens 16000, within SDK HTTP timeout limits.
"""
from __future__ import annotations

import json
import os

from .base import OUTPUT_SCHEMA, SYSTEM_PROMPT, ProviderError, ProviderInput, render_user_message

DEFAULT_MODEL = "claude-opus-5-5"


class ClaudeProvider:
    name = "claude"

    def __init__(self, client=None, model: str | None = None, effort: str = "high"):
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on environment
                raise ProviderError("Install the optional dependency: pip install 'incident-investigator[claude]'") from exc
            client = anthropic.Anthropic()   # credentials from ANTHROPIC_API_KEY or an `ant auth login` profile
        self.client = client
        self.model = model or os.environ.get("INVESTIGATOR_MODEL", DEFAULT_MODEL)
        self.effort = effort
        self.last_usage: dict | None = None

    def investigate(self, inp: ProviderInput) -> dict:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": render_user_message(inp)}],
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
        )
        usage = getattr(response, "usage", None)
        self.last_usage = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "model": getattr(response, "model", self.model),
            "request_id": getattr(response, "_request_id", None),
        }
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise ProviderError(f"Model declined the request (category: {getattr(details, 'category', None)})")
        if response.stop_reason == "max_tokens":
            raise ProviderError("Response hit max_tokens before the JSON was complete")
        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
        if text is None:
            raise ProviderError("No text block in the response")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Response was not valid JSON: {exc}") from exc
