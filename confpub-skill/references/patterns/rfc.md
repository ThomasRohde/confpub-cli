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
| Performance | {status:Low\|colour=Green} | No expected regression |
| Security | {status:Medium\|colour=Yellow} | New API needs auth review |
| Cost | {status:High\|colour=Red} | ~$5K/month additional infra |
| Teams affected | {status:Medium\|colour=Yellow} | Platform, Mobile |

## Migration Plan

Phased rollout with milestones and rollback criteria.

## Feedback

> [!NOTE]
> Leave comments directly on this page. Inline comments on specific
> sections preferred over general page comments.

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

- The Impact Assessment table with status lozenges is the key differentiator — it lets stakeholders quickly assess whether this RFC affects them.
- Set a deadline. Open-ended RFCs never close.
- The TL;DR section is critical — many stakeholders will read nothing else.
