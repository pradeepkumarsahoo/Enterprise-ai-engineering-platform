# Use case 1 · Incident investigation

_Author: Pradeep Sahoo_ · package `ecc-incident` (`ecc_incident`) · depends on `ecc-core` only

Read-only, evidence-backed diagnosis. It runs on past incidents first (**replay**), where every
answer can be scored against the known cause, then alongside on-call engineers (**shadow mode**),
writing to a review queue without paging anyone. Why and how: root README
[section 5.1](../../README.md#51-use-case-1--incident-investigation).

## Commands

```bash
python ecc.py incident replay                       # past incidents vs known causes, pilot gates
python ecc.py incident investigate use-cases/incident-investigation/data/synthetic/live/INC-1042.json
python ecc.py incident shadow run                   # new incidents -> review queue
python ecc.py incident shadow feedback INC-1042 --useful yes --confirmed-cause config_change --minutes 31 --by sam.sre
python ecc.py incident shadow report

# Replay on incident history from ServiceNow (read-only; a dummy instance with fixtures by default)
python ecc.py incident servicenow pull             # alert-time incident files, labels, analysis
python ecc.py incident servicenow replay           # pull, then replay and score
```

Add `--provider claude` to `investigate`, `replay`, `shadow run` or the `servicenow` commands to use
Claude (for ServiceNow it also reads the resolution notes into labels). Outputs go to `runs/incident/`.

## Configuration · `[use_cases.incident]`

| Key | Default | Meaning |
|-----|---------|---------|
| `paths.incidents` | — | Past incidents for replay (no labels in these files) |
| `paths.labels` | — | Known causes and human baseline; read by scoring only, never by the investigator |
| `paths.live` | — | Shadow-mode inbox |
| `settings.lead_confidence_min` | 0.5 | Below this, the answer is "cause not established" |
| `settings.max_confidence` | 0.95 | No hypothesis is ever shown as certain |
| `settings.servicenow_query` | `active=false^priorityIN1,2` | Which closed ServiceNow incidents to replay (encoded query) |
| `gates.*` | see config | Lead accuracy, confident-but-wrong leads, unsupported claims, actions executed |

Runbooks come from `[sources].runbooks`, shared with use case 2. ServiceNow comes from
`[connectors.servicenow]`: a dummy URL with `transport = "fixture"` out of the box; for a real
instance set the URL, `transport = "http"` and `ECC_SERVICENOW_TOKEN` (or user and password).
Action risk and approval rules are in `policy.py`, not the configuration: they are governance and
change through code review.

## Code map

| Path | Role |
|------|------|
| `src/ecc_incident/__init__.py` | `USE_CASE`: key, paths, settings and gates with defaults |
| `src/ecc_incident/cli.py` | Commands under `ecc incident` |
| `src/ecc_incident/adapters.py` | Read-only `IncidentSource` interface, tool allow-list, fixture adapters |
| `src/ecc_incident/evidence.py` | Records → numbered evidence (E1…); statistics computed here |
| `src/ecc_incident/detectors.py` | Eight rule-based detectors |
| `src/ecc_incident/providers/` | Prompt, schema, mock provider, Claude adapter on `ecc_core.llm` |
| `src/ecc_incident/validate.py` | Removes unsupported claims; applies policy |
| `src/ecc_incident/policy.py` | Action risk/approval table, modes, confidence `Limits` |
| `src/ecc_incident/investigator.py` | Orchestrates one investigation |
| `src/ecc_incident/replay.py` · `shadow.py` · `render.py` | Replay scoring, shadow mode, Markdown output |
| `src/ecc_incident/servicenow.py` | ServiceNow pull: alert-time/outcome split, labeller with verbatim quotes, incident analysis |
| `data/synthetic/` | Past incidents, live incidents, labels |
| `reports/` | [`replay-mock.md`](reports/replay-mock.md), [`example-INC-1011.md`](reports/example-INC-1011.md); ServiceNow: [`servicenow-analysis-mock.md`](reports/servicenow-analysis-mock.md), [`servicenow-replay-mock.md`](reports/servicenow-replay-mock.md), [`servicenow-example-INC0011003.md`](reports/servicenow-example-INC0011003.md) |
