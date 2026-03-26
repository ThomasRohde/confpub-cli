# Pattern: RFC (Request for Comments)

Proposals needing cross-team feedback before a decision.

**Labels:** `rfc`, `proposal`, plus domain label

## Template

```markdown
---
labels:
  - rfc
  - proposal
---

# RFC: Proposal Title {status:Open for Comments|colour=Blue}

::: panel Metadata
| Field | Value |
|-------|-------|
| **Purpose** | Proposal seeking cross-team feedback before a decision |
| **Author** | @author |
| **Status** | {status:Open for Comments\|colour=Blue} |
| **Created** | 2026-03-15 |
| **Deadline** | 2026-04-01 |
| **Stakeholders** | Platform, Security, Product |
:::

{toc:maxLevel=2}

## TL;DR

Two to three sentences. A busy VP should understand the proposal from this alone.

## Motivation

Why now? What changed?

## Proposal

The core of what you want to do. Be specific and concrete.

## Impact Assessment

| Area | Impact | Details |
|------|--------|---------|
| Performance | {status:Low\|colour=Green} | Benchmarks show no regression (assumption — verify under load) |
| Security | {status:Medium\|colour=Yellow} | New API endpoint requires auth review before launch |
| Cost | {status:High\|colour=Red} | Estimated ~$5K/month additional infra (based on current pricing) |
| Teams affected | {status:Medium\|colour=Yellow} | Platform and Mobile teams must update client integrations |

## Migration Plan

Describe each phase as a numbered step with a milestone and rollback trigger. Each step should produce a verifiable result before the next begins.

## Feedback

> [!NOTE]
> Leave comments directly on this page. Prefer inline comments on specific
> sections over general page comments.

- [ ] Platform team review
- [ ] Security review
- [ ] Product sign-off
```

## Status Lifecycle

| Status | Colour | When |
|--------|--------|------|
| `Open for Comments` | Blue | Accepting feedback |
| `Under Review` | Purple | Feedback period closed, decision pending |
| `Accepted` | Green | Approved for implementation |
| `Rejected` | Red | Not proceeding |
| `Withdrawn` | Red | Author withdrew |

## Tips

- The Impact Assessment table with status lozenges lets stakeholders scan for areas that affect their team without reading the full proposal.
- Set a deadline. Open-ended RFCs never close.
- Most stakeholders read only the TL;DR. Write it so a VP can approve or redirect without reading further.
