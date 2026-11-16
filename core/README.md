# Engineering Command Centre · code

_Author: Pradeep Sahoo_

The Engineering Command Centre is one platform core plus one folder per use case. Use cases plug
into the core through a small contract, and one configuration file sets up the whole product.
Why each use case exists, how it works and its results are in the root README:
[section 5, Implementation](../README.md#5-implementation).

## Repository layout

```text
config/product.toml            the product configuration (one file for everything below)
ecc.py                         run the CLI from a checkout, with nothing installed
pytest.ini                     runs every package's tests from the repository root
core/                          ecc-core: shared platform code, no use-case logic
  src/ecc_core/
    config.py                  load + strictly validate config/product.toml
    plugin.py                  the use-case contract (UseCase) and what commands get (Context)
    cli.py                     the `ecc` command: loads enabled use cases as plugins
    llm.py                     Claude client: complete_json with structured output
    evidence.py                the Evidence record every use case cites
    safety.py                  secret redaction and prompt-injection flagging
    audit.py                   append-only JSON Lines audit log
    sources.py                 read-only sources shared by several use cases (runbooks)
    servicenow.py              read-only ServiceNow connector: REST Table API or fixtures
  tests/
use-cases/
  incident-investigation/      ecc-incident     · use case 1
  knowledge-runbooks/          ecc-knowledge    · use case 2
  architecture-adlc/           ecc-architecture · use case 3
    README.md                  what it does, commands, settings, code map
    pyproject.toml             depends on ecc-core only
    src/ecc_<name>/            the package; __init__.py declares USE_CASE
    data/synthetic/            its sample data and labels
    tests/
    reports/                   committed sample outputs
shared-data/synthetic/         data read by more than one use case (runbooks)
scripts/                       generate_synthetic_data.py, screenshot_architecture.py
runs/                          outputs, per use case (git-ignored)
```

**Rules that keep it modular** (the last one is enforced by a test):
- Core contains no use-case logic and never imports a use case by name.
- A use case depends on `ecc_core` only, never on another use case. Something two use cases need
  goes into core (as the runbook loader did).
- Each use case owns its prompts, schemas, thresholds, data, tests and sample reports.

## Run

Python 3.11 or newer. The core and all use cases use the standard library only.

```bash
python ecc.py use-cases                      # what is enabled
python ecc.py config validate                # check the configuration and every data path
python ecc.py incident replay
python ecc.py knowledge evaluate
python ecc.py architecture run --requirement-doc use-cases/architecture-adlc/data/synthetic/requirement-document.md
python -m pytest                             # every package's tests, no network
```

Each use case's README lists its commands.

**Install as packages** (optional), then use `ecc` instead of `python ecc.py`:

```bash
pip install -e core -e use-cases/incident-investigation -e use-cases/knowledge-runbooks -e use-cases/architecture-adlc
pip install -e "core[claude]"                # only for provider = "claude"
```

Install only the use cases you need. A use case that is enabled in the configuration but not
installed is reported by `ecc config validate`.

## Configuration

Everything configurable lives in [`config/product.toml`](../config/product.toml):

| Section | What it sets |
|---------|--------------|
| `[product]` | Name, environment, repository root, where outputs go |
| `[model]` | Default provider (`mock` or `claude`), Claude model, effort, max tokens, refusal fallbacks |
| `[sources]` | Read-only sources shared by several use cases |
| `[connectors.servicenow]` | ServiceNow instance URL, transport (`fixture` or `http`), credential variable names, timeout, page size, record cap |
| `[use_cases.<key>]` | `enabled`, and `module`: the package that implements it |
| `[use_cases.<key>.paths]` | That use case's data |
| `[use_cases.<key>.settings]` | Its thresholds, such as the stale-runbook age or the NFR assessment margins |
| `[use_cases.<key>.gates]` | Its pilot pass/fail thresholds |

- **Precedence:** command-line flag > environment variable > the file > the default in code.
  Environment variables: `ECC_CONFIG` (the file's location), `ECC_PROVIDER`, `ECC_MODEL`.
- **Finding the file:** `--config`, else `$ECC_CONFIG`, else `config/product.toml` in the current
  directory or the nearest parent that has one.
- **Strict validation:** an unknown key, a wrong type, a missing path or a module that does not
  implement the use case it is configured as is an error, not a silent default.
  `ecc config validate` lists every problem; `ecc config show` prints the resolved values.
- **What is deliberately not configurable:** action risk and approval rules (use case 1's
  `policy.py`), the publish paths that do not exist, and validation rules. They are governance, so
  they change through code review, not a config edit.

## Adding a use case

1. Create `use-cases/<name>/` with `pyproject.toml` (depending on `ecc-core`), `src/ecc_<name>/`,
   `data/`, `tests/` and `README.md`.
2. In `src/ecc_<name>/__init__.py`, declare the contract:

   ```python
   from ecc_core.plugin import UseCase
   from .cli import register          # register(parser, ctx) adds the use case's commands

   USE_CASE = UseCase(
       key="capacity", title="Capacity planning", summary="peak forecasts and headroom per service",
       register=register,
       paths=("metrics_dir",),                       # required [use_cases.capacity.paths] keys
       settings={"headroom_min": 0.2},               # defaults; the config may override, not add
       gates={"forecast_error_max": 0.15, "note": ""},
   )
   ```

3. Add `[use_cases.capacity]` with `module = "ecc_capacity"` and its paths to `config/product.toml`,
   and its `src` folder to `pytest.ini`.
4. Build on core: `ctx.path(...)`, `ctx.settings`, `ctx.gates`, `ctx.runs`, `ctx.provider_name(...)`,
   `ctx.claude()` for a `ClaudeClient`, `Evidence`, `clean()`, `AuditLog`.

Nothing in core changes.

## Using Claude

Set `provider = "claude"` in `[model]`, `ECC_PROVIDER=claude`, or pass `--provider claude` to a
command. Credentials come from `ANTHROPIC_API_KEY` or an `ant auth login` profile. Each task is one
request with structured JSON output and no tools. These calls cost money.

## Connecting ServiceNow

`ctx.servicenow()` gives a use case a read-only client: `get(table, query, fields)` against the
REST Table API, GET only, tables on an allow-list, records capped. Out of the box the URL is a
dummy instance and `transport = "fixture"` reads `shared-data/synthetic/servicenow/`. For a real
instance: set `url`, `transport = "http"`, and export `ECC_SERVICENOW_TOKEN` (or
`ECC_SERVICENOW_USER` and `ECC_SERVICENOW_PASSWORD`) for a read-only integration user whose time
zone is UTC. Credentials never go in the configuration file.

## Adding a real data source

Each use case reads its data through a read-only interface (`IncidentSource`, `KnowledgeBase.load`,
`ArchitectureInputs.load`). Implement it for the real tool with read-only credentials and point the
configuration at it. Keep every method a read.
