# Author: Pradeep Sahoo
"""Read-only sources for use case 5.

- The cost export: one CSV with FOCUS-style columns (FinOps Open Cost and Usage Specification),
  one row per resource, line item and billing month. In production this is the cloud provider's
  scheduled cost export; here, a file.
- Utilisation: 30-day CPU and memory p95, running hours, and attachment state, per resource.
- The cloud configuration change log: what changed on a resource, by whom, when, and the change
  request it was made under (if any).
- The savings register: recommendations decided before the pilot, with their frozen estimates.
- ServiceNow change requests (through the core connector).
- The service catalogue (shared): which team owns a service, used to allocate cost that is tagged
  with a service but not a team.

Free text (configuration notes, change titles) is untrusted: secrets are redacted and
instruction-like text is flagged before anything reaches a model or a report.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ecc_core.safety import clean
from ecc_core.servicenow import ServiceNowClient

COST_COLUMNS = ("BillingPeriodStart", "ChargePeriodStart", "ChargePeriodEnd", "ChargeCategory", "ServiceCategory",
                "ServiceName", "ResourceId", "BilledCost", "BillingCurrency", "Tags")
CHANGE_FIELDS = ("number", "cmdb_ci", "state", "short_description", "start_date", "end_date", "requested_by",
                 "close_code")


@dataclass
class CostLine:
    month: str                 # YYYY-MM, from BillingPeriodStart
    charge_start: date
    charge_end: date           # exclusive
    charge_category: str       # Usage, Credit, Tax, ...
    category: str              # ServiceCategory: Compute, Storage, ...
    line_item: str             # ServiceName: Kubernetes nodes, Database snapshots, ...
    resource: str
    cost: float
    tags: dict


@dataclass
class FinOpsInputs:
    lines: list[CostLine]
    utilisation: dict[str, dict]
    config_changes: list[dict]          # cleaned; each has "flags"
    register: list[dict]
    changes: dict[str, dict]            # ServiceNow change requests by number, cleaned
    catalogue: dict
    problems: list[str] = field(default_factory=list)   # rows skipped while reading, with the reason

    def owner_of_service(self, service: str) -> str | None:
        return (self.catalogue.get("services", {}).get(service) or {}).get("owner")

    @classmethod
    def load(cls, client: ServiceNowClient, finops_dir: Path, catalogue: Path) -> "FinOpsInputs":
        d = Path(finops_dir)
        lines, problems = read_cost_export(d / "cost_export.csv")
        util = _json(d / "utilisation.json")["resources"]
        cfg = []
        for c in _json(d / "config_changes.json")["changes"]:
            note, flags = clean(c.get("note", ""))
            cfg.append({**c, "note": note, "flags": flags})
        register = _json(d / "savings_register.json")["recommendations"]
        changes = {}
        for c in client.get("change_request", "", CHANGE_FIELDS):
            text, flags = clean(c.get("short_description", ""))
            changes[c["number"]] = {**c, "short_description": text, "flags": flags}
        return cls(lines, util, cfg, register, changes, _json(Path(catalogue)), problems)


def _json(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("_meta", None)
    return data


def read_cost_export(path: Path) -> tuple[list[CostLine], list[str]]:
    """Parse the export. A malformed row is skipped and reported, never guessed at."""
    with Path(path).open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COST_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing column(s) {', '.join(missing)}")
        lines, problems = [], []
        for n, row in enumerate(reader, start=2):
            try:
                if row["BillingCurrency"] != "USD":
                    raise ValueError(f"currency {row['BillingCurrency']} (only USD is supported)")
                tags = json.loads(row["Tags"] or "{}")
                if not isinstance(tags, dict):
                    raise ValueError("Tags is not a JSON object")
                lines.append(CostLine(
                    month=row["BillingPeriodStart"][:7],
                    charge_start=date.fromisoformat(row["ChargePeriodStart"]),
                    charge_end=date.fromisoformat(row["ChargePeriodEnd"]),
                    charge_category=row["ChargeCategory"], category=row["ServiceCategory"],
                    line_item=row["ServiceName"], resource=row["ResourceId"], cost=float(row["BilledCost"]),
                    tags={str(k): str(v) for k, v in tags.items()}))
            except (ValueError, KeyError) as exc:
                problems.append(f"row {n}: {exc}")
    return lines, problems
