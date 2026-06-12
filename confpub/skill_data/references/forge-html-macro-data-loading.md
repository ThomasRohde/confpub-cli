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
  var LOADER_NAME = "loader.js";
  var SELF = (document.currentScript && document.currentScript.src) || "";
  if (!SELF) {
    var scripts = document.getElementsByTagName("script");
    for (var i = scripts.length - 1; i >= 0; i--) {
      if (scripts[i].src && scripts[i].src.indexOf(LOADER_NAME) !== -1) {
        SELF = scripts[i].src;
        break;
      }
    }
  }
  if (!SELF) {
    throw new Error("Cannot find " + LOADER_NAME + " attachment URL");
  }
  var base = SELF.replace(/loader\.js(\?.*)?$/, "");

  var root = document.getElementById("widget");
  root.textContent = "Waiting for data...";

  window.__dataReady = function (payload) {
    root.textContent = "Loaded " + payload.rows.length + " rows from data.js";
  };

  window.__dataFailed = function (message) {
    root.textContent = "Data failed: " + message;
  };

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

Capture the loader URL synchronously at the top of the script before any deferred handler runs:

```javascript
var LOADER_NAME = "loader.js";
var SELF = (document.currentScript && document.currentScript.src) || "";
if (!SELF) {
  var scripts = document.getElementsByTagName("script");
  for (var i = scripts.length - 1; i >= 0; i--) {
    if (scripts[i].src && scripts[i].src.indexOf(LOADER_NAME) !== -1) {
      SELF = scripts[i].src;
      break;
    }
  }
}
if (!SELF) throw new Error("Cannot find " + LOADER_NAME + " attachment URL");
var base = SELF.replace(/loader\.js(\?.*)?$/, "");
```

If `loader.js` was loaded from:

```text
https://example.atlassian.net/wiki/download/attachments/123456/loader.js?api=v2
```

then `base + "data.js"` points at the sibling attachment:

```text
https://example.atlassian.net/wiki/download/attachments/123456/data.js
```

Do not read `document.currentScript` inside `DOMContentLoaded`, `setTimeout`, `onload`, or another deferred callback; it is `null` there. Do not fall back to the last `<script>` element in a Forge macro. Forge apps can append platform scripts after yours, so match your loader by filename and fail loudly if it cannot be found.

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
