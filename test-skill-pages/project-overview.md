# Project Phoenix Overview {status:On Track|colour=Green}

::: panel Project Summary
| Field | Value |
|-------|-------|
| **Project** | Phoenix — Next-gen payment platform |
| **Sponsor** | VP Engineering |
| **Lead** | Thomas Rohde |
| **Timeline** | Q1–Q3 2026 |
| **Status** | {status:On Track\|colour=Green} |
:::

{toc:maxLevel=2}

## Health Dashboard

:::: layout three-equal
::: cell
### Schedule
{status:On Track|colour=Green}

Sprint 14 of 18 complete
**78% through timeline**

Key milestone: Beta launch April 15
:::
::: cell
### Budget
{status:At Risk|colour=Yellow}

$340K of $400K spent
**85% consumed at 78% progress**

Variance driven by cloud costs
:::
::: cell
### Quality
{status:Good|colour=Green}

0 P1 bugs open
Test coverage: 87%
**P99 latency: 142ms**
:::
::::

## KPI Summary

::: html
<style>
  .kpi-row { display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0; }
  .kpi-card {
    flex: 1; min-width: 140px; padding: 20px;
    border-radius: 8px; text-align: center; border: 1px solid #DFE1E6;
  }
  .kpi-card .value { font-size: 32px; font-weight: 700; margin: 0; }
  .kpi-card .label { font-size: 12px; color: #6B778C; margin: 4px 0 0; text-transform: uppercase; letter-spacing: 0.5px; }
  .kpi-card.success { background: #E3FCEF; border-color: #36B37E; }
  .kpi-card.success .value { color: #006644; }
  .kpi-card.warning { background: #FFFAE6; border-color: #FFAB00; }
  .kpi-card.warning .value { color: #FF8B00; }
  .kpi-card.danger { background: #FFEBE6; border-color: #FF5630; }
  .kpi-card.danger .value { color: #DE350B; }
  .kpi-card.info { background: #DEEBFF; border-color: #0065FF; }
  .kpi-card.info .value { color: #0747A6; }
</style>
<div class="kpi-row">
  <div class="kpi-card success">
    <p class="value">99.97%</p>
    <p class="label">Uptime (30d)</p>
  </div>
  <div class="kpi-card success">
    <p class="value">142ms</p>
    <p class="label">P95 Latency</p>
  </div>
  <div class="kpi-card warning">
    <p class="value">87%</p>
    <p class="label">SLO Budget</p>
  </div>
  <div class="kpi-card info">
    <p class="value">14</p>
    <p class="label">Sprints Done</p>
  </div>
</div>
:::

## Milestone Tracker

| Milestone | Target | Status | Notes |
|-----------|--------|--------|-------|
| Core Platform | 2026-01-31 | {status:Complete\|colour=Green} | Delivered on time |
| Payment Integration | 2026-03-31 | {status:In Progress\|colour=Blue} | Sprint 14 — on track |
| Beta Launch | 2026-04-15 | {status:On Track\|colour=Green} | 12 beta customers confirmed |
| GA Release | 2026-05-01 | {status:At Risk\|colour=Yellow} | Pending security audit |
| Post-GA Hardening | 2026-05-31 | {status:Not Started\|colour=Yellow} | Planned |

## Team Structure

:::: layout two-equal
::: cell
### Squad Atlas (Payments)
**Lead:** @atlas-lead · 6 engineers
{status:Fully Staffed|colour=Green}

Current focus: Payment gateway integration with Stripe and Adyen. Webhook handlers and retry logic.
:::
::: cell
### Squad Phoenix (Platform)
**Lead:** @phoenix-lead · 4 engineers
{status:Hiring 1|colour=Blue}

Current focus: Infrastructure, CI/CD, monitoring. Cloud cost optimization.
:::
::::

## Active Risks

| Risk | Impact | Mitigation | Owner | Status |
|------|--------|------------|-------|--------|
| Security audit delayed 2 weeks | {status:High\|colour=Red} | Escalated to CISO, parallel prep | @security-lead | {status:Open\|colour=Yellow} |
| Cloud costs exceeding budget | {status:Medium\|colour=Yellow} | Reserved instances, right-sizing | @infra-lead | {status:In Progress\|colour=Blue} |
| Key engineer PTO during beta | {status:Low\|colour=Green} | Knowledge transfer complete | @atlas-lead | {status:Mitigated\|colour=Green} |

## Key Decisions

> [!NOTE]
> Architecture decisions are documented as ADRs in child pages below.

| Decision | Date | Status | ADR |
|----------|------|--------|-----|
| Use PostgreSQL as primary datastore | 2026-02-15 | {status:Accepted\|colour=Green} | [ADR-001](ADR-001 Use PostgreSQL for Phoenix) |
| Stripe primary, Adyen fallback | 2026-03-10 | {status:Accepted\|colour=Green} | — |
| Event-driven architecture for webhooks | 2026-03-15 | {status:Proposed\|colour=Yellow} | — |

## Action Items

- [ ] Complete security audit pre-work by April 1
- [ ] Finalize beta customer onboarding guide
- [ ] Set up production monitoring dashboards
- [x] Hire 1 additional platform engineer
- [x] Complete payment gateway client library

## Child Pages

{children:sort=title}
