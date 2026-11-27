# Author: Pradeep Sahoo
"""Read-only sources for use case 5.

- The cost export: FOCUS, AWS CUR 2.0 or Azure cost details, read by `exports.py` into one shape.
  One row per resource, line item and charge period (a day or a month). In production this is the
  cloud provider's scheduled cost export; here, a file.
- Utilisation: 30-day CPU and memory p95, running hours, and attachment state, per resource.
- The cloud configuration change log: what changed on a resource, by whom, when, and the change
  request it was made under (if any).
- The savings register: recommendations decided before the pilot, with their frozen estimates.
- Commitments: reservations and savings plans with their term (from the provider's API); their
  cost and use come from the export.
- ServiceNow change requests (through the core connector).
- The service catalogue (shared): which team owns a service, used to allocate cost that is tagged
  with a service but not a team.
- The team directory (shared): who belongs to which team, in which role, and who has left. Used
  to check that whoever decides on a recommendation belongs to the team that owns it.

Free text (configuration notes, change titles) is untrusted: secrets are redacted and
instruction-like text is flagged before anything reaches a model or a report.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ecc_core.safety import clean
from ecc_core.servicenow import ServiceNowClient

from .exports import FOCUS_COLUMNS as COST_COLUMNS, CostLine, read_export

CHANGE_FIELDS = ("number", "cmdb_ci", "state", "short_description", "start_date", "end_date", "requested_by",
                 "close_code")


@dataclass
class FinOpsInputs:
    lines: list[CostLine]
    utilisation: dict[str, dict]
    config_changes: list[dict]          # cleaned; each has "flags"
    register: list[dict]
    changes: dict[str, dict]            # ServiceNow change requests by number, cleaned
    catalogue: dict
    problems: list[str] = field(default_factory=list)   # rows skipped while reading, with the reason
    commitments: list[dict] = field(default_factory=list)
    directory: dict = field(default_factory=dict)        # team directory: {"people": {name: {...}}}
    export_format: str = "focus"
    has_billed: bool = True
    has_effective: bool = True

    def owner_of_service(self, service: str) -> str | None:
        return (self.catalogue.get("services", {}).get(service) or {}).get("owner")

    @property
    def known_teams(self) -> set[str]:
        """Teams a `team` tag may name: owners in the catalogue and teams with an active member.
        Empty when no team directory was given (then any team tag is accepted)."""
        people = (self.directory or {}).get("people", {})
        if not people:
            return set()
        return ({p["team"] for p in people.values() if p.get("active", True)}
                | {s.get("owner") for s in self.catalogue.get("services", {}).values() if s.get("owner")})

    @classmethod
    def load(cls, client: ServiceNowClient, finops_dir: Path, catalogue: Path, directory: Path | None = None,
             export_file: str = "cost_export.csv", export_format: str = "auto") -> "FinOpsInputs":
        d = Path(finops_dir)
        read = read_export(d / export_file, export_format)
        util = _json(d / "utilisation.json")["resources"]
        cfg = []
        for c in _json(d / "config_changes.json")["changes"]:
            note, flags = clean(c.get("note", ""))
            cfg.append({**c, "note": note, "flags": flags})
        register = _json(d / "savings_register.json")["recommendations"]
        commitments = _json(d / "commitments.json")["commitments"] if (d / "commitments.json").exists() else []
        changes = {}
        for c in client.get("change_request", "", CHANGE_FIELDS):
            text, flags = clean(c.get("short_description", ""))
            changes[c["number"]] = {**c, "short_description": text, "flags": flags}
        return cls(read.lines, util, cfg, register, changes, _json(Path(catalogue)), read.problems, commitments,
                   _json(Path(directory)) if directory else {}, read.format, read.has_billed, read.has_effective)


def _json(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("_meta", None)
    return data


def read_cost_export(path: Path, fmt: str = "auto") -> tuple[list[CostLine], list[str]]:
    """Parse an export (any supported format). A malformed row is skipped and reported, never guessed at."""
    read = read_export(path, fmt)
    return read.lines, read.problems
