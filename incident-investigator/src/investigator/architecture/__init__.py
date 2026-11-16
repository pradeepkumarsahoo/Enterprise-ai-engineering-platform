# Author: Pradeep Sahoo
"""Use case 3: architecture & ADLC.

From a structured requirement: scores reference patterns against every NFR,
ranks the options, flags conflicts with accepted ADRs, raises open questions,
drafts an ADR and user stories, and traces each NFR to a component, ADRs and
stories. Everything drafted goes to a proposal pack for approval.
"""
from .assess import assess, trace
from .drafting import MockDrafter
from .sources import ArchitectureInputs


def get_drafter(name: str):
    if name == "mock":
        return MockDrafter()
    if name == "claude":
        from ..providers.claude import ClaudeProvider
        return ClaudeProvider()
    raise ValueError(f"Unknown provider: {name} (use 'mock' or 'claude')")


__all__ = ["ArchitectureInputs", "MockDrafter", "assess", "get_drafter", "trace"]
