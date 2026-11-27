# Author: Pradeep Sahoo
"""The likely cause of a cost anomaly, and how confident the rule is (use case 5).

A configuration change in the window before the anomaly whose attribute fits the cost category
(retention for storage, log level for logging, ...), on the same resource, the same service or the
same team. Confidence is a points rule, shown with its parts:
    attribute fits the category +2 · same resource or service +1 · made under a change request +1
    high from 4 points, medium 2 to 3, low 1.
With no configuration change, a change request on the same resource or service scores 1 (low).
The model never picks a cause or sets a confidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ecc_core.servicenow import sn_time

from .fmt import month_add
from .rules import Rules
from .sources import FinOpsInputs

# attribute words that can explain a cost increase in each FOCUS ServiceCategory
CATEGORY_TOKENS = {
    "Storage": {"retention", "backup", "snapshot", "snapshots", "lifecycle", "storage", "class", "replication",
                "versioning", "size"},
    "Compute": {"instance", "type", "node", "nodes", "count", "replicas", "autoscaling", "schedule", "size",
                "min", "desired"},
    "Databases": {"instance", "class", "iops", "replicas", "multi", "az", "storage", "size"},
    "Networking": {"egress", "nat", "region", "replication", "peering", "endpoint", "transfer"},
    "Management and Governance": {"log", "level", "logging", "retention", "sampling", "verbosity", "trace", "tracing"},
}
CONFIDENCE_BANDS = ((4, "high"), (2, "medium"), (1, "low"))
CONFIDENCE_RULE = "high from 4 points, medium 2 to 3, low 1"


@dataclass
class Cause:
    config: str | None                 # CFG id
    change: str | None                 # ServiceNow change number
    scope: str                         # resource | service | team | change-only
    points: int
    parts: list[str]                   # how the points were earned
    summary: str


def confidence(points: int) -> str:
    return next((name for floor, name in CONFIDENCE_BANDS if points >= floor), "not established")


def tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t}


def _utc(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


class CauseFinder:
    """Called with (series, onset month); returns the best-scoring Cause, or None."""

    def __init__(self, inp: FinOpsInputs, r: Rules, team_of: dict[str, str]):
        self.inp, self.r, self.team_of = inp, r, team_of     # team_of: resource -> team, from allocation

    def __call__(self, s, onset: str) -> Cause | None:
        start = _utc(f"{onset}-01") - timedelta(days=self.r.cause_lookback_days)
        end = _utc(f"{month_add(onset, 1)}-01")
        found = [x for c in self.inp.config_changes if (x := self._config(s, c, start, end))]
        if found:
            return max(found, key=lambda x: (x[0].points, x[1]))[0]       # most points, then the latest
        return self._change_only(s, start, end)

    def _scope(self, s, resource: str) -> tuple[str, int] | None:
        if resource == s.resource:
            return "resource", 1
        if s.service and resource == s.service:
            return "service", 1
        if s.team in (self.inp.owner_of_service(resource), self.team_of.get(resource)):
            return "team", 0
        return None

    def _config(self, s, c: dict, start: datetime, end: datetime) -> tuple[Cause, datetime] | None:
        at = sn_time(c["at"])
        if not (start <= at < end) or not (tokens(c["attribute"]) & CATEGORY_TOKENS.get(s.category, set())):
            return None
        scope = self._scope(s, c["resource"])
        if scope is None:
            return None
        name, extra = scope
        linked = c.get("change") if c.get("change") in self.inp.changes else None
        parts = [f"attribute {c['attribute']} fits {s.category} cost (+2)",
                 f"same {name} (+1)" if extra else "same team only (+0)",
                 f"made under change request {linked} (+1)" if linked else "no change request (+0)"]
        summary = (f"{c['id']} on {c['at'][:10]}: {c['resource']} {c['attribute']} changed from {c['old']} to "
                   f"{c['new']} by {c['actor']}" + (f" under {linked}" if linked else ", with no change request"))
        return Cause(c["id"], linked, name, 2 + extra + (1 if linked else 0), parts, summary), at

    def _change_only(self, s, start: datetime, end: datetime) -> Cause | None:
        for n, c in sorted(self.inp.changes.items()):
            if c.get("cmdb_ci") in {s.resource, s.service} and c.get("start_date") \
                    and start <= sn_time(c["start_date"]) < end:
                return Cause(None, n, "change-only", 1, ["change request on the same resource or service, but no "
                                                        "configuration change recorded (+1)"],
                             f"{n} on {c['start_date'][:10]}: {c['short_description']}")
        return None
