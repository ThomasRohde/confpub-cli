# Pattern: Meeting Notes

Structured meeting record with decisions and action items.

**Labels:** `meeting-notes`, plus team/project label

## Template

```markdown
---
labels:
  - meeting-notes
---

# Meeting: Topic — 2026-03-20 {status:Final|colour=Green}

::: panel Logistics
| | |
|---|---|
| **Purpose** | Weekly engineering sync — review OKRs, unblock vendor decision, hiring pipeline |
| **Date/Time** | 2026-03-20, 14:00–15:00 CET |
| **Owner** | @person-1 |
| **Attendees** | @person-1, @person-2, @person-3 |
| **Absent** | @person-4 (PTO) |
| **Note taker** | @person-2 |
:::

## Agenda

1. Review Q1 OKR progress
2. Payment gateway vendor selection
3. Hiring update

## Discussion

### Q1 OKR Progress

Three of five KRs are on track. KR-2 (reduce checkout latency to < 300ms P99) is blocked by the payment gateway migration — current P99 is 480ms. KR-5 (hire 2 senior engineers) is behind; see Hiring Update below.

### Payment Gateway Vendor Selection

::: panel Decision
Selected Stripe as primary, Adyen as fallback.
Rationale: Stripe's developer experience and documentation reduce estimated integration time from 6 weeks to 3.
:::

### Hiring Update

Two senior engineer roles open since February. Four candidates in pipeline: two at final round, two at phone screen. Target: extend one offer by end of March.

## Decisions

| # | Decision | Owner |
|---|----------|-------|
| 1 | Stripe as primary payment provider | @tech-lead |
| 2 | Defer mobile redesign to Q3 | @product-owner |

## Action Items

- [ ] @person-1: Draft Stripe integration proposal by 2026-03-27
- [ ] @person-2: Update project timeline with revised gateway milestones by 2026-03-28
- [ ] @person-3: Schedule security review for Stripe integration by 2026-04-03
- [x] @person-2: Share meeting notes (this page) by 2026-03-20
```

## Tips

- The Logistics panel states purpose, owner, and attendees upfront so readers know in seconds whether this meeting is relevant to them.
- Decisions table separates outcomes from discussion noise.
- Panels around key decisions make them findable when scanning.
- Every action item follows `@owner: description by date` format — no exceptions, no missing deadlines.
- Status lozenge in title (`Final` vs `Draft`) signals completeness.
