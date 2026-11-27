# Author: Pradeep Sahoo
"""Read-only cloud resource inventory for the tagging agent (use case 5).

Every resource the company runs, with its tags exactly as they are in the cloud (keys keep their
case: `Team` and `team` are different tags to AWS). Three shapes are read:

| Shape | Detected by | Where it comes from |
|---|---|---|
| inventory | `resources` | the organisation's inventory export (here, synthetic): adds account, creator, creation date |
| aws-tagging | `ResourceTagMappingList` | `aws resourcegroupstaggingapi get-resources` |
| azure-graph | `data` | `az graph query -q "Resources | project id, name, type, subscriptionId, location, tags"` |

The two cloud shapes carry no creator, so the rules that use one simply score nothing; the report
says what could not be established. Nothing here writes to the cloud.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Resource:
    id: str                    # ARN or Azure resource id
    name: str
    provider: str              # aws | azure
    type: str
    account: str
    region: str
    tags: dict[str, str]       # as in the cloud, case kept
    created_by: str = ""
    created_on: str = ""


@dataclass
class Inventory:
    format: str
    resources: list[Resource]
    accounts: dict[str, dict] = field(default_factory=dict)   # account id -> {name, env, shared, owner_team}
    problems: list[str] = field(default_factory=list)


def _last(resource_id: str) -> str:
    t = resource_id.rstrip("/")
    for sep in ("/", ":"):
        if sep in t:
            t = t.rsplit(sep, 1)[1]
    return t


def read_inventory(path: Path) -> Inventory:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("_meta", None)
    if "resources" in data:
        return _native(data)
    if "ResourceTagMappingList" in data:
        return _aws(data)
    if "data" in data:
        return _azure(data)
    raise ValueError(f"{path}: not an inventory, AWS get-resources or Azure Resource Graph output")


def _native(data: dict) -> Inventory:
    out, problems = [], []
    for n, r in enumerate(data["resources"], start=1):
        try:
            out.append(Resource(r["id"], r.get("name") or _last(r["id"]), r.get("provider", "aws"), r.get("type", ""),
                                str(r.get("account", "")), r.get("region", ""), _str_tags(r.get("tags") or {}),
                                r.get("created_by", ""), r.get("created_on", "")))
        except (KeyError, TypeError, ValueError) as exc:
            problems.append(f"resource {n}: {exc}")
    return Inventory("inventory", out, data.get("accounts", {}), problems)


def _aws(data: dict) -> Inventory:
    out, problems = [], []
    for n, r in enumerate(data["ResourceTagMappingList"], start=1):
        try:
            arn = r["ResourceARN"]
            parts = arn.split(":")
            tags = {t["Key"]: t["Value"] for t in r.get("Tags", [])}
            out.append(Resource(arn, tags.get("Name") or _last(arn), "aws", f"{parts[2]}:{parts[5].split('/')[0]}",
                                parts[4], parts[3], _str_tags(tags)))
        except (KeyError, IndexError, TypeError) as exc:
            problems.append(f"resource {n}: {exc}")
    return Inventory("aws-tagging", out, {}, problems)


def _azure(data: dict) -> Inventory:
    out, problems = [], []
    for n, r in enumerate(data["data"], start=1):
        try:
            out.append(Resource(r["id"], r.get("name") or _last(r["id"]), "azure", r.get("type", ""),
                                r.get("subscriptionId", ""), r.get("location", ""), _str_tags(r.get("tags") or {})))
        except (KeyError, TypeError) as exc:
            problems.append(f"resource {n}: {exc}")
    return Inventory("azure-graph", out, {}, problems)


def _str_tags(tags: dict) -> dict[str, str]:
    if not isinstance(tags, dict):
        raise ValueError("tags is not an object")
    return {str(k): str(v) for k, v in tags.items()}
