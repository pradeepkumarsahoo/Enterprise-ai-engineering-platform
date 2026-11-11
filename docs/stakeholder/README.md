# Engineering Command Centre — Stakeholder Materials

Materials for the stakeholder review and pilot approval of the **Engineering Command Centre**,
a governed AI layer for the software lifecycle and production operations.

> Independently developed reference concept. All data shown is synthetic, and the prototype uses a
> deterministic mock AI provider. Nothing here is a production outcome.

![Command Centre overview](screenshots/01-overview.png)

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

*Qualitative assessment from discovery conversations. The pilot measures a real baseline in its
first two weeks rather than relying on industry figures.*

---

## 2. What it solves

The Command Centre is **one governed layer above the tools teams already use**. It reads their data
through read-only adapters, connects it into a single evidence trail, uses AI to help interpret it,
and keeps a named person accountable for every consequential action.

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
| Architecture & ADLC | Proposals, ADRs and NFR traceability from a structured requirement |
| Developer assistant | Scaffolds, test suggestions and PR review, shown as diffs for approval |
| Jira & delivery | Backlog generation, sprint risk, blocked and ageing work, release notes |
| Chaos engineering | Sandbox-only experiments with abort rules and SLO comparison |
| Licensing & TCO | Multi-year estimates with open formulas and editable prices |
| FinOps | Cost anomalies and recommendations; estimated and realised savings kept apart |
| Security | Findings prioritised by exposure and reachability; exceptions approved and tracked |
| Engineering intelligence | DORA-style measures at team level, never used to rank individuals |

**Built-in guardrails:** evidence before conclusions; permissions, money and state changes handled
by plain code and policy rather than the model; secrets redacted before any model call; logs,
tickets and code treated as untrusted input so they cannot override policy; synthetic, imported and
AI-generated data labelled as such.

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

**Proposed pilot:** eight weeks, read-only, incident investigation on [2–3 services] in shadow mode,
with a go/no-go review at week 8.

---

## 4. Screenshots from the prototype

All screens use synthetic data and the mock AI provider. Captured from
`prototype/command-centre-prototype.html` at 1440 px width.

### Overview — command centre
Open incidents, change failure rate, pending approvals and cloud spend. Each figure names the records
it comes from. Agent activity shows runs, failures, latency and estimated model cost.

![Overview](screenshots/01-overview.png)

### Production support — incident investigation (INC-1042)
`membership-api` latency rose tenfold after deploy v2.14. Latency and DB-pool charts mark the deploy.
The leading hypothesis (pool limit cut from 50 to 20) has a confidence score and links to evidence
E1–E7. A competing hypothesis is ruled down, and the "could not establish" list states what the
agent doesn't know. A prompt-injection attempt in the logs is flagged and ignored. Remediation steps
are simulated and need approval.

![Incident investigation](screenshots/02-incident-investigation.png)

### Approvals — human in the loop
Each request shows its risk, environment and the permission the decider needs. A written reason is
mandatory, and requesters cannot approve their own requests.

![Approvals](screenshots/03-approvals.png)

### Audit log
An append-only record of actor, action, target, outcome and correlation ID, including denied
actions such as a blocked tool call.

![Audit log](screenshots/04-audit-log.png)

### Architecture & ADLC
Two architecture options for a global loyalty platform compared against requirements, a container
view, NFR coverage with gaps, and open questions for the business. Marked as a draft for architect
review.

![Architecture](screenshots/05-architecture.png)

### FinOps
Monthly spend by team, a statistically flagged anomaly with its likely cause, and recommendations
that track estimated and realised savings in separate columns.

![FinOps](screenshots/06-finops.png)

### Licensing & TCO
A multi-year estimate with the formula shown, using a fictional vendor and fictional prices.

![Licensing and TCO](screenshots/07-licensing-tco.png)

### Engineering intelligence
DORA-style measures with sample sizes and date range, and bottlenecks by team. No individual
rankings.

![Engineering intelligence](screenshots/08-engineering-intelligence.png)

---

## Files in this folder

| File | What it is | How to open |
|------|------------|-------------|
| `problem-statement-and-positioning.html` | Pre-read: problem, positioning, value by stakeholder, decision requested | Open in any browser |
| `prototype/command-centre-prototype.html` | Clickable product mockup for the live demo | Open in any browser (no server or install needed) |
| `presentation/source/` | Source of the 13-slide stakeholder deck (`deck.json` + one HTML file per slide, with speaker notes) | Edit as source; present from the online deck |
| `presentation/` *(add the .pptx here)* | PowerPoint export of the deck | Download from the online deck, see below |
| `screenshots/` | Prototype screenshots used in this README | Any image viewer |

### Online versions (private until shared)

- Positioning page: https://claude.ai/artifact/BF2GhjwFngYhd7Ft13Agzg
- Prototype: https://claude.ai/artifact/VyjMUX2orG3Sdo8CpeS5qT
- Deck: https://claude.ai/artifact/7uEePDma7T5Ar4MmG8b912

### Getting the PowerPoint file

The slide files in `presentation/source/` use the online deck viewer's format and are not a
standalone presentation. To get a `.pptx`, open the deck link above, download it as PowerPoint from
the deck's menu, and save it as `presentation/engineering-command-centre-stakeholder-briefing.pptx`.

### Suggested demo path (about 5 minutes)

1. **Overview**: every KPI names the records it was calculated from.
2. **Production support**: INC-1042. Show the evidence panel, hypothesis confidence,
   "could not establish", and the flagged prompt-injection log line.
3. Click **Request approval** on the simulated rollback.
4. **Approvals**: as the SRE you cannot approve your own request. Switch **Viewing as** to
   Platform admin and approve it with a written reason.
5. **Audit log**: the request and the decision are recorded.

### Before presenting

Fill in the bracketed placeholders: presenter name and date, pilot services, observability tool,
Jira instance, sponsor and SRE lead names, budget, and success targets.
