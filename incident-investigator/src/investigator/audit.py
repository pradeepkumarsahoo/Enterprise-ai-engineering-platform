# Author: Pradeep Sahoo
"""Append-only audit log (JSON Lines).

The class has no update or delete method. Each entry carries a correlation ID
that links every tool call and decision back to the investigation that caused it.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:8]


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, actor: str, action: str, target: str, cid: str, outcome: str = "success", **detail) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "actor": actor, "action": action, "target": target,
            "outcome": outcome, "cid": cid,
        }
        if detail:
            entry["detail"] = detail
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
