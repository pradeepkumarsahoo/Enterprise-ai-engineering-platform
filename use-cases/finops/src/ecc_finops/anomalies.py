# Author: Pradeep Sahoo
"""Statistical anomalies in monthly cost (use case 5).

Per resource and line item, on usage only (credits excluded). A month is flagged when its cost is
at least `z_threshold` standard deviations above the mean of the previous `baseline_months`
months, AND the increase is at least `min_increase_usd` AND at least `min_increase_ratio` of the
mean. The two floors stop steady growth and small, quiet series from being flagged. Months
already flagged are left out of later baselines, so an anomaly that persists is not absorbed
into "normal". Consecutive flagged months form one anomaly. The model never flags anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Callable

from .causes import Cause, confidence
from .rules import Rules
from .sources import FinOpsInputs
from .spend import Coverage, allocate


@dataclass
class Series:
    resource: str
    line_item: str
    category: str
    team: str
    service: str
    env: str
    values: dict[str, float]          # month -> usage cost; the partial month is its run-rate


def build_series(inp: FinOpsInputs, cov: Coverage) -> list[Series]:
    out: dict[tuple, Series] = {}
    for l in inp.lines:
        if l.charge_category != "Usage":
            continue
        k = (l.resource, l.line_item)
        if k not in out:
            out[k] = Series(l.resource, l.line_item, l.category, allocate(l, inp)[0], l.tags.get("service", ""),
                            l.tags.get("env", ""), {})
        out[k].values[l.month] = out[k].values.get(l.month, 0.0) + l.cost
    if cov.partial and cov.days_covered:
        for s in out.values():
            if cov.partial in s.values:
                s.values[cov.partial] = s.values[cov.partial] * cov.partial_days / cov.days_covered
    return sorted(out.values(), key=lambda s: (s.team, s.resource, s.line_item))


@dataclass
class Point:
    month: str
    value: float
    mean: float
    sd: float
    z: float
    increase: float
    ratio: float
    baseline: list[str]
    flagged: bool
    provisional: bool


def judge(s: Series, cov: Coverage, r: Rules) -> list[Point]:
    """Every month that has enough history, judged in order; flagged months leave later baselines."""
    points, flagged = [], set()
    for i, m in enumerate(cov.months):
        if m not in s.values:
            continue
        window = [x for x in cov.months[max(0, i - r.baseline_months):i] if x in s.values and x not in flagged]
        if len(window) < r.min_baseline_months:
            continue
        base = [s.values[x] for x in window]
        mu = mean(base)
        sd = max(stdev(base) if len(base) > 1 else 0.0, abs(mu) * r.stdev_floor_ratio, 1e-9)
        x = s.values[m]
        inc = x - mu
        ratio = inc / mu if mu else 0.0
        z = inc / sd
        hit = z >= r.z_threshold and inc >= r.min_increase_usd and ratio >= r.min_increase_ratio
        if hit:
            flagged.add(m)
        points.append(Point(m, x, mu, sd, z, inc, ratio, window, hit, m == cov.partial))
    return points


def runs(points: list[Point], cov: Coverage) -> list[list[Point]]:
    """Flagged points grouped into runs of consecutive months."""
    out: list[list[Point]] = []
    for p in (p for p in points if p.flagged):
        if out and cov.months.index(p.month) == cov.months.index(out[-1][-1].month) + 1:
            out[-1].append(p)
        else:
            out.append([p])
    return out


@dataclass
class Anomaly:
    id: str
    resource: str
    line_item: str
    category: str
    team: str
    service: str
    months: list[str]
    points: list[Point]                # the flagged months
    provisional: bool                  # the latest flagged month is the partial month
    cause: Cause | None
    confidence: str                    # high | medium | low | not established
    evidence: list[str] = field(default_factory=list)
    could_not_establish: list[str] = field(default_factory=list)
    history: dict[str, float] = field(default_factory=dict)   # the whole series, for the report

    @property
    def onset(self) -> Point:
        return self.points[0]

    def basis(self) -> Point:
        """The month a saving is estimated from: the latest complete flagged month, else the run-rate."""
        complete = [p for p in self.points if not p.provisional]
        return complete[-1] if complete else self.points[-1]


def detect(series: list[Series], cov: Coverage, r: Rules,
           cause_of: Callable[[Series, str], Cause | None]) -> tuple[list[Anomaly], dict]:
    """Anomalies (largest increase first, numbered AN-1, AN-2, ...) and every judged point by series."""
    anomalies, judged = [], {}
    for s in series:
        pts = judge(s, cov, r)
        judged[(s.resource, s.line_item)] = pts
        for run in runs(pts, cov):
            cause = cause_of(s, run[0].month)
            anomalies.append(Anomaly("", s.resource, s.line_item, s.category, s.team, s.service,
                                     [p.month for p in run], run, run[-1].provisional, cause,
                                     confidence(cause.points if cause else 0),
                                     history={m: round(v, 2) for m, v in s.values.items()}))
    anomalies.sort(key=lambda a: (-a.basis().increase, a.resource))
    for n, a in enumerate(anomalies, start=1):
        a.id = f"AN-{n}"
    return anomalies, judged
