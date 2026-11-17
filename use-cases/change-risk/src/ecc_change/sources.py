# Author: Pradeep Sahoo
"""Read-only sources for use case 4.

- ServiceNow (through the core connector): change requests and incident history.
- Change sets: what each change contains, from pull requests and CI: files, config diffs,
  migrations, new queries, contract changes and coverage of changed lines. In production these
  come from the Git host and CI; here, one JSON file per change.
- The service catalogue (shared): SLOs, and which services consume which contract.
- The release calendar: low-traffic windows, freezes and the standard release policy.
- Runbooks (shared with use cases 1 and 2).

Incident history is read with alert-time fields only (number, CI, priority, title, opened_at).
Resolution notes are never read here, so the scorer cannot learn a change's outcome from them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ecc_core.servicenow import ServiceNowClient
from ecc_core.sources import load_runbooks

CHANGE_FIELDS = ("number", "cmdb_ci", "type", "state", "short_description", "start_date", "end_date", "requested_by",
                 "close_code")
INCIDENT_FIELDS = ("number", "cmdb_ci", "priority", "short_description", "opened_at")


def sn_time(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def _read(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("_meta", None)
    return data


@dataclass
class ChangeInputs:
    changes: dict[str, dict]        # ServiceNow change requests by number
    changesets: dict[str, dict]     # change contents by change number
    incidents: list[dict]           # ServiceNow incidents, alert-time fields only
    catalogue: dict
    calendar: dict
    runbooks: list[dict]

    def start(self, number: str) -> datetime:
        return sn_time(self.changes[number]["start_date"])

    def end(self, number: str) -> datetime:
        c = self.changes[number]
        return sn_time(c.get("end_date") or c["start_date"])

    def incidents_on(self, ci: str, after: datetime, before: datetime) -> list[dict]:
        return [i for i in self.incidents
                if i["cmdb_ci"] == ci and after < sn_time(i["opened_at"]) <= before]

    def linked_incident(self, number: str, window_hours: int, known_by: datetime | None = None) -> dict | None:
        """The first incident on the same CI that opened within the window after the change ended.

        With known_by, only incidents already opened by then count: that is what a scorer could know.
        """
        end = self.end(number)
        limit = end + timedelta(hours=window_hours)
        if known_by is not None:
            limit = min(limit, known_by)
        hits = sorted(self.incidents_on(self.changes[number]["cmdb_ci"], end, limit), key=lambda i: i["opened_at"])
        return hits[0] if hits else None

    @classmethod
    def load(cls, client: ServiceNowClient, changesets_dir: Path, calendar: Path, catalogue: Path,
             runbooks: Path) -> "ChangeInputs":
        changes = {c["number"]: c for c in client.get("change_request", "", CHANGE_FIELDS)}
        sets = {}
        for p in sorted(Path(changesets_dir).glob("CHG*.json")):
            data = _read(p)
            sets[data["change"]] = data
        missing = sorted(set(sets) - set(changes))
        if missing:
            raise ValueError(f"Change sets without a ServiceNow change request: {', '.join(missing)}")
        return cls(changes, sets, client.get("incident", "", INCIDENT_FIELDS), _read(catalogue), _read(calendar),
                   load_runbooks(runbooks))
