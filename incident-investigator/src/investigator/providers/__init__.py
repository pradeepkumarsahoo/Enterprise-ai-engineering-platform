# Author: Pradeep Sahoo
from .base import OUTPUT_SCHEMA, Provider, ProviderError, ProviderInput
from .mock import MockProvider


def get_provider(name: str) -> Provider:
    if name == "mock":
        return MockProvider()
    if name == "claude":
        from .claude import ClaudeProvider
        return ClaudeProvider()
    raise ValueError(f"Unknown provider: {name} (use 'mock' or 'claude')")


__all__ = ["OUTPUT_SCHEMA", "Provider", "ProviderError", "ProviderInput", "MockProvider", "get_provider"]
