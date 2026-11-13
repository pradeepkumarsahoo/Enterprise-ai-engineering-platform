# Author: Pradeep Sahoo
"""Read-only access to the knowledge sources used by use case 2.

In production these come from the runbook wiki (pages + revision history), the
incident tool (post-incident reviews and follow-up actions), the config
repository and the team directory. Here they come from the synthetic JSON
files. As with use case 1, there is no write method: drafted edits go to a
review queue, never back to the wiki.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..adapters import load_runbooks


def _read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@dataclass
class KnowledgeBase:
    runbooks: list[dict]
    timelines: list[dict]          # what responders did in each incident (post-incident review)
    actions: list[dict]            # follow-up actions from post-incident reviews
    config_inventory: dict         # per service: settings removed or renamed
    org: dict                      # active / retired teams, service owners, evaluation date

    @property
    def as_of(self) -> date:
        return date.fromisoformat(self.org["as_of"])

    def runbook(self, rb_id: str) -> dict | None:
        return next((r for r in self.runbooks if r["id"] == rb_id), None)

    @classmethod
    def load(cls, runbooks_path: Path, knowledge_dir: Path) -> "KnowledgeBase":
        k = Path(knowledge_dir)
        return cls(
            runbooks=load_runbooks(runbooks_path),
            timelines=_read(k / "timelines.json")["timelines"],
            actions=_read(k / "actions.json")["actions"],
            config_inventory=_read(k / "config_inventory.json")["services"],
            org={key: v for key, v in _read(k / "org.json").items() if key != "_meta"},
        )
