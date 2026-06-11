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

Only static `<script src>` and `<link href>` references in the HTML block are auto-discovered. Files referenced at runtime by JavaScript, including injected scripts and `fetch()` URLs, are not discovered by `page publish`; upload those files manually with `confpub attachment upload`.

## Cloud Forge Runtime Summary

Forge HTML macro apps on Confluence Cloud run client-side in sandboxed, cross-origin iframes. These runtime behaviors were browser-confirmed on Appfire "HTML for Confluence":

| Scenario | Method | Forge Cloud result | Server/DC |
|----------|--------|--------------------|-----------|
| Execute JavaScript from a page attachment | `<script src="widget.js">` | Works | Works |
| Load data from attached JSON | `fetch("data.json")` | Blocked by cross-origin iframe and missing CORS headers | Works |
| Load data from an attachment | `data.js` script that calls a global callback | Works | Works |
| Read config from another HTML macro | `document.getElementById()` in a second macro | Blocked; each macro has its own iframe DOM | Works |
| Read another macro via `window.parent` or `window.top` | frame traversal | Blocked with `SecurityError` | Not applicable |
| Read config embedded in the same macro | `<script type="application/json">` plus reader in one `::: html` block | Works | Works |

Rules:
- Attachment JavaScript and CSS loaded with static `<script src>` / `<link href>` can execute after confpub rewrites the URLs.
- Do not fetch Confluence attachment JSON from a Forge macro iframe; `fetch()` / XHR is blocked by cross-origin isolation.
- Ship data/config as a JavaScript attachment that calls a global callback, or embed config in the same macro that reads it.
- Do not split hidden config and reader code across two HTML macros on Forge Cloud.

For the complete runtime rules, read `references/forge-html-macro-runtime.md`. For data loading patterns, read `references/forge-html-macro-data-loading.md`.

Callback data loading uses a sibling attachment URL derived from the script URL:

```javascript
var base = document.currentScript.src.replace(/loader\.js.*$/, "");
var s = document.createElement("script");
s.src = base + "data.js";
document.head.appendChild(s);
```

`data.js` calls `window.__dataReady(payload)`.

### Iframe Isolation

Each Forge HTML macro is rendered in its own sandboxed iframe. The iframe document contains only that macro's HTML. A second macro cannot read DOM nodes from the first macro, and attempts to climb to `window.parent` or `window.top` throw `SecurityError` on cross-origin Forge sites.

Working same-macro config pattern:

```markdown
::: html
<script id="widget-config" type="application/json">
{"title":"Release readiness","threshold":95}
</script>
<div id="widget"></div>
<script>
  var cfg = JSON.parse(document.getElementById("widget-config").textContent);
  document.getElementById("widget").textContent = cfg.title + ": " + cfg.threshold;
</script>
:::
```

## Cloud vs. Server/DC Macro Names

The HTML macro key is not guaranteed by hosting model alone, and some Cloud apps require a different storage format.

| Environment | Typical macro key | Notes |
|-------------|-------------------|-------|
| Server/DC | `html` | Built-in or administrator-enabled HTML macro |
| Cloud classic app | `html-macro` or `macro-html` | Uses `ac:structured-macro`; key depends on installed Marketplace app |
| Cloud Forge app | Often `macro-html` | Uses `ac:adf-extension`; key override alone is not enough |

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

## Forge HTML Macro Apps

Forge-based Cloud HTML macro apps, including Appfire "HTML for Confluence", store macros as `ac:adf-extension` nodes. If confpub publishes a classic structured macro to one of these sites, Confluence may accept the page but render an empty HTML placeholder because the app never receives the body.

Classic storage:

```xml
<ac:structured-macro ac:name="macro-html">
  <ac:plain-text-body><![CDATA[<div>...</div>]]></ac:plain-text-body>
</ac:structured-macro>
```

Forge storage:

```xml
<ac:adf-extension>
  <ac:adf-node type="extension">
    <ac:adf-attribute key="extension-key">...</ac:adf-attribute>
    <ac:adf-attribute key="parameters">
      <ac:adf-parameter key="extension-id">...</ac:adf-parameter>
      <ac:adf-parameter key="guest-params">
        <ac:adf-parameter key="source-type">MacroBody</ac:adf-parameter>
        <ac:adf-parameter key="__body-content">&lt;div&gt;...&lt;/div&gt;</ac:adf-parameter>
      </ac:adf-parameter>
    </ac:adf-attribute>
  </ac:adf-node>
</ac:adf-extension>
```

To use Forge storage, inspect a working macro page and copy `extension-key` and `extension-id`:

```bash
confpub page inspect --page-id PAGE_ID --raw
```

If the working macro includes `cloud-id`, `context-ids`, or `account-id` parameters, copy those too. Then publish with:

```bash
confpub page publish page.md \
  --html-macro-name macro-html \
  --html-macro-format forge-adf-extension \
  --html-macro-forge-extension-key "7dc8a3ac/.../static/macro-html" \
  --html-macro-forge-extension-id "ari:cloud:ecosystem::extension/7dc8a3ac/.../static/macro-html" \
  --html-macro-forge-cloud-id "CLOUD_ID" \
  --html-macro-forge-context-ids "ari:cloud:confluence:site/CLOUD_ID" \
  --html-macro-forge-account-id "ACCOUNT_ID"
```

Or persist the site settings:

```bash
confpub config set html_macro_name macro-html
confpub config set html_macro_format forge-adf-extension
confpub config set html_macro_forge_extension_key "7dc8a3ac/.../static/macro-html"
confpub config set html_macro_forge_extension_id "ari:cloud:ecosystem::extension/7dc8a3ac/.../static/macro-html"
confpub config set html_macro_forge_cloud_id "CLOUD_ID"
confpub config set html_macro_forge_context_ids "ari:cloud:confluence:site/CLOUD_ID"
confpub config set html_macro_forge_account_id "ACCOUNT_ID"
```

Front matter is also supported:

```yaml
---
html_macro_name: macro-html
html_macro_format: forge-adf-extension
html_macro_forge_extension_key: 7dc8a3ac/.../static/macro-html
html_macro_forge_extension_id: ari:cloud:ecosystem::extension/7dc8a3ac/.../static/macro-html
html_macro_forge_cloud_id: CLOUD_ID
html_macro_forge_context_ids: ari:cloud:confluence:site/CLOUD_ID
html_macro_forge_account_id: ACCOUNT_ID
---
```

Forge macros render client-side in a sandboxed iframe. Confluence REST `body.view` can show a fallback message such as "We don't have a way to export this macro" even when the browser-rendered page works. Verify Forge HTML macros in the browser rendered view.

## When to Use HTML Macro

Use it for visual designs that native Confluence can't achieve:
- KPI dashboard cards with custom styling
- Traffic light status boards
- Timeline/roadmap visualizations
- Branded content with company colors
- Interactive widgets with JavaScript

For specific HTML recipes (KPI cards, status boards, timelines), read `references/design-styling.md`.

Prefer native Confluence elements (panels, layouts, macros) when possible — they're more maintainable and work in Confluence's editor. Reserve HTML macro for genuine visual needs.
