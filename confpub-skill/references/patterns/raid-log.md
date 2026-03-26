# Pattern: RAID Log

Risks, Assumptions, Issues, Dependencies tracker.

**Labels:** `raid`, `project-management`, plus project label

## Template

```markdown
---
labels:
  - raid
  - project-management
---

# RAID Log: Project Name {status:Active|colour=Blue}

::: panel Last Updated
2026-03-20 by @project-manager
:::

{toc:maxLevel=2}

## Risks

| ID | Risk | Likelihood | Impact | Mitigation | Owner | Status |
|----|------|-----------|--------|------------|-------|--------|
| R1 | Vendor API changes | Medium | High | Pin API version, compatibility layer | @tech-lead | {status:Open\|colour=Yellow} |
| R2 | Key engineer leaving | Low | High | Cross-training, pair programming | @eng-mgr | {status:Mitigated\|colour=Green} |
| R3 | Performance targets missed | Medium | Medium | Early load testing Sprint 15 | @perf-eng | {status:Open\|colour=Yellow} |

## Assumptions

| ID | Assumption | Validated | Impact if Wrong |
|----|-----------|-----------|-----------------|
| A1 | Vendor sandbox by March 15 | {status:Yes\|colour=Green} | 2-week delay |
| A2 | Existing auth supports OAuth2 | {status:No\|colour=Red} | Auth service changes needed |
| A3 | Max 1000 concurrent sessions | {status:Pending\|colour=Yellow} | Architecture revisit |

## Issues

| ID | Issue | Severity | Owner | Status | Ticket |
|----|-------|----------|-------|--------|--------|
| I1 | Sandbox intermittently down | {status:Medium\|colour=Yellow} | @vendor | {status:Open\|colour=Yellow} | {jira:PROJ-456} |
| I2 | Test data contains PII | {status:High\|colour=Red} | @data-eng | {status:In Progress\|colour=Blue} | {jira:PROJ-478} |

## Dependencies

| ID | Dependency | Provider | Needed By | Status |
|----|-----------|----------|-----------|--------|
| D1 | OAuth2 scopes | Auth team | 2026-04-01 | {status:On Track\|colour=Green} |
| D2 | SSL certificates | Infra team | 2026-03-25 | {status:At Risk\|colour=Yellow} |
| D3 | Legal approval | Legal | 2026-04-15 | {status:Pending\|colour=Yellow} |
```

## Tips

- Status lozenges in every table make the RAID scannable at a glance.
- The Assumptions table with validated status prevents "we assumed X" surprises.
- Link Issues to Jira tickets for tracking.
- Update the "Last Updated" panel to signal freshness — stale RAIDs are misleading.
