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

What is changing and why. Link to the driving feature or incident.

## Impact Assessment

| Area | Impact |
|------|--------|
| **Downtime** | None (online DDL) |
| **Performance** | Brief I/O spike (~5 min) |
| **Data** | No data loss; additive change |
| **Dependents** | None — new column is nullable |

## Implementation Plan

1. Run migration in staging, measure duration
2. Take database snapshot
3. Execute `ALTER TABLE` and `CREATE INDEX CONCURRENTLY`
4. Verify index and query plans
5. Update application config

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

- Rollback plan with `> [!WARNING]` about data implications is essential.
- Task list for approvals creates a visible sign-off trail.
- Link to the Jira ticket or feature that drives the change.
