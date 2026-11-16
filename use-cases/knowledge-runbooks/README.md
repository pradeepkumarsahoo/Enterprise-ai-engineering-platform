# Use case 2 · Knowledge & runbooks

_Author: Pradeep Sahoo_ · package `ecc-knowledge` (`ecc_knowledge`) · depends on `ecc-core` only

Finds stale, unowned and broken runbooks, practice drift, coverage gaps, repeat incidents and
overdue follow-up actions, and drafts runbook edits for owners to approve. Nothing is ever
published to the wiki. Why and how: root README
[section 5.2](../../README.md#52-use-case-2--knowledge--runbooks).

## Commands

```bash
python ecc.py knowledge run                         # review queue per owning team
python ecc.py knowledge evaluate                    # run + score against labels and pilot gates
python ecc.py knowledge feedback EDIT-RB-017-3-replace --accept yes --by ria.owner
python ecc.py knowledge report
```

Add `--provider claude` to `run` or `evaluate` to draft edits with Claude. Outputs go to
`runs/knowledge/` (override with `ecc knowledge --workdir DIR ...`).

## Configuration · `[use_cases.knowledge]`

| Key | Default | Meaning |
|-----|---------|---------|
| `paths.knowledge_dir` | — | Post-incident records, follow-up actions, config inventory, teams, labels |
| `settings.stale_days` | 180 | A runbook not validated for this long is stale |
| `settings.drift_lookback_days` | 180 | Incidents considered for practice drift and coverage gaps |
| `settings.repeat_gap_days` | 90 | The same cause again within this many days is a repeat |
| `settings.repeat_lookback_days` | 180 | The latest incident of a repeat cluster must be this recent |
| `gates.*` | see config | Findings recall and precision, repeat clusters, rejected and published edits |

Runbooks come from `[sources].runbooks`, shared with use case 1.

## Code map

| Path | Role |
|------|------|
| `src/ecc_knowledge/__init__.py` | `USE_CASE`, and the Claude drafter on `ecc_core.llm` |
| `src/ecc_knowledge/cli.py` | Commands under `ecc knowledge` |
| `src/ecc_knowledge/sources.py` | Read-only knowledge sources |
| `src/ecc_knowledge/checks.py` | Deterministic checks, repeats, overdue actions, recommendations, `Thresholds` |
| `src/ecc_knowledge/drafting.py` | Edit schema and prompt, mock drafter, edit validation |
| `src/ecc_knowledge/review.py` | Run, per-team review queue, feedback, evaluation |
| `data/synthetic/` | Timelines, actions, config inventory, teams, labels |
| `reports/` | [`knowledge-evaluation-mock.md`](reports/knowledge-evaluation-mock.md) and review queues for [Loyalty](reports/knowledge-review-loyalty.md) and [Membership & Identity](reports/knowledge-review-membership-identity.md) |
