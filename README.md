# Engineering Command Centre — Stakeholder Materials

_Author: Pradeep Sahoo_

Materials for the stakeholder review and pilot approval of the **Engineering Command Centre**,
a governed AI layer for the software lifecycle and production operations.

**What this platform does**

- **Connects** the tools engineering teams already use (monitoring, code, tickets, cloud cost,
  security, identity) and links their data into one evidence trail.
- **Investigates and flags** with AI agents: incidents, risky releases, capacity, DR, data and
  access gaps, stale runbooks and unclear ownership. Every answer is backed by source records.
- **Recommends, never acts alone.** A named person approves every consequential step, and
  everything is recorded in an audit log.

> Independently developed reference concept. All data shown is synthetic, and the prototype uses a
> deterministic mock AI provider. Nothing here is a production outcome.

**Code:** the first three use cases are implemented, one folder each under [`use-cases/`](use-cases/), on a
shared [`core/`](core/), configured by [`config/product.toml`](config/product.toml).
1. **Incident investigation:** on past incidents first, then alongside on-call engineers.
2. **Knowledge & runbooks:** stale runbooks, repeat incidents and drafted fixes.
3. **Architecture & ADLC:** from a requirement document to options scored against NFRs, a drafted ADR
   and stories, NFR traceability and a container diagram.

