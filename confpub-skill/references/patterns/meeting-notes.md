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
| **Date/Time** | 2026-03-20, 14:00–15:00 CET |
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
Key points...

### Payment Gateway Vendor Selection

::: panel Decision
Selected Stripe as primary, Adyen as fallback.
Rationale: Stripe's developer experience and documentation.
:::

### Hiring Update
Status on open positions...

## Decisions

| # | Decision | Owner |
|---|----------|-------|
| 1 | Stripe as primary payment provider | @tech-lead |
| 2 | Defer mobile redesign to Q3 | @product-owner |

## Action Items

- [ ] @person-1: Draft Stripe proposal by 2026-03-27
- [ ] @person-2: Update project timeline
- [ ] @person-3: Schedule security review
- [x] @person-2: Share meeting notes (this page)
```

## Tips

- Decisions table separates outcomes from discussion noise.
- Panels around key decisions make them findable when scanning.
- Task list with `@owner: description by date` format is unambiguous.
- Status lozenge in title (`Final` vs `Draft`) signals completeness.
