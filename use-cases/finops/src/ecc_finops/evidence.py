# Author: Pradeep Sahoo
"""Evidence records F1, F2, ... for FinOps (use case 5): every sentence is written here, by code.

The model may only repeat figures that appear in these summaries, and must cite their IDs.
"""
from __future__ import annotations

from ecc_core.evidence import Evidence

from .anomalies import Anomaly
from .causes import CONFIDENCE_RULE
from .fmt import money, month_label, pct
from .rules import Rules
from .sources import FinOpsInputs
from .spend import UNALLOCATED, Coverage, Spend


class EvidenceBook:
    """Numbers evidence F1, F2, ... in the order it is added; one record per distinct summary."""

    def __init__(self):
        self.items: list[Evidence] = []
        self._by_summary: dict[str, str] = {}

    def add(self, kind: str, source: str, summary: str, flags: list[str] | None = None) -> str:
        if summary in self._by_summary:
            return self._by_summary[summary]
        eid = f"F{len(self.items) + 1}"
        self.items.append(Evidence(eid, kind, source, summary, list(flags or [])))
        self._by_summary[summary] = eid
        return eid


def describe_spend(book: EvidenceBook, spend: Spend, cov: Coverage, problems: list[str]) -> tuple[dict, str, list[str]]:
    """Spend, allocation and forecast. Returns (kpis, the spend evidence ID, what could not be established)."""
    unknown: list[str] = []
    last = cov.complete[-1]
    prev = cov.complete[-2] if len(cov.complete) > 1 else None
    t_last, t_prev = spend.total(last), spend.total(prev) if prev else 0.0
    change = (t_last - t_prev) / t_prev if prev and t_prev else 0.0
    forecast = sum(spend.forecast.values())
    text = (f"Spend in {month_label(last)} was {money(t_last)}"
            + (f", {pct(abs(change))} {'up' if change >= 0 else 'down'} on {month_label(prev)} ({money(t_prev)})"
               if prev else "")
            + (f". {month_label(cov.partial)} forecast {money(forecast)}: {cov.run_rate}" if cov.partial else "") + ".")
    spend_ev = book.add("spend", "cost-export", text)

    unalloc = spend.by_team.get(UNALLOCATED, {}).get(last, 0.0)
    share = unalloc / t_last if t_last else 0.0
    unalloc_res = sorted(res for res, x in spend.allocation.items() if x["how"] == "none")
    if unalloc_res:
        book.add("allocation", "cost-export",
                 f"Unallocated in {month_label(last)}: {money(unalloc)} ({pct(share)} of spend) from "
                 f"{', '.join(unalloc_res)}: no team tag and no service in the catalogue")
        unknown.append(f"Who owns {', '.join(unalloc_res)}: no team tag, and no service tag the catalogue knows")
    for res, x in sorted(spend.allocation.items()):
        if x["how"] == "catalogue":
            book.add("allocation", "service-catalogue",
                     f"{res} allocated to {x['team']} through the service catalogue (service tag, no team tag)")
    if problems:
        unknown.append(f"{len(problems)} cost export row(s) could not be read and are left out: "
                       + "; ".join(problems[:3]))
    kpis = {"last_month": last, "prev_month": prev, "total_last": round(t_last, 2), "total_prev": round(t_prev, 2),
            "change_vs_prev": round(change, 4), "partial_month": cov.partial, "forecast_total": round(forecast, 2),
            "days_covered": cov.days_covered, "partial_days": cov.partial_days,
            "unallocated_last": round(unalloc, 2), "unallocated_share": round(share, 4),
            "unallocated_resources": unalloc_res}
    return kpis, spend_ev, unknown


def describe_anomaly(book: EvidenceBook, a: Anomaly, inp: FinOpsInputs, cov: Coverage, r: Rules) -> None:
    """Fills a.evidence and a.could_not_establish."""
    run_rate = lambda p: f" ({cov.run_rate})" if p.provisional else ""
    o = a.onset
    text = (f"{a.line_item} on {a.resource} ({a.team}): {month_label(o.month)} {money(o.value)}{run_rate(o)}"
            f" against a {len(o.baseline)}-month baseline mean of {money(o.mean)} (standard deviation "
            f"{money(o.sd)}): +{money(o.increase)}, +{pct(o.ratio)}, z = {o.z:.1f}")
    for p in a.points[1:]:
        text += f"; {month_label(p.month)} {money(p.value)}{run_rate(p)}, +{pct(p.ratio)} on its baseline, z = {p.z:.1f}"
    text += f". Rule: z ≥ {r.z_threshold:g}, increase ≥ {money(r.min_increase_usd)} and ≥ {pct(r.min_increase_ratio)}"
    a.evidence.append(book.add("anomaly", "cost-export", text))

    cfg = next((c for c in inp.config_changes if a.cause and c["id"] == a.cause.config), None)
    if a.cause:
        if cfg:
            a.evidence.append(book.add("config_change", "cloud-config-log", f"{a.cause.summary}. Note: {cfg['note']}",
                                       cfg["flags"]))
        if a.cause.change:
            n = inp.changes[a.cause.change]
            a.evidence.append(book.add("servicenow_change", "servicenow",
                                       f"{n['number']}: {n['short_description']} ({n['state']}, "
                                       f"{n['start_date'][:10]}, requested by {n['requested_by']})", n["flags"]))
        a.evidence.append(book.add("confidence", "finops-rules", f"{a.id} cause confidence {a.confidence}: "
                                   + "; ".join(a.cause.parts) + f" ({CONFIDENCE_RULE})"))
        if cfg and not a.cause.change:
            a.could_not_establish.append(f"Who approved {cfg['id']} ({cfg['attribute']} on {cfg['resource']}): no "
                                         "change request covers it")
        if a.cause.scope == "team":
            a.could_not_establish.append(
                f"Whether {cfg['resource']} is the source of the increase: it shares only an owning team with "
                f"{a.resource}, and the export has no breakdown below {a.resource}")
    else:
        a.could_not_establish.append(f"The cause: no configuration change or change request on {a.resource}"
                                     f"{', ' + a.service if a.service else ''} or team {a.team} in the window")
    if a.provisional:
        a.could_not_establish.append(f"Whether {month_label(cov.partial)} ends this way: the figure is a "
                                     f"{cov.run_rate}")


def describe_savings(book: EvidenceBook, s: dict) -> None:
    book.add("savings", "finops-rules",
             f"Open recommendations: {s['open']}, estimated at {money(s['estimated_open_usd'])} a month. Realised "
             f"savings measured from the bill: {money(s['realised_usd'])} a month from {s['measured']} implemented "
             f"recommendation(s), against {money(s['estimated_implemented_usd'])} estimated at approval")
