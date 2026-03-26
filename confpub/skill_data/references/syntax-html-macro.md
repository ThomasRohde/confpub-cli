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

## Cloud vs. Server

The HTML macro has different names:
- **Confluence Cloud:** `html-macro`
- **Confluence Server/DC:** `html`

confpub auto-detects based on your Confluence URL. Override with:
- CLI flag: `--html-macro-name html-macro`
- Front-matter: `html_macro_name: html-macro`

## When to Use HTML Macro

Use it for visual designs that native Confluence can't achieve:
- KPI dashboard cards with custom styling
- Traffic light status boards
- Timeline/roadmap visualizations
- Branded content with company colors
- Interactive widgets with JavaScript

For specific HTML recipes (KPI cards, status boards, timelines), read `references/design-styling.md`.

Prefer native Confluence elements (panels, layouts, macros) when possible — they're more maintainable and work in Confluence's editor. Reserve HTML macro for genuine visual needs.
