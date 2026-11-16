# Author: Pradeep Sahoo
"""The contract between the platform and a use case.

A use case is a package that exposes `USE_CASE = UseCase(...)` in the module
named by `[use_cases.<key>].module` in the product configuration. It declares:
- the data paths it needs,
- its settings and pilot gates, with defaults (the config may override them,
  but cannot add keys the use case does not know, or change their types),
- a `register(parser, ctx)` function that adds its commands under `ecc <key>`.

Core never imports a use case by name, and use cases never import each other;
they share only `ecc_core`. Adding a use case means adding a package and a
config section; nothing in core changes.
"""
from __future__ import annotations

import argparse
import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import ENV_PROVIDER, Config, ConfigError, UseCaseConfig
from .llm import ClaudeClient
from .servicenow import ServiceNowClient


@dataclass
class UseCase:
    key: str                         # command name: ecc <key> ...
    title: str
    summary: str
    register: Callable[[argparse.ArgumentParser, "Context"], None]
    paths: tuple[str, ...] = ()      # required keys under [use_cases.<key>.paths]
    sources: tuple[str, ...] = ()    # required keys under [sources]
    settings: dict = field(default_factory=dict)   # name -> default
    gates: dict = field(default_factory=dict)      # name -> default


def _merge(defaults: dict, given: dict, where: str, problems: list[str]) -> dict:
    out = dict(defaults)
    for k, v in given.items():
        if k not in defaults:
            problems.append(f"{where}: unknown key '{k}' (known: {', '.join(sorted(defaults)) or 'none'})")
            continue
        d = defaults[k]
        ok = (isinstance(v, bool) == isinstance(d, bool)) and (
            isinstance(v, type(d)) or (isinstance(d, float) and isinstance(v, int)) or d is None)
        if not ok:
            problems.append(f"{where}.{k}: expected {type(d).__name__}, got {type(v).__name__}")
            continue
        out[k] = v
    return out


@dataclass
class Context:
    """What a use case's commands get from the platform."""
    config: Config
    use_case: UseCase
    section: UseCaseConfig
    settings: dict
    gates: dict

    def path(self, name: str) -> Path:
        return self.section.paths[name]

    def source(self, name: str) -> Path:
        return self.config.sources[name]

    @property
    def runs(self) -> Path:
        """Default output folder for this use case: <runs_dir>/<key>."""
        return self.config.runs_dir / self.use_case.key

    def provider_name(self, override: str | None = None) -> str:
        return override or os.environ.get(ENV_PROVIDER) or self.config.provider

    def claude(self) -> ClaudeClient:
        return ClaudeClient(self.config.model)

    def servicenow(self) -> ServiceNowClient:
        if self.config.servicenow is None:
            raise ValueError("ServiceNow is not configured: add [connectors.servicenow] to the product configuration")
        return ServiceNowClient(self.config.servicenow)


def load_use_case(config: Config, section: UseCaseConfig, check_paths: bool = False) -> Context:
    where = f"[use_cases.{section.key}]"
    try:
        module = importlib.import_module(section.module)
    except ImportError as exc:
        raise ConfigError([f"{where}.module: cannot import '{section.module}' ({exc})"], config.path) from exc
    uc = getattr(module, "USE_CASE", None)
    if not isinstance(uc, UseCase):
        raise ConfigError([f"{where}.module: '{section.module}' does not define USE_CASE"], config.path)
    problems: list[str] = []
    if uc.key != section.key:
        problems.append(f"{where}: module '{section.module}' implements use case '{uc.key}'")
    problems += [f"{where}.paths: '{p}' is required" for p in uc.paths if p not in section.paths]
    problems += [f"{where}.paths: unknown key '{p}'" for p in section.paths if p not in uc.paths]
    problems += [f"[sources]: '{s}' is required by {uc.key}" for s in uc.sources if s not in config.sources]
    settings = _merge(uc.settings, section.settings, f"{where}.settings", problems)
    gates = _merge(uc.gates, section.gates, f"{where}.gates", problems)
    if check_paths:
        problems += [f"{where}.paths.{k}: {p} does not exist" for k, p in section.paths.items() if not p.exists()]
        problems += [f"[sources].{s}: {config.sources[s]} does not exist" for s in uc.sources
                     if s in config.sources and not config.sources[s].exists()]
    if problems:
        raise ConfigError(problems, config.path)
    return Context(config, uc, section, settings, gates)


def load_enabled(config: Config, check_paths: bool = False) -> list[Context]:
    return [load_use_case(config, s, check_paths) for s in config.enabled()]


def context_for(key: str, config_path: str | Path | None = None) -> Context:
    """A use case's context straight from the product configuration (for tests and scripts)."""
    from .config import load_config
    config = load_config(config_path)
    if key not in config.use_cases:
        raise ConfigError([f"no [use_cases.{key}] section"], config.path)
    return load_use_case(config, config.use_cases[key])
