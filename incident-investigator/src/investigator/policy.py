# Author: Pradeep Sahoo
"""Policy: which recommended actions need a human, and what each mode may do.

Risk and approval are set here, in code, from the action type. The model
proposes an action type; it cannot lower the risk or skip approval.

Neither mode can execute anything. There is no execute function in this
package; recommendations are written to a report or review queue only.
"""
from __future__ import annotations

ACTION_POLICY: dict[str, tuple[str, bool]] = {
    # action_type: (risk, requires_approval)
    "read_only_diagnostic": ("low", False),
    "escalate": ("low", False),
    "config_change": ("medium", True),
    "feature_flag_change": ("medium", True),
    "scale": ("medium", True),
    "restart": ("medium", True),
    "rollback": ("high", True),
}

MODES = {
    # replay: past incidents, results go to an evaluation report only
    "replay": {"notify_on_call": False, "write_ticket": False},
    # shadow: live incidents, results go to a review queue the SRE lead reads;
    # on-call engineers are not paged and the incident ticket is not changed
    "shadow": {"notify_on_call": False, "write_ticket": False},
}

LEAD_CONFIDENCE_MIN = 0.5   # below this, the investigation reports "cause not established"
MAX_CONFIDENCE = 0.95       # no hypothesis is ever shown as certain


def classify(action_type: str) -> tuple[str, bool]:
    # Unknown action types are treated as the riskiest kind.
    return ACTION_POLICY.get(action_type, ("high", True))
