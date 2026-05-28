# HTML Macro: Embedding Raw HTML

The escape hatch for anything Confluence's native formatting can't do. Preserves `<style>`, `<script>`, and `<iframe>` tags which Confluence normally strips.

## Basic Usage

```markdown
::: html
<style>
  .card { border: 2px solid #0052CC; padding: 16px; border-radius: 8px; }
</style>
<div class="card">
  <h3>Custom Styled Card</h3>
  <p>This HTML is preserved verbatim in Confluence.</p>
</div>
:::
```

Content inside `::: html` blocks is **not processed as Markdown** — it's raw HTML passed directly to Confluence's HTML macro.

## Asset Auto-Discovery

Local file references in `<script src="...">` and `<link href="...">` are automatically:
1. Discovered by confpub
2. Uploaded as Confluence attachments
3. URLs rewritten to Confluence attachment download paths

```markdown
::: html
<link rel="stylesheet" href="styles/dashboard.css">
<script src="scripts/chart.js"></script>
<div id="chart-container"></div>
:::
```

The CSS and JS files are uploaded alongside the page. Missing files produce warnings but don't block publishing.

Attachment URL rewriting makes local files loadable as page resources. It does not guarantee those URLs are readable through `fetch()` or XHR from every Cloud HTML macro app.

## Cloud HTML Macro Sandbox Behavior

In Confluence Cloud, HTML macros are often rendered by a Marketplace app inside a sandboxed iframe. The iframe origin can differ from the Confluence site origin. Attachment-backed scripts can load as browser resources, while `fetch()` to Confluence attachment URLs may fail due CORS.

| Pattern | Cloud behavior |
|---------|----------------|
| `<script src="local.js"></script>` | Often works after confpub uploads and rewrites the attachment URL |
| `<link rel="stylesheet" href="local.css">` | May work, warn, or fail depending on the macro app CSP |
| `fetch("data.json")` after URL rewrite | May fail because the macro iframe origin differs from Confluence |
| Data as JavaScript callback | More reliable than JSON fetch for attachment-backed data |

For Cloud interactive widgets, prefer loading data as a script callback:

```html
<script src="widget.js"></script>
```

`data.js`:

```javascript
(function (global) {
  var payload = { rows: [] };
  if (typeof global.__widgetDataReady === "function") {
    global.__widgetDataReady(payload);
  }
}(window));
```

Avoid examples that require `fetch()` to Confluence attachment URLs unless the page is explicitly testing CORS behavior.

## Cloud vs. Server/DC Macro Names

The HTML macro key is not guaranteed by hosting model alone.

| Environment | Typical macro key | Notes |
|-------------|-------------------|-------|
| Server/DC | `html` | Built-in or administrator-enabled HTML macro |
| Cloud | `html-macro` or `macro-html` | Depends on installed Marketplace app |

Override with:

```bash
confpub page publish page.md --html-macro-name macro-html
```

```yaml
---
html_macro_name: macro-html
---
```

To discover the key on a Cloud site, create or inspect a working HTML macro page and check its storage:

```bash
confpub page inspect --page-id PAGE_ID --raw
```

Look for:

```xml
<ac:structured-macro ac:name="...">
```

You can persist a known site key with `confpub config set html_macro_name macro-html` or `CONFPUB_HTML_MACRO_NAME=macro-html`.

## When to Use HTML Macro

Use it for visual designs that native Confluence can't achieve:
- KPI dashboard cards with custom styling
- Traffic light status boards
- Timeline/roadmap visualizations
- Branded content with company colors
- Interactive widgets with JavaScript

For specific HTML recipes (KPI cards, status boards, timelines), read `references/design-styling.md`.

Prefer native Confluence elements (panels, layouts, macros) when possible — they're more maintainable and work in Confluence's editor. Reserve HTML macro for genuine visual needs.
