# Author: Pradeep Sahoo
"""Use case 5 runs: analyse spend, decide on recommendations, evaluate against labels.

analyse  -> allocation, spend by team, forecast, anomalies and likely causes, recommendations with
            estimated savings, realised savings measured from the bill (all code); explanations and
            notes (model, validated); results.json, report.md, report.html, audit log
refresh  -> re-render after a decision (statuses and savings totals; nothing is re-estimated)
evaluate -> anomaly precision and recall, causes, recommendations, realised savings vs labels
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ecc_core.audit import AuditLog, new_correlation_id
from ecc_core.evidence import Evidence

from . import ledger
from .analysis import (RULES_VERSION, UNALLOCATED, Anomaly, Coverage, EvidenceBook, Rules, Spend, build_series,
                       coverage, detect, money, month_label, pct, spend_by_team)
from .drafting import validate
from .html import report_html
from .recommendations import Recommendation, candidates, merge, totals
from .sources import FinOpsInputs

AGENT = "agent:finops-analyst"


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


def build(inp: FinOpsInputs, r: Rules, decisions: dict | None = None) -> Analysis:
    cov = coverage(inp.lines)
    spend = spend_by_team(inp, cov)
    series = build_series(inp, cov)
    anomalies, judged = detect(series, cov, inp, r)
    book = EvidenceBook()
    unknown: list[str] = []

    # ---- spend and allocation
    last = cov.complete[-1]
    prev = cov.complete[-2] if len(cov.complete) > 1 else None
    total = lambda m: sum(row[m] for row in spend.by_team.values())
    t_last, t_prev = total(last), total(prev) if prev else 0.0
    change = (t_last - t_prev) / t_prev if prev and t_prev else 0.0
    forecast = sum(spend.forecast.values())
    spend_text = (f"Spend in {month_label(last)} was {money(t_last)}"
                  + (f", {pct(abs(change))} {'up' if change >= 0 else 'down'} on {month_label(prev)} ({money(t_prev)})"
                     if prev else "")
                  + (f". {month_label(cov.partial)} forecast {money(forecast)}: run-rate from {cov.days_covered} of "
                     f"{cov.partial_days} days" if cov.partial else "") + ".")
    kpi_ev = book.add("spend", "cost-export", spend_text)
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
    if inp.problems:
        unknown.append(f"{len(inp.problems)} cost export row(s) could not be read and are left out: "
                       + "; ".join(inp.problems[:3]))

    # ---- anomalies: evidence and what could not be established
    cfg = {c["id"]: c for c in inp.config_changes}
    for a in anomalies:
        o = a.onset
        text = (f"{a.line_item} on {a.resource} ({a.team}): {month_label(o.month)} {money(o.value)}"
                f"{' (run-rate from ' + str(cov.days_covered) + ' of ' + str(cov.partial_days) + ' days)' if o.provisional else ''}"
                f" against a {len(o.baseline)}-month baseline mean of {money(o.mean)} (standard deviation "
                f"{money(o.sd)}): +{money(o.increase)}, +{pct(o.ratio)}, z = {o.z:.1f}")
        for p in a.points[1:]:
            text += (f"; {month_label(p.month)} {money(p.value)}"
                     f"{' (run-rate from ' + str(cov.days_covered) + ' of ' + str(cov.partial_days) + ' days)' if p.provisional else ''}"
                     f", +{pct(p.ratio)} on its baseline, z = {p.z:.1f}")
        text += (f". Rule: z ≥ {r.z_threshold:g}, increase ≥ {money(r.min_increase_usd)} and ≥ "
                 f"{pct(r.min_increase_ratio)}")
        a.evidence.append(book.add("anomaly", "cost-export", text))
        if a.cause:
            if a.cause.config:
                c = cfg[a.cause.config]
                a.evidence.append(book.add("config_change", "cloud-config-log",
                                           f"{a.cause.summary}. Note: {c['note']}", c["flags"]))
            if a.cause.change:
                n = inp.changes[a.cause.change]
                a.evidence.append(book.add("servicenow_change", "servicenow",
                                           f"{n['number']}: {n['short_description']} ({n['state']}, "
                                           f"{n['start_date'][:10]}, requested by {n['requested_by']})", n["flags"]))
            a.evidence.append(book.add("confidence", "finops-rules",
                                       f"{a.id} cause confidence {a.confidence}: " + "; ".join(a.cause.parts)
                                       + " (high from 4 points, medium 2 to 3, low 1)"))
            if a.cause.config and not a.cause.change:
                c = cfg[a.cause.config]
                a.could_not_establish.append(f"Who approved {c['id']} ({c['attribute']} on {c['resource']}): no "
                                             "change request covers it")
            if a.cause.scope == "team":
                a.could_not_establish.append(
                    f"Whether {cfg[a.cause.config]['resource']} is the source of the increase: it shares only an "
                    f"owning team with {a.resource}, and the export has no breakdown below {a.resource}")
        else:
            a.could_not_establish.append(f"The cause: no configuration change or change request on {a.resource}"
                                         f"{', ' + a.service if a.service else ''} or team {a.team} in the window")
        if a.provisional:
            a.could_not_establish.append(f"Whether {month_label(cov.partial)} ends this way: the figure is a run-rate "
                                         f"from {cov.days_covered} of {cov.partial_days} days")

    # ---- recommendations, register, pilot decisions, realised savings
    recs = merge(candidates(series, anomalies, inp, cov, r, book), inp.register, decisions or {}, series, cov, r, book)
    s = totals([asdict(x) for x in recs])
    book.add("savings", "finops-rules",
             f"Open recommendations: {s['open']}, estimated at {money(s['estimated_open_usd'])} a month. Realised "
             f"savings measured from the bill: {money(s['realised_usd'])} a month from {s['measured']} implemented "
             f"recommendation(s), against {money(s['estimated_implemented_usd'])} estimated at approval")

    kpis = {"last_month": last, "prev_month": prev, "total_last": round(t_last, 2), "total_prev": round(t_prev, 2),
            "change_vs_prev": round(change, 4), "partial_month": cov.partial, "forecast_total": round(forecast, 2),
            "days_covered": cov.days_covered, "partial_days": cov.partial_days,
            "unallocated_last": round(unalloc, 2), "unallocated_share": round(share, 4),
            "unallocated_resources": unalloc_res, "anomalies": len(anomalies), "savings": s}
    judged_rows = [{"resource": k[0], "line_item": k[1], "month": p.month, "value": round(p.value, 2),
                    "mean": round(p.mean, 2), "z": round(p.z, 2), "flagged": p.flagged, "provisional": p.provisional}
                   for k, pts in judged.items() for p in pts]
    fingerprint = json.dumps([RULES_VERSION, asdict(r), [(l.month, l.resource, l.line_item, l.charge_category, l.cost)
                                                         for l in inp.lines], inp.config_changes], sort_keys=True,
                             default=str)
    aid = hashlib.sha256(fingerprint.encode()).hexdigest()[:10]
    return Analysis(aid, r.as_of, cov, spend, anomalies, recs, book.items, kpis, kpi_ev, judged_rows, unknown)


# ------------------------------------------------------------------ analyse

def analyse(inp: FinOpsInputs, r: Rules, drafter, workdir: Path) -> dict:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(workdir / "audit.jsonl")
    cid = new_correlation_id()
    audit.record(AGENT, "finops.analyse.started", r.as_of, cid, provider=drafter.name)
    for tool in ("cost_export.read", "utilisation.read", "config_log.read", "savings_register.read",
                 "servicenow.change_request.read", "catalogue.read"):
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
        "rules": asdict(r),
        "coverage": asdict(a.coverage),
        "spend": {"months": a.spend.months, "partial": a.spend.partial, "by_team": a.spend.by_team,
                  "forecast": a.spend.forecast, "allocation": a.spend.allocation},
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
        if x is None or x["status"] == "suppressed":
            continue
        x.update({"status": d["status"], "decided_by": d["decided_by"], "decided_on": d["decided_on"],
                  "decision_note": d.get("note", "")})
        if d.get("estimate_at_approval") is not None:
            x["estimated_monthly_usd"] = d["estimate_at_approval"]
            x["estimate_basis"] = f"frozen at approval on {d['decided_on']}"
        if d["status"] == "implemented":
            x.update({"implemented_on": d["implemented_on"], "change": d.get("change", ""),
                      "realised_monthly_usd": None,
                      "realised_note": "pending: measured from the bill at the next analysis"})
    res["kpis"]["savings"] = totals(res["recommendations"])
    write(workdir, res)
    return res


def find(res: dict, rid: str) -> dict:
    x = next((y for y in res["recommendations"] if y["id"] == rid), None)
    if x is None:
        raise ValueError(f"{rid} is not in the last analysis")
    return x


# ------------------------------------------------------------------ Markdown report

def report_md(d: dict) -> str:
    k, sp = d["kpis"], d["spend"]
    months = sp["months"]
    L = ["# FinOps · cloud cost by team", "",
         f"> Analysis `{d['analysis_id']}` as of {d['as_of']} · {d['rules_version']} · provider `{d['provider']}`. "
         "Allocation, anomalies, causes and savings estimates come from rules in code; the model only explains "
         "them. Nothing here changes a cloud resource.", ""]
    if d["summary"]:
        L += ["## Summary", "", d["summary"], ""]
    L += ["## Monthly spend by team (USD, net of credits)", "",
          "| Team | " + " | ".join(month_label(m) + (" (to date)" if m == sp["partial"] else "") for m in months)
          + (f" | {month_label(sp['partial'])} forecast |" if sp["partial"] else " |"),
          "|---|" + "---:|" * (len(months) + (1 if sp["partial"] else 0))]
    for team, row in sp["by_team"].items():
        L.append(f"| {team} | " + " | ".join(money(row[m]) for m in months)
                 + (f" | {money(sp['forecast'][team])} |" if sp["partial"] else " |"))
    tot = {m: sum(r[m] for r in sp["by_team"].values()) for m in months}
    L.append("| **Total** | " + " | ".join(f"**{money(tot[m])}**" for m in months)
             + (f" | **{money(k['forecast_total'])}** |" if sp["partial"] else " |"))
    L += ["", f"Forecast = month to date × {k['partial_days']} / {k['days_covered']} days (run-rate). "
          f"Unallocated in {month_label(k['last_month'])}: {money(k['unallocated_last'])} "
          f"({pct(k['unallocated_share'])}).", "", "## Anomalies", ""]
    if not d["anomalies"]:
        L += ["None flagged.", ""]
    for a in d["anomalies"]:
        o = a["points"][0]
        L += [f"### {a['id']} · {a['line_item']} on {a['resource']} ({a['team']})"
              + (" · provisional" if a["provisional"] else ""), "",
              f"- Months: {', '.join(month_label(m) for m in a['months'])}",
              f"- {month_label(o['month'])}: {money(o['value'])} vs baseline mean {money(o['mean'])} "
              f"(sd {money(o['sd'])}), z = {o['z']:.1f}, +{pct(o['ratio'])}",
              f"- Likely cause ({a['confidence']} confidence): {a['cause']['summary'] if a['cause'] else 'not established'}"]
        if a["explanation"]:
            L.append(f"- Explanation: {a['explanation']['text']}")
        L += [f"- Could not establish: {u}" for u in a["could_not_establish"]]
        L += [f"- Evidence: {', '.join(a['evidence'])}", ""]
    L += ["## Recommendations", "",
          "Estimated savings come from the formula shown; realised savings are measured from the bill after at "
          "least one complete month. The two columns are never added together.", "",
          "| Recommendation | Team | Type | Est. monthly saving | Realised (measured) | Status | Evidence |",
          "|---|---|---|---:|---:|---|---|"]
    for x in d["recommendations"]:
        real = money(x["realised_monthly_usd"]) if x["realised_monthly_usd"] is not None else "—"
        L.append(f"| {x['title']} (`{x['id']}`) | {x['team']} | {x['type']} | {money(x['estimated_monthly_usd'])}"
                 f"{' (provisional)' if x['provisional'] else ''} | {real} | {x['status']} | {', '.join(x['evidence'])} |")
    s = k["savings"]
    L += [f"| **Open** ({s['open']}) | | | **{money(s['estimated_open_usd'])}** | | | |",
          f"| **Implemented, measured** ({s['measured']}) | | | {money(s['estimated_implemented_usd'])} at approval | "
          f"**{money(s['realised_usd'])}** | | |", ""]
    L += [f"- `{x['id']}`: {x['formula']}" + (f"; realised: {x['realised_note']}" if x["realised_note"] else "")
          + (f"; {x['decision_note']}" if x["decision_note"] else "") for x in d["recommendations"]]
    drafted = [x for x in d["recommendations"] if x.get("note")]
    if drafted:
        L += ["", "### Notes to owning teams (draft)", ""] + [f"- **{x['id']}**: {x['note']['text']}" for x in drafted]
    if d["rejected_drafts"]:
        L += ["", "Drafts rejected by validation:", ""] + [f"- {x['item']}: {x['reason']}" for x in d["rejected_drafts"]]
    L += ["", "## Could not establish", ""] + ([f"- {u}" for u in d["could_not_establish"]] or ["- nothing"])
    L += ["", "## Evidence", ""]
    L += [f"- **{e['id']}** {e['summary']}" + (f" _[{', '.join(e['flags'])}]_" if e["flags"] else "")
          for e in d["evidence"]]
    L += ["", "_Generated by Engineering Command Centre · use case 5 · synthetic data · Author: Pradeep Sahoo_", ""]
    return "\n".join(L)


# ------------------------------------------------------------------ evaluation

def evaluate(inp: FinOpsInputs, r: Rules, drafter, gates: dict, labels: dict, workdir: Path) -> dict:
    res = analyse(inp, r, drafter, workdir)
    flagged = {(j["resource"], j["line_item"], j["month"]) for j in res["judged"] if j["flagged"]}
    want = {(x["resource"], x["line_item"], m) for x in labels["anomalies"] for m in x["months"]}
    tp = len(flagged & want)
    precision = tp / len(flagged) if flagged else 1.0
    recall = tp / len(want) if want else 1.0
    causes = []
    for x in labels["anomalies"]:
        got = next((a for a in res["anomalies"] if a["resource"] == x["resource"]
                    and a["line_item"] == x["line_item"] and a["months"][0] == x["months"][0]), None)
        c = (got or {}).get("cause") or {}
        ok = bool(got) and c.get("config") == x["cause_config"] and c.get("change") == x["cause_change"] \
            and got["confidence"] == x["confidence"]
        causes.append({"anomaly": f"{x['resource']} · {x['line_item']}", "expected": x, "correct": ok,
                       "got": {"config": c.get("config"), "change": c.get("change"),
                               "confidence": (got or {}).get("confidence")}})
    cause_acc = sum(c["correct"] for c in causes) / len(causes) if causes else 1.0
    proposed = sorted(x["id"] for x in res["recommendations"] if x["status"] == "proposed")
    suppressed = sorted(x["id"] for x in res["recommendations"] if x["status"] == "suppressed")
    real_err = {}
    for rid, x in labels.get("realised", {}).items():
        got = next((y["realised_monthly_usd"] for y in res["recommendations"] if y["id"] == rid), None)
        real_err[rid] = abs(got - x["expected_monthly_usd"]) / x["expected_monthly_usd"] if got is not None else 1.0
    audit = AuditLog(Path(workdir) / "audit.jsonl").entries()
    m = {"anomaly_precision": round(precision, 3), "anomaly_recall": round(recall, 3),
         "false_positives": sorted(f"{a} · {b} · {c}" for a, b, c in flagged - want),
         "missed": sorted(f"{a} · {b} · {c}" for a, b, c in want - flagged),
         "cause_accuracy": round(cause_acc, 3), "recommendations_match": proposed == sorted(labels["recommendations"]),
         "suppressed_match": suppressed == sorted(labels.get("suppressed", [])),
         "realised_error_max": round(max(real_err.values()), 3) if real_err else 0.0,
         "unallocated_match": res["kpis"]["unallocated_resources"] == sorted(labels.get("unallocated_resources", [])),
         "rejected_drafts": len(res["rejected_drafts"]),
         "invented_figures": sum(len(x["invented_figures"]) for x in res["rejected_drafts"]),
         "cloud_changes": sum(1 for e in audit if e["action"].startswith("cloud."))}
    checks = {"anomaly_precision": m["anomaly_precision"] >= gates["anomaly_precision_min"],
              "anomaly_recall": m["anomaly_recall"] >= gates["anomaly_recall_min"],
              "cause_accuracy": m["cause_accuracy"] >= gates["cause_accuracy_min"],
              "realised_error": m["realised_error_max"] <= gates["realised_error_max"],
              "rejected_drafts": m["rejected_drafts"] <= gates["rejected_drafts_max"],
              "invented_figures": m["invented_figures"] <= gates["invented_figures_max"],
              "cloud_changes": m["cloud_changes"] <= gates["cloud_changes_max"]}
    ok = all(checks.values())
    tick = lambda b: "✅" if b else "❌"
    months = sorted({j["month"] for j in res["judged"]})
    md = [f"# FinOps evaluation · {RULES_VERSION} · provider `{res['provider']}`", "",
          f"{len({(j['resource'], j['line_item']) for j in res['judged']})} cost series judged over "
          f"{month_label(months[0])}–{month_label(months[-1])} ({len(res['judged'])} series-months) against hand-written "
          f"labels. Gates: **{'PASS' if ok else 'FAIL'}**.", "",
          "| Measure | Result | Gate | |", "|---|---|---|---|",
          f"| Anomaly precision (series-months) | {m['anomaly_precision']:.0%} | ≥ {gates['anomaly_precision_min']:.0%} | {tick(checks['anomaly_precision'])} |",
          f"| Anomaly recall (series-months) | {m['anomaly_recall']:.0%} | ≥ {gates['anomaly_recall_min']:.0%} | {tick(checks['anomaly_recall'])} |",
          f"| Likely cause and confidence correct | {m['cause_accuracy']:.0%} | ≥ {gates['cause_accuracy_min']:.0%} | {tick(checks['cause_accuracy'])} |",
          f"| Realised saving vs expected (worst error) | {m['realised_error_max']:.1%} | ≤ {gates['realised_error_max']:.0%} | {tick(checks['realised_error'])} |",
          f"| Drafts rejected by validation | {m['rejected_drafts']} | ≤ {gates['rejected_drafts_max']} | {tick(checks['rejected_drafts'])} |",
          f"| Invented figures | {m['invented_figures']} | ≤ {gates['invented_figures_max']} | {tick(checks['invented_figures'])} |",
          f"| Changes made to cloud resources | {m['cloud_changes']} | ≤ {gates['cloud_changes_max']} | {tick(checks['cloud_changes'])} |",
          "", "Checks without a gate:", "",
          f"- Proposed recommendations match labels: {tick(m['recommendations_match'])} ({', '.join(proposed)})",
          f"- Suppressed after rejection match labels: {tick(m['suppressed_match'])} ({', '.join(suppressed) or 'none'})",
          f"- Unallocated resources match labels: {tick(m['unallocated_match'])}",
          f"- Not flagged, on purpose: steady growth on order-service-nodes, the August bump on partner-gateway-egress, "
          f"the September SLA credit. False positives: {', '.join(m['false_positives']) or 'none'}. "
          f"Missed: {', '.join(m['missed']) or 'none'}.", "",
          "| Anomaly | Expected cause | Got | |", "|---|---|---|---|"]
    md += [f"| {c['anomaly']} | {c['expected']['cause_config']} · {c['expected']['cause_change'] or 'no change request'} · "
           f"{c['expected']['confidence']} | {c['got']['config']} · {c['got']['change'] or 'no change request'} · "
           f"{c['got']['confidence']} | {tick(c['correct'])} |" for c in causes]
    md += ["", f"_Gate note: {gates.get('note', '')}_", "",
           "_Synthetic data: the cost export and labels were written together, so this proves the pipeline works, "
           "not that the thresholds are right. Re-run on a real cost export before relying on it._", "",
           "_Generated by Engineering Command Centre · use case 5 · Author: Pradeep Sahoo_", ""]
    return {"metrics": m, "causes": causes, "gate_results": checks, "passed": ok, "report_md": "\n".join(md)}
