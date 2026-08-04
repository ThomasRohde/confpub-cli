# Macros: Status, TOC, Children, Jira, Anchors, Includes

Generic macro syntax: `{macro-name:positional-param|key=value|key2=value2}`

## Learned Site-Specific Macros

Marketplace and Forge apps can register different macro names and storage shapes on each Confluence site. Never guess a diagramming macro from its display name. Learn it from a known-good page using confpub itself:

```bash
confpub macro inspect --from-page <WORKING_PAGE_ID>
confpub macro learn --from-page <WORKING_PAGE_ID> --alias mermaid --dry-run
confpub macro learn --from-page <WORKING_PAGE_ID> --alias mermaid
confpub macro list
```

`macro inspect` classifies classic structured macros, attachment-backed macros, plain-text and rich-text bodies, and Forge ADF extensions. `macro learn` persists the selected contract under the configured Confluence URL, so another site can use the same alias with a different underlying app.

Invoke the learned profile with an explicit local source file:

```markdown
{macro:mermaid|source=diagrams/checkout-flow}
```

For attachment-backed macros, confpub uploads the source file and sets the learned attachment parameter to its basename. For plain-text, rich-text, and Forge body macros, confpub reads the UTF-8 source into the learned body shape. Body-less macros do not require `source`.

On `page pull`, attachment-backed sources reuse the downloaded attachment path. Embedded classic and Forge bodies are extracted into `assets/.../macro-sources/` and the generated `{macro:alias|source=...}` invocation points to that file, preserving the publish round-trip.

Use `--candidate N` when the sample page contains more than one macro. Keep the source file basename stable for attachment-backed apps, dry-run before publishing, and verify the browser-rendered page after publishing. Storage validity alone does not prove a Marketplace or Forge macro rendered successfully.

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
[Special title](<ADR-001: API & Settlement>)
```

confpub auto-converts these to native Confluence page links (`ri:page` references). Link text can differ from page title. External URLs work normally.

## Cloud Page Link Caveats

Bare Markdown link targets with spaces or special characters can be left as literal Markdown by the Markdown parser. Wrap page titles in angle brackets (`[text](<Page Title>)`) or use an absolute Confluence URL. Page-title links can also fail to resolve in Cloud when the title contains apostrophes, special characters, or points to a personal-space home page. If a rendered page shows literal Markdown such as `[Personal home](Example User's Home)`, use an absolute Confluence URL or inspect the target page and link by a stable URL.

For Cloud personal spaces, the overview URL is typically:

```text
https://example.atlassian.net/wiki/spaces/~username/overview
```
