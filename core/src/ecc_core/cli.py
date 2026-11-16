# Author: Pradeep Sahoo
"""`ecc`: one command line for every enabled use case.

    ecc [--config PATH] use-cases            list use cases and whether each is enabled
    ecc [--config PATH] config show          the resolved configuration
    ecc [--config PATH] config validate      check the file, every enabled use case and every path
    ecc [--config PATH] <use-case> ...       commands registered by that use case's plugin

Use cases are loaded from the modules named in the configuration, so core has
no knowledge of any particular use case.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .config import ConfigError, load_config
from .llm import ProviderError
from .plugin import load_enabled, load_use_case


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):      # Windows consoles default to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _jsonable(o):
    if isinstance(o, Path):
        return str(o)
    raise TypeError(type(o).__name__)


def cmd_use_cases(config, contexts) -> int:
    loaded = {c.use_case.key: c for c in contexts}
    for key, section in config.use_cases.items():
        c = loaded.get(key)
        state = "enabled " if section.enabled else "disabled"
        title = f"{c.use_case.title}: {c.use_case.summary}" if c else section.module
        print(f"{state}  {key:<14} {title}")
    return 0


def cmd_config_show(config, contexts) -> int:
    out = {"file": config.path, "root": config.root, "product": {"name": config.name, "environment": config.environment,
                                                              "runs_dir": config.runs_dir},
           "model": {"provider": config.provider, **asdict(config.model)}, "sources": config.sources,
           "connectors": {"servicenow": asdict(config.servicenow)} if config.servicenow else {},
           "use_cases": {c.use_case.key: {"module": c.section.module, "paths": c.section.paths,
                                          "settings": c.settings, "gates": c.gates} for c in contexts}}
    print(json.dumps(out, indent=2, default=_jsonable))
    return 0


def cmd_config_validate(config, contexts) -> int:
    problems = []
    for section in config.enabled():
        try:
            load_use_case(config, section, check_paths=True)
        except ConfigError as exc:
            problems += exc.problems
    sn = config.servicenow
    if sn and sn.transport == "fixture" and not (sn.fixture_dir and sn.fixture_dir.exists()):
        problems.append(f"[connectors.servicenow].fixture_dir: {sn.fixture_dir} does not exist")
    for p in problems:
        print(f"problem: {p}")
    print(f"{config.path}: {'invalid' if problems else 'valid'} · {len(config.enabled())} use case(s) enabled")
    return 1 if problems else 0


def build_parser(config, contexts) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ecc", description=f"{config.name}: governed AI for the software lifecycle.")
    p.add_argument("--config", help="product configuration file (default: config/product.toml)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("use-cases", help="List use cases").set_defaults(core=cmd_use_cases)
    c = sub.add_parser("config", help="Show or validate the product configuration")
    csub = c.add_subparsers(dest="config_cmd", required=True)
    csub.add_parser("show", help="Print the resolved configuration").set_defaults(core=cmd_config_show)
    csub.add_parser("validate", help="Check the file, enabled use cases and paths").set_defaults(core=cmd_config_validate)
    for ctx in contexts:
        uc = ctx.use_case
        up = sub.add_parser(uc.key, help=uc.title, description=f"{uc.title}: {uc.summary}")
        uc.register(up, ctx)
    return p


def main(argv=None) -> int:
    _utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config")
    known, _ = pre.parse_known_args(argv)
    try:
        config = load_config(known.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    try:
        contexts = load_enabled(config)
    except ConfigError as exc:
        if [a for a in argv if not a.startswith("-") and a != known.config][:2] != ["config", "validate"]:
            print(f"Configuration error: {exc} (run `ecc config validate` for every problem)", file=sys.stderr)
            return 2
        contexts = []                    # `config validate` reports each use case's problems itself
    args = build_parser(config, contexts).parse_args(argv)
    try:
        if hasattr(args, "core"):
            return args.core(config, contexts)
        return args.fn(args)
    except ProviderError as exc:
        print(f"Provider error: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
