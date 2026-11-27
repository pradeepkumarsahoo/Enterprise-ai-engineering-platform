# Author: Pradeep Sahoo
"""Billing coverage, allocation to teams, and monthly spend with a run-rate forecast (use case 5).

- Coverage: which months of the export are complete, and how many days of the latest one it holds.
- Allocation: a cost line belongs to its `team` tag, if that names a known team; failing that, to
  the owner of its `service` tag in the service catalogue; failing that, it is unallocated (and
  reported as such). A team tag that names no known team ("loyalty" for Loyalty) is not trusted:
  it would create a phantom team in the report. The tagging agent proposes the fix.
- Spend: effective (amortised) cost net of credits, per team and billing month. The partial
  month's forecast is its month-to-date figure scaled to the whole month (run-rate). The billed
  total per month is kept beside it, to reconcile with the invoice: the two differ by commitment
  purchases being spread over their term.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .fmt import days_in, month_add
from .sources import CostLine, FinOpsInputs

UNALLOCATED = "Unallocated"


@dataclass
class Coverage:
    months: list[str]            # every month in the export, oldest first
    complete: list[str]
    partial: str | None          # the month still in progress, if any
    days_covered: int            # days of the partial month in the export
    partial_days: int            # days in the partial month

    @property
    def scale(self) -> float:
        """Month to date × scale = the whole partial month (run-rate); 0 without a partial month."""
        return self.partial_days / self.days_covered if self.partial and self.days_covered else 0.0

    @property
    def run_rate(self) -> str:
        return f"run-rate from {self.days_covered} of {self.partial_days} days"


def coverage(lines: list[CostLine]) -> Coverage:
    months = sorted({l.month for l in lines})
    complete, partial, covered = [], None, 0
    for m in months:
        last = max(l.charge_end for l in lines if l.month == m)
        if last >= date.fromisoformat(f"{month_add(m, 1)}-01"):
            complete.append(m)
        else:
            partial, covered = m, (last - date.fromisoformat(f"{m}-01")).days
    if partial and partial != months[-1]:
        raise ValueError(f"Only the latest month may be partial; {partial} is incomplete")
    return Coverage(months, complete, partial, covered, days_in(partial) if partial else 0)


def allocate(line: CostLine, inp: FinOpsInputs) -> tuple[str, str]:
    """(team, how): how is 'tag', 'catalogue', 'invalid' (a team tag naming no known team) or 'none'."""
    return allocate_tags(line.tags, inp)


def allocate_tags(tags: dict, inp: FinOpsInputs, known: set[str] | None = None) -> tuple[str, str]:
    known = inp.known_teams if known is None else known
    team = tags.get("team")
    if team and (not known or team in known):
        return team, "tag"
    owner = inp.owner_of_service(tags.get("service", ""))
    if owner:
        return owner, "catalogue"
    return UNALLOCATED, "invalid" if team else "none"


@dataclass
class Spend:
    months: list[str]
    partial: str | None
    by_team: dict[str, dict[str, float]]       # team -> month -> net cost (partial month = month to date)
    forecast: dict[str, float]                 # team -> partial month projected to the whole month
    allocation: dict[str, dict]                # resource -> {team, how}
    billed: dict[str, float] | None = None     # month -> billed total (None: the export has no billed cost)

    def total(self, month: str) -> float:
        return sum(row[month] for row in self.by_team.values())

    def team_of(self) -> dict[str, str]:
        return {res: x["team"] for res, x in self.allocation.items()}


def spend_by_team(inp: FinOpsInputs, cov: Coverage) -> Spend:
    by_team: dict[str, dict[str, float]] = {}
    alloc = {}
    known = inp.known_teams
    billed = {m: 0.0 for m in cov.months} if inp.has_billed else None
    for l in inp.lines:
        if billed is not None:
            billed[l.month] += l.billed or 0.0
        team, how = allocate_tags(l.tags, inp, known)
        alloc.setdefault(l.resource, {"team": team, "how": how})
        by_team.setdefault(team, {m: 0.0 for m in cov.months})[l.month] += l.cost
    order = sorted(t for t in by_team if t != UNALLOCATED) + ([UNALLOCATED] if UNALLOCATED in by_team else [])
    forecast = {t: by_team[t][cov.partial] * cov.scale if cov.partial else 0.0 for t in order}
    return Spend(cov.months, cov.partial, {t: by_team[t] for t in order}, forecast, alloc,
                 {m: round(v, 2) for m, v in billed.items()} if billed is not None else None)
