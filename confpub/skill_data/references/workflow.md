# Publishing Workflow

## Agent Setup & Configuration

### Bootstrap

```bash
# Learn the full CLI schema (all commands, flags, error codes)
confpub guide

# Or request a specific section
confpub guide --section commands
confpub guide --section error_codes
confpub guide --section auth

# Check credentials
confpub auth inspect

# View current config
confpub config inspect

# Set config values
confpub config set base_url https://yourorg.atlassian.net/wiki
confpub config set user you@example.com
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `CONFPUB_URL` | Confluence base URL |
| `CONFPUB_USER` | Email or username |
| `CONFPUB_TOKEN` | API token (Cloud) or PAT (Server/DC) |
| `CONFPUB_SPACE` | Default space key (avoids `--space` on every command) |
| `CONFPUB_SSL_VERIFY` | SSL verification (`true`/`false` or CA bundle path) |
| `CONFPUB_HTML_MACRO_NAME` | HTML macro key for `::: html` blocks when your Cloud app differs from the built-in fallback |
| `CONFPUB_HTML_MACRO_FORMAT` | `classic` or `forge-adf-extension` for Forge HTML macro apps |
| `CONFPUB_HTML_MACRO_FORGE_EXTENSION_KEY` | Forge `extension-key` copied from a working HTML macro |
| `CONFPUB_HTML_MACRO_FORGE_EXTENSION_ID` | Forge `extension-id` copied from a working HTML macro |
| `CONFPUB_HTML_MACRO_FORGE_CLOUD_ID` | Optional Forge `cloud-id` copied from a working HTML macro |
| `CONFPUB_HTML_MACRO_FORGE_CONTEXT_IDS` | Optional Forge `context-ids` copied from a working HTML macro |
| `CONFPUB_HTML_MACRO_FORGE_ACCOUNT_ID` | Optional Forge `account-id` copied from a working HTML macro |
| `LLM=true` | Suppress interactive prompts; return structured errors instead |

**Credential precedence:** CLI flags > environment variables > config file (`~/.config/confpub/config.json`) > OS keychain.

## Personal Spaces and PowerShell

Personal space keys begin with `~`, for example `~username`. Some shells or tools can expand `~username` to a local path before confpub receives it. In PowerShell, prefer:

```powershell
$env:CONFPUB_SPACE = "~username"
confpub page list --limit 5
```

over:

```powershell
confpub page list --space "~username"
```

If confpub reports a path such as `C:\Users\username`, set `CONFPUB_SPACE` and omit `--space`.

### Installing the Skill

```bash
# Auto-detect agents in the current repo and install the confpub skill
confpub skill install

# Install for specific agents
confpub skill install --agent claude --agent copilot

# Check which agents are detected
confpub skill inspect
```

## Single Page (Fast Path)

```bash
# Dry-run first
confpub page publish doc.md --space SD --parent "Engineering" --dry-run

# Publish with labels
confpub page publish doc.md --space SD --parent "Engineering" \
  --label architecture --label approved

# Title options
--title "Custom Title"          # explicit title
--title-from-h1                 # use first # heading
# (default: filename → title case)
```

Use `--backup` to save existing page content before overwriting:
```bash
confpub page publish doc.md --space SD --parent "Engineering" --backup
```

After publishing, the JSON response includes a `webui` URL to verify in browser.

## Cloud Rendering Verification

For Cloud pages that use HTML macros, layouts, includes, Jira, or page links, verify the rendered view after publishing:

1. Publish with `--dry-run`.
2. Publish live only after the dry run shows the intended change.
3. Inspect storage:
   ```bash
   confpub page inspect --page-id PAGE_ID --raw
   ```
4. Check the rendered page for:
   - `unknown-macro?name=...`
   - empty Forge HTML placeholders after using `macro-html`
   - literal `:::` markers
   - literal `[text](Page Title)` links
   - HTML macro iframe console errors relevant to the custom widget

Storage being valid is not enough; Cloud macro apps can still fail at render time. Forge HTML macros render client-side in an iframe, so REST `body.view` can show export fallback text even when the browser-rendered page works. Verify Forge macros in the browser.

## Multi-Page Tree (Safe Path)

### Manifest (confpub.yaml)

```yaml
schema_version: "1.0"
space: SD
parent: "Engineering"

# Optional: per-manifest connection (overrides env vars)
confluence:
  base_url: https://yourorg.atlassian.net/wiki
  auth:
    type: token  # Credentials still come from CONFPUB_TOKEN + CONFPUB_USER

