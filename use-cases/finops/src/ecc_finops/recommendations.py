# Author: Pradeep Sahoo
"""Savings recommendations, with estimated and realised savings kept apart (use case 5).

Estimated saving: a formula in code, shown next to the figure, computed from the last complete
billing month. It is frozen when the owning team approves, so it can later be compared with what
actually happened.

Realised saving: never typed in by anyone. It is measured from the cost export once at least one
complete billing month has passed since implementation:
    realised = mean cost over the `realised_baseline_months` complete months before the
               implementation month − mean cost over the complete months since implementation.
It is gross: other changes to the same resource in that period also move it, and the report says so.

Rules (one recommendation per resource; the first that applies wins, so savings never overlap):
- revert:    an anomaly whose likely cause is a configuration change, with medium or high
             confidence → review the change. Estimate = the anomaly's increase over its baseline.
- idle:      a volume detached for at least `idle_days` → snapshot, then delete. Estimate = its cost.
- schedule:  a non-production resource running at least `always_on_hours_min` hours a week →
             stop it outside office hours. Estimate = cost × (1 − office_hours_per_week / 168).
- rightsize: CPU p95 and memory p95 under their thresholds for 30 days → one size down.
             Estimate = cost × rightsize_saving_ratio.
A recommendation rejected less than `rejected_cooldown_days` ago is not proposed again; it is
listed as suppressed with the reason the team gave.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, timedelta
from statistics import mean

from .anomalies import Anomaly, Series
from .evidence import EvidenceBook
from .fmt import money, month_label
from .rules import Rules
from .spend import Coverage

CODES = {"revert": "REV", "idle": "IDLE", "schedule": "SCH", "rightsize": "RS"}
OPEN = ("proposed", "approved")
STATUS_ORDER = {"proposed": 0, "approved": 1, "implemented": 2, "rejected": 3, "suppressed": 4}
RULE_TEXT = {   # the rule each recommendation type applies, cited as evidence
    "idle": lambda r: f"Idle rule: a volume detached for at least {r.idle_days} days",
    "schedule": lambda r: (f"Scheduling rule: a {'/'.join(sorted(r.non_prod))} resource running at least "
                           f"{r.always_on_hours_min} hours a week; office hours are {r.office_hours_per_week} a week"),
    "rightsize": lambda r: (f"Rightsizing rule: CPU p95 under {r.rightsize_cpu_p95_max:g}% and memory p95 under "
                            f"{r.rightsize_mem_p95_max:g}% over 30 days; one size down saves "
                            f"{r.rightsize_saving_ratio:g} of the cost"),
}


@dataclass
class Recommendation:
    id: str
    type: str
    title: str
    team: str
    resource: str
    line_item: str
    rationale: str
    formula: str
    estimated_monthly_usd: float
    estimate_basis: str                 # e.g. "Oct 2026 cost", or "Nov 2026 run-rate (provisional)"
    provisional: bool = False
    status: str = "proposed"            # proposed | approved | rejected | implemented | suppressed
    anomaly: str | None = None
    evidence: list[str] = field(default_factory=list)
    realised_monthly_usd: float | None = None
    realised_note: str = ""
    decided_by: str = ""
    decided_on: str = ""
    implemented_on: str = ""
    change: str = ""
    decision_note: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Recommendation":
        """From a results.json entry (which also carries the drafted note)."""
        return cls(**{f.name: d[f.name] for f in fields(cls)})


def rec_id(kind: str, resource: str) -> str:
    return f"REC-{CODES[kind]}-{resource}"


def _cost(s: Series, cov: Coverage) -> tuple[float, str]:
    last = next((m for m in reversed(cov.complete) if m in s.values), None)
    return (s.values[last], last) if last else (0.0, "")


def candidates(series: list[Series], anomalies: list[Anomaly], inp, cov: Coverage, r: Rules,
               book: EvidenceBook) -> list[Recommendation]:
    out: dict[str, Recommendation] = {}
    taken: set[str] = set()                     # resources that already have a recommendation

    # revert: anomalies with a configuration cause
    cfg = {c["id"]: c for c in inp.config_changes}
    for a in anomalies:
        if not a.cause or not a.cause.config or a.confidence not in ("high", "medium"):
            continue
        c = cfg[a.cause.config]
        p = a.basis()
        basis = f"{month_label(p.month)} {'run-rate (provisional)' if p.provisional else 'cost'}"
        est = round(p.increase)
        formula = f"{money(p.value)} {basis} − {money(p.mean)} baseline mean"
        rid = rec_id("revert", c["resource"])
        ev = book.add("estimate", "finops-rules",
                      f"{rid}: estimated saving {money(est)} a month = {formula}")
        out[rid] = Recommendation(
            rid, "revert", f"Review {c['attribute']} on {c['resource']}: {c['old']} before {c['id']}, {c['new']} now",
            a.team, a.resource, a.line_item,
            f"{a.line_item} on {a.resource} rose after this change ({a.id}, {a.confidence} confidence). Restoring "
            f"{c['old']}, or a value in between, is for {a.team} to decide"
            + (f" with whoever asked for {a.cause.change}" if a.cause.change else "") + ".",
            formula, float(est), basis, p.provisional, anomaly=a.id, evidence=a.evidence + [ev])
        taken.add(a.resource)

    for s in series:
        if s.resource in taken:
            continue
        u = inp.utilisation.get(s.resource)
        if not u:
            continue
        cost, month = _cost(s, cov)
        if cost <= 0:
            continue
        basis = f"{month_label(month)} cost"
        util_ev = book.add("utilisation", "metrics", _util_summary(s.resource, u))
        kind = None
        if u.get("attached") is False and u.get("days_unattached", 0) >= r.idle_days:
            kind, est = "idle", cost
            formula = f"{money(cost)} {basis} × 1"
            title = f"Snapshot, then delete {s.resource} (detached {u['days_unattached']} days)"
            why = f"Detached for {u['days_unattached']} days; nothing reads it. The owner confirms before deletion."
        elif s.env in r.non_prod and u.get("hours_per_week", 0) >= r.always_on_hours_min:
            kind, est = "schedule", cost * (1 - r.office_hours_per_week / 168)
            formula = f"{money(cost)} {basis} × (1 − {r.office_hours_per_week}/168)"
            title = f"Stop {s.resource} outside office hours ({r.office_hours_per_week} hours a week)"
            why = f"A {s.env} resource running {u['hours_per_week']} hours a week."
        elif (u.get("cpu_p95_pct") is not None and u["cpu_p95_pct"] < r.rightsize_cpu_p95_max
              and u.get("mem_p95_pct", 100) < r.rightsize_mem_p95_max):
            kind, est = "rightsize", cost * r.rightsize_saving_ratio
            formula = f"{money(cost)} {basis} × {r.rightsize_saving_ratio:g}"
            title = f"Rightsize {s.resource} one size down"
            why = (f"CPU p95 {u['cpu_p95_pct']}% and memory p95 {u['mem_p95_pct']}% over 30 days, under the "
                   f"{r.rightsize_cpu_p95_max:g}% and {r.rightsize_mem_p95_max:g}% thresholds.")
        if kind is None:
            continue
        rid = rec_id(kind, s.resource)
        est = round(est)
        ev = book.add("estimate", "finops-rules", f"{rid}: estimated saving {money(est)} a month = {formula}")
        rule_ev = book.add("rule", "finops-rules", RULE_TEXT[kind](r))
        out[rid] = Recommendation(rid, kind, title, s.team, s.resource, s.line_item, why, formula, float(est), basis,
                                  evidence=[util_ev, rule_ev, ev])
        taken.add(s.resource)
    return list(out.values())


def _util_summary(resource: str, u: dict) -> str:
    if u.get("attached") is False:
        return f"{resource}: detached for {u.get('days_unattached')} days"
    return (f"{resource} over 30 days: CPU p95 {u.get('cpu_p95_pct')}%, memory p95 {u.get('mem_p95_pct')}%, "
            f"running {u.get('hours_per_week')} hours a week")


def realised(s: Series | None, implemented_on: str, cov: Coverage, r: Rules) -> tuple[float | None, str]:
    """Realised monthly saving measured from the bill, or (None, why not yet)."""
    if s is None:
        return None, "the resource is no longer in the cost export"
    month = implemented_on[:7]
    after = [m for m in cov.complete if f"{m}-01" >= implemented_on and m in s.values]
    before = [m for m in cov.complete if m < month and m in s.values][-r.realised_baseline_months:]
    if not after:
        return None, f"pending: no complete billing month since {implemented_on}"
    if not before:
        return None, "no complete month before implementation to compare with"
    b, a = mean(s.values[m] for m in before), mean(s.values[m] for m in after)
    note = (f"mean {money(b)} over {month_label(before[0])}–{month_label(before[-1])} before, mean {money(a)} over "
            f"{month_label(after[0])}–{month_label(after[-1])} after implementation on {implemented_on}")
    return float(round(b - a)), note


def merge(recs: list[Recommendation], register: list[dict], decisions: dict[str, dict], series: list[Series],
          cov: Coverage, r: Rules, book: EvidenceBook) -> list[Recommendation]:
    """Apply the savings register and pilot decisions; measure realised savings for implemented ones."""
    by_id = {x.id: x for x in recs}
    _apply_register(by_id, register, r, book)
    for rid, d in decisions.items():
        if rid in by_id:
            apply_decision(by_id[rid], d)
    lookup = {(s.resource, s.line_item): s for s in series}
    for x in by_id.values():
        if x.status == "implemented":
            value, note = realised(lookup.get((x.resource, x.line_item)), x.implemented_on, cov, r)
            x.realised_monthly_usd, x.realised_note = value, note
            if value is not None:
                x.evidence.append(book.add("realised", "cost-export",
                                           f"{x.id}: realised saving {money(value)} a month = {note}"))
    return sorted(by_id.values(), key=lambda x: (STATUS_ORDER[x.status], -x.estimated_monthly_usd, x.id))


def _apply_register(by_id: dict[str, Recommendation], register: list[dict], r: Rules, book: EvidenceBook) -> None:
    """Decisions taken before the pilot: suppress recent rejections; add or update the others."""
    as_of = date.fromisoformat(r.as_of)
    for e in register:
        rid = e["id"]
        if e["status"] == "rejected":
            until = date.fromisoformat(e["decided_on"]) + timedelta(days=r.rejected_cooldown_days)
            if rid in by_id and until > as_of:
                x = by_id[rid]
                x.status, x.decided_by, x.decided_on = "suppressed", e["decided_by"], e["decided_on"]
                x.decision_note = (f"rejected by {e['decided_by']} on {e['decided_on']}: {e.get('note', '')}; "
                                   f"not proposed again before {until.isoformat()}")
            continue
        x = by_id.get(rid) or Recommendation(rid, e["type"], e["title"], e["team"], e["resource"], e["line_item"],
                                             "Decided before the pilot (savings register).", "frozen at approval",
                                             float(e["estimated_monthly_usd"]), "frozen at approval")
        x.status = e["status"]
        x.estimated_monthly_usd = float(e["estimated_monthly_usd"])        # frozen at approval
        x.estimate_basis = f"frozen at approval on {e['decided_on']}"
        x.decided_by, x.decided_on = e["decided_by"], e["decided_on"]
        x.implemented_on, x.change = e.get("implemented_on", ""), e.get("change", "")
        x.evidence = [book.add("register", "savings-register",
                               f"{rid}: {e['status']}; approved by {e['decided_by']} ({e['role']}) on {e['decided_on']} "
                               f"with an estimate of {money(e['estimated_monthly_usd'])} a month"
                               + (f"; implemented on {e['implemented_on']} under {e['change']}"
                                  if e.get("implemented_on") else ""))]
        by_id[rid] = x


def apply_decision(x: Recommendation, d: dict) -> bool:
    """Apply one pilot decision (from ledger.effective). A suppressed recommendation stays suppressed.

    Approval freezes the estimate. Returns whether anything was applied.
    """
    if x.status == "suppressed":
        return False
    x.status, x.decided_by, x.decided_on = d["status"], d["decided_by"], d["decided_on"]
    x.decision_note = d.get("note", "")
    if d.get("estimate_at_approval") is not None:
        x.estimated_monthly_usd = float(d["estimate_at_approval"])
        x.estimate_basis = f"frozen at approval on {d['decided_on']}"
    x.implemented_on, x.change = d.get("implemented_on", x.implemented_on), d.get("change", x.change)
    return True


def totals(recs: list[dict]) -> dict:
    """Estimated and realised savings, kept apart. They are never added together."""
    open_ = [x for x in recs if x["status"] in OPEN]
    done = [x for x in recs if x["status"] == "implemented"]
    measured = [x for x in done if x["realised_monthly_usd"] is not None]
    return {"estimated_open_usd": sum(x["estimated_monthly_usd"] for x in open_), "open": len(open_),
            "provisional_open": sum(1 for x in open_ if x["provisional"]),
            "estimated_implemented_usd": sum(x["estimated_monthly_usd"] for x in measured),
            "realised_usd": sum(x["realised_monthly_usd"] for x in measured), "implemented": len(done),
            "measured": len(measured)}
