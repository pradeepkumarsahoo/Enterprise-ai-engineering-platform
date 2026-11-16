# Author: Pradeep Sahoo
"""Use case 1 · incident investigation.

Read-only, evidence-backed incident investigation, run first on past incidents
(replay) and then alongside on-call engineers (shadow mode). Depends only on
ecc_core.
"""
from ecc_core.plugin import UseCase

from .cli import register
from .policy import LEAD_CONFIDENCE_MIN, MAX_CONFIDENCE

__version__ = "0.2.0"

USE_CASE = UseCase(
    key="incident",
    title="Incident investigation",
    summary="evidence-backed diagnosis, on past incidents (replay) then alongside on-call (shadow)",
    register=register,
    paths=("incidents", "labels", "live"),
    sources=("runbooks",),
    settings={"lead_confidence_min": LEAD_CONFIDENCE_MIN, "max_confidence": MAX_CONFIDENCE},
    gates={"lead_accuracy_min": 0.75, "false_confident_leads_max": 0, "unsupported_claims_max": 0,
           "actions_executed_max": 0, "note": ""},
)
