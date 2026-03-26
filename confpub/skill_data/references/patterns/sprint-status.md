# Pattern: Sprint / Iteration Status

Living page updated throughout the sprint. Layouts for visual scanning.

**Labels:** `sprint-status`, plus team label

## Template

```markdown
---
labels:
  - sprint-status
  - squad-atlas
---

# Sprint 14 Status {status:In Progress|colour=Blue}

::: panel Sprint Metadata
| Field | Value |
|-------|-------|
| **Sprint** | Sprint 14 (2026-03-11 → 2026-03-25) |
| **Goal** | Complete payment gateway integration |
| **Team** | Squad Atlas (6 engineers) |
| **Velocity** | Target: 34 SP · Committed: 32 SP |
:::

{toc:maxLevel=2}

## Health at a Glance

:::: layout three-equal
::: cell
### Delivery
{status:On Track|colour=Green}

21/32 story points (66%)
:::
::: cell
### Risks
{status:1 Active|colour=Yellow}

Third-party sandbox unstable
:::
::: cell
### Blockers
{status:None|colour=Green}

All blockers resolved
:::
::::

## Sprint Backlog

| Story | Points | Status | Owner |
|-------|--------|--------|-------|
| Payment gateway client | 8 | {status:Done\|colour=Green} | @eng-1 |
| Webhook handler | 5 | {status:In Progress\|colour=Blue} | @eng-2 |
| Retry logic | 5 | {status:In Progress\|colour=Blue} | @eng-3 |
| Reconciliation report | 8 | {status:To Do\|colour=Yellow} | @eng-4 |
| E2E tests | 3 | {status:Done\|colour=Green} | @eng-1 |

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation | Status |
|------|-----------|--------|------------|--------|
| Sandbox instability | High | Medium | Recorded responses for dev | {status:Monitoring\|colour=Yellow} |

## Key Decisions

1. **Idempotency keys for retry** — prevents duplicate charges ({jira:PAY-234})

## Carry-Over Risk

> [!NOTE]
> Reconciliation report (8 SP) may carry over if not started by Wednesday.
> Mitigation: split into generation (5 SP) + UI (3 SP).

## Jira Board

{jira:jql=sprint="Sprint 14" AND project=PAY ORDER BY status}
```

## Tips

- The three-column Health at a Glance carries the most weight — a manager should read it in 3 seconds.
- Status lozenges in the backlog table replace the need for a separate Jira board view.
- Update this page daily during standup or use confpub automation to refresh.
