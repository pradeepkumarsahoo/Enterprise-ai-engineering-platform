# Author: Pradeep Sahoo
"""Providers for use case 1: the mock (default) and Claude, through the shared client in ecc_core."""
from ecc_core.llm import ClaudeClient, ProviderError

from ..policy import DEFAULT_LIMITS, Limits
from .base import OUTPUT_SCHEMA, SYSTEM_PROMPT, Provider, ProviderInput, render_user_message
from .mock import MockProvider


class ClaudeInvestigator:
    """Use case 1's prompt and schema on the shared Claude client."""
    name = "claude"

    def __init__(self, client: ClaudeClient):
        self.client = client

    def investigate(self, inp: ProviderInput) -> dict:
        return self.client.complete_json(SYSTEM_PROMPT, render_user_message(inp), OUTPUT_SCHEMA)


def get_provider(name: str, client_factory=ClaudeClient, limits: Limits = DEFAULT_LIMITS) -> Provider:
    if name == "mock":
        return MockProvider(limits)
    if name == "claude":
        return ClaudeInvestigator(client_factory())
    raise ValueError(f"Unknown provider: {name} (use 'mock' or 'claude')")


__all__ = ["OUTPUT_SCHEMA", "ClaudeInvestigator", "MockProvider", "Provider", "ProviderError", "ProviderInput",
           "get_provider"]
