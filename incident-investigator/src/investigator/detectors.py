"""Deterministic detectors: rule-based candidate causes with a prior score.

These run before any model call. They make the system useful and testable with
no model at all, give the model a structured starting point, and give
evaluation a baseline to compare the model against.
"""
from __future__ import annotations

from .evidence import Facts
from .models import Candidate

RELEVANT_CONFIG = ("pool", "timeout", "thread", "connection", "limit", "max", "memory", "replica")


def _has(logs, *needles) -> list[str]:
    return [eid for eid, text in logs if any(n in text.lower() for n in needles)]


def _metric(f: Facts, name: str):
    return f.metrics.get(name)


def _primary_up(f: Facts) -> list[str]:
    return [m.evidence_id for m in f.metrics.values()
            if m.direction in ("up", "rising_trend") and m.name in ("p95_latency_ms", "error_rate_pct", "queue_depth")]


def _rate_contradiction(f: Facts) -> list[str]:
    rate = _metric(f, "request_rate_rps")
    return [rate.evidence_id] if rate and rate.direction == "up" else []


def _rate_steady(f: Facts) -> list[str]:
    rate = _metric(f, "request_rate_rps")
    return [rate.evidence_id] if rate and rate.direction == "steady" else []


def config_change(f: Facts) -> Candidate | None:
    diffs = [(eid, c) for eid, c in f.config_diffs if any(k in c["key"].lower() for k in RELEVANT_CONFIG)]
    if not diffs or not f.deploys_near:
        return None
    eid, c = diffs[0]
    support = [eid, f.deploys_near[0][0]] + _primary_up(f)
    score = 0.55
    pool_logs = _has(f.logs, "connection is not available", "pool", "waiting for connection")
    if pool_logs:
        support += pool_logs
        score += 0.1
    pmax = _metric(f, "db_pool_max")
    if pmax and pmax.direction != "steady":
        support.append(pmax.evidence_id)
        score += 0.1
    if _rate_steady(f):
        support += _rate_steady(f)
        score += 0.05
    return Candidate("config_change", f"{c['key']} changed {c['from']} → {c['to']} in the deploy just before onset",
                     support, _rate_contradiction(f), min(score, 0.9),
                     [f"Whether other changes in {f.deploys_near[0][1]['version_to']} also contribute"])


def slow_query(f: Facts) -> Candidate | None:
    slow = _has(f.logs, "slow query")
    q = _metric(f, "db_query_p95_ms")
    if not slow and not (q and q.direction == "up"):
        return None
    support = slow + _primary_up(f)
    score = 0.5
    if q and q.direction == "up":
        support.append(q.evidence_id)
        score += 0.15
    query_deploys = [eid for eid, d in f.deploys_near if "query" in d.get("change_summary", "").lower()]
    if query_deploys:
        support += query_deploys
        score += 0.1
    support += _rate_steady(f)
    if _rate_steady(f):
        score += 0.05
    pool = _metric(f, "db_pool_active")
    if pool and pool.direction == "up":
        support.append(pool.evidence_id)
    return Candidate("slow_query", "A slower database query is holding connections", support,
                     _rate_contradiction(f), min(score, 0.9),
                     ["Query plan not available; whether an index is missing is unconfirmed"])


def traffic_spike(f: Facts) -> Candidate | None:
    rate = _metric(f, "request_rate_rps")
    if not rate or f.onset is None:
        return None
    if rate.direction != "up" or rate.ratio < 1.5:
        # keep as an explicitly ruled-down alternative
        return Candidate("traffic_spike", "Traffic increase overloaded the service", [], [rate.evidence_id], 0.08,
                         [])
    support = [rate.evidence_id] + _primary_up(f)
    score = 0.6
    cpu = _metric(f, "cpu_utilisation_pct")
    if cpu and cpu.direction == "up":
        support.append(cpu.evidence_id)
        score += 0.1
    source_logs = _has(f.logs, "max replicas", "campaign", "push notification")
    if source_logs:
        support += source_logs
        score += 0.1
    gaps = [] if _has(f.logs, "campaign") else ["Source of the extra traffic is not confirmed"]
    return Candidate("traffic_spike", f"Traffic rose ×{rate.ratio:.1f} and the service ran out of capacity",
                     support, [], min(score, 0.9), gaps + ["Whether autoscaling limits were reached on every region"])


