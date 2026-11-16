# Author: Pradeep Sahoo
"""Use case 2 · knowledge & runbooks.

Checks runbooks against what responders actually did, finds broken references,
stale and unowned runbooks, coverage gaps, repeat incidents and overdue
follow-up actions, and drafts runbook edits for owners to approve. Depends only
on ecc_core.
"""
from ecc_core.llm import ClaudeClient
from ecc_core.plugin import UseCase

from .checks import (DRIFT_LOOKBACK_DAYS, REPEAT_GAP_DAYS, REPEAT_LOOKBACK_DAYS, STALE_DAYS, Thresholds,
                     analyse)
from .cli import register
from .drafting import EDIT_SCHEMA, EDIT_SYSTEM_PROMPT, MockDrafter, render_edit_request
from .sources import KnowledgeBase

__version__ = "0.2.0"


class ClaudeDrafter:
    """Use case 2's prompt and schema on the shared Claude client."""
    name = "claude"

    def __init__(self, client: ClaudeClient):
        self.client = client

    def draft_runbook_edits(self, inp) -> dict:
        return self.client.complete_json(EDIT_SYSTEM_PROMPT, render_edit_request(inp), EDIT_SCHEMA)


def get_drafter(name: str, client_factory=ClaudeClient):
    if name == "mock":
        return MockDrafter()
    if name == "claude":
        return ClaudeDrafter(client_factory())
    raise ValueError(f"Unknown provider: {name} (use 'mock' or 'claude')")


USE_CASE = UseCase(
    key="knowledge",
    title="Knowledge & runbooks",
    summary="stale, unowned and broken runbooks, repeat incidents, overdue actions, drafted runbook edits",
    register=register,
    paths=("knowledge_dir",),
    sources=("runbooks",),
    settings={"stale_days": STALE_DAYS, "drift_lookback_days": DRIFT_LOOKBACK_DAYS,
              "repeat_gap_days": REPEAT_GAP_DAYS, "repeat_lookback_days": REPEAT_LOOKBACK_DAYS},
    gates={"findings_recall_min": 0.8, "findings_precision_min": 0.8, "repeat_clusters_exact": True,
           "rejected_edits_max": 0, "edits_published_without_approval_max": 0, "note": ""},
)

__all__ = ["ClaudeDrafter", "KnowledgeBase", "MockDrafter", "Thresholds", "USE_CASE", "analyse", "get_drafter"]
