# Forge HTML Macro Runtime on Confluence Cloud

Use this when a Forge HTML macro already publishes as `ac:adf-extension` and the remaining question is whether the widget works inside the browser-rendered macro iframe.

## Verified Runtime Matrix

These results were browser-confirmed on a production Confluence Cloud site using Appfire "HTML for Confluence", a Forge HTML macro app.

| Scenario | Method | Forge Cloud result | Server/DC |
|----------|--------|--------------------|-----------|
| Execute JavaScript from a page attachment | `<script src="widget.js">` | Works | Works |
| Load data from attached JSON | `fetch("data.json")` | Blocked by cross-origin iframe and missing CORS headers | Works |
| Load data from an attachment | `data.js` script that calls a global callback | Works | Works |
| Read config from another HTML macro | `document.getElementById()` in a second macro | Blocked; each macro has its own iframe DOM | Works |
| Read another macro via `window.parent` or `window.top` | frame traversal | Blocked with `SecurityError` | Not applicable |
| Read config embedded in the same macro | `<script type="application/json">` plus reader in one `::: html` block | Works | Works |

## Rules

- Treat the Forge HTML macro as a sandboxed, cross-origin iframe.
- Static attachment scripts can execute after confpub rewrites `<script src="...">` URLs.
- Do not use `fetch()` or XHR to read Confluence attachment URLs from a Forge macro iframe. Use a JavaScript data attachment that calls a callback.
- Do not split hidden configuration into one HTML macro and reader code into another. Co-locate config with code in the same `::: html` block, or distribute config as a JavaScript data attachment.
- Do not use `window.parent` or `window.top` to reach the Confluence page DOM; cross-origin Forge iframes throw `SecurityError`.

## Iframe Isolation

Each HTML macro instance gets its own iframe and its own `document`. This works:

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

This does not work on Forge Cloud:

```markdown
::: html
<script id="shared-config" type="application/json">{"title":"A"}</script>
:::

::: html
<script>
  document.getElementById("shared-config"); // null in this macro iframe
  window.parent.document; // SecurityError on cross-origin Forge sites
</script>
:::
```

## CSP and Origin Notes

Forge macro apps render in an iframe whose origin differs from the Confluence page origin. Browser resource loading allows `<script src>` to execute when the app CSP permits it, but that does not grant JavaScript read access to attachment responses. Confluence attachment download URLs do not provide the CORS headers needed by `fetch()` from the Forge iframe origin.

## Verification

Verify in the browser-rendered page. REST `body.storage` proves the macro was emitted, but not that the client-side runtime succeeded. REST `body.view` can show export fallback text such as "We don't have a way to export this macro" even when the browser-rendered macro works.
