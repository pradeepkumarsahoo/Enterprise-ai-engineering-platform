# Author: Pradeep Sahoo
"""FinOps evaluation against hand-written labels (use case 5).

Runs a full analysis, then scores it: anomaly precision and recall over every judged
series-month, likely cause and confidence, the recommendations proposed and suppressed, realised
savings, unallocated resources, the series that must NOT be flagged, rejected drafts, invented
figures, and changes made to cloud resources (from the audit log; must be zero).
"""
from __future__ import annotations

from pathlib import Path

from ecc_core.audit import AuditLog

from .fmt import month_label
from .review import analyse
from .rules import RULES_VERSION, Rules
from .sources import FinOpsInputs

# (gate key, metric, label in the report, comparison, format of the result)
GATES = (
    ("anomaly_precision_min", "anomaly_precision", "Anomaly precision (series-months)", ">=", "{:.0%}"),
    ("anomaly_recall_min", "anomaly_recall", "Anomaly recall (series-months)", ">=", "{:.0%}"),
    ("cause_accuracy_min", "cause_accuracy", "Likely cause and confidence correct", ">=", "{:.0%}"),
    ("realised_error_max", "realised_error_max", "Realised saving vs expected (worst error)", "<=", "{:.1%}"),
    ("rejected_drafts_max", "rejected_drafts", "Drafts rejected by validation", "<=", "{}"),
    ("invented_figures_max", "invented_figures", "Invented figures", "<=", "{}"),
    ("cloud_changes_max", "cloud_changes", "Changes made to cloud resources", "<=", "{}"),
)


def _name(gate: str) -> str:
    """anomaly_precision_min -> anomaly_precision: the key in gate_results."""
    return gate.rsplit("_", 1)[0]


def tick(ok: bool) -> str:
    return "✅" if ok else "❌"


def _causes(res: dict, labels: dict) -> list[dict]:
    out = []
    for x in labels["anomalies"]:
        got = next((a for a in res["anomalies"] if a["resource"] == x["resource"]
                    and a["line_item"] == x["line_item"] and a["months"][0] == x["months"][0]), None)
        c = (got or {}).get("cause") or {}
        ok = bool(got) and c.get("config") == x["cause_config"] and c.get("change") == x["cause_change"] \
            and got["confidence"] == x["confidence"]
        out.append({"anomaly": f"{x['resource']} · {x['line_item']}", "expected": x, "correct": ok,
                    "got": {"config": c.get("config"), "change": c.get("change"),
                            "confidence": (got or {}).get("confidence")}})
    return out


def metrics(res: dict, labels: dict, audit: list[dict]) -> tuple[dict, list[dict]]:
    flagged = {(j["resource"], j["line_item"], j["month"]) for j in res["judged"] if j["flagged"]}
    want = {(x["resource"], x["line_item"], m) for x in labels["anomalies"] for m in x["months"]}
    tp = len(flagged & want)
    causes = _causes(res, labels)
    recs = res["recommendations"]
    real_err = {}
    for rid, x in labels.get("realised", {}).items():
        got = next((y["realised_monthly_usd"] for y in recs if y["id"] == rid), None)
        real_err[rid] = abs(got - x["expected_monthly_usd"]) / x["expected_monthly_usd"] if got is not None else 1.0
    quiet = {(x["resource"], x["line_item"]) for x in labels.get("not_flagged", [])}
    m = {"anomaly_precision": round(tp / len(flagged) if flagged else 1.0, 3),
         "anomaly_recall": round(tp / len(want) if want else 1.0, 3),
         "false_positives": sorted(" · ".join(k) for k in flagged - want),
         "missed": sorted(" · ".join(k) for k in want - flagged),
         "cause_accuracy": round(sum(c["correct"] for c in causes) / len(causes) if causes else 1.0, 3),
         "proposed": sorted(x["id"] for x in recs if x["status"] == "proposed"),
         "suppressed": sorted(x["id"] for x in recs if x["status"] == "suppressed"),
         "realised_error_max": round(max(real_err.values()), 3) if real_err else 0.0,
         "not_flagged_ok": not any((r, li) in quiet for r, li, _ in flagged),
         "unallocated_match": res["kpis"]["unallocated_resources"] == sorted(labels.get("unallocated_resources", [])),
         "rejected_drafts": len(res["rejected_drafts"]),
         "invented_figures": sum(len(x["invented_figures"]) for x in res["rejected_drafts"]),
         "cloud_changes": sum(1 for e in audit if e["action"].startswith("cloud."))}
    m["recommendations_match"] = m["proposed"] == sorted(labels["recommendations"])
    m["suppressed_match"] = m["suppressed"] == sorted(labels.get("suppressed", []))
    return m, causes


