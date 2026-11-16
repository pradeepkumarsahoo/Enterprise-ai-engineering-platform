# incident-investigator

_Author: Pradeep Sahoo_

The first three use cases of the Engineering Command Centre, in one Python package:

1. **Incident investigation:** read-only, evidence-backed diagnosis. It runs on past incidents first
   (**replay**), then alongside on-call engineers (**shadow mode**).
2. **Knowledge & runbooks:** finds stale, unowned and broken runbooks, practice drift, coverage gaps,
   repeat incidents and overdue follow-up actions. It drafts runbook edits for owners to approve.
3. **Architecture & ADLC:** from a structured requirement, scores reference patterns against every
   NFR, ranks the options, flags conflicts with accepted ADRs and raises open questions. It drafts an
   ADR and user stories, and traces each NFR to a component, ADRs and stories.

Why these use cases, how they work, results and every design decision are in the root README:
[section 5, Implementation](../README.md#5-implementation) and
[section 6, Decisions and trade-offs](../README.md#6-decisions-and-trade-offs-made-during-development).

## Requirements

- Python 3.10 or newer. The core uses the standard library only.
- Optional: `anthropic` for `--provider claude` (`pip install -e ".[claude]"`).
- Optional: `pytest` to run the tests (`pip install -e ".[dev]"`).

## Test and build

```bash
python -m pytest                       # 51 tests, no network
pip wheel . --no-deps -w dist          # installable wheel
```

## Run

```bash
export PYTHONPATH=src                  # PowerShell: $env:PYTHONPATH="src"

# Use case 1: incident investigation
python -m investigator replay
python -m investigator investigate data/synthetic/live/INC-1042.json
python -m investigator shadow run
python -m investigator shadow feedback INC-1042 --useful yes --confirmed-cause config_change --minutes 31 --by sam.sre
python -m investigator shadow report

# Use case 2: knowledge & runbooks
python -m investigator knowledge run           # review queue per owning team
python -m investigator knowledge evaluate      # run + score against labels and pilot gates
python -m investigator knowledge feedback EDIT-RB-017-3-replace --accept yes --by ria.owner
python -m investigator knowledge report

# Use case 3: architecture & ADLC
python -m investigator architecture run        # proposal pack: options, ADR draft, traceability, stories
python -m investigator architecture evaluate   # run + score against labels and pilot gates
python -m investigator architecture feedback ADR-007 --accept yes --by arb.chair
python -m investigator architecture report
```

After `pip install .`, use the `investigator` command instead. An installed copy does not include
the sample data, so pass `--runbooks`, `--incidents`, `--labels`, `--knowledge-dir`, `--arch-dir` and `--gates`
explicitly.

**Using Claude:** add `--provider claude` to `investigate`, `replay`, `shadow run`, `knowledge run`
`knowledge evaluate`, `architecture run` or `architecture evaluate`. Credentials come from `ANTHROPIC_API_KEY` or an `ant auth login` profile.
Each task is one request to `claude-opus-5-5` at effort `high`, with structured JSON output and
server-side refusal fallback. Override the model with `INVESTIGATOR_MODEL`. These calls cost money.

Outputs go to `runs/`, which is git-ignored: reports, per-incident investigations, review queues,
feedback, proposal packs and the append-only audit logs. Sample outputs are committed in `reports/`.

## Code map

| Path | Role |
|------|------|
| `src/investigator/adapters.py` | Read-only source interface, tool allow-list, fixture adapters |
| `src/investigator/safety.py` | Secret redaction and prompt-injection flagging |
| `src/investigator/evidence.py` | Use case 1: records → numbered evidence (E1…); statistics computed here |
| `src/investigator/detectors.py` | Use case 1: eight rule-based detectors |
| `src/investigator/validate.py` | Use case 1: removes unsupported claims; applies policy |
| `src/investigator/investigator.py` | Use case 1: orchestrates one investigation |
| `src/investigator/replay.py` | Use case 1: scores past incidents, pilot gates, report |
| `src/investigator/shadow.py` | Use case 1: inbox → review queue, feedback, report |
| `src/investigator/knowledge/sources.py` | Use case 2: read-only knowledge sources |
| `src/investigator/knowledge/checks.py` | Use case 2: deterministic checks, repeats, overdue actions, recommendations |
| `src/investigator/knowledge/drafting.py` | Use case 2: edit schema, mock drafter, edit validation |
| `src/investigator/knowledge/review.py` | Use case 2: run, per-team review queue, feedback, evaluation |
| `src/investigator/architecture/sources.py` | Use case 3: read-only requirement, pattern library and ADR sources |
| `src/investigator/architecture/assess.py` | Use case 3: option-by-NFR assessment rules, ranking, ADR conflicts, open questions, traceability |
| `src/investigator/architecture/drafting.py` | Use case 3: ADR and story schema, mock drafter, validation including the invented-figures check |
| `src/investigator/architecture/review.py` | Use case 3: run, proposal pack, approver feedback, evaluation |
| `src/investigator/providers/` | `mock` and `claude` providers; `complete_json` shared by all three use cases |
| `src/investigator/policy.py` | Action risk/approval table, mode rules, confidence limits |
| `src/investigator/audit.py` | Append-only JSON Lines audit log |
| `src/investigator/render.py` | Markdown for investigations |
| `src/investigator/cli.py` | Command line for all three use cases |
| `config/pilot_gates.json` | Placeholder pass/fail thresholds per use case |
| `data/synthetic/` | Incidents, labels, live incidents, runbooks; `knowledge/` holds post-incident records, actions, config inventory, teams, labels; `architecture/` holds the requirement, patterns, ADRs, labels |
| `scripts/generate_synthetic_data.py` | Regenerates all synthetic data reproducibly |
| `tests/` | `test_investigator.py` (use case 1), `test_knowledge.py` (use case 2 + CLI), `test_architecture.py` (use case 3 + CLI) |
| `reports/` | Sample outputs from all three use cases |

## Adding a real data source

Implement the `IncidentSource` protocol (use case 1), or extend `KnowledgeBase.load` (use case 2)
or `ArchitectureInputs.load` (use case 3), for the real tool, using read-only credentials. Keep every method a read. Nothing else in the
pipeline changes.
