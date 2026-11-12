"""Plain data types shared across the investigator."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

CAUSE_CATEGORIES = (
    "config_change",
    "slow_query",
    "traffic_spike",
    "dependency_failure",
    "resource_leak",
    "certificate_expiry",
    "bad_feature_flag",
    "code_change",
    "unknown",
)

ACTION_TYPES = (
    "read_only_diagnostic",
    "config_change",
    "rollback",
    "restart",
    "scale",
    "feature_flag_change",
    "escalate",
)


@dataclass
class Evidence:
    id: str              # E1, E2, ... stable within one investigation
    kind: str            # deployment | metric | logs | config_diff | flag_change | dependency_status | runbook
    source: str          # which adapter produced it
    summary: str         # computed in code; never written by the model
    flags: list[str] = field(default_factory=list)   # e.g. "possible_prompt_injection", "secret_redacted"


@dataclass
class Candidate:
    """A cause suggested by a deterministic detector, before the model sees it."""
    cause_category: str
    title: str
    supporting: list[str]
    contradicting: list[str]
    score: float         # 0..1, rule-based prior
    gaps: list[str] = field(default_factory=list)


@dataclass
class Hypothesis:
    title: str
    cause_category: str
    confidence: float
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    explanation: str


@dataclass
class NextStep:
    description: str
    action_type: str
    evidence: list[str]
    risk: str = "low"
    requires_approval: bool = False


@dataclass
class Investigation:
    incident_id: str
    service: str
    mode: str                         # replay | shadow
    provider: str
    summary: str
    hypotheses: list[Hypothesis]
    could_not_establish: list[str]
    next_steps: list[NextStep]
    evidence: list[Evidence]
    candidates: list[Candidate]
    unsupported_claims: list[str]     # what validation removed, and why
    duration_s: float
    correlation_id: str

    def lead(self) -> Hypothesis | None:
        return self.hypotheses[0] if self.hypotheses else None

    def to_dict(self) -> dict:
        return asdict(self)
