# Author: Pradeep Sahoo
"""Use case 3 · architecture & ADLC.

From a structured requirement, or one extracted from a requirement document:
scores reference patterns against every NFR, ranks the options, flags
conflicts with accepted ADRs, raises open questions, drafts an ADR and user
stories, traces each NFR to a component, ADRs and stories, and draws a
container diagram of the preferred option. Everything drafted goes to a
proposal pack for approval. Depends only on ecc_core.
"""
from ecc_core.llm import ClaudeClient
from ecc_core.plugin import UseCase

from .assess import AVAILABILITY_MARGIN, LATENCY_MARGIN, THROUGHPUT_MARGIN, Rules, assess, trace
from .cli import register
from .diagram import container_diagram
from .drafting import DRAFT_SCHEMA, DRAFT_SYSTEM_PROMPT, MockDrafter, render_draft_request
from .html import MERMAID_ESM
from .intake import EXTRACT_SCHEMA, EXTRACT_SYSTEM_PROMPT, MockExtractor, render_extract_request
from .sources import ArchitectureInputs

__version__ = "0.2.0"


class ClaudeArchitect:
    """Use case 3's prompts and schemas on the shared Claude client: drafting and document extraction."""
    name = "claude"

    def __init__(self, client: ClaudeClient):
        self.client = client

    def draft_architecture(self, inp) -> dict:
        return self.client.complete_json(DRAFT_SYSTEM_PROMPT, render_draft_request(inp), DRAFT_SCHEMA)

    def extract_requirement(self, inp) -> dict:
        return self.client.complete_json(EXTRACT_SYSTEM_PROMPT, render_extract_request(inp), EXTRACT_SCHEMA)


def get_drafter(name: str, client_factory=ClaudeClient):
    if name == "mock":
        return MockDrafter()
    if name == "claude":
        return ClaudeArchitect(client_factory())
    raise ValueError(f"Unknown provider: {name} (use 'mock' or 'claude')")


def get_extractor(name: str, client_factory=ClaudeClient):
    if name == "mock":
        return MockExtractor()
    if name == "claude":
        return ClaudeArchitect(client_factory())
    raise ValueError(f"Unknown provider: {name} (use 'mock' or 'claude')")


USE_CASE = UseCase(
    key="architecture",
    title="Architecture & ADLC",
    summary="requirement (or requirement document) to scored options, ADR, stories, NFR traceability and diagram",
    register=register,
    paths=("arch_dir",),
    settings={"availability_margin": AVAILABILITY_MARGIN, "latency_margin": LATENCY_MARGIN,
              "throughput_margin": THROUGHPUT_MARGIN, "mermaid_url": MERMAID_ESM},
    gates={"assessment_accuracy_min": 0.95, "preferred_option_match": True, "nfr_trace_recall_min": 0.9,
           "rejected_drafts_max": 0, "invented_figures_max": 0, "decisions_made_without_approval_max": 0,
           "diagram_issues_max": 0, "note": ""},
)

__all__ = ["ArchitectureInputs", "ClaudeArchitect", "MockDrafter", "MockExtractor", "Rules", "USE_CASE", "assess",
           "container_diagram", "get_drafter", "get_extractor", "trace"]
