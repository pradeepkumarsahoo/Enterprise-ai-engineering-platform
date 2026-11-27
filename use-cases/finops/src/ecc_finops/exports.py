# Author: Pradeep Sahoo
"""Read-only cost export adapters for use case 5: FOCUS, AWS CUR 2.0 and Azure cost details.

Every format is normalised into the same `CostLine`, so nothing after this module knows which
cloud the bill came from. The format is detected from the header (or named in the configuration).

Two costs are kept per line:
- `billed`: what the invoice says for that line (an upfront reservation is billed in full on the
  day it is bought; usage it covers is billed at 0). None when the export does not carry it.
- `cost`: the effective (amortised) cost: a commitment's price spread over the usage it covers,
  plus the unused part of the commitment as its own line. Spend, anomalies and savings all use
  this, so a purchase does not look like a spike and covered usage does not look free.

| Format | Effective cost from | Billed cost from |
|---|---|---|
| FOCUS 1.x (`BilledCost`) | `EffectiveCost` (falls back to `BilledCost`) | `BilledCost` |
| AWS CUR 2.0 (`line_item_unblended_cost`) | reservation / savings plan effective cost; unused commitment from the fee lines | `line_item_unblended_cost` |
| Azure cost details, amortised (`CostInBillingCurrency`) | `CostInBillingCurrency` | not in this export (None) |

A row that cannot be read is skipped and reported with its line number, never guessed at.
Only USD is supported: converting currencies needs a rate source this pilot does not have.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

FORMATS = ("focus", "aws-cur", "azure")
FOCUS_COLUMNS = ("BillingPeriodStart", "ChargePeriodStart", "ChargePeriodEnd", "ChargeCategory", "ServiceCategory",
                 "ServiceName", "ResourceId", "BilledCost", "BillingCurrency", "Tags")
CUR_COLUMNS = ("bill_billing_period_start_date", "line_item_usage_start_date", "line_item_usage_end_date",
               "line_item_line_item_type", "line_item_product_code", "line_item_usage_type", "line_item_resource_id",
               "line_item_unblended_cost", "line_item_currency_code")
AZURE_COLUMNS = ("BillingPeriodStartDate", "Date", "ChargeType", "MeterCategory", "ResourceId",
                 "CostInBillingCurrency", "Tags")
SIGNATURE = {"focus": "BilledCost", "aws-cur": "line_item_unblended_cost", "azure": "CostInBillingCurrency"}
REQUIRED = {"focus": FOCUS_COLUMNS, "aws-cur": CUR_COLUMNS, "azure": AZURE_COLUMNS}


@dataclass
class CostLine:
    month: str                 # YYYY-MM, the billing period
    charge_start: date
    charge_end: date           # exclusive
    charge_category: str       # FOCUS ChargeCategory: Usage, Purchase, Credit, Tax, Adjustment
    category: str              # FOCUS ServiceCategory: Compute, Storage, ...
    line_item: str             # what is charged: Kubernetes nodes, Database snapshots, ...
    resource: str
    cost: float                # effective (amortised) cost
    tags: dict
    billed: float | None = None
    commitment: str = ""       # reservation or savings plan id, when the line is covered by or is one
    commitment_status: str = ""   # Used | Unused | "" (FOCUS CommitmentDiscountStatus)
    frequency: str = ""        # One-Time | Recurring | Usage-Based

    @property
    def days(self) -> int:
        return (self.charge_end - self.charge_start).days


@dataclass
class ExportRead:
    format: str
    lines: list[CostLine]
    problems: list[str] = field(default_factory=list)
    has_billed: bool = True
    has_effective: bool = True


# ------------------------------------------------------------------ helpers

def _day(text: str) -> date:
    """2026-10-01, 2026-10-01T00:00:00Z, 2026-10-01 00:00:00 or 10/01/2026 (Azure, US order)."""
    t = text.strip()
    if "/" in t:
        m, d, y = t.split(" ")[0].split("/")
        return date(int(y), int(m), int(d))
    return date.fromisoformat(t[:10])


def _end_day(text: str) -> date:
    """An exclusive end: 2026-10-01T13:00:00Z ends during Oct 1, so the charge covers up to Oct 2."""
    t = text.strip()
    d = _day(t)
    clock = t[11:19] if len(t) > 10 and t[10] in "T " else ""
    return d + timedelta(days=1) if clock and clock.strip("0:") else d


def _money(text: str) -> float:
    return float(text) if text and text.strip() else 0.0


def _tags(text: str) -> dict:
    """JSON object; Azure older exports drop the braces ('"team": "Loyalty","env": "prod"')."""
    t = (text or "").strip()
    if not t:
        return {}
    if not t.startswith("{"):
        t = "{" + t + "}"
    tags = json.loads(t)
    if not isinstance(tags, dict):
        raise ValueError("Tags is not a JSON object")
    return {str(k).lower(): str(v) for k, v in tags.items()}


def _name(resource_id: str) -> str:
    """The last segment of an ARN or Azure resource path: arn:...:db:loyalty-ledger-db -> loyalty-ledger-db."""
    t = (resource_id or "").strip().rstrip("/")
    for sep in ("/", ":"):
        if sep in t:
            t = t.rsplit(sep, 1)[1]
    return t


def _usd(code: str) -> None:
    if code != "USD":
        raise ValueError(f"currency {code} (only USD is supported)")


def detect(header: list[str]) -> str:
    found = [f for f, col in SIGNATURE.items() if col in header]
    if len(found) != 1:
        raise ValueError("Cannot tell the cost export format from its header "
                         f"(expected one of: {', '.join(f'{c} ({f})' for f, c in SIGNATURE.items())})")
    return found[0]


def read_export(path: Path, fmt: str = "auto") -> ExportRead:
    """Read a cost export. fmt: 'auto' (from the header) or one of FORMATS."""
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        fmt = detect(header) if fmt == "auto" else fmt
        if fmt not in FORMATS:
            raise ValueError(f"Unknown cost export format '{fmt}' (use auto, {', '.join(FORMATS)})")
        missing = [c for c in REQUIRED[fmt] if c not in header]
        if missing:
            raise ValueError(f"{path}: missing column(s) {', '.join(missing)}")
        parse = {"focus": _focus, "aws-cur": _cur, "azure": _azure}[fmt]
        out = ExportRead(fmt, [], has_billed=fmt != "azure",
                         has_effective=fmt != "focus" or "EffectiveCost" in header)
        for n, row in enumerate(reader, start=2):
            try:
                out.lines += parse(row)
            except (ValueError, KeyError) as exc:
                out.problems.append(f"row {n}: {exc}")
    return out


# ------------------------------------------------------------------ FOCUS

def _focus(row: dict) -> list[CostLine]:
    _usd(row["BillingCurrency"])
    billed = _money(row["BilledCost"])
    eff = row.get("EffectiveCost")
    return [CostLine(
        month=row["BillingPeriodStart"][:7], charge_start=_day(row["ChargePeriodStart"]),
        charge_end=_end_day(row["ChargePeriodEnd"]), charge_category=row["ChargeCategory"],
        category=row["ServiceCategory"], line_item=row["ServiceName"], resource=row["ResourceId"],
        cost=_money(eff) if eff not in (None, "") else billed, tags=_tags(row["Tags"]), billed=billed,
        commitment=row.get("CommitmentDiscountId", "") or "", commitment_status=row.get("CommitmentDiscountStatus", "") or "",
        frequency=row.get("ChargeFrequency", "") or "")]


# ------------------------------------------------------------------ AWS CUR 2.0

CUR_PRODUCTS = {   # line_item_product_code -> (FOCUS ServiceCategory, line item)
    "AmazonEC2": ("Compute", "EC2 instances"), "AmazonEKS": ("Compute", "Kubernetes control plane"),
    "AmazonRDS": ("Databases", "Managed database"), "AmazonS3": ("Storage", "Object storage"),
    "AmazonCloudWatch": ("Management and Governance", "Log analytics"), "AWSDataTransfer": ("Networking", "Data transfer"),
    "AmazonVPC": ("Networking", "VPC"), "ComputeSavingsPlans": ("Compute", "Savings plan"),
}
CUR_USAGE_TYPES = (   # a usage-type fragment refines the product: (fragment, category, line item)
    ("BackupUsage", "Storage", "Database snapshots"), ("SnapshotUsage", "Storage", "Snapshots"),
    ("VolumeUsage", "Storage", "Block storage volumes"), ("NatGateway", "Networking", "NAT gateway"),
    ("DataTransfer", "Networking", "Data transfer"), ("DataProcessing-Bytes", "Management and Governance", "Log analytics"),
)
CUR_TYPES = {   # line_item_line_item_type -> FOCUS ChargeCategory
    "Usage": "Usage", "DiscountedUsage": "Usage", "SavingsPlanCoveredUsage": "Usage", "SavingsPlanNegation": "Usage",
    "RIFee": "Purchase", "SavingsPlanRecurringFee": "Purchase", "Fee": "Purchase", "SavingsPlanUpfrontFee": "Purchase",
    "Credit": "Credit", "Refund": "Credit", "BundledDiscount": "Credit", "Tax": "Tax",
}


def _cur_tags(row: dict) -> dict:
    """CUR 2.0 `resource_tags` map ({"user_team": "Loyalty"}), or legacy resource_tags_user_<key> columns."""
    tags = {}
    for k, v in _tags(row.get("resource_tags", "")).items():
        tags[k.removeprefix("user_").removeprefix("user:")] = v
    for col, v in row.items():
        if col and col.startswith("resource_tags_user_") and v:
            tags[col.removeprefix("resource_tags_user_")] = v
    return tags


def _cur(row: dict) -> list[CostLine]:
    _usd(row["line_item_currency_code"])
    kind = row["line_item_line_item_type"]
    if kind not in CUR_TYPES:
        raise ValueError(f"line item type {kind} is not supported")
    category, item = CUR_PRODUCTS.get(row["line_item_product_code"], ("Other", row["line_item_product_code"]))
    for fragment, cat, name in CUR_USAGE_TYPES:
        if fragment.lower() in row["line_item_usage_type"].lower():
            category, item = cat, name
            break
    tags = _cur_tags(row)
    billed = _money(row["line_item_unblended_cost"])
    ri, sp = _name(row.get("reservation_reservation_a_r_n", "")), _name(row.get("savings_plan_savings_plan_a_r_n", ""))
    base = dict(month=row["bill_billing_period_start_date"][:7], charge_start=_day(row["line_item_usage_start_date"]),
                charge_end=_end_day(row["line_item_usage_end_date"]), category=category, line_item=item, tags=tags)
    resource = tags.get("name") or _name(row["line_item_resource_id"])
    if kind == "DiscountedUsage":
        return [CostLine(**base, charge_category="Usage", resource=resource, billed=billed,
                         cost=_money(row.get("reservation_effective_cost", "")), commitment=ri,
                         commitment_status="Used", frequency="Usage-Based")]
    if kind == "SavingsPlanCoveredUsage":
        return [CostLine(**base, charge_category="Usage", resource=resource, billed=billed,
                         cost=_money(row.get("savings_plan_savings_plan_effective_cost", "")), commitment=sp,
                         commitment_status="Used", frequency="Usage-Based")]
    if kind == "SavingsPlanNegation":   # cancels the on-demand amount of covered usage on the invoice
        return [CostLine(**base, charge_category="Usage", resource=resource, billed=billed, cost=0.0, commitment=sp,
                         commitment_status="Used", frequency="Usage-Based")]
    if kind in ("RIFee", "SavingsPlanRecurringFee"):
        cid = ri if kind == "RIFee" else sp
        unused = (_money(row.get("reservation_unused_amortized_upfront_fee_for_billing_period", ""))
                  + _money(row.get("reservation_unused_recurring_fee", ""))) if kind == "RIFee" else \
            max(_money(row.get("savings_plan_total_commitment_to_date", ""))
                - _money(row.get("savings_plan_used_commitment", "")), 0.0)
        out = [CostLine(**{**base, "line_item": "Commitment fee"}, charge_category="Purchase", resource=cid,
                        billed=billed, cost=0.0, commitment=cid, frequency="Recurring")]
        if unused:
            kind_name = "Reserved instance" if kind == "RIFee" else "Savings plan"
            out.append(CostLine(**{**base, "line_item": f"{kind_name} (unused)"}, charge_category="Usage",
                                resource=cid, billed=0.0, cost=unused, commitment=cid, commitment_status="Unused",
                                frequency="Usage-Based"))
        return out
    if kind in ("Fee", "SavingsPlanUpfrontFee"):   # upfront payment: billed now, amortised through covered usage
        cid = ri or sp or resource
        return [CostLine(**{**base, "line_item": "Commitment purchase"}, charge_category="Purchase", resource=cid,
                         billed=billed, cost=0.0, commitment=cid if (ri or sp) else "", frequency="One-Time")]
    return [CostLine(**base, charge_category=CUR_TYPES[kind], resource=resource, billed=billed, cost=billed,
                     frequency="Usage-Based")]


# ------------------------------------------------------------------ Azure cost details (amortised)

AZURE_METERS = {   # MeterCategory -> FOCUS ServiceCategory
    "Virtual Machines": "Compute", "Azure Kubernetes Service": "Compute", "Container Instances": "Compute",
    "Storage": "Storage", "Bandwidth": "Networking", "Virtual Network": "Networking", "NAT Gateway": "Networking",
    "SQL Database": "Databases", "Azure Database for PostgreSQL": "Databases", "Azure Database for MySQL": "Databases",
    "Azure Cosmos DB": "Databases", "Log Analytics": "Management and Governance", "Azure Monitor": "Management and Governance",
}
AZURE_TYPES = {"Usage": "Usage", "UnusedReservation": "Usage", "UnusedSavingsPlan": "Usage", "Purchase": "Purchase",
               "Refund": "Credit", "Tax": "Tax", "RoundingAdjustment": "Adjustment"}


def _azure(row: dict) -> list[CostLine]:
    _usd(row.get("BillingCurrency") or row.get("BillingCurrencyCode") or "")
    kind = row["ChargeType"]
    if kind not in AZURE_TYPES:
        raise ValueError(f"charge type {kind} is not supported")
    sub = row.get("MeterSubCategory", "") or ""
    category = AZURE_METERS.get(row["MeterCategory"], "Other")
    if any(w in sub.lower() for w in ("snapshot", "backup")):
        category = "Storage"
    day = _day(row["Date"])
    benefit = _name(row.get("BenefitId") or row.get("ReservationId") or "")
    unused = kind in ("UnusedReservation", "UnusedSavingsPlan")
    if unused:
        item = "Reserved instance (unused)" if kind == "UnusedReservation" else "Savings plan (unused)"
    else:
        item = sub or row["MeterCategory"]
    covered = kind == "Usage" and (row.get("PricingModel", "") or "") in ("Reservation", "SavingsPlan")
    resource = row.get("ResourceName") or _name(row["ResourceId"])
    return [CostLine(
        month=_day(row["BillingPeriodStartDate"]).isoformat()[:7], charge_start=day, charge_end=day + timedelta(days=1),
        charge_category=AZURE_TYPES[kind], category=category, line_item=item,
        resource=benefit if unused or (kind == "Purchase" and not resource) else resource,
        cost=_money(row["CostInBillingCurrency"]), tags=_tags(row["Tags"]), billed=None,
        commitment=benefit if (unused or covered or kind == "Purchase") else "",
        commitment_status="Unused" if unused else ("Used" if covered else ""),
        frequency={"Purchase": "One-Time"}.get(kind, "Usage-Based"))]
