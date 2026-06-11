# Forge HTML Macro Data Loading

Use this when a Forge HTML macro widget needs data or configuration from attachments.

## Rule

On Forge HTML macro apps, attachment JavaScript loaded by `<script src>` executes, but `fetch()` / XHR to Confluence attachment URLs is blocked by cross-origin iframe isolation. Ship data as JavaScript that calls a callback.

## What confpub Uploads Automatically

`confpub page publish` auto-discovers only static references in the `::: html` block:

- `<script src="widget.js"></script>`
- `<link rel="stylesheet" href="widget.css">`

Files referenced only at runtime are not auto-uploaded:

- `fetch("data.json")`
- `document.createElement("script").src = "data.js"`
- URLs embedded inside `widget.js`

Upload runtime files manually:

```bash
confpub page publish page.md
confpub attachment upload data.js --page-id PAGE_ID
```

Manifest publishing can also use `assets:` globs for extra files.

## Loader Pattern

`page.md`:

```markdown
::: html
<div id="widget">Loading...</div>
<script src="loader.js"></script>
:::
```

`loader.js`:

```javascript
(function () {
  var root = document.getElementById("widget");
  root.textContent = "Waiting for data...";

  window.__dataReady = function (payload) {
    root.textContent = "Loaded " + payload.rows.length + " rows from data.js";
  };

  window.__dataFailed = function (message) {
    root.textContent = "Data failed: " + message;
  };

  var base = document.currentScript.src.replace(/loader\.js.*$/, "");
  var script = document.createElement("script");
  script.src = base + "data.js";
  script.onload = function () {
    if (!window.__dataReadyCalled) {
      window.__dataFailed("data.js loaded but did not call __dataReady");
    }
  };
  script.onerror = function () {
    window.__dataFailed("data.js could not be loaded");
  };
  document.head.appendChild(script);
}());
```

`data.js`:

```javascript
(function () {
  var payload = {
    rows: [
      { name: "Alpha", status: "Green" },
      { name: "Beta", status: "Yellow" }
    ]
  };
  window.__dataReadyCalled = true;
  window.__dataReady(payload);
}());
```

The `document.currentScript.src` line derives the page attachment base URL without hardcoding a page ID:

```javascript
var base = document.currentScript.src.replace(/loader\.js.*$/, "");
```

If `loader.js` was loaded from:

```text
https://example.atlassian.net/wiki/download/attachments/123456/loader.js?api=v2
```

then `base + "data.js"` points at the sibling attachment:

```text
https://example.atlassian.net/wiki/download/attachments/123456/data.js
```

## Same-Macro Inline Config

For small config, avoid attachments and keep the config in the same macro as the reader:

```markdown
::: html
<script id="widget-config" type="application/json">
{"title":"Release readiness","showDetails":true}
</script>
<div id="widget"></div>
<script src="widget.js"></script>
:::
```

`widget.js`:

```javascript
var configEl = document.getElementById("widget-config");
var config = JSON.parse(configEl.textContent);
document.getElementById("widget").textContent = config.title;
```

Do not put the config script in one HTML macro and the reader in another on Forge Cloud; each macro has a separate iframe document.
