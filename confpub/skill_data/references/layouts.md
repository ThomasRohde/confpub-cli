# Layouts: Multi-Column Page Design

Confluence's native layout system for multi-column content. Use for dashboards, comparisons, side-by-side content.

## Layout Types

| Type | Columns | Split | Use Case |
|------|---------|-------|----------|
| `single` | 1 | 100% | Full width (rarely needed explicitly) |
| `two-equal` | 2 | 50/50 | Side-by-side comparison |
| `two-three` | 2 | 33/67 | Sidebar + main content |
| `three-equal` | 3 | 33/33/33 | Status overview, team structure |
| `three-two-three` | 3 | 25/50/25 | KPIs flanking central detail |

## Syntax

Outer `:::: layout <type>` with inner `::: cell` blocks. Cell count must match column count.

```markdown
:::: layout two-equal
::: cell
### Left Column
Content here.
:::
::: cell
### Right Column
Content here.
:::
::::
```

```markdown
:::: layout three-equal
::: cell
**Column 1**
:::
::: cell
**Column 2**
:::
::: cell
**Column 3**
:::
::::
```

## Composition Patterns

### Sidebar + Main (two-three)

Navigation or metadata on the left, content on the right.

```markdown
:::: layout two-three
::: cell
::: panel Quick Links
- [API Reference](API Reference)
- [Runbooks](Runbooks)
:::

::: panel Contacts
| Role | Person |
|------|--------|
| Lead | @lead |
| On-call | @oncall |
:::
:::
::: cell
## Main Content
Primary content goes here...
:::
::::
```

### Comparison (two-equal)

Side-by-side evaluation of options.

```markdown
:::: layout two-equal
::: cell
### Option A: Build
**Cost:** $150K + $30K/yr
**Timeline:** 4 months
**Risk:** {status:Medium|colour=Yellow}

- Full control
- No vendor dependency
:::
::: cell
### Option B: Buy
**Cost:** $50K/yr
**Timeline:** 2 weeks
**Risk:** {status:Low|colour=Green}

- Immediate availability
- Vendor handles maintenance
:::
::::
```

### Triple Overview (three-equal)

Status dashboards, capability overviews.

```markdown
:::: layout three-equal
::: cell
### Frontend
{status:Healthy|colour=Green}
Build time: 45s
:::
::: cell
### Backend
{status:Degraded|colour=Yellow}
P99 latency: 280ms
:::
::: cell
### Infrastructure
{status:Healthy|colour=Green}
Monthly: $12.4K
:::
::::
```

## Rules

- Cell count must match layout type (2 cells for two-column, 3 for three-column)
- **Do not nest** layouts inside layouts — Confluence doesn't support it
- Content outside layout blocks is auto-wrapped in a `single` layout
- Panels, admonitions, tables, code blocks all work inside cells
- Avoid wide tables in narrow columns — use `two-equal` or `single` for wide tables
