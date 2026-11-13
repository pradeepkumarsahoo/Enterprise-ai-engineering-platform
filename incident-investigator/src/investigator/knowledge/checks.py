# Author: Pradeep Sahoo
"""Deterministic knowledge checks (use case 2).

Everything that decides *whether* something is wrong runs here, in code:
runbook age, broken references, practice drift, ownership, coverage gaps,
repeat incidents and overdue follow-up actions. The model is only asked to
draft wording for fixes afterwards.

Every finding cites evidence records (K1, K2, ...) built from the source data,
in the same way use case 1 cites E1, E2, ...
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from ..models import Evidence
from .sources import KnowledgeBase

STALE_DAYS = 180          # a runbook not validated for this long is stale
DRIFT_LOOKBACK_DAYS = 180  # incidents considered for practice drift and coverage gaps
REPEAT_GAP_DAYS = 90       # same cause again within this many days = repeat
REPEAT_LOOKBACK_DAYS = 180 # the latest incident of a repeat cluster must be this recent

FINDING_KINDS = ("stale", "unvalidated", "unowned", "broken_reference", "practice_drift", "missing_runbook")


@dataclass
class Finding:
    id: str
    kind: str
    subject: str                 # runbook id, or service name for missing_runbook
    detail: str
    evidence: list[str]
    owner_team: str
    step: int | None = None      # runbook step the finding is about (1-based)
    data: dict = field(default_factory=dict)


@dataclass
class RepeatCluster:
    cause_key: str
    incidents: list[str]
    services: list[str]
    evidence: list[str]
    open_actions: list[str]


@dataclass
class OverdueAction:
    id: str
    incident_id: str
    description: str
    owner_team: str
    days_overdue: int
    on_repeat_cause: bool
    evidence: str


@dataclass
class Recommendation:
    finding_id: str
    description: str
    action_type: str             # knowledge.validate | ownership.assign | knowledge.create | escalate
    owner_team: str
    requires_approval: bool


@dataclass
class Analysis:
    as_of: str
    evidence: list[Evidence]
    findings: list[Finding]
    repeats: list[RepeatCluster]
    overdue: list[OverdueAction]
    recommendations: list[Recommendation]


def _d(s: str) -> date:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date() if "T" in s else date.fromisoformat(s)


class _EvidenceBook:
    """Assigns K-ids and avoids duplicate records."""

    def __init__(self):
        self.items: list[Evidence] = []
        self._keys: dict[str, str] = {}

    def add(self, key: str, kind: str, source: str, summary: str) -> str:
        if key not in self._keys:
            eid = f"K{len(self.items) + 1}"
            self.items.append(Evidence(eid, kind, source, summary))
            self._keys[key] = eid
        return self._keys[key]


def analyse(kb: KnowledgeBase) -> Analysis:
    as_of = kb.as_of
    ev = _EvidenceBook()
    findings: list[Finding] = []
    retired = {t["name"]: t for t in kb.org.get("retired_teams", [])}

    def new(kind, subject, detail, evidence, owner, step=None, **data):
        findings.append(Finding(f"F{len(findings) + 1}", kind, subject, detail, list(dict.fromkeys(evidence)),
                                owner, step, data))

    def owner_of(rb) -> str:
        """The team that should act: the runbook owner, or its successor if that team was retired."""
        team = rb["owner_team"]
        if team in retired:
            return retired[team].get("services_moved_to") or kb.org["service_owners"].get(rb["services"][0], "unassigned")
        return team

    def rb_meta(rb) -> str:
        v = rb.get("last_validated")
        age = f"last validated {v} ({(as_of - _d(v)).days} days before {as_of})" if v else "never validated"
        return ev.add(f"meta:{rb['id']}", "runbook", "runbook wiki",
                      f"{rb['id']} “{rb['title']}” · owner {rb['owner_team']} · {age} · services {', '.join(rb['services'])}")

    def rb_step(rb, n) -> str:
        return ev.add(f"step:{rb['id']}:{n}", "runbook_step", "runbook wiki", f"{rb['id']} step {n}: “{rb['steps'][n - 1]}”")

    def timeline(t) -> str:
        parts = [f"{t['incident_id']} ({t['service']}, {_d(t['opened_at'])}) confirmed cause {t['confirmed_cause']}"]
        if t.get("runbook_used"):
            parts.append(f"runbook {t['runbook_used']}: followed steps {t['steps_followed'] or 'none'}, "
                         f"skipped {t['steps_skipped'] or 'none'}")
        else:
            parts.append("no runbook used")
        if t["off_runbook_actions"]:
            parts.append("off-runbook: " + "; ".join(t["off_runbook_actions"]))
        parts.append(f"resolved by {t['resolved_by'].replace('_', ' ')}")
        return ev.add(f"tl:{t['incident_id']}", "post_incident_review", "incident tool", " · ".join(parts))

    # ---- per-runbook checks
    for rb in kb.runbooks:
        owner = owner_of(rb)
        v = rb.get("last_validated")
        if v is None:
            new("unvalidated", rb["id"], "Never validated by its owner", [rb_meta(rb)], owner)
        elif (as_of - _d(v)).days > STALE_DAYS:
            new("stale", rb["id"], f"Not validated for {(as_of - _d(v)).days} days (limit {STALE_DAYS})", [rb_meta(rb)], owner)

        if rb["owner_team"] in retired:
            old = rb["owner_team"]
            org_ev = ev.add(f"org:{old}", "team_directory", "team directory",
                            f"Team {old} retired on {retired[old]['retired_on']}; services moved to {owner}")
            new("unowned", rb["id"], f"Owner team {old} was retired", [rb_meta(rb), org_ev], owner, proposed_owner=owner)

        for svc in rb["services"]:
            for item in kb.config_inventory.get(svc, {}).get("removed", []):
                for n, step in enumerate(rb["steps"], start=1):
                    if item["name"] in step:
                        inv_ev = ev.add(f"inv:{svc}:{item['name']}", "config_inventory", "config repository",
                                        f"{svc}: {item['name']} removed in {item['removed_in']}; "
                                        f"replaced by {item['replaced_by']}" + (f" ({item['where']})" if item.get("where") else ""))
                        new("broken_reference", rb["id"], f"Step {n} references {item['name']}, removed in {item['removed_in']}",
                            [rb_step(rb, n), inv_ev], owner, step=n, removed=item["name"], replaced_by=item["replaced_by"])

    # ---- practice drift and coverage gaps, from recent post-incident reviews
    recent = [t for t in kb.timelines if (as_of - _d(t["opened_at"])).days <= DRIFT_LOOKBACK_DAYS]
    for rb in kb.runbooks:
        uses = [t for t in recent if t.get("runbook_used") == rb["id"]]
        drifted = [t for t in uses if t["resolved_by"] == "off_runbook" or len(t["steps_skipped"]) >= 2]
        if drifted:
            t = drifted[-1]
            first_skipped = t["steps_skipped"][0] if t["steps_skipped"] else None
            evs = [timeline(x) for x in drifted] + ([rb_step(rb, first_skipped)] if first_skipped else [])
            new("practice_drift", rb["id"],
                f"In {len(drifted)} of {len(uses)} recent uses, responders left the runbook "
                f"({'; '.join(t['off_runbook_actions']) or 'skipped steps'})",
                evs, owner_of(rb), step=first_skipped, incident=t["incident_id"], off_runbook=t["off_runbook_actions"])

    for t in recent:
        if t["runbook_used"] or t["confirmed_cause"] == "unknown":
            continue
        covered = [rb for rb in kb.runbooks if t["service"] in rb["services"] and t["confirmed_cause"] in rb.get("covers", [])]
        if not covered:
            new("missing_runbook", t["service"], f"No runbook covers {t['confirmed_cause']} on {t['service']}",
                [timeline(t)], kb.org["service_owners"].get(t["service"], "unassigned"),
                cause=t["confirmed_cause"], incident=t["incident_id"])

    # ---- repeat incidents: same cause again within REPEAT_GAP_DAYS
    by_key: dict[str, list[dict]] = {}
    for t in sorted(kb.timelines, key=lambda x: x["opened_at"]):
        if t["cause_key"] != "unknown":
            by_key.setdefault(t["cause_key"], []).append(t)
    repeats: list[RepeatCluster] = []
    for key, items in by_key.items():
        chain = [items[0]]
        for t in items[1:]:
            if (_d(t["opened_at"]) - _d(chain[-1]["opened_at"])).days <= REPEAT_GAP_DAYS:
                chain.append(t)
            else:
                chain = [t]
        if len(chain) >= 2 and (as_of - _d(chain[-1]["opened_at"])).days <= REPEAT_LOOKBACK_DAYS:
            ids = [t["incident_id"] for t in chain]
            open_actions = [a["id"] for a in kb.actions if a["incident_id"] in ids and a["status"] != "done"]
            repeats.append(RepeatCluster(key, ids, sorted({t["service"] for t in chain}),
                                         [timeline(t) for t in chain], open_actions))

    # ---- overdue follow-up actions
    repeat_incidents = {i for r in repeats for i in r.incidents}
    overdue: list[OverdueAction] = []
    for a in kb.actions:
        days = (as_of - _d(a["due"])).days
        if a["status"] != "done" and days > 0:
            eid = ev.add(f"pia:{a['id']}", "follow_up_action", "incident tool",
                         f"{a['id']} from {a['incident_id']}: “{a['description']}” · owner {a['owner_team']} · "
                         f"due {a['due']} · status {a['status']} · {days} days overdue")
            overdue.append(OverdueAction(a["id"], a["incident_id"], a["description"], a["owner_team"], days,
                                         a["incident_id"] in repeat_incidents, eid))
    overdue.sort(key=lambda o: (not o.on_repeat_cause, -o.days_overdue))

    return Analysis(str(as_of), ev.items, findings, repeats, overdue, recommend(findings, repeats, overdue))


def recommend(findings: list[Finding], repeats: list[RepeatCluster], overdue: list[OverdueAction]) -> list[Recommendation]:
    """Fixed recommendations per finding kind. Written by code, not the model."""
    recs: list[Recommendation] = []
    for f in findings:
        if f.kind in ("stale", "unvalidated"):
            recs.append(Recommendation(f.id, f"Walk through {f.subject} with {f.owner_team} in a game day and record the validation",
                                       "knowledge.validate", f.owner_team, False))
        elif f.kind == "unowned":
            recs.append(Recommendation(f.id, f"Assign {f.subject} to {f.data['proposed_owner']}", "ownership.assign",
                                       f.data["proposed_owner"], True))
        elif f.kind == "missing_runbook":
            recs.append(Recommendation(f.id, f"Create a runbook for {f.data['cause']} on {f.subject}, starting from the "
                                             f"{f.data['incident']} timeline", "knowledge.create", f.owner_team, True))
    for r in repeats:
        for o in overdue:
            if o.on_repeat_cause and o.incident_id in r.incidents:
                recs.append(Recommendation(o.id, f"Escalate {o.id} to the {o.owner_team} engineering manager: "
                                                 f"{r.cause_key} has occurred {len(r.incidents)} times", "escalate",
                                           o.owner_team, False))
    return recs