# Conflict handling
conflict_strategy: fail     # fail (default) | overwrite | skip
on_removal: leave           # leave (default) | delete — what happens when a page is removed from the manifest

# Version message shown in Confluence page history
version_comment: "Published by confpub @ {timestamp}"

# Global labels — applied to every page in the tree
labels:
  - auto-published

# Post-apply verification assertions (used by `plan verify`)
assertions:
  - type: page.exists
    title: "Architecture Overview"
  - type: page.parent
    title: "ADR-001: Use PostgreSQL"
    expected_parent: "Architecture Overview"

pages:
  - title: "Architecture Overview"
    file: architecture.md
    labels: [architecture]
    assets:
      - diagrams/*.png
    children:
      - title: "ADR-001: Use PostgreSQL"
        file: adrs/adr-001.md
        labels: [adr]
      - title: "ADR-002: Event Sourcing"
        file: adrs/adr-002.md
        labels: [adr]
```

**Manifest fields:**

| Field | Default | Description |
|-------|---------|-------------|
| `schema_version` | — | Always `"1.0"` |
| `space` | — | Confluence space key |
| `parent` | — | Title of parent page |
| `confluence` | — | Optional connection overrides (`base_url`, `auth.type`) |
| `conflict_strategy` | `fail` | `fail` = error on conflict, `overwrite` = force update, `skip` = leave unchanged |
| `on_removal` | `leave` | `leave` = keep orphaned pages, `delete` = remove pages no longer in manifest |
| `version_comment` | `"Published by confpub @ {timestamp}"` | Message in Confluence version history |
| `labels` | `[]` | Labels applied to all pages |
| `assertions` | `[]` | Post-apply verification checks for `plan verify` |
| `pages[].title` | — | Page title in Confluence |
| `pages[].file` | — | Path to Markdown source file |
| `pages[].labels` | `[]` | Page-specific labels (additive to global) |
| `pages[].assets` | `[]` | Glob patterns for additional attachments |
| `pages[].children` | `[]` | Nested child pages (recursive) |

### Transactional Workflow

```bash
# 1. Plan — generates confpub-plan.json (no writes)
confpub plan create --manifest confpub.yaml

# 2. Validate — checks for drift
confpub plan validate --plan confpub-plan.json

# 3. Apply — executes the plan
confpub plan apply --plan confpub-plan.json

# 4. Verify — assert post-conditions
confpub plan verify --plan confpub-plan.json
```

Plan → validate → apply → verify separates "what will change" from "do it." Plans are JSON artifacts that can be reviewed, diffed, and versioned.

## Lockfile (confpub.lock)

Maps page titles to Confluence page IDs and content fingerprints. Enables:
- **Idempotent re-publishing** — unchanged content is a no-op
- **Conflict detection** — detects external edits since last publish

The lockfile updates automatically after publish/apply. Commit it to version control for team consistency.

## Labels Strategy

Apply at three levels:
- **Manifest root** `labels:` — applied to all pages in the tree
- **Page-level** `labels:` — page-specific within manifest
- **CLI flag** `--label` — ad-hoc for single publishes

Recommended taxonomy:
| Category | Examples |
|----------|---------|
| **Type** | `adr`, `design-doc`, `runbook`, `retro`, `meeting-notes` |
| **Domain** | `payments`, `auth`, `infra`, `data-platform` |
| **Lifecycle** | `draft`, `in-review`, `approved`, `deprecated`, `archived` |
| **Team** | `squad-atlas`, `platform-team`, `security` |

## Error Recovery

| Error Code | Exit | Meaning | Recovery |
|------------|------|---------|----------|
| `ERR_AUTH_*` | 20 | Bad credentials | Check env vars: `CONFPUB_URL`, `CONFPUB_USER`, `CONFPUB_TOKEN` |
| `ERR_VALIDATION_*` | 10 | Bad input | Fix file paths, space key, or YAML syntax |
| `ERR_CONFLICT_*` | 40 | External page edit | Re-run `plan create` to pick up remote changes |
| `ERR_IO_*` | 50 | Network/API issue | Retry — these are transient |

## Updating Existing Pages

confpub is idempotent. Re-run the same publish command — only changed pages update. The lockfile tracks page IDs and content fingerprints (SHA-256 of storage format body).

## Assets (Images, Diagrams)

Reference images in Markdown normally: `![diagram](diagrams/arch.png)`. confpub discovers local files, uploads as Confluence attachments, and rewrites URLs automatically. In manifests, use `assets:` globs for additional files:

```yaml
pages:
  - title: "Architecture"
    file: architecture.md
    assets:
      - diagrams/*.png
      - diagrams/*.svg
```
