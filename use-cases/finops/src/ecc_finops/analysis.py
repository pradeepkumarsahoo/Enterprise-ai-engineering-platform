# Author: Pradeep Sahoo
"""Deterministic FinOps analysis (use case 5): allocation, monthly spend, anomalies, likely cause.

Everything here is plain code with thresholds from the product configuration. The model never
computes a figure, flags an anomaly, picks a cause or sets a confidence; it only explains them.

- Allocation: a cost line belongs to its `team` tag; failing that, to the owner of its `service`
  tag in the service catalogue; failing that, it is unallocated (and reported as such).
- Spend: net of credits, per team and billing month. The current month is partial; its forecast
  is the month-to-date figure scaled to the whole month (run-rate).
- Anomalies: per resource and line item, on usage only (credits excluded). A month is flagged
  when its cost is at least `z_threshold` standard deviations above the mean of the previous
  `baseline_months` months, AND the increase is at least `min_increase_usd` AND at least
  `min_increase_ratio` of the mean. The two floors stop steady growth and small, quiet series
  from being flagged. Months already flagged are left out of later baselines, so an anomaly that
  persists is not absorbed into "normal". Consecutive flagged months form one anomaly.
- Likely cause: a configuration change in the window before the anomaly whose attribute fits the
  cost category (retention for storage, log level for logging, ...), on the same resource, the
  same service or the same team. Confidence is a points rule, shown with its parts.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field, fields
from datetime import date, datetime, timedelta
from statistics import mean, stdev

from ecc_core.evidence import Evidence

from .sources import CostLine, FinOpsInputs

RULES_VERSION = "finops rules v1.0"
UNALLOCATED = "Unallocated"

# attribute words that can explain a cost increase in each FOCUS ServiceCategory
CATEGORY_TOKENS = {
    "Storage": {"retention", "backup", "snapshot", "snapshots", "lifecycle", "storage", "class", "replication",
                "versioning", "size"},
    "Compute": {"instance", "type", "node", "nodes", "count", "replicas", "autoscaling", "schedule", "size",
                "min", "desired"},
    "Databases": {"instance", "class", "iops", "replicas", "multi", "az", "storage", "size"},
    "Networking": {"egress", "nat", "region", "replication", "peering", "endpoint", "transfer"},
    "Management and Governance": {"log", "level", "logging", "retention", "sampling", "verbosity", "trace", "tracing"},
}


@dataclass(frozen=True)
class Rules:
    """Thresholds; set in [use_cases.finops.settings] of the product configuration."""
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


# ------------------------------------------------------------------ formatting (shared with reports)

def money(x: float) -> str:
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def month_label(m: str) -> str:
    return f"{calendar.month_abbr[int(m[5:])]} {m[:4]}"


def month_add(m: str, k: int) -> str:
    y, mo = int(m[:4]), int(m[5:]) - 1 + k
    return f"{y + mo // 12}-{mo % 12 + 1:02d}"


def days_in(m: str) -> int:
    return calendar.monthrange(int(m[:4]), int(m[5:]))[1]


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


class EvidenceBook:
    """Numbers evidence F1, F2, ... in the order it is added; one record per distinct summary."""

    def __init__(self):
        self.items: list[Evidence] = []
        self._by_summary: dict[str, str] = {}

    def add(self, kind: str, source: str, summary: str, flags: list[str] | None = None) -> str:
        if summary in self._by_summary:
            return self._by_summary[summary]
        eid = f"F{len(self.items) + 1}"
        self.items.append(Evidence(eid, kind, source, summary, list(flags or [])))
        self._by_summary[summary] = eid
        return eid


# ------------------------------------------------------------------ coverage and allocation

@dataclass
class Coverage:
    months: list[str]            # every month in the export, oldest first
    complete: list[str]
    partial: str | None          # the month still in progress, if any
    days_covered: int            # days of the partial month in the export
    partial_days: int            # days in the partial month


def coverage(lines: list[CostLine]) -> Coverage:
    months = sorted({l.month for l in lines})
    complete, partial, covered = [], None, 0
    for m in months:
        last = max(l.charge_end for l in lines if l.month == m)
        first_of_next = date.fromisoformat(f"{month_add(m, 1)}-01")
        if last >= first_of_next:
            complete.append(m)
        else:
            partial, covered = m, (last - date.fromisoformat(f"{m}-01")).days
    if partial and partial != months[-1]:
        raise ValueError(f"Only the latest month may be partial; {partial} is incomplete")
    return Coverage(months, complete, partial, covered, days_in(partial) if partial else 0)


def allocate(line: CostLine, inp: FinOpsInputs) -> tuple[str, str]:
    """(team, how): how is 'tag', 'catalogue' or 'none'."""
    if line.tags.get("team"):
        return line.tags["team"], "tag"
    owner = inp.owner_of_service(line.tags.get("service", ""))
    if owner:
        return owner, "catalogue"
    return UNALLOCATED, "none"


@dataclass
class Spend:
    months: list[str]
    partial: str | None
    by_team: dict[str, dict[str, float]]       # team -> month -> net cost (partial month = month to date)
    forecast: dict[str, float]                 # team -> partial month projected to the whole month
    allocation: dict[str, dict]                # resource -> {team, how}


def spend_by_team(inp: FinOpsInputs, cov: Coverage) -> Spend:
    by_team: dict[str, dict[str, float]] = {}
    alloc = {}
    for l in inp.lines:
        team, how = allocate(l, inp)
        alloc.setdefault(l.resource, {"team": team, "how": how})
        row = by_team.setdefault(team, {m: 0.0 for m in cov.months})
        row[l.month] += l.cost
    scale = cov.partial_days / cov.days_covered if cov.partial and cov.days_covered else 0
    forecast = {t: row[cov.partial] * scale for t, row in by_team.items()} if cov.partial else {}
    order = sorted((t for t in by_team if t != UNALLOCATED)) + ([UNALLOCATED] if UNALLOCATED in by_team else [])
    return Spend(cov.months, cov.partial, {t: by_team[t] for t in order}, {t: forecast.get(t, 0.0) for t in order}, alloc)


# ------------------------------------------------------------------ series and anomalies

@dataclass
class Series:
    resource: str
    line_item: str
    category: str
    team: str
    service: str
    env: str
    values: dict[str, float]          # month -> usage cost; the partial month is its run-rate
    month_to_date: float | None = None

    @property
    def key(self) -> str:
        return f"{self.resource} · {self.line_item}"


def build_series(inp: FinOpsInputs, cov: Coverage) -> list[Series]:
    out: dict[tuple, Series] = {}
    for l in inp.lines:
        if l.charge_category != "Usage":
            continue
        k = (l.resource, l.line_item)
        if k not in out:
            team, _ = allocate(l, inp)
            out[k] = Series(l.resource, l.line_item, l.category, team, l.tags.get("service", ""), l.tags.get("env", ""), {})
        out[k].values[l.month] = out[k].values.get(l.month, 0.0) + l.cost
    for s in out.values():
        if cov.partial and cov.partial in s.values and cov.days_covered:
            s.month_to_date = s.values[cov.partial]
            s.values[cov.partial] = s.month_to_date * cov.partial_days / cov.days_covered
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


@dataclass
class Cause:
    config: str | None                 # CFG id
    change: str | None                 # ServiceNow change number
    scope: str                         # resource | service | team | change-only
    points: int
    parts: list[str]                   # how the points were earned
    summary: str


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

    @property
    def latest(self) -> Point:
        return self.points[-1]

    def basis(self) -> Point:
        """The month a saving is estimated from: the latest complete flagged month, else the run-rate."""
        complete = [p for p in self.points if not p.provisional]
        return complete[-1] if complete else self.latest


def group(s: Series, points: list[Point], cov: Coverage) -> list[list[Point]]:
    runs, cur = [], []
    for p in points:
        if p.flagged and cur and cov.months.index(p.month) == cov.months.index(cur[-1].month) + 1:
            cur.append(p)
        elif p.flagged:
            if cur:
                runs.append(cur)
            cur = [p]
    if cur:
        runs.append(cur)
    return runs


def tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t}


def _sn_time(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def find_cause(s: Series, onset: str, inp: FinOpsInputs, r: Rules) -> Cause | None:
    """Best-scoring configuration change (or, failing that, change request) for an anomaly."""
    start = datetime.fromisoformat(f"{onset}-01") - timedelta(days=r.cause_lookback_days)
    end = datetime.fromisoformat(f"{month_add(onset, 1)}-01")
    words = CATEGORY_TOKENS.get(s.category, set())
    best = None
    for c in inp.config_changes:
        at = _sn_time(c["at"])
        if not (start <= at < end) or not (tokens(c["attribute"]) & words):
            continue
        if c["resource"] == s.resource:
            scope, extra = "resource", 1
        elif s.service and c["resource"] == s.service:
            scope, extra = "service", 1
        elif inp.owner_of_service(c["resource"]) == s.team or _team_of_resource(c["resource"], inp) == s.team:
            scope, extra = "team", 0
        else:
            continue
        parts = [f"attribute {c['attribute']} fits {s.category} cost (+2)"]
        parts.append(f"same {scope} (+1)" if extra else f"same team only (+0)")
        linked = c.get("change") if c.get("change") in inp.changes else None
        parts.append(f"made under change request {linked} (+1)" if linked else "no change request (+0)")
        pts = 2 + extra + (1 if linked else 0)
        summary = (f"{c['id']} on {c['at'][:10]}: {c['resource']} {c['attribute']} changed from {c['old']} to "
                   f"{c['new']} by {c['actor']}" + (f" under {linked}" if linked else ", with no change request"))
        cand = Cause(c["id"], linked, scope, pts, parts, summary)
        if best is None or (cand.points, at) > (best.points, best_at):
            best, best_at = cand, at
    if best:
        return best
    for n, c in sorted(inp.changes.items()):
        if c.get("cmdb_ci") not in {s.resource, s.service} or not c.get("start_date"):
            continue
        if start <= _sn_time(c["start_date"]) < end:
            return Cause(None, n, "change-only", 1, ["change request on the same resource or service, but no "
                                                    "configuration change recorded (+1)"],
                         f"{n} on {c['start_date'][:10]}: {c['short_description']}")
    return None


def _team_of_resource(resource: str, inp: FinOpsInputs) -> str | None:
    for l in inp.lines:
        if l.resource == resource:
            return allocate(l, inp)[0]
    return None


def confidence(points: int) -> str:
    return "high" if points >= 4 else "medium" if points >= 2 else "low" if points >= 1 else "not established"


def detect(series: list[Series], cov: Coverage, inp: FinOpsInputs, r: Rules) -> tuple[list[Anomaly], dict]:
    """Anomalies, and every judged point by series key (for evaluation and the report)."""
    anomalies, judged = [], {}
    for s in series:
        pts = judge(s, cov, r)
        judged[(s.resource, s.line_item)] = pts
        for run in group(s, pts, cov):
            cause = find_cause(s, run[0].month, inp, r)
            anomalies.append(Anomaly("", s.resource, s.line_item, s.category, s.team, s.service,
                                     [p.month for p in run], run, run[-1].provisional, cause,
                                     confidence(cause.points if cause else 0),
                                     history={m: round(v, 2) for m, v in s.values.items()}))
    anomalies.sort(key=lambda a: (-a.basis().increase, a.resource))
    for n, a in enumerate(anomalies, start=1):
        a.id = f"AN-{n}"
    return anomalies, judged
