# Pattern: Change Request

Impact assessment, implementation plan, rollback procedure, approvals.

**Labels:** `change-request`, `governance`

## Template

```markdown
---
labels:
  - change-request
  - governance
---

# CR-042: Brief Description {status:Pending Approval|colour=Yellow}

::: panel Change Summary
| | |
|---|---|
| **Requestor** | @engineer |
| **Change type** | {status:Standard\|colour=Blue} |
| **Risk level** | {status:Medium\|colour=Yellow} |
| **Target date** | 2026-04-01, 02:00 UTC (maintenance window) |
| **Duration** | ~45 minutes |
| **Approvers** | @tech-lead, @dba-lead |
:::

{toc:maxLevel=2}

## Description

State the concrete change (what) and the business or technical reason (why). Link to the originating Jira ticket, feature request, or incident.

## Impact Assessment

| Area | Impact |
|------|--------|
| **Downtime** | None (online DDL) |
| **Performance** | Brief I/O spike (~5 min) |
| **Data** | No data loss; additive change |
| **Dependents** | None — new column is nullable |

## Implementation Plan

1. Run migration in staging — confirm it completes in < 10 min and logs no errors
2. Take database snapshot — verify snapshot status shows `available`
3. Execute `ALTER TABLE` and `CREATE INDEX CONCURRENTLY` — confirm `ALTER TABLE` returns without error
4. Run `EXPLAIN ANALYZE` on key queries — confirm the new index appears in the plan
5. Update application config and deploy — verify health check returns 200

## Rollback Plan

> [!WARNING]
> Rollback drops the new column. Data written after migration will be lost.

```sql
DROP INDEX IF EXISTS idx_transactions_method;
ALTER TABLE transactions DROP COLUMN IF EXISTS payment_method;
```

## Approval

- [ ] Technical Lead approval
- [ ] DBA Lead approval
- [ ] Change Advisory Board (if High risk)
```

## Status Lifecycle

| Status | When |
|--------|------|
| `{status:Draft\|colour=Yellow}` | Being written |
| `{status:Pending Approval\|colour=Yellow}` | Awaiting sign-off |
| `{status:Approved\|colour=Green}` | Ready to execute |
| `{status:Executed\|colour=Green}` | Successfully applied |
| `{status:Rolled Back\|colour=Red}` | Reverted |

## Tips

- Always include a rollback plan with `> [!WARNING]` stating data-loss consequences — reviewers reject CRs without one.
- Task list for approvals creates a visible sign-off trail.
- Link to the Jira ticket or feature that drives the change so reviewers can trace the motivation.
