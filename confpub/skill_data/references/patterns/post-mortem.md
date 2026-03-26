# Pattern: Incident Post-Mortem

Written within 48 hours of resolution. Blameless, focused on systemic improvements.

**Labels:** `post-mortem`, `incident`, plus severity and service

## Template

```markdown
---
labels:
  - post-mortem
  - incident
---

# Post-Mortem: Brief Incident Title {status:Complete|colour=Green}

::: panel Incident Summary
| Field | Value |
|-------|-------|
| **Severity** | {status:SEV-2\|colour=Red} |
| **Duration** | 2026-03-10 14:23 – 15:47 UTC (84 min) |
| **Impact** | 12% of checkout transactions failed |
| **Detection** | Automated alert (PaymentErrorRate) |
| **Responders** | @eng-1, @eng-2, @oncall-lead |
| **Related** | {jira:INC-567} |
:::

{toc:maxLevel=2}

## What Happened

One-paragraph narrative for someone with no context.

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 14:15 | Deploy payment-service v2.14.3 begins |
| 14:23 | Alert: PaymentErrorRate > 1% |
| 14:25 | On-call acknowledges |
| 14:32 | Root cause: migration timeout |
| 14:40 | Decision to rollback |
| 14:45 | Rollback initiated |
| 15:47 | All-clear, incident resolved |

## Root Cause

Specific technical explanation. "Database migration acquired a table lock
blocking all writes for 45 minutes — ALTER TABLE on 200M-row table without
CREATE INDEX CONCURRENTLY."

## Contributing Factors

- Migration not tested against production-size dataset
- No migration duration limits in pipeline
- No canary deployment for DB-heavy releases

## What Went Well

- Alert fired within 8 minutes
- Root cause identified in 7 minutes
- Clear escalation path followed

## What Went Poorly

- Rollback took 45 minutes (manual steps)
- No automated rollback trigger
- Staging DB has 1% of production data

## Action Items

| Action | Owner | Priority | Ticket |
|--------|-------|----------|--------|
| Migration duration check in CI | @eng-1 | {status:P1\|colour=Red} | {jira:PLAT-890} |
| Automated rollback on error spike | @eng-2 | {status:P1\|colour=Red} | {jira:PLAT-891} |
| Seed staging with prod-scale data | @data | {status:P2\|colour=Yellow} | {jira:DATA-345} |

## Lessons Learned

> [!IMPORTANT]
> Database migrations touching large tables need duration testing against
> production-scale data. "Worked in staging" is not sufficient validation.
```

## Tips

- Incident Summary panel is the most-read section — keep it factual and complete.
- Timeline should be UTC with 1-line entries. It's the forensic record.
- Action Items table with Jira links and priority lozenges creates accountability.
- "What Went Well" prevents post-mortems from being purely negative.
