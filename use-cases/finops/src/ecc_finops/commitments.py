# Author: Pradeep Sahoo
"""Reservations and savings plans (use case 5).

The term of each commitment comes from the commitments inventory (the provider's reservations and
savings plans API); what it costs and how much of it is used come from the cost export:
    used        = effective cost of usage the commitment covered, in the last complete month
    unused      = effective cost of the commitment's unused lines, same month
    utilisation = used / (used + unused)
    billed      = what was invoiced for it in the export window (an upfront purchase lands here
                  in full, in the month it was bought)
    amortised   = effective cost of it in the export window (the same price, spread over its term)
A commitment under `commitment_utilisation_min` is underused; one ending within
`commitment_renewal_days` needs a renewal decision. Both are facts from code; whether to renew,
resize or let it lapse is the owning team's decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .rules import Rules
from .sources import FinOpsInputs
from .spend import Coverage

KINDS = {"reserved-instance": "Reserved instance", "savings-plan": "Savings plan"}


@dataclass
class Commitment:
    id: str
    type: str                     # reserved-instance | savings-plan
    team: str
    covers: str                   # the resource (reservation) or scope (savings plan) it applies to
    start: str
    end: str
    payment: str                  # all-upfront | partial-upfront | no-upfront
    month: str                    # the month used, unused and utilisation are measured in
    used: float
    unused: float
    utilisation: float | None
    billed_window: float | None
    amortised_window: float
    days_to_expiry: int
    underused: bool
    expiring: bool
    evidence: list[str] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return KINDS.get(self.type, self.type)


def measure(inp: FinOpsInputs, cov: Coverage, r: Rules) -> list[Commitment]:
    as_of = date.fromisoformat(r.as_of)
    last = cov.complete[-1] if cov.complete else None
    out = []
    for c in inp.commitments:
        mine = [l for l in inp.lines if l.commitment == c["id"]]
        used = sum(l.cost for l in mine if l.month == last and l.commitment_status == "Used")
        unused = sum(l.cost for l in mine if l.month == last and l.commitment_status == "Unused")
        util = used / (used + unused) if used + unused else None
        billed = sum(l.billed or 0.0 for l in mine) if inp.has_billed else None
        days = (date.fromisoformat(c["end"]) - as_of).days
        out.append(Commitment(c["id"], c["type"], c["team"], c["covers"], c["start"], c["end"], c["payment"],
                              last or "", round(used, 2), round(unused, 2), round(util, 4) if util is not None else None,
                              round(billed, 2) if billed is not None else None,
                              round(sum(l.cost for l in mine), 2), days,
                              util is not None and util < r.commitment_utilisation_min,
                              0 <= days <= r.commitment_renewal_days))
    return sorted(out, key=lambda x: (x.days_to_expiry, x.id))


def coverage_of(inp: FinOpsInputs) -> set[str]:
    """Resources with usage covered by a commitment anywhere in the export."""
    return {l.resource for l in inp.lines if l.commitment and l.commitment_status == "Used"}
