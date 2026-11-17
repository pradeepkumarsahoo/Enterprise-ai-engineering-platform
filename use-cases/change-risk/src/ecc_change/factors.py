# Author: Pradeep Sahoo
"""Deterministic change-risk factors (use case 4).

The score is the sum of the weights of the factors that fire, capped at 10. Every factor is a
rule in code, cites evidence records (C1, C2, ...) and takes its weight from the product
configuration. The model never sets, changes or sees a weight it could alter: it only explains
the factors and drafts release conditions afterwards.

Everything is evaluated as of an assessment time: for an upcoming change, now; when
backtesting a past change, the moment it started. Only incidents already opened by then are
used, so a backtest cannot see the outcome it is scored against.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timedelta

from ecc_core.evidence import Evidence
from ecc_core.safety import clean

from .sources import ChangeInputs, sn_time

CAPACITY_TOKENS = {"pool", "max", "maximum", "limit", "limits", "replica", "replicas", "thread", "threads",
                   "connection", "connections", "timeout", "memory", "heap", "concurrency"}
GENERIC_TOKENS = {"max", "maximum", "limit", "limits"}      # too common to match two changes on their own
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
RULES_VERSION = "change-risk rules v1.0"


@dataclass(frozen=True)
class Rules:
    """Weights and thresholds; set in [use_cases.change.settings] of the product configuration."""
    weight_sensitive_config: float = 2.5
    weight_capacity_cut: float = 1.0
    weight_repeat_pattern: float = 1.5
    weight_migration_blocking: float = 1.8
    weight_migration_online: float = 0.6
    weight_unindexed_query: float = 1.8
    weight_contract_base: float = 0.5
    weight_contract_per_consumer: float = 0.25
    weight_contract_max: float = 1.5
    weight_coverage_gap: float = 0.8
    weight_deploy_window: float = 0.5
    weight_freeze: float = 2.0
    weight_recent_instability: float = 0.4
    weight_no_rollback: float = 0.5
    weight_change_size: float = 0.3
    medium_min: float = 3.0
    high_min: float = 7.0
    capacity_cut_ratio: float = 0.5          # a capacity setting cut by at least this share
    large_table_rows: int = 1_000_000
    coverage_gate_pct: int = 80
    instability_days: int = 30
    runbook_stale_days: int = 180
    change_size_files: int = 20
    outcome_window_hours: int = 48           # an incident this soon after a change is linked to it
    as_of: str = "2026-11-17"                # "now" for upcoming changes; production passes today's date

    @classmethod
    def from_settings(cls, settings: dict) -> "Rules":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in settings.items() if k in known})


@dataclass
class Factor:
    key: str
    title: str
    signal: str
    weight: float
    evidence: list[str]


@dataclass
class Similar:
    change: str
    incident: str
    ci: str
    matched_on: list[str]
    evidence: list[str]


@dataclass
class Assessment:
    change: str
    service: str
    title: str
    requested_by: str
    planned_start: str
    assessed_at: str
    factors: list[Factor]
    score: float
    band: str
    similar: list[Similar]
    could_not_establish: list[str]
    kpis: dict
    evidence: list[Evidence]
    assessment_id: str = ""
    rules_version: str = RULES_VERSION

    def fired(self) -> set[str]:
        return {f.key for f in self.factors}


def tokens(key: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", key.lower()) if t}


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def _fmt_rows(n: int) -> str:
    return f"{n / 1_000_000:g}M" if n >= 1_000_000 else f"{n:,}"


def _signature(cs: dict) -> dict:
    """What two changes can have in common: capacity settings, tables and contracts."""
    cfg = set()
    for d in cs.get("config_diff", []):
        cfg |= (tokens(d["key"]) & CAPACITY_TOKENS) - GENERIC_TOKENS
    tables = {m["table"] for m in cs.get("migrations", [])} | {q["table"] for q in cs.get("queries", [])}
    contracts = {c["contract"] for c in cs.get("contract_changes", [])}
    return {"config": cfg, "tables": tables, "contracts": contracts}


def band(score: float, r: Rules) -> str:
    return "high" if score >= r.high_min else "medium" if score >= r.medium_min else "low"


def in_window(at: datetime, calendar: dict) -> bool:
    day, hm = DAYS[at.weekday()], at.strftime("%H:%M")
    return any(day in w["days"] and w["from"] <= hm < w["to"] for w in calendar.get("low_traffic_windows", []))


def assess(inp: ChangeInputs, number: str, r: Rules, at: datetime | None = None) -> Assessment:
    """Score one change. at: the assessment time (default: the change's start for past changes, else as_of)."""
    chg, cs = inp.changes[number], inp.changesets.get(number, {})
    service, start = chg["cmdb_ci"], inp.start(number)
    now = datetime.fromisoformat(r.as_of + "T00:00:00+00:00")
    at = at or (start if start < now else now)
    evidence: list[Evidence] = []
    factors: list[Factor] = []
    unknown: list[str] = []

    def ev(kind: str, source: str, summary: str) -> str:
        text, flags = clean(summary)
        eid = f"C{len(evidence) + 1}"
        evidence.append(Evidence(eid, kind, source, text, flags))
        return eid

    def fire(key, title, signal, weight, eids):
        factors.append(Factor(key, title, signal, round(weight, 2), list(dict.fromkeys(eids))))

    # ---- the change itself
    files = [f for pr in cs.get("pull_requests", []) for f in pr["files"]]
    kinds = {}
    for f in files:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    c_change = ev("change", "ServiceNow", f"{number} · {service} · {chg['short_description']} · requested by "
                  f"{chg.get('requested_by', 'unknown')} · planned {start:%a %Y-%m-%d %H:%M} UTC")
    pr_ids = [ev("pull_request", "Git host",
                 f"{pr['id']} “{pr['title']}”: {len(pr['files'])} files ("
                 + ", ".join(f"{n} {k}" for k, n in sorted(_kinds(pr['files']).items())) + f"), {pr['lines_changed']} lines")
              for pr in cs.get("pull_requests", [])]
    if not cs:
        unknown.append(f"No change set (pull requests, diffs, coverage) found for {number}")

    # ---- 1. sensitive configuration
    cfg_ids = []
    cut = None
    for d in cs.get("config_diff", []):
        t = tokens(d["key"]) & CAPACITY_TOKENS
        if not t:
            continue
        old, new = _num(d["from"]), _num(d["to"])
        delta = f" ({(new - old) / old:+.0%})" if old and new is not None else ""
        eid = ev("config_diff", "Git diff", f"{d['key']}: {d['from']} → {d['to']}{delta} in {d['file']}")
        cfg_ids.append(eid)
        if old and new is not None and new <= old * (1 - r.capacity_cut_ratio) and t - {"timeout"}:
            cut = (d, eid, (old - new) / old)
    if cfg_ids:
        first = next(d for d in cs["config_diff"] if tokens(d["key"]) & CAPACITY_TOKENS)
        fire("sensitive_config", "Capacity or timeout setting changed",
             f"{first['key']}: {first['from']} → {first['to']}", r.weight_sensitive_config, cfg_ids + pr_ids[:1])
    if cut:
        d, eid, share = cut
        fire("capacity_cut", "Capacity limit cut sharply",
             f"{d['key']} cut by {share:.0%} (rule: at least {r.capacity_cut_ratio:.0%})", r.weight_capacity_cut, [eid])

    # ---- 2. repeats the pattern of a past change that was followed by an incident
    similar = similar_changes(inp, number, r, at)
    if similar:
        sim_ids = []
        for s in similar:
            eid = ev("similar_change", "ServiceNow history",
                     f"{s.change} on {s.ci} was followed by {s.incident} within {r.outcome_window_hours} h; "
                     f"same {', '.join(s.matched_on)}")
            s.evidence = [eid]
            sim_ids.append(eid)
        fire("repeat_pattern", "Repeats a change that was followed by an incident",
             "; ".join(f"{s.change} → {s.incident} (same {', '.join(s.matched_on)})" for s in similar),
             r.weight_repeat_pattern, sim_ids)

    # ---- 3. migrations
    best = None
    for m in cs.get("migrations", []):
        blocking = ((m["operation"] == "add_column" and not m.get("nullable", True) and not m.get("online"))
                    or (not m.get("online") and m.get("rows_estimate", 0) >= r.large_table_rows))
        eid = ev("migration", "Git diff",
                 f"{m['id']}: {m['operation'].replace('_', ' ')} {m.get('column', '')} on {m['table']} "
                 f"({_fmt_rows(m.get('rows_estimate', 0))} rows), "
                 + ("non-null, " if m["operation"] == "add_column" and not m.get("nullable", True) else "")
                 + ("online" if m.get("online") else "not online"))
        cand = (r.weight_migration_blocking if blocking else r.weight_migration_online, blocking, m, eid)
        best = max(best, cand, key=lambda x: x[0]) if best else cand
    if best:
        w, blocking, m, eid = best
        fire("migration_blocking" if blocking else "migration_online",
             "Schema migration that can lock a large table" if blocking else "Online schema migration",
             f"{m['id']} on {m['table']} ({_fmt_rows(m.get('rows_estimate', 0))} rows)", w, [eid])

    # ---- 4. new query on a large table without an index
    for q in cs.get("queries", []):
        if not q.get("index_covered", True) and q.get("rows_estimate", 0) >= r.large_table_rows:
            eid = ev("query", "Git diff", f"New query on {q['table']} ({_fmt_rows(q['rows_estimate'])} rows) "
                     f"filtering on {q.get('where', 'unknown columns')}, not covered by an index")
            fire("unindexed_query", "New query on a large table without an index",
                 f"{q['table']} by {q.get('where', '?')}", r.weight_unindexed_query, [eid])
            break

    # ---- 5. contract changes and their consumers
    consumers_total = 0
    for c in cs.get("contract_changes", []):
        spec = inp.catalogue.get("contracts", {}).get(c["contract"])
        if not spec:
            unknown.append(f"{c['contract']} is not in the service catalogue; its consumers are unknown")
            continue
        consumers = spec["consumers"]
        consumers_total += len(consumers)
        untested = sorted(k for k, v in consumers.items() if not v.get("contract_tests"))
        eid = ev("contract", "schema registry + service catalogue",
                 f"{c['contract']}: field {c['field_from']} {c['change']}d to {c.get('field_to', '—')}; "
                 f"{len(consumers)} consumers ({', '.join(sorted(consumers))}); without contract tests: "
                 f"{', '.join(untested) or 'none'}")
        w = min(r.weight_contract_base + r.weight_contract_per_consumer * len(consumers), r.weight_contract_max)
        fire("contract_change", "Event or API contract change with consumers",
             f"{c['contract']} {c['field_from']} → {c.get('field_to', '—')}; {len(consumers)} consumers", w, [eid])
        for u in untested:
            unknown.append(f"Whether {u} still reads the old {c['field_from']} field of {c['contract']}: it has no "
                           "contract tests")

    # ---- 6. test coverage of changed lines
    cov = cs.get("coverage")
    code_like = kinds.get("code", 0) + kinds.get("migration", 0)
    if cov:
        eid = ev("coverage", "CI", f"{cov['changed_lines_pct']}% of changed lines covered in {cov['run']} "
                 f"(gate {r.coverage_gate_pct}%)")
        if code_like and cov["changed_lines_pct"] < r.coverage_gate_pct:
            fire("coverage_gap", "Test coverage of changed lines below the gate",
                 f"{cov['changed_lines_pct']}% against {r.coverage_gate_pct}%", r.weight_coverage_gap, [eid])
    elif code_like:
        unknown.append("Coverage of changed lines: no CI coverage report for this change")

    # ---- 7. deploy window and freezes
    windows = "; ".join(f"{', '.join(w['days'])} {w['from']}–{w['to']} UTC" for w in inp.calendar.get("low_traffic_windows", []))
    freeze = next((f for f in inp.calendar.get("freezes", [])
                   if date.fromisoformat(f["from"]) <= start.date() <= date.fromisoformat(f["to"])), None)
    if freeze:
        eid = ev("calendar", "release calendar",
                 f"Planned {start:%a %Y-%m-%d %H:%M} UTC is inside the freeze {freeze['from']} to {freeze['to']} "
                 f"({freeze['reason']})")
        fire("freeze", "Planned inside a change freeze", f"{freeze['reason']}, {freeze['from']} to {freeze['to']}",
             r.weight_freeze, [eid])
    if not in_window(start, inp.calendar):
        eid = ev("calendar", "release calendar",
                 f"Planned {start:%a %H:%M} UTC is outside the low-traffic window ({windows})")
        fire("deploy_window", "Outside the low-traffic window", f"{start:%a %H:%M} UTC; window {windows}",
             r.weight_deploy_window, [eid])

    # ---- 8. recent instability on the same service
    recent = inp.incidents_on(service, at - timedelta(days=r.instability_days), at)
    if recent:
        ids = [ev("incident", "ServiceNow", f"{i['number']} on {service}, opened {i['opened_at']} UTC: "
                  f"{i['short_description']}") for i in recent]
        fire("recent_instability", f"Incidents on {service} in the last {r.instability_days} days",
             ", ".join(i["number"] for i in recent), r.weight_recent_instability, ids)

    # ---- 9. rollback runbook
    books = [b for b in inp.runbooks if service in b.get("services", [])]
    validated = [(b, b.get("last_validated")) for b in books]
    usable = [(b, v) for b, v in validated if v and date.fromisoformat(v) <= at.date()]
    if not books:
        eid = ev("runbook", "runbook wiki", f"No runbook covers {service}")
        fire("no_rollback", "No rollback runbook", f"no runbook covers {service}", r.weight_no_rollback, [eid])
    elif usable:
        b, v = max(usable, key=lambda x: x[1])
        age = (at.date() - date.fromisoformat(v)).days
        eid = ev("runbook", "runbook wiki", f"{b['id']} “{b['title']}” covers {service}; last validated {v} "
                 f"({age} days before assessment)")
        if age > r.runbook_stale_days:
            fire("no_rollback", "Rollback runbook is stale", f"{b['id']} validated {age} days ago "
                 f"(limit {r.runbook_stale_days})", r.weight_no_rollback, [eid])
    elif any(v is None for _, v in validated):
        eid = ev("runbook", "runbook wiki", f"Runbooks for {service} have never been validated")
        fire("no_rollback", "Rollback runbook never validated", f"{service}", r.weight_no_rollback, [eid])
    else:
        unknown.append(f"Runbook state for {service} at {at:%Y-%m-%d}: only later validation dates are recorded")

    # ---- 10. size
    if len(files) > r.change_size_files:
        fire("change_size", "Large change", f"{len(files)} files (threshold {r.change_size_files})",
             r.weight_change_size, pr_ids)

    score = min(round(sum(f.weight for f in factors), 1), 10.0)
    b = band(score, r)
    slo = inp.catalogue.get("services", {}).get(service, {}).get("slo_p95_ms")
    policy = inp.calendar.get("release_policy", {})
    if slo:
        ev("slo", "service catalogue", f"{service} SLO: p95 {slo} ms")
    if policy:
        ev("release_policy", "release calendar",
           f"Release policy: canary {policy['canary_pct']}% for {policy['canary_minutes']} min, then full rollout")
    ev("score", "change-risk rules", f"Score {score} of 10 ({b}); medium from {r.medium_min:g}, high from "
       f"{r.high_min:g}; a high score needs a second approver")

    kpis = {"files_changed": len(files), "files_by_kind": kinds, "consumers": consumers_total,
            "coverage_pct": cov["changed_lines_pct"] if cov else None, "coverage_gate_pct": r.coverage_gate_pct,
            "slo_p95_ms": slo}
    a = Assessment(number, service, chg["short_description"], chg.get("requested_by", ""), chg["start_date"],
                   at.strftime("%Y-%m-%d %H:%M"), factors, score, b, similar, unknown, kpis, evidence)
    payload = json.dumps({"change": chg, "changeset": cs, "rules": asdict(r), "factors": [asdict(f) for f in factors]},
                         sort_keys=True, default=str)
    a.assessment_id = hashlib.sha256(payload.encode()).hexdigest()[:12]
    return a


def _kinds(files: list[dict]) -> dict:
    out: dict[str, int] = {}
    for f in files:
        out[f["kind"]] = out.get(f["kind"], 0) + 1
    return out


def similar_changes(inp: ChangeInputs, number: str, r: Rules, at: datetime) -> list[Similar]:
    """Past changes that share a capacity setting, table or contract with this one, and that were
    followed by an incident on their CI, as far as could be known at time `at`."""
    mine = _signature(inp.changesets.get(number, {}))
    out = []
    for other, cs in inp.changesets.items():
        if other == number or inp.end(other) >= at:
            continue
        inc = inp.linked_incident(other, r.outcome_window_hours, known_by=at)
        if not inc:
            continue
        theirs = _signature(cs)
        matched = ([f"setting ({', '.join(sorted(mine['config'] & theirs['config']))})"] if mine["config"] & theirs["config"] else []) \
            + ([f"table {', '.join(sorted(mine['tables'] & theirs['tables']))}"] if mine["tables"] & theirs["tables"] else []) \
            + ([f"contract {', '.join(sorted(mine['contracts'] & theirs['contracts']))}"] if mine["contracts"] & theirs["contracts"] else [])
        if matched:
            out.append(Similar(other, inc["number"], inp.changes[other]["cmdb_ci"], matched, []))
    return sorted(out, key=lambda s: inp.start(s.change), reverse=True)


def is_upcoming(inp: ChangeInputs, number: str, r: Rules) -> bool:
    return inp.start(number) >= datetime.fromisoformat(r.as_of + "T00:00:00+00:00")
