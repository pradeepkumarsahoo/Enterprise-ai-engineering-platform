# Author: Pradeep Sahoo
"""FinOps thresholds (use case 5), set in [use_cases.finops.settings] of the product configuration.

Who may approve a recommendation is governance and lives in `ledger.py`, not here.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

RULES_VERSION = "finops rules v1.0"


@dataclass(frozen=True)
class Rules:
    baseline_months: int = 6                  # trailing months the mean and deviation come from
    min_baseline_months: int = 4              # fewer usable months than this: the month is not judged
    z_threshold: float = 3.0
    stdev_floor_ratio: float = 0.02           # deviation is at least this share of the mean (flat series)
    min_increase_usd: float = 1000.0
    min_increase_ratio: float = 0.10
    cause_lookback_days: int = 14             # a cause may start this long before the anomaly's month
    rightsize_cpu_p95_max: float = 25.0
    rightsize_mem_p95_max: float = 40.0
    rightsize_saving_ratio: float = 0.5       # one instance size down halves the price in most families
    office_hours_per_week: int = 65           # 07:00-20:00, Monday to Friday
    always_on_hours_min: int = 160            # running this many hours a week counts as always on
    non_prod_envs: str = "sandbox,staging,dev"
    idle_days: int = 30
    realised_baseline_months: int = 3         # complete months before implementation, for realised savings
    rejected_cooldown_days: int = 180         # a rejected recommendation is not proposed again for this long
    as_of: str = "2026-11-17"                 # "now" for the synthetic data; production passes today's date

    @classmethod
    def from_settings(cls, settings: dict) -> "Rules":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in settings.items() if k in known})

    @property
    def non_prod(self) -> set[str]:
        return {e.strip() for e in self.non_prod_envs.split(",") if e.strip()}
