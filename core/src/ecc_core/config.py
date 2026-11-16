# Author: Pradeep Sahoo
"""Product configuration: one TOML file for the whole Engineering Command Centre.

    [product]     name, environment, root, runs_dir
    [model]       default provider and Claude settings
    [sources]     read-only sources shared by several use cases (e.g. runbooks)
    [connectors.servicenow]   read-only ServiceNow instance: url, transport (fixture | http), limits
    [use_cases.<key>]
        enabled, module           which use cases are switched on, and the package that implements each
        [.paths]                  that use case's data locations
        [.settings]               its thresholds (defaults live in the use case's plugin)
        [.gates]                  its pilot pass/fail thresholds

Where the file is found: --config, else $ECC_CONFIG, else config/product.toml in
the current directory or the nearest parent directory that has one.
Precedence for a value: command-line flag > environment variable > this file >
the default in code. Relative paths are resolved against [product].root, which
is itself relative to the config file.

Validation is strict: an unknown key or a value of the wrong type is an error,
so a typo cannot silently fall back to a default.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .llm import ModelSettings
from .servicenow import SCHEMA as SERVICENOW_SCHEMA, TRANSPORTS as SERVICENOW_TRANSPORTS, ServiceNowSettings

PROVIDERS = ("mock", "claude")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
ENV_CONFIG, ENV_PROVIDER, ENV_MODEL = "ECC_CONFIG", "ECC_PROVIDER", "ECC_MODEL"

_PRODUCT = {"name": str, "environment": str, "root": str, "runs_dir": str}
_MODEL = {"provider": str, "claude_model": str, "effort": str, "max_tokens": int, "fallbacks": str}
_USE_CASE = {"enabled": bool, "module": str, "paths": dict, "settings": dict, "gates": dict}


class ConfigError(ValueError):
    def __init__(self, problems: list[str], path: Path | None = None):
        self.problems = problems
        where = f"{path}: " if path else ""
        super().__init__(where + "; ".join(problems))


@dataclass
class UseCaseConfig:
    key: str
    enabled: bool
    module: str
    paths: dict[str, Path]
    settings: dict
    gates: dict


@dataclass
class Config:
    path: Path
    root: Path
    name: str
    environment: str
    runs_dir: Path
    provider: str
    model: ModelSettings
    sources: dict[str, Path]
    use_cases: dict[str, UseCaseConfig] = field(default_factory=dict)
    servicenow: ServiceNowSettings | None = None

    def enabled(self) -> list[UseCaseConfig]:
        return [u for u in self.use_cases.values() if u.enabled]


def find_config(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    if os.environ.get(ENV_CONFIG):
        return Path(os.environ[ENV_CONFIG]).resolve()
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        candidate = d / "config" / "product.toml"
        if candidate.exists():
            return candidate
    raise ConfigError(["no config/product.toml found here or in a parent directory; pass --config or set "
                       f"{ENV_CONFIG}"])


def _check(table: dict, schema: dict, where: str, problems: list[str]) -> None:
    for k, v in table.items():
        if k not in schema:
            problems.append(f"{where}: unknown key '{k}'")
        elif not isinstance(v, schema[k]) or (schema[k] is int and isinstance(v, bool)):
            problems.append(f"{where}.{k}: expected {schema[k].__name__}, got {type(v).__name__}")


def load_config(path: str | Path | None = None) -> Config:
    path = find_config(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError([str(exc)], path) from exc

    problems: list[str] = []
    for k in raw:
        if k not in ("product", "model", "sources", "connectors", "use_cases"):
            problems.append(f"unknown section [{k}]")
    product, model = raw.get("product", {}), raw.get("model", {})
    _check(product, _PRODUCT, "[product]", problems)
    _check(model, _MODEL, "[model]", problems)
    root = (path.parent / product.get("root", "..")).resolve()

    provider = os.environ.get(ENV_PROVIDER) or model.get("provider", "mock")
    if provider not in PROVIDERS:
        problems.append(f"[model].provider: '{provider}' is not one of {', '.join(PROVIDERS)}")
    effort = model.get("effort", "high")
    if effort not in EFFORTS:
        problems.append(f"[model].effort: '{effort}' is not one of {', '.join(EFFORTS)}")
    settings = ModelSettings(model=os.environ.get(ENV_MODEL) or model.get("claude_model", ModelSettings.model),
                             effort=effort, max_tokens=model.get("max_tokens", ModelSettings.max_tokens),
                             fallbacks=model.get("fallbacks", ModelSettings.fallbacks))

    sources = {}
    for k, v in raw.get("sources", {}).items():
        if isinstance(v, str):
            sources[k] = (root / v).resolve()
        else:
            problems.append(f"[sources].{k}: expected a path string")

    servicenow = None
    for name, table in raw.get("connectors", {}).items():
        if name != "servicenow":
            problems.append(f"[connectors.{name}]: unknown connector (known: servicenow)"); continue
        _check(table, SERVICENOW_SCHEMA, "[connectors.servicenow]", problems)
        if table.get("transport", "fixture") not in SERVICENOW_TRANSPORTS:
            problems.append(f"[connectors.servicenow].transport: not one of {', '.join(SERVICENOW_TRANSPORTS)}")
        if not table.get("url", "").startswith("https://"):
            problems.append("[connectors.servicenow].url: must start with https://")
        if table.get("transport", "fixture") == "fixture" and "fixture_dir" not in table:
            problems.append("[connectors.servicenow].fixture_dir: required when transport = \"fixture\"")
        known = {k: v for k, v in table.items() if k in SERVICENOW_SCHEMA and k != "fixture_dir"}
        if not problems:
            servicenow = ServiceNowSettings(**known, fixture_dir=(root / table["fixture_dir"]).resolve()
                                            if "fixture_dir" in table else None)

    use_cases = {}
    for key, table in raw.get("use_cases", {}).items():
        where = f"[use_cases.{key}]"
        if not isinstance(table, dict):
            problems.append(f"{where}: expected a table"); continue
        _check(table, _USE_CASE, where, problems)
        if "module" not in table:
            problems.append(f"{where}: 'module' is required")
        paths = {}
        for k, v in (table.get("paths") or {}).items():
            if isinstance(v, str):
                paths[k] = (root / v).resolve()
            else:
                problems.append(f"{where}.paths.{k}: expected a path string")
        use_cases[key] = UseCaseConfig(key, table.get("enabled", True), table.get("module", ""), paths,
                                       dict(table.get("settings") or {}), dict(table.get("gates") or {}))
    if problems:
        raise ConfigError(problems, path)
    return Config(path, root, product.get("name", "Engineering Command Centre"), product.get("environment", "pilot"),
                  (root / product.get("runs_dir", "runs")).resolve(), provider, settings, sources, use_cases,
                  servicenow)
