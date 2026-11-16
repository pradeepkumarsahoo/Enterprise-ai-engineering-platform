# Author: Pradeep Sahoo
"""Model client shared by every use case, via the official Anthropic Python SDK.

One method, `complete_json`: one structured-output request per task. Each use
case owns its own system prompt, schema and request rendering, and passes them
in. The model gets no tools, so it cannot query, change or notify anything.
Inputs are gathered by code before the call; every citation in the reply is
checked by code after it.

Settings come from `[model]` in the product configuration:
- model claude-opus-5-5 at effort "high": the tasks are reasoning-heavy and low
  volume, and a wrong answer costs engineer time. Thinking is adaptive by
  default on this model, so the request does not set it.
- output_config.format with a JSON schema, so the reply always parses.
- server-side refusal fallbacks, so a safety decline is retried on a fallback
  model inside the same call instead of failing the task.
- non-streaming with max_tokens 16000, within SDK HTTP timeout limits.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelSettings:
    model: str = DEFAULT_MODEL
    effort: str = "high"
    max_tokens: int = 16000
    fallbacks: str = "default"      # "" turns server-side fallbacks off


class ClaudeClient:
    name = "claude"

    def __init__(self, settings: ModelSettings | None = None, client=None):
        self.settings = settings or ModelSettings()
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on environment
                raise ProviderError("Install the optional dependency: pip install -e 'core[claude]'") from exc
            client = anthropic.Anthropic()   # credentials from ANTHROPIC_API_KEY or an `ant auth login` profile
        self.client = client
        self.last_usage: dict | None = None

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        """One structured-output request. Raises ProviderError on refusal, truncation or bad JSON."""
        s = self.settings
        extra = {"betas": [FALLBACK_BETA], "fallbacks": s.fallbacks} if s.fallbacks else {}
        response = self.client.beta.messages.create(
            model=s.model,
            max_tokens=s.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": s.effort, "format": {"type": "json_schema", "schema": schema}},
            **extra,
        )
        usage = getattr(response, "usage", None)
        self.last_usage = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "model": getattr(response, "model", s.model),
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


def fake_anthropic(payload: dict, calls: dict):
    """A stand-in for anthropic.Anthropic() in tests: records the request, returns payload as the reply."""
    from types import SimpleNamespace

    def create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(payload))], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1), model=DEFAULT_MODEL)

    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
