# Pattern: Retrospective

Sprint or project retrospective. Three-column layout for scanning.

**Labels:** `retrospective`, plus team label

## Template

```markdown
---
labels:
  - retrospective
  - squad-atlas
---

# Sprint 14 Retrospective {status:Complete|colour=Green}

::: panel Metadata
| | |
|---|---|
| **Date** | 2026-03-25 |
| **Facilitator** | @scrum-master |
| **Attendees** | @eng-1, @eng-2, @eng-3, @eng-4, @product-owner |
:::

:::: layout three-equal
::: cell
### What Went Well
- Payment integration ahead of schedule
- Pair programming improved knowledge sharing
- E2E tests caught 3 regressions
:::
::: cell
### What Didn't Go Well
- Third-party sandbox down 2 days
- Reconciliation report underestimated 60%
- Stand-ups ran over 15 minutes
:::
::: cell
### Ideas / Experiments
- Mob programming for complex work
- Mock server for third-party APIs
- Timeboxed stand-ups with parking lot
:::
::::

## Action Items

| Action | Owner | Due | Status |
|--------|-------|-----|--------|
| Set up WireMock for payment API | @eng-3 | Sprint 15 | {status:To Do\|colour=Yellow} |
| Standup timer (15 min hard stop) | @sm | Next standup | {status:To Do\|colour=Yellow} |
| Spike: report complexity | @eng-4 | Sprint 15 Day 2 | {status:To Do\|colour=Yellow} |

## Previous Action Items

| Action (Sprint 13) | Status |
|---------------------|--------|
| Improve test data seeding | {status:Done\|colour=Green} |
| Document deployment process | {status:Carried Over\|colour=Yellow} |
```

## Tips

- The three-column layout is the standard retrospective format — it lets the team see all three categories at once.
- Previous Action Items section creates accountability across sprints.
- Keep items brief (one line each). The discussion happened in person; this is the record.
