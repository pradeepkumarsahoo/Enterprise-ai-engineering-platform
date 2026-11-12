# Incident investigator

The first use case of the Engineering Command Centre: read-only, evidence-backed incident
investigation. It runs on past incidents first (**replay**), then alongside on-call engineers
(**shadow mode**).

Why this use case, the trade-off decisions and what is and isn't built yet are in the
[root README, section 5](../README.md#5-implementation-first-use-case--incident-investigation).

## Run

```bash
python -m pytest                                   # 20 tests, no network

export PYTHONPATH=src                              # PowerShell: $env:PYTHONPATH="src"
python -m investigator replay                      # past incidents vs known causes
python -m investigator investigate data/synthetic/live/INC-1042.json
python -m investigator shadow run
python -m investigator shadow feedback INC-1042 --useful yes --confirmed-cause config_change --minutes 31 --by sam.sre
python -m investigator shadow report
```

Or install it: `pip install -e .` (add `[claude]` for the Claude provider), then use `investigator ...`.

**Using Claude:** add `--provider claude`. Credentials come from `ANTHROPIC_API_KEY` or an
`ant auth login` profile. Each investigation is one request to `claude-opus-5-5` at effort `high`, with
structured JSON output and server-side refusal fallback enabled. Override the model with
`INVESTIGATOR_MODEL`. These calls cost money, so run replay with Claude deliberately.

Outputs go to `runs/` (git-ignored): replay reports, per-incident investigations, the shadow review
queue, feedback and the append-only audit log.

## Code map

| Path | Role |
|------|------|
| `src/investigator/adapters.py` | Read-only source interface + tool allow-list; fixture adapters |
| `src/investigator/safety.py` | Secret redaction and prompt-injection flagging |
| `src/investigator/evidence.py` | Records → numbered evidence; all statistics computed here |
| `src/investigator/detectors.py` | Eight rule-based detectors producing candidate causes |
| `src/investigator/providers/` | `mock` (deterministic) and `claude` (Anthropic SDK) behind one interface |
| `src/investigator/validate.py` | Removes unsupported claims; applies policy to next steps |
| `src/investigator/policy.py` | Action risk/approval table, mode rules, confidence limits |
| `src/investigator/audit.py` | Append-only JSON Lines audit log |
| `src/investigator/investigator.py` | Orchestrates one investigation |
| `src/investigator/replay.py` | Scores past incidents, checks pilot gates, writes the report |
| `src/investigator/shadow.py` | Inbox → review queue, engineer feedback, shadow report |
| `config/pilot_gates.json` | Placeholder pass/fail thresholds (replace after the baseline) |
| `data/synthetic/` | 8 past incidents, held-out labels, 2 live incidents, runbooks |
| `scripts/generate_synthetic_data.py` | Regenerates the dataset reproducibly |
| `reports/` | Sample replay report and example investigation |

## Adding a real data source

Implement the `IncidentSource` protocol in `adapters.py` for the real tool, using read-only
credentials, and keep every method a read. Nothing else in the pipeline changes.
