# Author: Pradeep Sahoo
"""Use case 4 · change risk (pre-deploy assessment).

Scores a change before it ships from rule-based factors (sensitive settings, migrations,
contracts, coverage, deploy window, incident history, runbooks, size), finds similar past changes
that were followed by incidents, drafts release conditions with the model, and gates the release:
a high score needs two approvers, and the requester cannot approve. Depends only on ecc_core.
"""
from dataclasses import asdict

from ecc_core.llm import ClaudeClient
from ecc_core.plugin import UseCase

from .cli import register
from .drafting import DRAFT_SCHEMA, DRAFT_SYSTEM_PROMPT, MockDrafter, render_draft_request
from .factors import Rules, assess

__version__ = "0.2.0"


class ClaudeDrafter:
    """Use case 4's prompt and schema on the shared Claude client."""
    name = "claude"

    def __init__(self, client: ClaudeClient):
        self.client = client

    def draft_conditions(self, a) -> dict:
        return self.client.complete_json(DRAFT_SYSTEM_PROMPT, render_draft_request(a), DRAFT_SCHEMA)


def get_drafter(name: str, client_factory=ClaudeClient):
    if name == "mock":
        return MockDrafter()
    if name == "claude":
        return ClaudeDrafter(client_factory())
    raise ValueError(f"Unknown provider: {name} (use 'mock' or 'claude')")


USE_CASE = UseCase(
    key="change",
    title="Change risk",
    summary="pre-deploy risk score from rule-based factors, similar past changes, release conditions, release gate",
    register=register,
    paths=("changesets_dir", "calendar"),
    sources=("runbooks", "catalogue"),
    settings=asdict(Rules()),
    gates={"recall_min": 0.8, "false_alarm_max": 0.3, "rejected_conditions_max": 0, "invented_figures_max": 0,
           "note": ""},
)

__all__ = ["ClaudeDrafter", "MockDrafter", "Rules", "USE_CASE", "assess", "get_drafter"]
