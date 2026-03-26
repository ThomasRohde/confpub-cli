# Containers: Panels, Expand, Admonitions, Excerpts

## Panels

Titled information boxes with a visible header bar. Use for decisions, summaries, key takeaways — anything that should draw the reader's eye.

```markdown
::: panel Decision
We will use PostgreSQL 16 as our primary data store.
:::

::: panel Prerequisites
- Access to the staging environment
- VPN configured for database access
:::
```

Title is optional: `::: panel` without text creates a box with no header.

Panel body supports full Markdown: lists, tables, code blocks, bold/italic, links. Panels cannot nest inside other panels or admonitions.

## Admonitions

GitHub-flavored alert syntax → native Confluence info/tip/warning/note macros.

```markdown
> [!NOTE]
> Background context. Renders as blue info box.
> Supports **multiple lines** and full Markdown.

> [!TIP]
> Best practice or helpful advice. Green tip box.

> [!WARNING]
> Caution needed. Yellow warning box.

> [!CAUTION]
> Serious risk — data loss, security, outage. Red note box.

> [!IMPORTANT]
> Critical information. Yellow warning box (same as WARNING).
```

Admonitions support bold, italic, code, links, and lists inside. They do NOT support nested containers (no panels, expands, or layouts inside).

## Expand Blocks

Collapsible sections. Content is hidden by default — the reader clicks to open. Use for supplementary details, long code samples, historical context, verbose logs.

```markdown
::: expand Click to see the full error trace
```java
java.lang.NullPointerException
    at com.example.Service.process(Service.java:42)
```
:::

::: expand Historical context (optional reading)
This system was originally designed in 2019 when...
:::
```

Expand body supports full Markdown including code blocks, tables, lists, and even panels.

## Excerpts

Mark content as reusable — other pages can include it via `{excerpt-include:This Page Title}`.

```markdown
::: excerpt
This is the reusable summary. Keep it self-contained — it will
appear on other pages without its surrounding context.
:::
```

Hidden excerpt (invisible on this page, only available for inclusion):
```markdown
::: excerpt hidden
Content available via excerpt-include but not shown here.
:::
```

## When to Use Which

| Situation | Container | Why |
|-----------|-----------|-----|
| Key decision or conclusion | Panel | Draws the eye with header bar |
| Background context | `> [!NOTE]` | Distinct but doesn't demand attention |
| Setup steps or advice | `> [!TIP]` | Green = constructive/positive |
| Risk, breaking change | `> [!WARNING]` | Yellow = caution |
| Data loss, security, outage | `> [!CAUTION]` | Red = danger |
| Long details most skip | Expand | Keeps page scannable |
| Reusable on other pages | Excerpt | DRY principle for docs |
