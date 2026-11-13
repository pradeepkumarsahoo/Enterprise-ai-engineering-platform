# Author: Pradeep Sahoo
"""Turn raw source records into numbered evidence, with all numbers computed in code.

The model never computes a statistic. It only sees evidence summaries written
here, and it can only cite evidence by the IDs assigned here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean

from .adapters import IncidentSource, Runbooks
from .models import Evidence
from .safety import clean

DEPLOY_WINDOW_MIN = 30      # a deploy this close before onset counts as "near onset"
CHANGE_RATIO = 1.3          # before/after ratio that counts as a real change


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class MetricFact:
    evidence_id: str
    name: str
    before: float
    after: float
    ratio: float
    direction: str          # up | down | steady | rising_trend
    near_limit: bool = False


@dataclass
class Facts:
    """Structured view of the evidence for the deterministic detectors."""
    onset: datetime | None
    metrics: dict[str, MetricFact] = field(default_factory=dict)
    deploys_near: list[tuple[str, dict]] = field(default_factory=list)
    deploys_far: list[tuple[str, dict]] = field(default_factory=list)
    config_diffs: list[tuple[str, dict]] = field(default_factory=list)
    logs: list[tuple[str, str]] = field(default_factory=list)          # (evidence id, cleaned message)
    flags_near: list[tuple[str, dict]] = field(default_factory=list)
    dependencies: list[tuple[str, dict]] = field(default_factory=list)
    runbooks: list[tuple[str, dict]] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)


def _detect_onset(m: dict) -> int | None:
    vals = m["values"]
    base = mean(vals[:5])
    for i, v in enumerate(vals[1:], start=1):
        if base > 0 and (v > base * 1.5 or v < base / 1.5):
            return i
    return None


def _fmt(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}"


def build(source: IncidentSource, runbooks: Runbooks | None = None) -> tuple[dict, list[Evidence], Facts]:
    inc = source.incident()
    metrics = source.metrics()
    evidence: list[Evidence] = []

    def add(kind: str, src: str, summary: str, flags=None) -> str:
        eid = f"E{len(evidence) + 1}"
        evidence.append(Evidence(eid, kind, src, summary, list(flags or [])))
        return eid

    # ---- onset, from the alerting metric
    primary = metrics.get(inc["alert"]["metric"])
    onset_idx = _detect_onset(primary) if primary else None
    onset = None
    if primary and onset_idx is not None:
        onset = parse_ts(primary["start"]) + timedelta(seconds=primary["step_s"] * onset_idx)
    facts = Facts(onset=onset)

    # ---- deploys (anything in the 7 days before the alert)
    opened = parse_ts(inc["opened_at"])
    for d in source.deploys():
        at = parse_ts(d["at"])
        if at > opened or opened - at > timedelta(days=7):
            continue
        ref = onset or opened
        minutes = (ref - at).total_seconds() / 60
        when = (f"{minutes:.0f} min before onset" if minutes < 120
                else f"{minutes / 60:.0f} h before onset" if minutes < 48 * 60
                else f"{minutes / 1440:.0f} days before onset")
        summary = (f"{d['id']} · {d['service']} {d['version_from']} → {d['version_to']} at "
                   f"{at:%H:%M} UTC ({when}). Change: {d.get('change_summary', 'n/a')}")
        text, flags = clean(summary)
        eid = add("deployment", "deploy pipeline", text, flags)
        near = 0 <= minutes <= DEPLOY_WINDOW_MIN
        (facts.deploys_near if near else facts.deploys_far).append((eid, d))
        for c in d.get("config_diff", []):
            ctext, cflags = clean(f"{c['key']}: {c['from']} → {c['to']} in {d['version_to']} ({c['file']})")
            facts.config_diffs.append((add("config_diff", "git diff", ctext, cflags), c))

    # ---- metrics: before/after onset, computed here
    if onset_idx is not None:
        for name, m in metrics.items():
            vals = m["values"]
            before, after = mean(vals[:onset_idx]), mean(vals[onset_idx:])
            ratio = after / before if before else float("inf")
            rising = sum(1 for a, b in zip(vals, vals[1:]) if b > a) >= 0.8 * (len(vals) - 1) and vals[-1] > vals[0] * 1.25
            direction = ("rising_trend" if rising else "up" if ratio >= CHANGE_RATIO
                         else "down" if ratio <= 1 / CHANGE_RATIO else "steady")
            unit = m.get("unit", "")
            limit = metrics.get(name.replace("_mb", "_limit_mb")) if name.endswith("_mb") and not name.endswith("_limit_mb") else None
            near_limit = bool(limit and vals[-1] >= 0.95 * limit["values"][-1])
            if name.endswith("_limit_mb") or name == "db_pool_max":
                if direction == "steady":
                    summary = f"{name} unchanged at {_fmt(vals[-1])} {unit}"
                else:
                    summary = f"{name} changed {_fmt(vals[0])} → {_fmt(vals[-1])} {unit} at onset"
            elif direction == "rising_trend":
                summary = (f"{name} rising steadily {_fmt(vals[0])} → {_fmt(vals[-1])} {unit} over the window"
                           + (f", {vals[-1] / limit['values'][-1]:.0%} of limit" if limit else ""))
            else:
                word = {"up": "up", "down": "down", "steady": "steady"}[direction]
                summary = (f"{name} {word}: {_fmt(before)} → {_fmt(after)} {unit} "
                           f"(×{ratio:.2f}) before vs after onset {onset:%H:%M} UTC")
            eid = add("metric", "metrics", summary)
            facts.metrics[name] = MetricFact(eid, name, before, after, ratio, direction, near_limit)
    else:
        facts.missing_sources.append("No clear onset found in the alerting metric")

    # ---- feature flags
    for f in source.flag_changes():
        at = parse_ts(f["at"])
        minutes = ((onset or opened) - at).total_seconds() / 60
        text, flags = clean(f"Flag {f['flag']}: {f['from']} → {f['to']} by {f['by']} at {at:%H:%M} UTC "
                            f"({minutes:.0f} min before onset)")
        eid = add("flag_change", "feature flags", text, flags)
        if 0 <= minutes <= DEPLOY_WINDOW_MIN:
            facts.flags_near.append((eid, f))

    # ---- dependency status
    for d in source.dependency_status():
        text, flags = clean(f"{d['dependency']} status: {d['status']} from {parse_ts(d['at']):%H:%M} UTC. {d.get('note', '')}")
        facts.dependencies.append((add("dependency_status", "status pages", text, flags), d))

    # ---- logs (untrusted text: redacted and flagged)
    for line in source.logs():
        text, flags = clean(f"{line['level']} ×{line.get('count', 1):,} from {parse_ts(line['at']):%H:%M} UTC: {line['message']}")
        eid = add("logs", "log search", text, flags)
        facts.logs.append((eid, text))

    # ---- runbooks matched on service + log text
    if runbooks is not None:
        blob = " ".join(t for _, t in facts.logs) + " " + inc["title"]
        for rb in runbooks.search(inc["service"], blob):
            validated = rb.get("last_validated")
            note = f" (last validated {validated})" if validated else " (never validated)" if "last_validated" in rb else ""
            eid = add("runbook", "knowledge base", f"{rb['id']} “{rb['title']}”{note}: " + "; ".join(rb["steps"]))
            facts.runbooks.append((eid, rb))

    # ---- what we know is not available (feeds "could not establish")
    if not any(k.startswith("trace") for k in metrics):
        facts.missing_sources.append("No request traces for this window")
    return inc, evidence, facts
