# Design Principles: Container Selection & Page Structure

## Container Nesting Rules

| Outer Container | Can Contain |
|----------------|-------------|
| `::: panel` | Paragraphs, lists, tables, code, inline macros, links |
| `::: expand` | Everything panel can, plus panels and admonitions |
| `> [!NOTE/TIP/...]` | Paragraphs, lists, bold/italic, code, links (no nested containers) |
| Layout `::: cell` | Everything — panels, expands, admonitions, tables, macros |
| `::: excerpt` | Same as panel content |
| `::: html` | Raw HTML only — no Markdown rendering inside |

## Anti-Patterns

**Don't nest layouts inside layouts.** Confluence doesn't support it.

**Don't put admonitions inside panels.** Two colored boxes nested looks messy. Pick one.

**Don't overuse panels.** If everything is highlighted, nothing stands out. Reserve for decisions, key findings, prerequisites.

**Don't put wide tables in narrow layout cells.** In `three-equal`, each column is ~33% width. Wide tables overflow.

## Effective Compositions

**Panel + task list** — Decision with follow-up actions:
```markdown
::: panel Decision: Use PostgreSQL
We will use PostgreSQL 16 based on team expertise and compliance needs.
:::

- [ ] Create migration plan by 2026-04-01
- [ ] Set up read replicas in staging
```

**Layout + panels** — Dashboard categories:
```markdown
:::: layout two-equal
::: cell
::: panel Current Sprint
Sprint 14 — 66% complete
:::
:::
::: cell
::: panel Next Milestone
Beta Launch — April 15
:::
:::
::::
```

**Expand for progressive detail:**
```markdown
## Summary
Brief overview everyone reads.

::: expand Technical Details
Detailed explanation for engineers...
:::

::: expand Business Context
Context for product managers...
:::
```

## Information Density Guide

| Content | Best Approach |
|---------|---------------|
| 1–3 values | Status lozenges inline |
| 4–8 KPIs | HTML macro cards (see `design-styling.md`) |
| Structured items with attributes | Table |
| Long procedure with branching | Headings + expand blocks |
| Side-by-side comparison | `two-equal` layout |
| Overview of 3 areas | `three-equal` layout |
| Metadata about the page | Panel at top |
| Content most readers skip | Expand block |
| Critical warning | `> [!WARNING]` or `> [!CAUTION]` |
| Supplementary context | `> [!NOTE]` |

## Standard Page Structure

Most pages benefit from this flow:

1. **Title with status** — `# Page Title {status:State|colour=Color}`
2. **Context panel** — Who, what, when, why in a `::: panel`
3. **TOC** — `{toc:maxLevel=2}` for pages with >3 sections
4. **Summary** — One paragraph or layout overview
5. **Detail sections** — The body of the page
6. **Action items** — Task lists at the bottom
7. **References** — Related pages, Jira links, external docs
8. **Child pages** — `{children}` if this is a parent page