def evaluate(inp: FinOpsInputs, r: Rules, drafter, gates: dict, labels: dict, workdir: Path) -> dict:
    res = analyse(inp, r, drafter, workdir)
    m, causes = metrics(res, labels, AuditLog(Path(workdir) / "audit.jsonl").entries())
    checks = {_name(gate): (m[metric] >= gates[gate] if op == ">=" else m[metric] <= gates[gate])
              for gate, metric, _, op, _ in GATES}
    ok = all(checks.values())
    months = sorted({j["month"] for j in res["judged"]})
    series = len({(j["resource"], j["line_item"]) for j in res["judged"]})
    quiet = "; ".join(f"{x['resource']} · {x['line_item']} ({x['why']})" for x in labels.get("not_flagged", []))
    md = [f"# FinOps evaluation · {RULES_VERSION} · provider `{res['provider']}`", "",
          f"{series} cost series judged over {month_label(months[0])}–{month_label(months[-1])} "
          f"({len(res['judged'])} series-months) against hand-written labels. Gates: **{'PASS' if ok else 'FAIL'}**.", "",
          "| Measure | Result | Gate | |", "|---|---|---|---|"]
    for gate, metric, label, op, fmt in GATES:
        gfmt = "{:.0%}" if "%" in fmt else "{}"
        md.append(f"| {label} | {fmt.format(m[metric])} | {'≥' if op == '>=' else '≤'} {gfmt.format(gates[gate])} | "
                  f"{tick(checks[_name(gate)])} |")
    md += ["", "Checks without a gate:", "",
           f"- Proposed recommendations match labels: {tick(m['recommendations_match'])} ({', '.join(m['proposed'])})",
           f"- Suppressed after rejection match labels: {tick(m['suppressed_match'])} "
           f"({', '.join(m['suppressed']) or 'none'})",
           f"- Unallocated resources match labels: {tick(m['unallocated_match'])}",
           f"- Deliberately not flagged: {tick(m['not_flagged_ok'])} {quiet or 'none listed'}. "
           f"False positives: {', '.join(m['false_positives']) or 'none'}. Missed: {', '.join(m['missed']) or 'none'}.",
           "", "| Anomaly | Expected cause | Got | |", "|---|---|---|---|"]
    md += [f"| {c['anomaly']} | {c['expected']['cause_config']} · {c['expected']['cause_change'] or 'no change request'} · "
           f"{c['expected']['confidence']} | {c['got']['config']} · {c['got']['change'] or 'no change request'} · "
           f"{c['got']['confidence']} | {tick(c['correct'])} |" for c in causes]
    md += ["", f"_Gate note: {gates.get('note', '')}_", "",
           "_Synthetic data: the cost export and labels were written together, so this proves the pipeline works, "
           "not that the thresholds are right. Re-run on a real cost export before relying on it._", "",
           "_Generated by Engineering Command Centre · use case 5 · Author: Pradeep Sahoo_", ""]
    return {"metrics": m, "causes": causes, "gate_results": checks, "passed": ok, "report_md": "\n".join(md)}
