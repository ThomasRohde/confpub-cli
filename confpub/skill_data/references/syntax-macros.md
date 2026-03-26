# Macros: Status, TOC, Children, Jira, Anchors, Includes

Generic macro syntax: `{macro-name:positional-param|key=value|key2=value2}`

## Status Lozenges

Colored pills for governance state, lifecycle, priority. Work **inline** — embed in table cells, headings, paragraphs.

```markdown
{status:Approved|colour=Green}
{status:Draft|colour=Yellow}
{status:Blocked|colour=Red}
{status:In Progress|colour=Blue}
{status:Under Review|colour=Purple}
```

Colors: `Green`, `Yellow`, `Red`, `Blue`, `Purple` (case-sensitive, British spelling `colour`).

**Critical: escape `|` inside table cells.** The pipe in `{status:Done|colour=Green}` is also the Markdown table column delimiter. Inside tables, escape it with `\|`. Outside tables (headings, paragraphs, layout cells), no escaping needed.

```markdown
## Database Migration {status:Approved|colour=Green}

| Component | Status |
|-----------|--------|
| API Gateway | {status:Done\|colour=Green} |
| Auth Service | {status:In Progress\|colour=Blue} |
```

## Table of Contents

```markdown
{toc}
{toc:maxLevel=3}
{toc:maxLevel=2|minLevel=1}
```

Add `{toc}` or `{toc:maxLevel=2}` near the top of any page with more than 3 sections.

## Children

List child pages of the current page.

```markdown
{children}
{children:depth=3|sort=title}
```

Use at the bottom of parent/index pages to auto-list sub-pages.

## Anchors

Named link targets within a page.

```markdown
{anchor:design-decisions}

<!-- Link to it from elsewhere on the same page: -->
[Jump to decisions](#design-decisions)
```

## Include / Excerpt Include

Embed another page's content (or excerpt) inline.

```markdown
{include:Shared API Reference}
{include:Common Setup Steps|space=DOCS}

{excerpt-include:Service Overview}
{excerpt-include:Auth Service|space=PLATFORM}
```

`include` embeds the full page. `excerpt-include` embeds only the content inside that page's `::: excerpt` block.

## Recently Updated

Show recently modified pages.

```markdown
{recently-updated}
{recently-updated:max=10}
```

## Jira Integration

### Single issue link
```markdown
{jira:PROJ-123}
```
Renders as a clickable issue with live status from Jira.

### JQL query (dynamic issue table)
```markdown
{jira:jql=project=PROJ AND status="In Progress"}
{jira:jql=assignee=currentUser() AND resolution=Unresolved}
{jira:jql=sprint in openSprints() AND project=PAY}
```
Renders as a table of matching Jira issues, updated in real-time.

## Page Links

Links to other Confluence pages — use the page title as the URL:

```markdown
[See the Architecture Overview](Architecture Overview)
[API docs](API Reference)
```

confpub auto-converts these to native Confluence page links (`ri:page` references). Link text can differ from page title. External URLs work normally.