See [section 5](#5-implementation) for what is built and
[section 6](#6-decisions-and-trade-offs-made-during-development) for the decisions behind it.

![Command Centre overview](docs/stakeholder/screenshots/01-overview.png)

---

## 1. Problem statement

**Engineering teams make high-stakes decisions from scattered evidence, under time pressure, with
no consistent record of why.**

Most organisations already own good tools for monitoring, tickets, code, cost and security. The
problem is that the evidence for any single decision is spread across many of them:

- **Evidence is fragmented.** Logs, metrics, deployments, tickets, code, cost exports and scanner
  results have separate owners and separate screens.
- **Context is rebuilt by hand.** During an incident, an on-call engineer opens a dashboard, a log
  search, the deploy history, a runbook wiki and a chat channel, then pieces the story together.
  The same happens in design reviews, security triage and budget cycles.
- **AI arrives ungoverned.** Assistants are adopted team by team, each with its own data handling,
  and none shares approval rules, evaluation or an audit trail.

Where the gap shows up today:

| Area | What happens today | Business impact |
|------|--------------------|-----------------|
| Production support | On-call engineers correlate logs, deploys and dashboards by hand | Longer outages; senior staff pulled off roadmap work |
| Architecture and delivery | Requirements become designs and backlogs through meetings and copy-paste | Slow starts; needs such as data residency or cost surface late |
| Security | Findings pile up without exposure or reachability context | Fix effort spent on the wrong findings |
| Cloud and licence cost | Spend reviewed after the fact, in spreadsheets | Idle resources and overlapping licences go unnoticed |
| AI governance | Assistants used without approval gates, evaluation or audit | Changes nobody can explain or reproduce |
| Change and release risk | Releases judged from the diff alone, without dependents, test gaps or incident history | Avoidable change failures and rollbacks |
| Runbooks and incident learning | Runbooks drift from how systems really work; post-incident actions stay open | The same incidents recur; new on-call engineers lose time |
| Service ownership and end-of-life software | No current map of who owns a service, what depends on it, or which runtimes are past support | Unowned services and unplanned upgrade work |
| Capacity and performance planning | Scaling decisions made after slowdowns, not from trends | Peak-time outages or over-provisioning |
| Disaster recovery that is never tested | DR plans exist on paper; failover is not exercised | Unknown recovery time when it matters |
| API and contract breakage between teams | Producers change events or APIs without knowing who consumes them | Cross-team incidents that fail silently |
| Data pipeline quality | Broken or late data is noticed by business users first | Wrong reports and decisions; trust in data drops |
| Access and permissions sprawl | Production access is granted and never removed | Security exposure; audit findings |
| Joiners, leavers and fragmented ownership | Ownership is recorded differently in four places; when people leave or move, what they own, know and can access goes unnoticed | Orphaned services, lost knowledge and leftover access; slow onboarding |

*Qualitative assessment from discovery conversations. The pilot measures a real baseline in its
first two weeks rather than relying on industry figures.*

---

## 2. What it solves

The Command Centre is **one governed layer above the tools teams already use**. It reads their data
through read-only adapters, connects it into a single evidence trail, uses AI to help interpret it,
and keeps a named person accountable for every consequential action.

**How it solves an engineering organisation's problems**

| Problem today | What the platform does | What changes for the organisation |
|---------------|------------------------|-----------------------------------|
| Incidents diagnosed by hand across many tools | Correlates deploys, metrics, logs and runbooks into evidence-linked hypotheses with confidence and known gaps | Faster first diagnosis; senior engineers back on roadmap work |
| Designs and backlogs built through meetings and copy-paste | Drafts architecture options, ADRs, NFR traceability and stories from a structured requirement | Faster project starts; residency, cost and other needs surface early |
| Security findings without context | Ranks findings by exposure, reachability and asset tier; tracks approved exceptions | Fix effort goes to findings that can actually be exploited |
| Cost reviewed after the fact | Flags spend anomalies with likely causes; open-formula TCO; estimated and realised savings tracked apart | Waste found while it can still be stopped; finance can trace every estimate |
| AI tools adopted without rules | One policy, approval, audit and evaluation model shared by every agent | AI use the organisation can explain, reproduce and audit |
| Releases judged from the diff alone | Scores each release on rule-based risk factors and similar past incidents; suggests release conditions | Fewer change failures and rollbacks |
| Runbooks drift; lessons are lost | Checks runbooks against what responders actually did; flags repeat incidents and overdue follow-ups | The same incident stops coming back |
| No map of owners, dependents or end-of-life software | Builds a service catalogue with blast radius and a transparent debt-priority score | Upgrade and ownership work planned, not discovered in an outage |
| Scaling decided after slowdowns | Forecasts peaks from metrics and business calendars; shows headroom per service | Capacity in place before the peak; idle capacity released |
| DR plans never tested | Compares recovery targets with measured drills; finds broken plan steps; drafts sandbox drills | Recovery time known and proven, not assumed |
| API changes break other teams | Detects breaking changes, lists every consumer, drafts migration plans and notices | Cross-team breakages caught before release |
| Bad data found by report users | Monitors pipeline freshness and quality; traces failures upstream through lineage | Data issues fixed before decisions are made on them |
| Access granted and never removed | Continuously reviews production access: unused, standing admin and leaver grants | Smaller attack surface; audit evidence available at any time |
| People leave, knowledge and ownership leave too | Hands over what leavers own, reconciles conflicting ownership records, drafts onboarding packs | No orphaned services; joiners productive sooner. Never used to judge individuals |

**How it works**

1. **Read** — read-only adapters pull logs, metrics, deploys, tickets, code, cost exports and findings.
2. **Reason** — the platform links records, retrieves runbooks and proposes hypotheses with a
   confidence level and a list of what it could not establish.
3. **Approve** — anything consequential waits for a person with the right role and a written reason.
   Requesters cannot approve their own requests.
4. **Record** — the ticket, report or simulated action is written to an append-only audit trail,
   linked by a correlation ID.

**What it is, and what it is not**

| It is | It is not |
|-------|-----------|
| Decision support that shows its evidence and confidence | An autonomous operator with production access |
| Controlled automation behind named human approval | A replacement for engineering judgement |
| One shared layer for policy, approvals, audit and evaluation | Another monitoring, ticketing or scanning tool |
| Measured: every AI workflow has a reproducible test suite | A source of vendor quotes or individual performance scores |

**Why existing tool categories don't cover it**

| Category | Strong at | What stays missing |
|----------|-----------|--------------------|
| Observability and AIOps | Telemetry, alerting, anomaly detection | Links to code, tickets, cost and security; approval and audit for actions |
| Coding assistants | Writing and explaining code in the editor | Operational context, organisation-wide policy, evaluation and audit |
| ITSM and work tracking | Process, ownership, workflow state | Evidence gathering and analysis across sources |
| FinOps and security platforms | Deep analysis in their own domain | Cross-domain trade-offs, such as the cost and risk of a design choice |

**Modules** (on shared services: agent registry, model gateway, policy engine, approvals, audit,
evaluations, data provenance)

| Module | What it does |
|--------|--------------|
| Command centre | KPIs, each traced to the records it was calculated from |
| Production support | Evidence-backed incident investigation and post-incident reports |
| Knowledge & runbooks | Runbook drift checked against real incidents, repeat-incident detection, overdue post-incident actions |
| Capacity planning | Peak forecasts from metrics and the promotions calendar; headroom per service; scaling proposals |
| Resilience & DR | Recovery targets vs. measured drill results; broken plan steps; sandbox DR drills |
| Architecture & ADLC | Proposals, ADRs and NFR traceability from a structured requirement |
| Developer assistant | Scaffolds, test suggestions and PR review, shown as diffs for approval |
| Change risk | Pre-deploy risk score from rule-based factors, similar past incidents and suggested release conditions |
| API contracts | Breaking-change detection on events and APIs, affected consumers, migration plan |
| Jira & delivery | Backlog generation, sprint risk, blocked and ageing work, release notes |
| Chaos engineering | Sandbox-only experiments with abort rules and SLO comparison |
| Data pipelines | Freshness, volume and quality checks; failures traced upstream through lineage |
| Licensing & TCO | Multi-year estimates with open formulas and editable prices |
| FinOps | Cost anomalies and recommendations; estimated and realised savings kept apart |
| Security | Findings prioritised by exposure and reachability; exceptions approved and tracked |
| Service catalogue | Ownership, dependencies and end-of-life runtimes, with a transparent debt-priority formula |
| Access review | Continuous review of production access: unused, standing-admin and leaver grants |
| Joiners & leavers | Ownership handover for leavers and movers, conflicting ownership records, onboarding packs for joiners |
| Engineering intelligence | DORA-style measures at team level, never used to rank individuals |

**Built-in guardrails:** evidence before conclusions; permissions, money and state changes handled
by plain code and policy rather than the model; secrets redacted before any model call; logs,
tickets and code treated as untrusted input so they cannot override policy; synthetic, imported and
AI-generated data labelled as such.

**How AI agents handle these use cases**

Every agent follows the same pattern: it reads through read-only adapters, the numbers come from
plain code and rules, the agent explains and drafts, and a person decides anything consequential.

| Use case | Agent | Reads (read-only) | What the agent does | What a person decides |
|----------|-------|-------------------|---------------------|-----------------------|
| Capacity planning | `capacity-planner` | Metrics, promotions calendar, service catalogue | Explains the forecast (computed in code), names the first constraint, drafts scaling proposals, lists unknowns | Platform team approves any scaling change; their pipeline applies it |
| Disaster recovery | `dr-readiness-checker` | DR plans, drill records, change records | Finds untested plans and steps that reference retired infrastructure; drafts a corrected sandbox drill | SRE approves the drill; it runs through Chaos engineering |
| API contracts | `contract-guardian` | Schema registry, API specs, service catalogue, traces | Explains breaking changes found by rules, lists affected consumers, drafts the migration plan and notices | Producer team approves sending notices; consumers own their migration |
| Data pipelines | `data-quality-tracer` | Pipeline runs, lineage, change records | Traces a failed check upstream to a likely cause, with evidence and confidence; drafts the notice to report owners | Data platform approves notices and reruns |
| Access sprawl | `access-reviewer` | Identity provider, cloud IAM, CI/CD access logs, HR feed | Writes the reason for each recommended removal; risk is set by rules | Identity team approves and applies; the agent never grants or removes access |
| Joiners, leavers and ownership | `ownership-steward` | HR feed (dates only), service catalogue, repository history, on-call, cost tags | Lists what a leaver owns, proposes new owners, drafts handover notes, reconciles conflicting ownership records, drafts onboarding packs | The leaver reviews notes; the manager approves new owners; the team lead approves joiner access |

The joiner and leaver agent looks at ownership, knowledge and access only. It never measures
individual performance.

---

## 3. Business outcomes

The pilot is designed to show these outcomes. Targets are left blank on purpose: they are set with
sponsors after the baseline is measured in weeks 1–2.

| Outcome | Who benefits | How it is measured in the pilot | Target |
|---------|--------------|----------------------------------|--------|
| Faster incident diagnosis | SRE, on-call, customers | Time from alert to first evidence-backed hypothesis, agent vs. manual | [__ min] |
| Trustworthy AI recommendations | SRE, risk | Share of agent outputs that cite source records | [__%] |
| Fewer unsupported claims | SRE, risk | Unsupported-claim rate in the evaluation suite plus SRE review | [under __%] |
| Engineers find it useful | Engineering | Accept/reject rate on each recommendation | [__%] |
| AI use stays governed | Security, audit, leadership | Actions executed without approval (from the audit log) | **0** |

Outcomes expected as the platform extends beyond the pilot slice:

- **Engineering leadership** — team-level delivery insight (deployment frequency, lead time, change
  failure rate, time to restore) with sample sizes, to find system bottlenecks.
- **Architects and developers** — less blank-page work: draft proposals, ADRs, stories and review
  comments, clearly marked for human review.
- **Security** — remediation effort directed at findings that are exposed and reachable.
- **Finance** — traceable TCO and savings estimates, with realised savings tracked separately.
- **Risk and audit** — one record of who did what, why, and who approved it.
- **Release and platform teams** — risky changes flagged before deploy, with the factors and past
  incidents behind the score.
- **On-call engineers** — runbooks kept in line with what responders actually do, and repeat
  incidents surfaced with their open follow-up actions.
- **Service owners** — a current view of ownership, dependents and runtimes nearing end of support.
- **Platform teams** — capacity shortfalls found weeks before a peak, and DR plans proved by drills.
- **Data and analytics teams** — broken pipelines caught and traced before report users notice.
- **Engineering managers** — clean handovers when people leave, and faster onboarding for joiners.
- **Security and identity teams** — production access that shrinks back after people move or leave.

**Proposed pilot:** eight weeks, read-only, incident investigation on [2–3 services]. Weeks 1–2
measure the human baseline; weeks 3–4 replay 15–20 past incidents with known causes; weeks 5–8 run in
shadow mode alongside on-call engineers. Go/no-go review at week 8.

---

## 4. Screenshots from the prototype

All screens use synthetic data and the mock AI provider. Captured from
[`prototype/command-centre-prototype.html`](docs/stakeholder/prototype/command-centre-prototype.html) at 1440 px width.

### Overview — command centre
Open incidents, change failure rate, pending approvals and cloud spend. Each figure names the records
it comes from. Agent activity shows runs, failures, latency and estimated model cost.

![Overview](docs/stakeholder/screenshots/01-overview.png)

### Production support — incident investigation (INC-1042)
`membership-api` latency rose tenfold after deploy v2.14. Latency and DB-pool charts mark the deploy.
The leading hypothesis (pool limit cut from 50 to 20) has a confidence score and links to evidence
E1–E7. A competing hypothesis is ruled down, and the "could not establish" list states what the
agent doesn't know. A prompt-injection attempt in the logs is flagged and ignored. Remediation steps
are simulated and need approval.

![Incident investigation](docs/stakeholder/screenshots/02-incident-investigation.png)

### Approvals — human in the loop
Each request shows its risk, environment and the permission the decider needs. A written reason is
mandatory, and requesters cannot approve their own requests.

![Approvals](docs/stakeholder/screenshots/03-approvals.png)

### Audit log
An append-only record of actor, action, target, outcome and correlation ID, including denied
actions such as a blocked tool call.

![Audit log](docs/stakeholder/screenshots/04-audit-log.png)

### Architecture & ADLC
Two architecture options for a global loyalty platform compared against requirements, a container
view, NFR coverage with gaps, and open questions for the business. Marked as a draft for architect
review.

![Architecture](docs/stakeholder/screenshots/05-architecture.png)

### Architecture & ADLC — from a requirement document (working code)
Unlike the other screenshots, this one is not the prototype. It is the proposal page produced by the
real code (use case 3, [section 5.3](#53-use-case-3--architecture--adlc)) from the sample
[requirement document](use-cases/architecture-adlc/data/synthetic/requirement-document.md).
On the left, the requirement extracted from the document, each NFR's target and whether it is traced,
and the document flags (an API key redacted, an embedded instruction ignored). On the right, the
container diagram of the preferred option, drawn in code from the pattern library, with each component
labelled with the NFRs it satisfies. Regenerate with `python scripts/screenshot_architecture.py`.

![Architecture from a requirement document](docs/stakeholder/screenshots/18-architecture-from-document.png)

### FinOps
Monthly spend by team, a statistically flagged anomaly with its likely cause, and recommendations
that track estimated and realised savings in separate columns.

![FinOps](docs/stakeholder/screenshots/06-finops.png)

### Licensing & TCO
A multi-year estimate with the formula shown, using a fictional vendor and fictional prices.

![Licensing and TCO](docs/stakeholder/screenshots/07-licensing-tco.png)

### Engineering intelligence
DORA-style measures with sample sizes and date range, and bottlenecks by team. No individual
rankings.

![Engineering intelligence](docs/stakeholder/screenshots/08-engineering-intelligence.png)

### Change risk — pre-deploy assessment
A release of `loyalty-ledger` scores 7.1 out of 10. Each factor (a pool-size change matching
INC-1042, a schema migration, an event contract change, a coverage gap, the deploy window) has a
weight and links to a record. The score comes from versioned rules, not the model. The agent
suggests release conditions, and a score of 7 or more needs a second approver.

![Change risk](docs/stakeholder/screenshots/09-change-risk.png)

### Knowledge & runbooks
Runbook health checked against what responders did in real incidents. RB-017 still names a
setting removed two releases ago, and a draft edit is offered to the owning team. Pool exhaustion
has recurred three times in 90 days while its follow-up action is overdue.

![Knowledge and runbooks](docs/stakeholder/screenshots/10-knowledge-runbooks.png)

### Service catalogue
Ownership, tier, runtime support status and dependents for each service, ranked by a
deterministic debt-priority formula. Shows the blast radius of `loyalty-ledger` and states where
dependency data is missing.

![Service catalogue](docs/stakeholder/screenshots/11-service-catalogue.png)

### Capacity planning
Peak readiness for a double-points weekend. The forecast is computed in code from 13 weeks of
metrics and the promotions calendar; `loyalty-ledger` is 31% short of write capacity. The agent
explains the forecast, lists what it could not establish, and drafts a scaling proposal for approval.

![Capacity planning](docs/stakeholder/screenshots/12-capacity-planning.png)

### Resilience & DR
Recovery targets compared with measured drill results. Two tier-0/1 services have never been
drilled, and the `loyalty-ledger` plan restores from a backup vault retired in July. The agent drafts
a corrected sandbox drill that runs through Chaos engineering.

![Resilience and DR](docs/stakeholder/screenshots/13-resilience-dr.png)

### API contracts
A rename in the `PointsAccrued` event is caught before release. Four consumers are affected; one
would break silently and one has unknown usage. The agent drafts a migration plan and the notices
to consumer teams.

![API contracts](docs/stakeholder/screenshots/14-api-contracts.png)

### Data pipelines
A finance report's source pipeline lost 38% of its rows. The agent traces it through lineage to a
skipped regional extract after a credential rotation, and drafts the notice to report owners.

![Data pipelines](docs/stakeholder/screenshots/15-data-pipelines.png)

### Access review
Production access reviewed continuously: a leaver with live database access, an ownerless admin
service account, a team mover's old deploy rights and standing admin grants. Rules set the risk,
the agent writes the reason, and the identity team applies any removal.

![Access review](docs/stakeholder/screenshots/16-access-review.png)

### Joiners & leavers
A leaver's handover: code, runbooks, jobs, alert routes and pending approvals, each with a proposed
new owner. Ownership records that disagree across four sources are reconciled, and a joiner gets
an onboarding pack and a practice incident.

![Joiners and leavers](docs/stakeholder/screenshots/17-joiners-leavers.png)

---

## 5. Implementation

Code: [`core/`](core/) + one package per use case in [`use-cases/`](use-cases/) · Python 3.11+ ·
standard library only · 111 automated tests · each package builds as an installable wheel. Three use
cases are implemented, in priority order:

| # | Use case | Status | What it proves |
|---|----------|--------|----------------|
| 1 | Incident investigation, on past incidents then in shadow mode | Implemented | Evidence-backed diagnosis is accurate and useful, with zero risk |
| 2 | Knowledge & runbooks | Implemented | The same platform stops incidents repeating: stale runbooks fixed, follow-ups chased |
| 3 | Architecture & ADLC | Implemented | A requirement document becomes a reviewed design: options scored against NFRs in code, an ADR, stories and a diagram, with no invented figures |

All three share the same building blocks: read-only sources, evidence numbered in code, a deterministic
first pass, one structured model call with no tools, validation in code, policy-set approvals, an
append-only audit log and an evaluation against held-out labels.

### 5.1 Use case 1 — Incident investigation

**Why first.** It is read-only and needs only 3–4 sources most organisations already have. It
starts on **past** incidents, so it carries zero risk, and each answer is objectively right or wrong
against the known root cause. Every engineering leader feels outage pain. It also forces the shared
parts every later module needs.

```mermaid
flowchart LR
    A[Read-only adapters<br/>deploys · metrics · logs<br/>flags · dependencies · runbooks] --> B[Evidence builder<br/>numbers computed in code<br/>secrets redacted<br/>injection flagged]
    B --> C[Rule-based detectors<br/>candidate causes<br/>with a prior score]
    C --> D[Model call<br/>mock or Claude Opus 5.5<br/>no tools, structured JSON]
    D --> E[Validation in code<br/>unknown evidence IDs removed<br/>risk + approval set by policy]
    E --> F{Mode}
    F -->|replay| G[Score against held-out labels<br/>pilot gates]
    F -->|shadow| H[Review queue for SRE lead<br/>engineer feedback<br/>on-call not paged]
    B -.-> L[(Append-only<br/>audit log)]
    E -.-> L
    H -.-> L
```

1. **Read.** Adapters expose read methods only, behind a tool allow-list. No write, restart or
   notify method exists anywhere in the package.
2. **Build evidence.** Records become numbered evidence (E1, E2, …), with before/after-onset
   statistics computed in code. Secrets are redacted and instruction-like text is flagged.
3. **Detect.** Eight deterministic detectors propose candidate causes, including ones they rule
   down: config change, slow query, traffic spike, dependency failure, resource leak, certificate
   expiry, feature flag and code change.
4. **Reason.** One model call ranks and explains the candidates and returns JSON. It covers
   hypotheses with confidence and cited evidence, what could not be established, and next steps.
5. **Validate.** Code removes any claim citing evidence that doesn't exist, and any hypothesis
   resting only on flagged text. It caps confidence at 0.95. Policy sets each step's risk and
   whether it needs approval.
6. **Replay or shadow.** Replay scores the result against labels the investigator never reads.
   Shadow mode writes to a review queue and collects engineer feedback.

**Result (mock provider):** **8 of 8** past incidents correct. That includes one unexplained
incident, where the right answer is "cause not established". 0 unsupported claims, 0 actions
executed, 1 injection line flagged, 1 secret redacted. Report:
[`replay-mock.md`](use-cases/incident-investigation/reports/replay-mock.md) · example:
[`example-INC-1011.md`](use-cases/incident-investigation/reports/example-INC-1011.md).

#### Extension: replay on incident history from ServiceNow

**Why.** Synthetic incidents prove the pipeline; real incident history is how accuracy gets
measured. ServiceNow already holds what replay needs: past incidents, the alert text written into
each ticket, change records, CMDB relationships, and resolution notes that state the confirmed
cause.

```mermaid
flowchart LR
    S[(ServiceNow<br/>read-only connector<br/>incident · change_request<br/>problem · cmdb_rel_ci)] --> P[Pull: split each ticket]
    P --> A[Alert-time file<br/>title · CI · alert text<br/>changes BEFORE opening<br/>upstream incidents via CMDB]
    P --> O[Outcome<br/>close notes · problem cause]
    O --> L[Labeller<br/>cause only with a verbatim quote<br/>else left unlabelled]
    A --> I[Investigator<br/>same pipeline as replay]
    I --> R[Replay score vs labels<br/>+ incident analysis]
    L --> R
```

1. **Connect, read-only.** `[connectors.servicenow]` in the product configuration sets the
   instance, transport and limits. The connector only sends GET requests to the REST Table API,
   refuses tables outside an allow-list, caps records per read, and takes credentials from
   environment variables. The configured URL is a **dummy instance**
   (`https://dev00000.service-now.com`) with `transport = "fixture"`, which reads Table API-shaped
   records from [`shared-data/synthetic/servicenow/`](shared-data/synthetic/servicenow/).
   Switching to a real instance is a config change: the URL, `transport = "http"` and a read-only
   integration user.
2. **Split every ticket.** What was known when the incident was opened goes to the investigator:
   - the title, priority and CI, and the alert text from the description;
   - change records on the same CI in the 7 days **before** opening;
   - open incidents on CIs it depends on, found through CMDB relationships.

   Close notes, close codes, resolution times and problem records are fetched through a separate
   field list and go to scoring only. A change made after opening (usually the fix) is excluded.
   Secrets are redacted and instruction-like text flagged before anything is written to disk.
3. **Label from the notes, never guess.** A cause category is recorded only when the resolution
   notes state one, with the sentence quoted word for word. Notes like "Restarted pods, issue
   resolved" stay unlabelled and are left out of the score. Labels are marked "proposed": a person
   spot-checks them before the scores are relied on.
4. **Replay and analyse.** The same investigator runs on the pulled incidents and is scored against
   the labels. An analysis lists every incident with time to resolve, stated cause, problem
   record, changes before opening and upstream incidents, plus CIs with repeat incidents and notes
   that state no cause.

**Result (dummy instance, mock provider):**
- **8 incidents pulled**, of which 6 have a cause stated in the resolution notes.
- **4 of those 6 correct**, with **0 confident-but-wrong answers**. That's below the 75%
  placeholder gate, so the run reports FAIL.
- **The 2 misses** (a config change and a traffic spike) came out "cause not established".
  Naming them needs config diffs or metrics, which ServiceNow doesn't hold.
- **The 2 tickets with vague notes** were left out of the score and listed as a data-quality
  finding.
- **Nothing leaked:** no outcome text, no fix change and no secret reached the investigator, and
  tests check this.

This is the expected shape of a real result: tickets alone support some causes, not all. The
next gain comes from connecting monitoring and the deploy pipeline. Reports:
[`servicenow-analysis-mock.md`](use-cases/incident-investigation/reports/servicenow-analysis-mock.md) ·
[`servicenow-replay-mock.md`](use-cases/incident-investigation/reports/servicenow-replay-mock.md) · example
[`servicenow-example-INC0011003.md`](use-cases/incident-investigation/reports/servicenow-example-INC0011003.md).

### 5.2 Use case 2 — Knowledge & runbooks

**Why second.** It reuses use case 1's incident data, evidence pattern, provider, audit and
evaluation, and adds one source: post-incident records. It is still zero risk, because it only
drafts edits for owners to approve. Use case 1 makes diagnosis faster; this one stops the same
incident coming back. It also improves use case 1, whose investigations cite runbooks; those
citations now show when each runbook was last validated.

```mermaid
flowchart LR
    A[Read-only sources<br/>runbooks · post-incident reviews<br/>follow-up actions · config inventory<br/>team directory] --> B[Deterministic checks<br/>stale · unowned · broken reference<br/>practice drift · missing runbook<br/>repeat incidents · overdue actions]
    B --> C[Evidence K1, K2, ...<br/>+ code-written recommendations]
    C --> D[Model call<br/>drafts wording of runbook edits only]
    D --> E[Validation in code<br/>exact quote of current step<br/>valid evidence · no removed settings]
    E --> F[Review queue per owning team<br/>accept / reject feedback]
    F --> G[Evaluation vs labels<br/>pilot gates]
    B -.-> L[(Append-only<br/>audit log)]
    E -.-> L
    F -.-> L
```

1. **Read.** Runbooks with owner and last-validated date. Post-incident reviews: what responders
   actually did, which steps they skipped, and the confirmed cause. Follow-up actions, the config
   inventory (settings removed or renamed) and the team directory (active and retired teams).
2. **Check (code).** The checks:
   - **Stale or never validated:** not validated for more than 180 days, or never validated.
   - **Unowned:** the owner team was retired; the work routes to the team that took over its services.
   - **Broken reference:** a step names a setting that has been removed.
   - **Practice drift:** responders left the runbook to resolve a recent incident.
   - **Missing runbook:** a recent cause on a service that no runbook covers.
   - **Repeat incidents:** the same cause again within 90 days.
   - **Overdue follow-up actions:** recurring causes are listed first.
3. **Recommend (code).** Validation walk-throughs, ownership changes, new runbooks and escalations
   come from fixed rules. Ownership changes and new runbooks need approval.
4. **Draft (model).** For broken references and practice drift only, the model drafts the new step
   wording, citing evidence.
5. **Validate (code).** An edit is rejected if it misquotes the current step, points at a step that
   doesn't exist, still mentions a removed setting, cites no real evidence, or duplicates another
   edit. Every accepted edit is a **draft needing owner approval**. There is no code path that
   publishes to the wiki.
6. **Review.** One review file per owning team. Owners accept or reject each edit, and the report
   tracks the acceptance rate.

**Result (mock provider):** **9 of 9** expected findings, 0 unexpected. The repeat cluster was
found: database pool exhaustion, 3 incidents across 2 services. All 4 overdue actions were found,
including the 2 on the recurring cause. 3 edits were drafted, 0 rejected and 0 published.
Reports: [`knowledge-evaluation-mock.md`](use-cases/knowledge-runbooks/reports/knowledge-evaluation-mock.md) ·
review queues for
[Membership & Identity](use-cases/knowledge-runbooks/reports/knowledge-review-membership-identity.md) and
[Loyalty](use-cases/knowledge-runbooks/reports/knowledge-review-loyalty.md).

> **Read these results with care.** The synthetic data was written alongside the rules, so these
> results show the pipelines work end to end. They do **not** predict accuracy on real data. The
> numbers that matter come from real incidents and real runbooks during the pilot, run with the
> Claude provider against the placeholder gates in
> the `gates` sections of [`config/product.toml`](config/product.toml).

### 5.3 Use case 3 — Architecture & ADLC

**Why third.** It moves the platform from operations into the start of the lifecycle, still at zero
risk: it reads a requirement, either a structured intake form or a requirement document, and drafts a proposal, and people approve every decision. It reuses the
same evidence, provider, validation, audit and evaluation pattern, and adds three sources most
organisations already have: a requirements intake form, a reference pattern library and the ADR
repository. Use cases 1 and 2 deal with failures after release; this one brings residency, recovery
and other NFRs into the design before any code is written.

```mermaid
flowchart LR
    R[Requirement document<br/>.md / .txt] --> X[Extraction<br/>model quotes the document<br/>code checks quotes + figures]
    X --> A
    A[Read-only sources<br/>structured requirement · NFRs<br/>pattern library · existing ADRs] --> B[Assessment in code<br/>every option vs every NFR<br/>meets · at risk · fails · unknown]
    B --> C[Ranking + checks in code<br/>must-NFR failure rejects<br/>ADR conflicts · open questions]
    C --> D[Model call<br/>drafts ADR wording + user stories only]
    D --> E[Validation in code<br/>no rejected option · all alternatives<br/>no invented figures · targets quoted]
    E --> F[NFR traceability + container diagram<br/>component · mechanism · ADRs · stories<br/>Mermaid, drawn in code]
    F --> G[Proposal pack<br/>review board approves ADR<br/>product owner approves stories]
    G --> H[Evaluation vs labels<br/>pilot gates]
    B -.-> L[(Append-only<br/>audit log)]
    E -.-> L
    G -.-> L
```

1. **Read.** A structured requirement: capabilities, regions, NFRs with priority and target, open
   business decisions and stakeholder notes. The reference patterns with their published estimates,
   and the existing ADRs with their status.
   - **Or start from a requirement document** (Markdown or plain text). Secrets are redacted and
     instruction-like text is flagged before the model sees it. The model extracts capabilities, NFRs,
     open decisions and notes, quoting the document for each one. Code rejects any item whose quote is
     not in the document word for word, and parses every target from the quoted text, so a figure that
     isn't in the document can never become a target. "TBD" or "not agreed" stays empty, so it becomes
     an open question. The result is marked as needing the requester's confirmation. Word or PDF
     documents are exported to Markdown first.
2. **Assess (code).** Each pattern is scored against each NFR with a fixed rule per NFR category.
   For example, availability within 0.05 points of target is at risk, and throughput is computed per
   cell × number of regions. An NFR with no agreed target is **unknown** and is never guessed.
3. **Rank and check (code).** An option that fails a must-have NFR is rejected, and the result says
   when it would become viable (for example, "viable only for a single-region launch"). The rest are
   ranked by risk, conflicts with **accepted** ADRs and cost. Superseded ADRs are ignored. Missing
   targets and undecided business questions become open questions. The next ADR number is assigned.
4. **Draft (model).** One call drafts the ADR (context, decision, consequences, one entry per
   alternative) and user stories with acceptance criteria, citing evidence (A1, A2, …).
5. **Validate (code).** A draft is rejected if the ADR chooses a rejected option or skips an
   alternative, if any text states a **figure that is not in the evidence**, if a story traces to an
   unknown capability or NFR, if its acceptance criteria don't state the NFR's numeric target, or if it
   cites no real evidence other than flagged notes. If the ADR chooses a viable option other than the
   preferred one, it is kept and the disagreement is flagged for the review board.
6. **Trace, draw and review.** Each NFR is traced to a component, a mechanism, ADRs and stories, or
   shown as a gap with the reason. Code draws a **container diagram** (Mermaid) of the preferred option
   from the pattern library: the client, the global edge, and one regional cell naming the regions.
   Each component lists the NFRs traced to it, so the picture and the traceability matrix always agree.
   A connection to a component the pattern doesn't define is reported as an issue, not drawn.
   Every run writes the proposal pack three ways: Markdown, a `.mmd` diagram file, and an **HTML page**
   that puts the requirement document and the rendered diagram side by side, followed by the option
   comparison, the ADR draft, traceability, stories and open questions (screenshot in
   [section 4](#architecture--adlc--from-a-requirement-document-working-code)). The proposal pack goes to the architecture review board (ADR) and the
   product owner (stories). Nothing is written to the ADR repository or the backlog.

**Result (mock provider):** **44 of 44** assessment cells as expected, across 4 patterns × 11 NFRs.
PAT-A (regional cells + event-sourced ledger) is preferred and PAT-D is viable but conflicts with
ADR-005. PAT-B is rejected on residency (viable only for a single-region launch) and PAT-C on RPO,
residency and idempotency. ADR-007 was drafted with 6 stories covering all 6 capabilities, and
**9 of 11** NFRs are traced. The 2 gaps (cost ceiling, DR test cadence) have no agreed target and
become open questions, as in the prototype screen. 0 drafts rejected, 0 invented figures. The
container diagram shows all 8 components of the prototype's container view, and all 9 traced NFRs.
Starting from the [requirement document](use-cases/architecture-adlc/data/synthetic/requirement-document.md)
gives the same requirement with 0 items rejected, so the same results. 1 workshop note was flagged as
instructions and its API key redacted before the model saw it. Reports:
[`architecture-evaluation-mock.md`](use-cases/architecture-adlc/reports/architecture-evaluation-mock.md) ·
proposal pack [`architecture-proposal-REQ-LOY-001.md`](use-cases/architecture-adlc/reports/architecture-proposal-REQ-LOY-001.md) ·
diagram [`architecture-container-REQ-LOY-001.mmd`](use-cases/architecture-adlc/reports/architecture-container-REQ-LOY-001.mmd) ·
page [`architecture-proposal-REQ-LOY-001.html`](use-cases/architecture-adlc/reports/architecture-proposal-REQ-LOY-001.html)
(download and open in a browser).

![Use case 3: from requirement document to architecture](docs/stakeholder/screenshots/18-architecture-from-document.png)

### 5.4 Code structure and configuration

The code is one platform core plus one folder per use case. Details, and how to add a use case:
[`core/README.md`](core/README.md).

```text
config/product.toml          one file configures the whole product
ecc.py                       run `ecc` from a checkout, nothing installed
core/                        ecc-core: configuration, plugin contract, ecc CLI, Claude client,
                             evidence, secret redaction + injection flagging, audit log, shared sources
use-cases/
  incident-investigation/    ecc-incident      src/ · data/ · tests/ · reports/ · README.md · pyproject.toml
  knowledge-runbooks/        ecc-knowledge     (same layout)
  architecture-adlc/         ecc-architecture  (same layout)
shared-data/                 data read by more than one use case (runbooks)
scripts/                     synthetic data generator, README screenshot
```

- **Modular.** Core has no use-case logic. Each use case depends on core only, never on another use
  case (a test enforces this), and owns its prompts, schemas, thresholds, data, tests and reports.
  Each is a separate installable package, so a deployment installs only the use cases it runs.
- **Plugins.** A use case declares a `USE_CASE` contract: its command name, the data paths it
  needs, and its settings and gates with defaults. `ecc` loads the modules named in the
  configuration and adds their commands, as in `ecc incident replay` or `ecc architecture run`.
- **Configuration.** [`config/product.toml`](config/product.toml) sets which use cases are enabled,
  the model (provider, Claude model, effort, tokens, fallbacks), shared sources, and per use case its
  data paths, thresholds (for example the stale-runbook age or the NFR assessment margins) and pilot
  gates. Precedence: command-line flag > `ECC_*` environment variable > the file > the default in
  code. Validation is strict: an unknown key, a wrong type, a missing path or a module that is not
  installed is reported by `ecc config validate`, never silently replaced by a default. Approval
  and risk rules stay in code, because they are governance.

### 5.5 What is built, and what is not yet

| Area | Built | Not yet |
|------|-------|---------|
| Data sources | Read-only interfaces + fixture adapters for every source; read-only ServiceNow connector (REST Table API, or fixtures behind a dummy instance URL) | A run against a real ServiceNow instance; adapters for the deploy pipeline, Prometheus, log search, Jira, runbook wiki, team directory |
| Use case 1 | Evidence builder, 8 detectors, validation, replay, shadow mode, feedback and report | Traces, multi-service correlation, post-incident report drafting, webhook into the shadow inbox |
| Use case 2 | 7 checks, repeat clusters, overdue actions, recommendations, drafted edits with validation, per-team review queue, feedback, evaluation | Publishing approved edits back to the wiki (deliberately not built), reading the wiki's revision history |
| Use case 3 | Requirement document intake with quote and figure checks, option-by-NFR assessment, ranking, ADR conflicts, open questions, drafted ADR and stories with validation, NFR traceability, Mermaid container diagram, proposal pack as Markdown and an HTML page, approver feedback, evaluation | Reading Word or PDF directly (export to Markdown first), diagrams for options other than the preferred one, cost estimates (left to Licensing & TCO), writing approved ADRs and stories to the repository or Jira (deliberately not built) |
| Platform | Core package, plugin contract, one `ecc` CLI, product configuration with strict validation and environment overrides, a package per use case | Per-environment configuration files, secrets from a vault, a service deployment |
| Model | Mock (default) and one Claude Opus 5.5 client in core, used by all three use cases; request shape tested offline | A paid run with Claude. Commands are ready: `ecc incident replay --provider claude`, `ecc knowledge evaluate --provider claude`, `ecc architecture evaluate --provider claude` |
| Governance | Policy-set risk and approval, append-only audit, secret redaction, injection flagging | Approval workflow and UI from the prototype; tamper-evident audit storage |
| Quality | 111 tests (36 core, 27 + 13 + 35 per use case), compile check, a test that use cases never import each other, every package built and installed in a clean virtualenv | CI pipeline |

### 5.6 Build, test and run

Python 3.11 or newer; nothing to install for the mock provider. Run from the repository root.

```bash
python -m pytest                                   # 111 tests across core and the three use cases, no network
python ecc.py use-cases                            # what is enabled
python ecc.py config validate                      # check config/product.toml and every data path

# Use case 1: incident investigation
python ecc.py incident replay                      # past incidents vs known causes
python ecc.py incident investigate use-cases/incident-investigation/data/synthetic/live/INC-1042.json
python ecc.py incident shadow run                  # new incidents -> review queue
python ecc.py incident shadow feedback INC-1042 --useful yes --confirmed-cause config_change --minutes 31 --by sam.sre
python ecc.py incident shadow report
python ecc.py incident servicenow pull             # ServiceNow history: alert-time files, labels, analysis
python ecc.py incident servicenow replay           # pull, then replay and score (dummy instance by default)

# Use case 2: knowledge & runbooks
python ecc.py knowledge evaluate                   # run checks + drafts, score against labels
python ecc.py knowledge feedback EDIT-RB-017-3-replace --accept yes --by ria.owner
python ecc.py knowledge report

# Use case 3: architecture & ADLC
python ecc.py architecture evaluate                # assess options, draft ADR + stories, score against labels
python ecc.py architecture run --requirement-doc use-cases/architecture-adlc/data/synthetic/requirement-document.md
#   -> runs/architecture/proposal/REQ-LOY-001.html: open in a browser
python scripts/screenshot_architecture.py          # regenerate the README screenshot (needs Edge or Chrome)
python ecc.py architecture feedback ADR-007 --accept yes --by arb.chair
python ecc.py architecture report

# Install as packages (optional): then `ecc ...` replaces `python ecc.py ...`
pip install -e core -e use-cases/incident-investigation -e use-cases/knowledge-runbooks -e use-cases/architecture-adlc

# With Claude (costs money; needs ANTHROPIC_API_KEY or an `ant auth login` profile)
pip install -e "core[claude]"
python ecc.py incident replay --provider claude    # or set provider = "claude" in config/product.toml, or ECC_PROVIDER=claude
python ecc.py knowledge evaluate --provider claude
python ecc.py architecture evaluate --provider claude
```

---

## 6. Decisions and trade-offs made during development

### 6.1 Shared by all three use cases

| Decision | Chosen | Alternative considered | Why |
|----------|--------|------------------------|-----|
| Agent shape | Code-controlled workflow with **one** model call and no tools | Autonomous agent loop that queries tools itself | Easier to test, audit and cost-control; the model cannot be talked into calling anything. A tool loop can come later, when evidence needs grow |
| Split of work | Code decides *whether* something is wrong; the model explains and drafts | Model does detection and wording | Detection becomes deterministic, testable and free; the model adds value where wording and judgement matter |
| Numbers | Computed in code; the model only cites them | Let the model read raw data | No arithmetic errors or invented figures |
| Citations | Every evidence ID checked in code; invalid claims removed and **counted** | Trust the model's citations | "Unsupported claims" and "rejected edits" become measured metrics |
| Default provider | Deterministic mock; Claude is opt-in | Claude by default | Free, reproducible tests and demos. Real model quality is measured deliberately |
| Model | Claude Opus 5.5 at effort `high`, structured JSON output, server-side refusal fallback | A cheaper model such as Claude Sonnet 5.5 | Low volume, high stakes. Replay and evaluation make it cheap to compare a cheaper model later on the same data |
| One model client | `ClaudeClient.complete_json` in core, used by all three use cases; each use case passes its own prompt and schema | A client per use case | One place for model settings, error handling and refusal handling |
| Untrusted text | Redact secrets, flag injection, wrap evidence as data, give the model no tools | Rely on the system prompt alone | Defence in depth: even a successful injection has nothing to act on |
| Approval | Set by policy tables in code | Let the model rate risk | The model cannot lower risk or skip approval; unknown action types default to the highest risk |
| Labels | Separate files that the pipelines never read | Labels next to the input data | Prevents the answer leaking into the result; a test enforces it for use case 1 |
| Dependencies | Standard library only (Python 3.11+, for `tomllib`); `anthropic` optional | Frameworks (LangChain, pandas, a database) | Runs anywhere; fewer supply-chain and approval hurdles for a pilot |
| Data access | JSON fixtures behind read-only interfaces | Connect real tools straight away | Proves the pipeline first; real adapters slot in behind the same interface |
| Audit | Append-only JSON Lines with correlation IDs | Database or WORM storage | Simple and inspectable for a pilot; production moves it to tamper-evident storage |
| Packaging | A core package plus one package per use case, loaded as plugins named in the configuration; one CLI | One package for everything; a separate service per use case | Each use case can be owned, tested, versioned and deployed on its own, while shared code stays in one place. Services can come once there is real load |
| Configuration | One TOML file for the product, strictly validated; each use case declares its settings and defaults | Settings spread across code constants, JSON files and flags | One place to see and change how the product behaves; a typo is an error, not a silent default |
| What is configurable | Data paths, model, thresholds, pilot gates, which use cases are on | Also approval and risk rules | Approval rules are governance: they change through code review, not a config edit |

### 6.2 Use case 1 — Incident investigation

| Decision | Chosen | Alternative considered | Why |
|----------|--------|------------------------|-----|
| Where reasoning starts | 8 rule-based detectors, then the model re-ranks and explains | Model-only investigation | Works with no model, gives the model a structured start, and gives evaluation a baseline to beat |
| ServiceNow access | Code reads ServiceNow through a read-only connector; the model gets no tools | Give the model the ServiceNow MCP server's tools | Keeps "nothing can act, everything is cited": records are gathered and checked by code, then cited by the model |
| What the investigator sees from a ticket | Fields known when it was opened, and changes before opening | The whole ticket | Close notes and the fix are the answer; showing them would make replay score 100% and prove nothing |
| Labels from resolution notes | A cause only with a verbatim quote; otherwise unlabelled and not scored | Infer a cause from vague notes | A guessed label makes accuracy meaningless; vague notes are reported as a data-quality finding instead |
| Dummy instance | `transport = "fixture"` behind a dummy URL; the HTTP path is tested against a local Table API stub | Mock the HTTP client only | The same code path runs end to end without credentials; switching to a real instance is a config change |
| Rollout order | Replay → shadow → (later) live assist | Shadow mode from day one | Replay has known answers and zero risk; shadow measures real usefulness without interfering with on-call |
| "Not established" | Below 0.5 confidence the answer is "cause not established", and that can be scored as correct | Always name a cause | A confident wrong lead costs more on-call time than an honest "unknown" |
| Confidence cap | 0.95 | Allow 1.0 | No investigation from partial evidence should look certain |
| Ruled-down alternatives | Kept and shown with contradicting evidence | Show only supported causes | Shows engineers what was checked, as in "traffic was flat (E4)" |
| Shadow output | Review queue for the SRE lead; on-call not paged, ticket not changed | Post into the incident channel | Zero interference during the pilot. The cost is no real-time help until after go/no-go |

### 6.3 Use case 2 — Knowledge & runbooks

| Decision | Chosen | Alternative considered | Why |
|----------|--------|------------------------|-----|
| What the model does | Drafts wording for 2 finding kinds only: broken reference and practice drift | Ask the model to audit every runbook | Detection stays deterministic and cheap; the model is used where wording matters |
| Recommendations | Fixed rules in code (validate, assign owner, create runbook, escalate) | Model-written recommendations | Predictable, testable, and approval needs are fixed per action |
| Quote check | An edit must quote the current step **exactly** | Accept paraphrased edits | Stops edits to text that doesn't exist and makes every edit a reviewable diff |
| Removed settings | Rejected if the new text still mentions a removed setting | Trust the draft | Catches the most common bad fix automatically |
| Publishing | Never: drafts go to a per-team review queue | Auto-publish low-risk edits | Runbooks are used under pressure; a person must own every change. No publish path exists |
| Retired owners | Work routes to the team that took over the services | Route to the retired team's name | Nobody reads a retired team's queue |
| Thresholds | Stale after 180 days; repeat if the same cause recurs within 90 days of the previous one | A fixed 90-day window from today | Linking consecutive incidents catches a pattern across Aug–Nov that a fixed window would split |
| Evaluation date | Fixed `as_of` date stored in the data | Today's date | Results are reproducible; in production `as_of` is the run date |

### 6.4 Use case 3 — Architecture & ADLC

| Decision | Chosen | Alternative considered | Why |
|----------|--------|------------------------|-----|
| Who designs the options | The architecture team's reference patterns, scored in code | Ask the model to invent architectures | Options stay within what the organisation can build and support; scoring is repeatable and explainable |
| How options are compared | One fixed rule per NFR category, every cell cited as evidence | Model judges fit | The comparison table is identical on every run and each cell shows its figures |
| Rejection | Failing any must-have NFR rejects an option, with the condition under which it would become viable | Weighted total score | A weighted score can hide a residency failure behind good latency; a rejection with a condition is easier to discuss |
| Missing targets | "Unknown", shown as a gap and turned into an open question | Assume a typical target | A guessed cost ceiling looks like a requirement; an open question gets it decided |
| Model disagrees with the ranking | Kept and flagged for the review board; a rejected option is never accepted | Reject any disagreement | The ranking is a rule set, not the final word, but a must-have failure is not negotiable in a draft |
| Invented figures | Any number in drafted text must appear in the evidence | Trust the drafted numbers | ADRs and acceptance criteria are where invented numbers do lasting harm; the count becomes a measured metric |
| Acceptance criteria | Must state each covered NFR's numeric target | Free-form criteria | Makes stories testable against the NFR and traceability checkable in code |
| Approvals | ADR by the architecture review board, each story by the product owner | One approval for the whole pack | Matches who owns each decision today |
| Output | Proposal pack in Markdown; no write to the ADR repository or Jira | Open a pull request on the ADR repository | Zero risk during the pilot; a pull request is the natural next step once drafts are trusted |
| Cost | Relative cost from the pattern library only | Estimate cloud cost here | Cost estimates belong to Licensing & TCO with open formulas; until a ceiling is agreed, cost is an open question |
| Requirement documents | Model extracts with a word-for-word quote per item; code checks every quote and parses every target from it | Trust the model's extraction, or require the structured form only | Teams write documents, not JSON; the quote check makes each extracted item traceable to a line of the document, and targets cannot be invented |
| Missing targets in a document | Kept empty and marked "not agreed" | Let the model infer a typical value | The same rule as for structured input: guesses become open questions instead |
| Extracted requirement | Marked "needs requester confirmation" in the proposal pack | Treat it as confirmed | The requester owns the requirement; a misread NFR would skew the whole assessment |
| Who draws the diagram | Code, from the pattern library's components and connections | Ask the model to draw it | A drawn component that doesn't exist is worse than no diagram; code can only draw what the architecture team defined |
| Diagram format | Mermaid text in the proposal pack and a `.mmd` file | PNG/SVG image, or C4-PlantUML | Renders in GitHub, GitLab, Azure DevOps, VS Code and Confluence; diffs in review; no image toolchain in the package |
| What the diagram shows | Each component labelled with the NFRs traced to it; one cell drawn for all regions | One diagram per region | Ties the picture to the traceability matrix, and stays readable as regions are added |
| Proposal page | Static HTML written by every run from `results.json`, in the prototype's visual style | A web app with a server | Opens anywhere with no install, and shows exactly what the run produced; the approval UI comes later with the shared approval workflow |
| Mermaid renderer | Loaded from a pinned CDN version; without network the diagram source is shown | Bundle the renderer into the page | Keeps each page small; the source stays readable offline |
| README screenshot | Taken from a real run by a script, with headless Edge or Chrome | Hand-made image or a prototype mockup | The picture can't drift from what the code does; anyone can regenerate it |

### 6.5 Decisions made while building

| Situation | Decision | Why |
|-----------|----------|-----|
| Windows console could not print "≥" and "✅" (cp1252) | CLI switches stdout and stderr to UTF-8 | Same output on Windows, macOS and Linux |
| Runbook IDs in the prototype and the code disagreed (RB-052) | Renumbered the certificate runbook to RB-055, so RB-052 is "Ledger replay", as in the prototype screens | One consistent story across the prototype, deck and code |
| Data files needed an author and generator note, but JSON has no comments | A `_meta` block in each data file; readers ignore it | Every file is attributed without breaking the schema |
| `setuptools>=68` failed on the local Python (65.5) | Build requirement lowered to `setuptools>=61`, the first version with `pyproject.toml` support | The wheel builds on older toolchains too |
| No linter installed locally | Compile check and a standard-library static import check, rather than installing tools into the user's environment | Keeps the build dependency-free; add `ruff` in CI later |
| An installed wheel doesn't include the sample data | Data paths come from `config/product.toml`, resolved against the repository root | Running from the repository works out of the box; production points the configuration at real sources |
| The first diagram layout (left to right) was too wide to read once scaled into the page | Top-to-bottom layout, a shorter cell title so arrows don't cross it | Found by looking at the rendered screenshot, not the Mermaid text |
| All three use cases lived in one package named after the first (`incident-investigator`) | Split into `core/` and one folder and package per use case, with the product configuration in one file | Each use case can now be maintained, tested and installed on its own |
| Use case 2 imported the runbook loader from use case 1, and the Claude provider had one method per use case | The loader moved to core; core keeps one generic `complete_json`, and each use case owns its prompt, schema and small adapter | Removes every dependency between use cases; a new use case needs no change in core |
| Thresholds were module constants and gates were a separate JSON file | Both moved to `config/product.toml`, passed into the code as small typed values (`Limits`, `Thresholds`, `Rules`) | Configurable without global state; defaults stay documented in code and tested to match the file |
| `tomllib` needs Python 3.11 | Minimum raised from 3.10 to 3.11 | A configuration file people can comment is worth it; 3.10 reaches end of life in 2026 |
| A secret redacted during the ServiceNow pull was counted again by the investigator (`password=[REDACTED]` matched the pattern) | Redaction made idempotent; the pull records its own redactions in the audit log | Each redaction is counted once, where it happened. Found by a test |
| Mock results looked perfect (8/8, 9/9, 44/44) | Stated plainly in the README and in every generated report | The synthetic data was written alongside the rules; perfect scores prove the plumbing, not accuracy |

---

## Files (in `docs/stakeholder/`)

| File | What it is | How to open |
|------|------------|-------------|
| [`problem-statement-and-positioning.html`](docs/stakeholder/problem-statement-and-positioning.html) | Pre-read: problem, positioning, value by stakeholder, decision requested | Open in any browser |
| [`prototype/command-centre-prototype.html`](docs/stakeholder/prototype/command-centre-prototype.html) | Clickable product mockup for the live demo | Open in any browser (no server or install needed) |
| [`presentation/source/`](docs/stakeholder/presentation/source/) | Source of the 15-slide stakeholder deck (`deck.json` + one HTML file per slide, with speaker notes) | Edit as source; present from the online deck |
| [`presentation/`](docs/stakeholder/presentation/) *(add the .pptx here)* | PowerPoint export of the deck | Download from the online deck, see below |
| [`screenshots/`](docs/stakeholder/screenshots/) | Prototype screenshots used in this README | Any image viewer |

### Online versions (private until shared)

- Positioning page: https://claude.ai/artifact/BF2GhjwFngYhd7Ft13Agzg
- Prototype: https://claude.ai/artifact/VyjMUX2orG3Sdo8CpeS5qT
- Deck: https://claude.ai/artifact/7uEePDma7T5Ar4MmG8b912

### Getting the PowerPoint file

The slide files in `docs/stakeholder/presentation/source/` use the online deck viewer's format and are not a
standalone presentation. To get a `.pptx`, open the deck link above, download it as PowerPoint from
the deck's menu, and save it as `docs/stakeholder/presentation/engineering-command-centre-stakeholder-briefing.pptx`.

### Suggested demo path (about 5 minutes)

1. **Overview**: every KPI names the records it was calculated from.
2. **Production support**: INC-1042. Show the evidence panel, hypothesis confidence,
   "could not establish", and the flagged prompt-injection log line.
3. Click **Request approval** on the simulated rollback.
4. **Approvals**: as the SRE you cannot approve your own request. Switch **Viewing as** to
   Platform admin and approve it with a written reason.
5. **Audit log**: the request and the decision are recorded.

Optional extension (about 3 minutes), for engineering and platform leads:

6. **Change risk**: the `loyalty-ledger` release repeats the pool-size change behind INC-1042.
   Show how the score is built from weighted factors, and that 7 or more needs a second approver.
7. **Knowledge & runbooks**: RB-017, the runbook used in INC-1042, is stale, and the same cause has
   recurred three times. Show the draft edit going to the owning team for review.
8. **Service catalogue**: `notification-worker` has no owner and runs on an unsupported runtime.
   Show the blast radius and the "could not establish" note.

Optional platform and people extension (about 4 minutes), for platform, data, security and
engineering-management leads:

9. **API contracts**: the same `loyalty-ledger` release renames an event field. Show the consumer
   that would break silently, and the drafted migration notice.
10. **Capacity planning** and **Resilience & DR**: the ledger is short of capacity for the next
    peak and its DR plan has never been drilled. Request the sandbox drill.
11. **Access review** and **Joiners & leavers**: a leaver still has database access; another leaver's
    services, runbooks and approvals get proposed new owners. Point out that the agent never changes
    access itself.

### Before presenting

Fill in the bracketed placeholders: presenter name and date, pilot services, observability tool,
Jira instance, sponsor and SRE lead names, budget, and success targets.