def dependency_failure(f: Facts) -> Candidate | None:
    bad = [(eid, d) for eid, d in f.dependencies if d["status"].lower() not in ("ok", "operational", "healthy")]
    dep_metric = _metric(f, "dependency_error_rate_pct")
    dep_logs = _has(f.logs, "503", "service unavailable", "connection reset", "connection refused")
    if not bad and not (dep_metric and dep_metric.direction == "up"):
        return None
    support = [eid for eid, _ in bad] + dep_logs + _primary_up(f)
    score = 0.6
    if bad:
        score += 0.15
    if dep_metric and dep_metric.direction == "up":
        support.append(dep_metric.evidence_id)
        score += 0.1
    name = bad[0][1]["dependency"] if bad else "a downstream dependency"
    return Candidate("dependency_failure", f"{name} is failing and errors propagate to this service",
                     support, [], min(score, 0.9), [f"When {name} will fully recover"])


def resource_leak(f: Facts) -> Candidate | None:
    mem = _metric(f, "memory_mb")
    oom = _has(f.logs, "oomkilled", "out of memory")
    if not oom and not (mem and mem.direction == "rising_trend"):
        return None
    support = oom + _primary_up(f)
    score = 0.55
    if oom:
        score += 0.2
    if mem:
        support.append(mem.evidence_id)
        if mem.near_limit:
            score += 0.1
    support += _has(f.logs, "cache size", "no eviction", "heap")
    return Candidate("resource_leak", "Memory grows until pods are OOM-killed", support, [], min(score, 0.9),
                     ["Which object retains the memory; no heap profile was captured"])


def certificate_expiry(f: Facts) -> Candidate | None:
    certs = _has(f.logs, "x509", "certificate has expired", "certificate expired")
    if not certs:
        return None
    return Candidate("certificate_expiry", "An expired TLS certificate is failing handshakes",
                     certs + _primary_up(f), [], 0.9, ["Which other services use the same certificate"])


def bad_feature_flag(f: Facts) -> Candidate | None:
    if not f.flags_near:
        return None
    eid, flag = f.flags_near[0]
    tokens = [t for t in flag["flag"].lower().replace("-", "_").split("_") if len(t) >= 4]
    related = [lid for lid, text in f.logs if any(t in text.lower().replace("_", "") for t in tokens)]
    support = [eid] + related + _primary_up(f)
    score = 0.6 + (0.15 if related else 0) + (0.1 if _primary_up(f) else 0)
    return Candidate("bad_feature_flag", f"Flag {flag['flag']} turned on just before onset", support, [],
                     min(score, 0.9), ["Whether every cohort is affected or only the new code path"])


def code_change(f: Facts) -> Candidate | None:
    plain = [(eid, d) for eid, d in f.deploys_near if not d.get("config_diff")]
    if not plain:
        return None
    eid, d = plain[0]
    return Candidate("code_change", f"Code change in {d['version_to']} deployed just before onset",
                     [eid] + _primary_up(f), [], 0.35, [f"The diff of {d['version_to']} was not analysed"])


DETECTORS = (config_change, slow_query, traffic_spike, dependency_failure, resource_leak,
             certificate_expiry, bad_feature_flag, code_change)


def run_all(f: Facts) -> list[Candidate]:
    out = [c for c in (d(f) for d in DETECTORS) if c is not None]
    for c in out:   # de-duplicate evidence lists, keep order
        c.supporting = list(dict.fromkeys(c.supporting))
        c.contradicting = list(dict.fromkeys(c.contradicting))
    return sorted(out, key=lambda c: -c.score)
