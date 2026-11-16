# Author: Pradeep Sahoo
"""Read-only access to the sources used by use case 3.

In production these come from the requirements tool (a structured intake form),
the architecture team's pattern library and the ADR repository. Here they come
from the synthetic JSON files. There is no write method: the drafted ADR and
stories go to a review pack, never into the ADR repository or the backlog.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


def _read(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("_meta", None)
    return data


@dataclass
class ArchitectureInputs:
    requirement: dict          # capabilities, NFRs with targets, open decisions, stakeholder notes
    patterns: list[dict]       # reference patterns with published estimates
    adrs: list[dict]           # existing decision records with status

    def nfr(self, nfr_id: str) -> dict | None:
        return next((n for n in self.requirement["nfrs"] if n["id"] == nfr_id), None)

    def pattern(self, pat_id: str) -> dict | None:
        return next((p for p in self.patterns if p["id"] == pat_id), None)

    @classmethod
    def load(cls, arch_dir: Path) -> "ArchitectureInputs":
        d = Path(arch_dir)
        return cls(requirement=_read(d / "requirement.json"),
                   patterns=_read(d / "patterns.json")["patterns"],
                   adrs=_read(d / "adrs.json")["adrs"])
