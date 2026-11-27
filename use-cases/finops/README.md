# Use case 5 · FinOps (cloud cost by team)

_Author: Pradeep Sahoo_ · package `ecc-finops` (`ecc_finops`) · depends on `ecc-core` only

Allocates the cloud cost export to teams and shows monthly spend by team with a month-end forecast.
It flags statistically unusual increases with their likely cause and a confidence level, and
proposes savings. Estimated and realised savings go in separate columns: the estimate comes from
a formula in code, and the realised saving is measured from the bill after the change. The
owning team decides every recommendation, and nothing here changes a cloud resource. Why and how:
root README [section 5.5](../../README.md#55-use-case-5--finops).

![FinOps: cloud cost by team](../../docs/stakeholder/screenshots/20-finops-cost-by-team.png)

## Commands

```bash
python ecc.py finops analyse                         # spend, anomalies, causes, recommendations, report
#   -> runs/finops/report.html: open in a browser
python ecc.py finops status                          # recommendations with estimated and realised savings
python ecc.py finops decide REC-RS-promotion-engine-nodes --by lee.lead --role engineering-lead --note "CPU is low outside the peak"
python ecc.py finops decide REC-REV-loyalty-ledger-db --by dana.owner --role service-owner --reject --note "Audit needs a year of snapshots"
python ecc.py finops implemented REC-RS-promotion-engine-nodes --by lee.lead --on 2026-11-12 --change CHG0030777
python ecc.py finops evaluate                        # anomalies, causes and savings vs labels; pilot gates
python scripts/screenshots.py finops                 # regenerate the screenshot above (needs Edge or Chrome)
```

Add `--provider claude` to `analyse` or `evaluate` to draft explanations and notes with Claude.
Outputs go to `runs/finops/` (override with `ecc finops --workdir DIR ...`).

## How it works

| Step | Done by | What happens |
|------|---------|--------------|
| Allocate | code | A cost line belongs to its `team` tag; else to the catalogue owner of its `service` tag; else it is **unallocated** and reported |
| Spend | code | Net of credits, per team and billing month. The partial month's forecast = month to date × days in month ÷ days covered |
| Anomalies | code | Per resource and line item, on usage only (credits excluded). Flag when z ≥ 3 against the trailing 6-month mean **and** the increase is ≥ $1,000 **and** ≥ 10%. Flagged months leave later baselines; consecutive months form one anomaly |
| Likely cause | code | A configuration change in the window whose attribute fits the cost category (retention for storage, log level for logging, ...). Points: fits the category +2, same resource or service +1, made under a change request +1. High from 4, medium 2–3, low 1 |
| Recommend | code | One per resource, first rule wins (below), each with its formula |
| Realised | code | For implemented recommendations: mean cost over the 3 complete months before − mean over the complete months since. Waits for one complete month |
| Explain | model | Summary, one explanation per anomaly, one note per open recommendation |
| Validate | code | Rejects unknown or closed items, no valid evidence, invented figures, and any claim that something was changed |
| Decide | people | The owning team approves or rejects, with a reason |

**What the floors are for.** The September SLA credit is excluded from the usage baseline. The
1.5% a month growth on `order-service-nodes` is never 3 deviations out. The August bump on
`partner-gateway-egress` is (z = 4.0), but it is $586 and 9.7%, under both floors: noise, not an
anomaly.

## Recommendation rules

| Type | Fires when | Estimated monthly saving |
|------|-----------|--------------------------|
| `revert` | An anomaly's likely cause is a configuration change, at medium or high confidence | the anomaly's increase over its baseline (last complete month; a part-month run-rate is marked provisional) |
| `idle` | A volume detached for at least 30 days | its cost |
| `schedule` | A sandbox, staging or dev resource running at least 160 hours a week | cost × (1 − 65/168) |
| `rightsize` | CPU p95 under 25% and memory p95 under 40% over 30 days | cost × 0.5 |

A recommendation rejected within the last 180 days is not proposed again; it is listed as
**suppressed**, with the reason the team gave.

## Estimated vs realised (in code, not configuration)

- The estimate is frozen when the team approves, so the realised figure is compared with what the
  team agreed to, not with a number recomputed later.
- Nobody types in a realised saving: it is measured from the cost export. It is gross: other
  changes to the same resource in the same period also move it.
- The report and the KPI tiles show the two side by side and never add them together.

## Decisions (in code, not configuration)

- Only the owning team decides: role `service-owner` or `engineering-lead`. A FinOps analyst
  proposes and follows up but cannot approve alone; an agent can never decide.
- Every decision needs a written reason. Only a proposed recommendation can be decided.
- Only an approved recommendation can be recorded as implemented, by a person, on a date that is
  not in the future.
- Nothing here changes a cloud resource. The team makes the change through its own pipeline; the
  evaluation gate counts changes made to cloud resources and requires zero.

## Configuration · `[use_cases.finops]`

| Key | Meaning |
|-----|---------|
| `paths.finops_dir` | `cost_export.csv` (FOCUS-style columns), `utilisation.json`, `config_changes.json`, `savings_register.json`, `labels.json` (evaluation only) |
| `settings.baseline_months`, `min_baseline_months`, `z_threshold`, `stdev_floor_ratio`, `min_increase_usd`, `min_increase_ratio` | The anomaly rule |
| `settings.cause_lookback_days` | How long before the anomaly's month a cause may start |
| `settings.rightsize_*`, `office_hours_per_week`, `always_on_hours_min`, `non_prod_envs`, `idle_days` | Recommendation rules |
| `settings.realised_baseline_months`, `rejected_cooldown_days`, `as_of` | Realised savings, suppression, "now" |
| `gates.*` | Anomaly precision and recall, cause accuracy, realised error, rejected drafts, invented figures, cloud changes |

Change requests come from `[connectors.servicenow]`; the service catalogue from `[sources]`.

## Code map

| Path | Role |
|------|------|
| `src/ecc_finops/__init__.py` | `USE_CASE`, and the Claude drafter on `ecc_core.llm` |
| `src/ecc_finops/cli.py` | Commands under `ecc finops` |
| `src/ecc_finops/sources.py` | Read-only inputs: cost export, utilisation, config change log, savings register, ServiceNow changes, catalogue |
| `src/ecc_finops/rules.py` | `Rules`: every threshold, from the product configuration |
| `src/ecc_finops/fmt.py` | Money, percentages and months, as evidence, reports and the page show them |
| `src/ecc_finops/spend.py` | Billing coverage, allocation to teams, spend by team, run-rate forecast |
| `src/ecc_finops/anomalies.py` | Cost series, the anomaly rule, runs of flagged months |
| `src/ecc_finops/causes.py` | Likely cause and its points-based confidence |
| `src/ecc_finops/recommendations.py` | Recommendation rules, estimates, register and decisions, realised savings, totals |
| `src/ecc_finops/evidence.py` | Evidence records F1, F2, ...: every sentence the model may quote |
| `src/ecc_finops/drafting.py` | Prompt and schema, mock drafter, validation |
| `src/ecc_finops/ledger.py` | Decisions: who may decide, implementation records |
| `src/ecc_finops/review.py` | Build the analysis, analyse, refresh after a decision |
| `src/ecc_finops/report.py` · `html.py` | The Markdown report · the report page and its spend chart |
| `src/ecc_finops/evaluation.py` | Scores against labels, pilot gates |
| `data/synthetic/` | Cost export, utilisation, config change log, savings register, labels |
| `reports/` | [`finops-report.md`](reports/finops-report.md) · [page](reports/finops-report.html) · [`evaluation-mock.md`](reports/evaluation-mock.md) |
