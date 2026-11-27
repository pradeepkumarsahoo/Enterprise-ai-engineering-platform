# Author: Pradeep Sahoo
"""Use case 5 runs: build the analysis, analyse (draft, validate, write), refresh after a decision.

build    -> allocation, spend by team, forecast, anomalies and likely causes, daily alerts,
            commitments, recommendations with estimated savings, realised savings measured from the
            bill, evidence (all code)
analyse  -> build, then explanations and notes (model, validated); results.json, report.md,
            report.html, audit log
refresh  -> re-render after a decision (statuses and savings totals; nothing is re-estimated)
The evaluation against labels is in evaluation.py.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ecc_core.audit import AuditLog, new_correlation_id
from ecc_core.evidence import Evidence

from . import ledger
from .anomalies import Anomaly, build_series, detect
from .causes import CauseFinder
from .commitments import Commitment, measure
from .daily import DailyAlert, detect_daily, link
from .drafting import validate
from .evidence import (EvidenceBook, describe_anomaly, describe_commitments, describe_daily, describe_savings,
                       describe_spend)
from .html import report_html
from .recommendations import Recommendation, apply_decision, candidates, merge, totals
from .report import report_md
from .rules import RULES_VERSION, Rules
from .sources import FinOpsInputs
from .spend import Coverage, Spend, coverage, spend_by_team

AGENT = "agent:finops-analyst"
READS = ("cost_export.read", "utilisation.read", "config_log.read", "savings_register.read", "commitments.read",
         "servicenow.change_request.read", "catalogue.read")


@dataclass
class Analysis:
    analysis_id: str
    as_of: str
    coverage: Coverage
    spend: Spend
    anomalies: list[Anomaly]
    recommendations: list[Recommendation]
    evidence: list[Evidence]
    kpis: dict
    kpi_evidence: str
    judged: list[dict]
    could_not_establish: list[str] = field(default_factory=list)
    commitments: list[Commitment] = field(default_factory=list)
    daily_alerts: list[DailyAlert] = field(default_factory=list)
    daily: bool = False
    export_format: str = "focus"


def analysis_id(inp: FinOpsInputs, r: Rules) -> str:
    """Changes whenever the rules, the cost lines or the configuration log change."""
    fingerprint = json.dumps([RULES_VERSION, asdict(r), [(l.month, l.resource, l.line_item, l.charge_category, l.cost)
                                                         for l in inp.lines], inp.config_changes],
                             sort_keys=True, default=str)
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:10]


def build(inp: FinOpsInputs, r: Rules, decisions: dict | None = None) -> Analysis:
    cov = coverage(inp.lines)
    spend = spend_by_team(inp, cov)
    series = build_series(inp, cov)
    anomalies, judged = detect(series, cov, r, CauseFinder(inp, r, spend.team_of()))
    alerts, daily = detect_daily(inp, r)
    link(alerts, anomalies)
    commits = measure(inp, cov, r)
    book = EvidenceBook()
    kpis, kpi_ev, unknown = describe_spend(book, spend, cov, inp.problems)
    if not inp.has_effective:
        unknown.append("Amortised cost: the export has no EffectiveCost, so a commitment bought upfront counts in "
                       "the month it was paid")
    for a in anomalies:
        describe_anomaly(book, a, inp, cov, r)
    describe_daily(book, alerts, daily, unknown, r)
    for a in anomalies:
        for x in alerts:
            if x.anomaly == a.id:
                a.daily.append(x.id)
                a.evidence += [i for i in x.evidence if i not in a.evidence]
    describe_commitments(book, commits, unknown)
    recs = merge(candidates(series, anomalies, inp, cov, r, book, commits), inp.register, decisions or {}, series,
                 cov, r, book)
    savings = totals([asdict(x) for x in recs])
    describe_savings(book, savings)
    kpis.update({"anomalies": len(anomalies), "savings": savings, "daily_alerts": len(alerts),
                 "early_signals": sum(1 for x in alerts if x.anomaly is None),
                 "commitments": len(commits), "underused_commitments": sum(1 for c in commits if c.underused)})
    judged_rows = [{"resource": k[0], "line_item": k[1], "month": p.month, "value": round(p.value, 2),
                    "mean": round(p.mean, 2), "z": round(p.z, 2), "flagged": p.flagged, "provisional": p.provisional}
                   for k, pts in judged.items() for p in pts]
    return Analysis(analysis_id(inp, r), r.as_of, cov, spend, anomalies, recs, book.items, kpis, kpi_ev, judged_rows,
                    unknown, commits, alerts, daily, inp.export_format)


def analyse(inp: FinOpsInputs, r: Rules, drafter, workdir: Path) -> dict:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(workdir / "audit.jsonl")
    cid = new_correlation_id()
    audit.record(AGENT, "finops.analyse.started", r.as_of, cid, provider=drafter.name)
    for tool in READS:
        audit.record(AGENT, "tool.call", tool, cid)
    for c in inp.config_changes:
        for flag in c["flags"]:
            audit.record("policy-engine", "secret.redacted" if flag == "secret_redacted" else "untrusted_input.flagged",
                         c["id"], cid, stage="config_log.read")
    for p in inp.problems:
        audit.record("policy-engine", "cost_export.row_skipped", p, cid, outcome="skipped")
    a = build(inp, r, ledger.effective(workdir))
    summary, explanations, notes, rejected = validate(drafter.draft(a), a)
    for x in rejected:
        audit.record("policy-engine", "finops.draft.rejected", x["item"], cid, outcome="rejected", reason=x["reason"])
    res = {
        "analysis_id": a.analysis_id, "as_of": a.as_of, "rules_version": RULES_VERSION, "provider": drafter.name,
        "rules": asdict(r), "export_format": a.export_format,
        "coverage": asdict(a.coverage),
        "spend": {"months": a.spend.months, "partial": a.spend.partial, "by_team": a.spend.by_team,
                  "forecast": a.spend.forecast, "allocation": a.spend.allocation, "billed": a.spend.billed},
        "commitments": [asdict(c) for c in a.commitments],
        "daily": {"available": a.daily, "alerts": [asdict(x) for x in a.daily_alerts]},
        "kpis": a.kpis, "summary": summary,
        "anomalies": [{**asdict(x), "explanation": explanations.get(x.id)} for x in a.anomalies],
        "recommendations": [{**asdict(x), "note": notes.get(x.id)} for x in a.recommendations],
        "could_not_establish": a.could_not_establish, "rejected_drafts": rejected,
        "evidence": [asdict(e) for e in a.evidence], "judged": a.judged,
    }
    audit.record(AGENT, "finops.analysed", a.analysis_id, cid, anomalies=[x.id for x in a.anomalies],
                 proposed=[x.id for x in a.recommendations if x.status == "proposed"], changed_resources=0)
    write(workdir, res)
    return res


def results(workdir: Path) -> dict:
    path = Path(workdir) / "results.json"
    if not path.exists():
        raise ValueError("No analysis yet; run `ecc finops analyse` first")
    return json.loads(path.read_text(encoding="utf-8"))


def write(workdir: Path, res: dict) -> None:
    (Path(workdir) / "results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    (Path(workdir) / "report.md").write_text(report_md(res), encoding="utf-8")
    (Path(workdir) / "report.html").write_text(report_html(res), encoding="utf-8")


def refresh(workdir: Path) -> dict:
    """Apply pilot decisions to the last analysis and re-render. Realised savings wait for the next analysis."""
    res = results(workdir)
    for rid, d in ledger.effective(workdir).items():
        x = next((y for y in res["recommendations"] if y["id"] == rid), None)
        if x is None:
            continue
        rec = Recommendation.from_dict(x)
        if not apply_decision(rec, d):
            continue
        if rec.status == "implemented":
            rec.realised_monthly_usd, rec.realised_note = None, "pending: measured from the bill at the next analysis"
        x.update(asdict(rec))
    res["kpis"]["savings"] = totals(res["recommendations"])
    write(workdir, res)
    return res


def find(res: dict, rid: str) -> dict:
    x = next((y for y in res["recommendations"] if y["id"] == rid), None)
    if x is None:
        raise ValueError(f"{rid} is not in the last analysis")
    return x
