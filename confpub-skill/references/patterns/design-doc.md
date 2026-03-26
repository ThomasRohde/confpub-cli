# Pattern: Technical Design Document

For features or systems needing detailed design before implementation.

**Labels:** `design-doc`, `in-review`, plus domain label

## Template

```markdown
---
labels:
  - design-doc
  - in-review
---

# Technical Design: Feature Name {status:In Review|colour=Purple}

{toc:maxLevel=3}

::: panel Summary
One paragraph: what this covers, the problem it solves, target timeline.
Self-contained for a skip-level reader.
:::

## Authors & Reviewers

| Role | Name | Status |
|------|------|--------|
| Author | @engineer | {status:Complete\|colour=Green} |
| Reviewer (Backend) | @senior | {status:Pending\|colour=Yellow} |
| Reviewer (Security) | @security | {status:Pending\|colour=Yellow} |
| Approver | @tech-lead | {status:Pending\|colour=Yellow} |

## Problem Statement

What specific problem? Include impact metrics.

## Goals and Non-Goals

:::: layout two-equal
::: cell
### Goals
- Goal 1 with measurable outcome
- Goal 2 with acceptance criteria
:::
::: cell
### Non-Goals
- Explicitly out of scope item 1
- Future consideration, not now
:::
::::

## System Context

How this fits into the broader system. Embed a diagram if helpful.

## Detailed Design

### API Contract

```json
POST /api/v2/resources
{
  "name": "string",
  "config": { "timeout_ms": 5000 }
}
```

### Data Model

```sql
CREATE TABLE resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Alternatives Considered

::: expand Option B: Alternative Approach
Why rejected, with specific technical reasoning.
:::

::: expand Option C: Another Alternative
Why rejected.
:::

## Security Considerations

> [!CAUTION]
> Authentication, authorization, data exposure, input validation.
> Link to threat model if one exists.

## Operational Considerations

- **Monitoring:** Metrics and alerts needed
- **Rollback:** How to undo if something goes wrong
- **Migration:** Data migration required
- **Performance:** Expected load and resource needs

## Open Questions

- [ ] Question 1 — assigned to @person
- [x] Question 3 — resolved: using approach X

## References

- [Related ADR](ADR-NNN Title)
- {jira:PROJ-789}
```

## Tips

- The Goals/Non-Goals layout is one of the most valuable elements — it prevents scope creep visually.
- Use expand blocks for rejected alternatives so readers can skip them but reviewers can dig in.
- The Authors & Reviewers table with status lozenges creates a lightweight approval workflow.
