# Forge HTML Widget Pattern

Use this as a starting point for Confluence Cloud pages rendered by a Forge HTML macro app such as Appfire "HTML for Confluence".

## Page

`page.md`:

```markdown
---
title: Forge Widget Example
space: SPACEKEY
parent: Parent Page
html_macro_name: macro-html
html_macro_format: forge-adf-extension
html_macro_forge_extension_key: 7dc8a3ac/.../static/macro-html
html_macro_forge_extension_id: ari:cloud:ecosystem::extension/7dc8a3ac/.../static/macro-html
html_macro_forge_cloud_id: CLOUD_ID
html_macro_forge_context_ids: ari:cloud:confluence:site/CLOUD_ID
html_macro_forge_account_id: ACCOUNT_ID
---

# Forge Widget Example

::: html
<style>
  .fw-widget { border: 1px solid #C1C7D0; border-radius: 6px; padding: 12px; font-family: sans-serif; }
  .fw-row { display: flex; justify-content: space-between; padding: 6px 0; border-top: 1px solid #DFE1E6; }
  .fw-row:first-child { border-top: 0; }
  .fw-status { font-weight: 700; }
</style>
<script id="fw-config" type="application/json">
{"title":"Release readiness","emptyText":"No rows loaded yet"}
</script>
<div class="fw-widget" id="fw-widget">
  <h3 id="fw-title">Loading...</h3>
  <div id="fw-rows"></div>
  <p>Data source: <span id="fw-source">pending</span></p>
  <p>Last action: <span id="fw-action">none</span></p>
</div>
<script src="widget.js"></script>
:::
```

## Script

`widget.js` is auto-uploaded because it is a static `<script src>` in the HTML block.

```javascript
(function () {
  var config = JSON.parse(document.getElementById("fw-config").textContent);
  var title = document.getElementById("fw-title");
  var rows = document.getElementById("fw-rows");
  var source = document.getElementById("fw-source");
  var action = document.getElementById("fw-action");

  title.textContent = config.title;
  rows.textContent = config.emptyText;

  function render(payload) {
    source.textContent = payload.source || "data.js";
    rows.innerHTML = "";
    payload.rows.forEach(function (row) {
      var item = document.createElement("button");
      item.className = "fw-row";
      item.type = "button";
      item.setAttribute("data-name", row.name);
      item.innerHTML = "<span>" + row.name + "</span><span class=\"fw-status\">" + row.status + "</span>";
      rows.appendChild(item);
    });
  }

  window.__widgetDataReady = function (payload) {
    window.__widgetDataReadyCalled = true;
    render(payload);
  };

  rows.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-name]");
    if (!button) {
      return;
    }
    action.textContent = "selected " + button.getAttribute("data-name");
  });

  var base = document.currentScript.src.replace(/widget\.js.*$/, "");
  var script = document.createElement("script");
  script.src = base + "data.js";
  script.onload = function () {
    if (!window.__widgetDataReadyCalled) {
      source.textContent = "data.js loaded without callback";
    }
  };
  script.onerror = function () {
    source.textContent = "data.js failed to load";
  };
  document.head.appendChild(script);
}());
```

## Data

`data.js` is loaded at runtime by `widget.js`, so `confpub page publish` does not auto-upload it. Upload it separately or include it in manifest `assets:`.

```javascript
window.__widgetDataReady({
  source: "data.js callback",
  rows: [
    { name: "API", status: "Green" },
    { name: "Batch", status: "Yellow" },
    { name: "Reporting", status: "Red" }
  ]
});
```

## Publish

Dry-run first:

```bash
confpub page publish page.md --dry-run
```

Publish and capture the returned page ID:

```bash
confpub page publish page.md
```

Upload runtime data:

```bash
confpub attachment upload data.js --page-id PAGE_ID
```

Open the returned `webui` URL and verify in the browser-rendered page. Do not rely on REST `body.view` for Forge macro runtime verification.
