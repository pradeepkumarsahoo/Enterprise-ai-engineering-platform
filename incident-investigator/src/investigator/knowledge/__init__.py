# Author: Pradeep Sahoo
"""Use case 2: knowledge and runbooks.

Checks runbooks against what responders actually did, finds broken references,
stale and unowned runbooks, coverage gaps, repeat incidents and overdue
follow-up actions, and drafts runbook edits for owners to approve.
"""
from .checks import analyse
from .drafting import MockDrafter
from .sources import KnowledgeBase


def get_drafter(name: str):
    if name == "mock":
        return MockDrafter()
    if name == "claude":
        from ..providers.claude import ClaudeProvider
        return ClaudeProvider()
    raise ValueError(f"Unknown provider: {name} (use 'mock' or 'claude')")


__all__ = ["KnowledgeBase", "MockDrafter", "analyse", "get_drafter"]
