# Author: Pradeep Sahoo
"""Use case 5 · FinOps (cloud cost by team).

Allocates the cloud cost export to teams, shows monthly spend by team with a month-end forecast,
flags statistically unusual increases with their likely cause, and proposes savings with
estimated and realised savings kept apart: estimates from formulas in code, realised savings
measured from the bill. The owning team decides every recommendation; nothing here changes a
cloud resource. Depends only on ecc_core.
"""
from dataclasses import asdict

from ecc_core.llm import ClaudeClient
from ecc_core.plugin import UseCase

from .analysis import Rules
from .cli import register
from .drafting import DRAFT_SCHEMA, DRAFT_SYSTEM_PROMPT, MockDrafter, render_draft_request

__version__ = "0.2.0"


class ClaudeDrafter:
    """Use case 5's prompt and schema on the shared Claude client."""
    name = "claude"

    def __init__(self, client: ClaudeClient):
        self.client = client

    def draft(self, a) -> dict:
        return self.client.complete_json(DRAFT_SYSTEM_PROMPT, render_draft_request(a), DRAFT_SCHEMA)


def get_drafter(name: str, client_factory=ClaudeClient):
    if name == "mock":
        return MockDrafter()
    if name == "claude":
        return ClaudeDrafter(client_factory())
    raise ValueError(f"Unknown provider: {name} (use 'mock' or 'claude')")


USE_CASE = UseCase(
    key="finops",
    title="FinOps",
    summary="monthly spend by team, statistically flagged anomalies with likely cause, estimated vs realised savings",
    register=register,
    paths=("finops_dir",),
    sources=("catalogue",),
    settings=asdict(Rules()),
    gates={"anomaly_precision_min": 0.8, "anomaly_recall_min": 0.8, "cause_accuracy_min": 0.8,
           "realised_error_max": 0.1, "rejected_drafts_max": 0, "invented_figures_max": 0, "cloud_changes_max": 0,
           "note": ""},
)

__all__ = ["ClaudeDrafter", "MockDrafter", "Rules", "USE_CASE", "get_drafter"]
