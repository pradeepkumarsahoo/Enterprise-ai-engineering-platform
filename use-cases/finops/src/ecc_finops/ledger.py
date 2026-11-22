# Author: Pradeep Sahoo
"""Decisions on savings recommendations, enforced in code (use case 5).

These rules are governance, so they live here and change through code review, not a config edit:
- only the team that owns the resource decides: approvers need the role `service-owner` or
  `engineering-lead`. A FinOps analyst proposes and follows up, but cannot approve alone;
- an agent can never approve, reject or record an implementation;
- every decision needs a written reason;
- only a proposed recommendation can be approved or rejected; approval freezes its estimate,
  so the realised saving is later compared with the figure the team agreed to;
- only an approved recommendation can be recorded as implemented, by a person, on a date that
  is not in the future;
- nothing here changes a cloud resource. The owning team makes the change through its own
  pipeline; the realised saving is then measured from the bill, never typed in.

Decisions are appended to decisions.jsonl and the audit log.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from ecc_core.audit import AuditLog

OWNER_ROLES = ("service-owner", "engineering-lead")


def _entries(workdir: Path) -> list[dict]:
    path = Path(workdir) / "decisions.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def effective(workdir: Path) -> dict[str, dict]:
    """Current pilot state per recommendation: {status, decided_by, decided_on, estimate_at_approval, ...}."""
    out: dict[str, dict] = {}
    for e in _entries(workdir):
        cur = out.setdefault(e["rec"], {})
        if e["decision"] in ("approve", "reject"):
            cur.update({"status": "approved" if e["decision"] == "approve" else "rejected", "decided_by": e["by"],
                        "decided_on": e["at"][:10], "note": e["note"],
                        "estimate_at_approval": e.get("estimate_at_approval")})
        elif e["decision"] == "implemented":
            cur.update({"status": "implemented", "implemented_on": e["on"], "change": e.get("change", "")})
    return out


def _person(by: str) -> None:
    if not by or by.startswith("agent:"):
        raise ValueError("An agent cannot decide on or implement a savings recommendation")


def decide(rec: dict, workdir: Path, by: str, role: str, approve: bool, note: str, analysis_id: str) -> dict:
    """Record the owning team's decision. Raises ValueError when the rules above forbid it."""
    _person(by)
    if role not in OWNER_ROLES:
        raise ValueError(f"Role '{role}' cannot decide on savings (allowed: {', '.join(OWNER_ROLES)}); "
                         "the team that owns the resource decides")
    if not note.strip():
        raise ValueError("A written reason is required")
    if rec["status"] != "proposed":
        raise ValueError(f"{rec['id']} is {rec['status']}; only a proposed recommendation can be decided")
    entry = {"rec": rec["id"], "decision": "approve" if approve else "reject", "by": by, "role": role,
             "note": note.strip(), "team": rec["team"], "analysis_id": analysis_id,
             "estimate_at_approval": rec["estimated_monthly_usd"] if approve else None,
             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _append(workdir, entry)
    AuditLog(Path(workdir) / "audit.jsonl").record(by, f"finops.recommendation.{entry['decision']}", rec["id"],
                                                    analysis_id, role=role, team=rec["team"],
                                                    estimate=rec["estimated_monthly_usd"])
    return entry


def record_implemented(rec: dict, workdir: Path, by: str, on: str, change: str, as_of: str, analysis_id: str) -> dict:
    """Record that the owning team made the change. The saving is measured later, from the bill."""
    _person(by)
    if rec["status"] != "approved":
        raise ValueError(f"{rec['id']} is {rec['status']}; only an approved recommendation can be implemented")
    day = date.fromisoformat(on)
    if day > date.fromisoformat(as_of):
        raise ValueError(f"{on} is in the future (today is {as_of})")
    entry = {"rec": rec["id"], "decision": "implemented", "by": by, "on": on, "change": change,
             "analysis_id": analysis_id, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _append(workdir, entry)
    AuditLog(Path(workdir) / "audit.jsonl").record(by, "finops.recommendation.implemented", rec["id"], analysis_id,
                                                    on=on, change=change)
    return entry


def _append(workdir: Path, entry: dict) -> None:
    Path(workdir).mkdir(parents=True, exist_ok=True)
    with (Path(workdir) / "decisions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
