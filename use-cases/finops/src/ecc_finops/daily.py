# Author: Pradeep Sahoo
"""Daily step-change alerts (use case 5): a cost jump caught in days, not at month end.

Per resource and line item, on usage only, from an export with daily (or finer) charge periods.
A day is flagged when its cost is at least `daily_z_threshold` standard deviations above the mean
of the previous `daily_baseline_days` days, AND the increase is at least `daily_min_increase_usd`
AND at least `daily_min_increase_ratio` of that mean. An alert is raised once `daily_confirm_days`
consecutive days are flagged, so a one-day blip is not an alert.

The daily baseline rolls on: flagged days stay in it, so it absorbs a new level within days and
the alert ends. That is deliberate. The daily rule is for speed (is something jumping now?); the
monthly rule in `anomalies.py`, which leaves flagged months out of its baseline, is for
persistence, savings and causes. A daily alert links to the monthly anomaly on the same series
and month when there is one; otherwise it is an early signal, reported without a recommendation.
The model never flags anything.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, stdev

from .rules import Rules
from .sources import FinOpsInputs


@dataclass
class Day:
    day: str
    value: float
    mean: float
    sd: float
    z: float
    increase: float
    ratio: float
    flagged: bool


@dataclass
class DailyAlert:
    id: str
    resource: str
    line_item: str
    start: str                    # first flagged day
    confirmed: str                # the day the alert was raised (start + confirm days - 1)
    days: list[Day]               # the flagged run
    anomaly: str | None = None    # the monthly anomaly it belongs to, if any
    month_closes: str = ""        # the last day of the start month: when the monthly rule can judge it
    evidence: list[str] = field(default_factory=list)

    @property
    def first(self) -> Day:
        return self.days[0]


def daily_series(inp: FinOpsInputs) -> tuple[dict[tuple, dict[date, float]], bool]:
    """Usage cost per (resource, line item) per day, and whether the export is daily at all.

    A line spanning more than one day (a monthly export) is not spread over days: guessing a
    daily shape would invent data. When any usage line is longer than a day there is no daily view.
    """
    usage = [l for l in inp.lines if l.charge_category == "Usage"]
    if not usage or any(l.days > 1 for l in usage):
        return {}, False
    out: dict[tuple, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for l in usage:
        out[(l.resource, l.line_item)][l.charge_start] += l.cost
    return {k: dict(v) for k, v in out.items()}, True


def judge_days(values: dict[date, float], r: Rules) -> list[Day]:
    days = sorted(values)
    out = []
    for d in days:
        window = [values[x] for x in (d - timedelta(days=k) for k in range(1, r.daily_baseline_days + 1))
                  if x in values]
        if len(window) < r.daily_min_baseline_days:
            continue
        mu = mean(window)
        sd = max(stdev(window), abs(mu) * 0.02, 1e-9)
        x = values[d]
        inc = x - mu
        ratio = inc / mu if mu else 0.0
        z = inc / sd
        hit = z >= r.daily_z_threshold and inc >= r.daily_min_increase_usd and ratio >= r.daily_min_increase_ratio
        out.append(Day(d.isoformat(), round(x, 2), round(mu, 2), round(sd, 2), round(z, 2), round(inc, 2),
                       round(ratio, 4), hit))
    return out


def detect_daily(inp: FinOpsInputs, r: Rules) -> tuple[list[DailyAlert], bool]:
    """Alerts in order of their start day (numbered DA-1, DA-2, ...), and whether a daily view exists."""
    series, ok = daily_series(inp)
    alerts = []
    for (res, item), values in sorted(series.items()):
        run: list[Day] = []
        for d in judge_days(values, r) + [None]:
            if d is not None and d.flagged and (not run or date.fromisoformat(d.day)
                                                == date.fromisoformat(run[-1].day) + timedelta(days=1)):
                run.append(d)
                continue
            if len(run) >= r.daily_confirm_days:
                start = date.fromisoformat(run[0].day)
                closes = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                alerts.append(DailyAlert("", res, item, run[0].day, run[r.daily_confirm_days - 1].day, run,
                                         month_closes=closes.isoformat()))
            run = [d] if d is not None and d.flagged else []
    alerts.sort(key=lambda a: (a.start, a.resource, a.line_item))
    for n, a in enumerate(alerts, start=1):
        a.id = f"DA-{n}"
    return alerts, ok


def link(alerts: list[DailyAlert], anomalies) -> None:
    """Attach each alert to the monthly anomaly on the same series whose months include its start."""
    for a in alerts:
        hit = next((x for x in anomalies if x.resource == a.resource and x.line_item == a.line_item
                    and a.start[:7] in x.months), None)
        a.anomaly = hit.id if hit else None
