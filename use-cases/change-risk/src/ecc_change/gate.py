# Author: Pradeep Sahoo
"""The release gate: who must approve a change, enforced in code.

These rules are governance, so they live here and change through code review, not a config edit:
- a low or medium score needs one approver; a high score needs two different approvers;
- the person who requested the change cannot approve it;
- an agent can never approve;
- approvers need one of the release roles below;
- any rejection blocks the release until the change is re-assessed;
- approvals are tied to one assessment: if the change or the rules change, the score is
  recomputed under a new assessment ID and earlier approvals no longer count.

Decisions are appended to approvals.jsonl and the audit log. The gate records the decision;
nothing here deploys or blocks a pipeline.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ecc_core.audit import AuditLog

RELEASE_ROLES = ("release-manager", "engineering-lead", "sre-lead")


def required_approvers(band: str) -> int:
    return 2 if band == "high" else 1


def _decisions(workdir: Path) -> list[dict]:
    path = Path(workdir) / "approvals.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def status(assessment: dict, workdir: Path) -> dict:
    """Gate status for the latest assessment of a change."""
    mine = [d for d in _decisions(workdir)
            if d["change"] == assessment["change"] and d["assessment_id"] == assessment["assessment_id"]]
    approvers = sorted({d["by"] for d in mine if d["decision"] == "approve"})
    rejections = [d for d in mine if d["decision"] == "reject"]
    need = required_approvers(assessment["band"])
    state = ("rejected" if rejections else "approved" if len(approvers) >= need
             else f"awaiting {need - len(approvers)} approver(s)")
    return {"change": assessment["change"], "score": assessment["score"], "band": assessment["band"],
            "assessment_id": assessment["assessment_id"], "requested_by": assessment["requested_by"],
            "required_approvers": need, "approvers": approvers,
            "rejected_by": [d["by"] for d in rejections], "state": state}


def decide(assessment: dict, workdir: Path, by: str, role: str, approve: bool, note: str = "") -> dict:
    """Record one approver's decision. Raises ValueError when the rules above forbid it."""
    if by.startswith("agent:"):
        raise ValueError("An agent cannot approve or reject a release")
    if role not in RELEASE_ROLES:
        raise ValueError(f"Role '{role}' cannot approve releases (allowed: {', '.join(RELEASE_ROLES)})")
    if by == assessment["requested_by"]:
        raise ValueError(f"{by} requested {assessment['change']} and cannot approve it")
    current = status(assessment, workdir)
    if by in current["approvers"] or by in current["rejected_by"]:
        raise ValueError(f"{by} has already decided on this assessment of {assessment['change']}")
    entry = {"change": assessment["change"], "assessment_id": assessment["assessment_id"], "score": assessment["score"],
             "band": assessment["band"], "decision": "approve" if approve else "reject", "by": by, "role": role,
             "note": note, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with (Path(workdir) / "approvals.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    AuditLog(Path(workdir) / "audit.jsonl").record(by, f"release.gate.{entry['decision']}", assessment["change"],
                                                    assessment["assessment_id"], role=role, score=assessment["score"],
                                                    band=assessment["band"])
    return {**entry, "gate": status(assessment, workdir)}
