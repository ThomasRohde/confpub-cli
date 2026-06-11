# confpub

**Agent-first CLI to publish Markdown to Confluence.**

Publish one file or an entire documentation tree — from the terminal, a CI pipeline, or an LLM agent. Every command returns structured JSON. Every error has a stable code. One call to `confpub guide` gives an agent everything it needs to drive the tool zero-shot.

## Installation

Run directly with `uvx` (no install needed):

```bash
uvx confpub-cli --help
```

Or install permanently:

```bash
uv tool install confpub-cli   # recommended
pip install confpub-cli        # alternative
```

Once installed, the command is available as both `confpub` and `confpub-cli`.

---

## Quick Start

### Publish a single file

```bash
export CONFPUB_URL=https://yourorg.atlassian.net/wiki
export CONFPUB_TOKEN=your-api-token
export CONFPUB_USER=you@example.com

confpub page publish README.md --space DEV --parent "Engineering"
```

### Publish a documentation tree

Create a `confpub.yaml` manifest:

```yaml
schema_version: "1.0"
space: DEV
parent: "Engineering"

pages:
  - title: "Architecture Overview"
    file: docs/architecture.md
    assets:
      - docs/diagrams/*.png
    children:
      - title: "API Reference"
        file: docs/api.md
      - title: "Deployment Guide"
        file: docs/deploy.md
```

Then run the transactional workflow:

```bash
confpub plan create   --manifest confpub.yaml        # Plan (no writes)
confpub plan validate --plan confpub-plan.json       # Check for drift
confpub plan apply    --plan confpub-plan.json       # Apply to Confluence
confpub plan verify   --assertions verify.json       # Assert post-conditions
```

Or preview first with `--dry-run`:

```bash
confpub plan apply --plan confpub-plan.json --dry-run
```

---

## Features

- **Structured JSON output** — every command returns the same envelope shape on stdout
- **Transactional workflow** — plan → validate → apply → verify with fingerprint-based conflict detection
- **Markdown → Confluence** — code blocks become code macros, `> [!NOTE]` becomes Info panels, tables stay tables, task lists, math, definition lists, footnotes, panels, expand/collapse, page layouts, and `{macro}` syntax for Status, TOC, Jira, Anchor, Children, and more
- **Asset handling** — images are uploaded as attachments and URLs are rewritten automatically; JS/CSS files in `::: html` blocks are auto-discovered and uploaded
- **Idempotent** — a lockfile tracks page IDs so re-publishing updates in place
- **Full page lifecycle** — publish, pull, move, delete, export (PDF/Word), version history, labels, comments, and page properties
- **Trust scoring** — every page gets a 0–100 trust score based on governance, freshness, evidence, and structure signals — fully automatic from native Confluence data, no metadata setup required
- **Trust-aware search** — search results include trust scores and plain-language advisories ("trustworthy", "verify before using", "do not trust") so agents can prefer reliable sources
- **Trust anchors** — declare which spaces and pages you trust; your insider knowledge persists across conversations and boosts or caps scores automatically
- **Interactive TUI** — `confpub trust browse` opens a Textual-based browser for cached trust scores with sortable tables, detail drilldown, and live re-scoring
- **Installable skill** — `confpub skill install` drops a publishing skill into Claude Code, GitHub Copilot, Cursor, Windsurf, or AGENTS.md — with 14 document templates and full syntax references
- **Agent-ready** — `confpub guide` returns the full CLI schema; `LLM=true` suppresses interactive behavior
- **Cloud + Server** — works with Confluence Cloud (*.atlassian.net) and Server/Data Center

---

## Commands

All commands follow a `noun verb` pattern. Verbs telegraph mutation intent.

| Command | Mutates | Description |
|---------|---------|-------------|
| `confpub guide` | No | Machine-readable CLI schema |
| `confpub search` | No | Search Confluence content using CQL |
| **Page** | | |
| `confpub page list` | No | List pages in a space |
| `confpub page inspect` | No | Detailed view of one page |
| `confpub page publish` | **Yes** | Publish a single Markdown file |
| `confpub page pull` | No | Pull Confluence pages to local Markdown |
| `confpub page delete` | **Yes** | Delete a page (supports `--cascade`) |
| `confpub page move` | **Yes** | Move a page under a new parent |
| `confpub page history` | No | Show version history of a page |
| `confpub page version` | No | Get a specific page version |
| `confpub page export` | No | Export a page as PDF or Word |
| **Space** | | |
| `confpub space list` | No | List accessible spaces |
| `confpub space inspect` | No | Detailed view of one space |
| **Attachment** | | |
| `confpub attachment list` | No | List attachments on a page |
| `confpub attachment upload` | **Yes** | Upload a file as an attachment |
| `confpub attachment download` | No | Download an attachment |
| `confpub attachment delete` | **Yes** | Delete an attachment |
| **Label** | | |
| `confpub label list` | No | List labels on a page |
| `confpub label add` | **Yes** | Add labels to a page |
| `confpub label remove` | **Yes** | Remove labels from a page |
| **Comment** | | |
| `confpub comment list` | No | List comments on a page |
| `confpub comment add` | **Yes** | Add a comment to a page |
| **Property** | | |
| `confpub property list` | No | List all properties on a page |
| `confpub property get` | No | Get a single page property |
| `confpub property set` | **Yes** | Set a page property (create or update) |
| `confpub property delete` | **Yes** | Delete a page property |
| **Plan** | | |
| `confpub plan create` | No | Generate a plan artifact from a manifest |
| `confpub plan validate` | No | Check a plan against current state |
| `confpub plan apply` | **Yes** | Execute a plan (supports `--dry-run`) |
| `confpub plan verify` | No | Assert post-conditions hold |
| **Skill** | | |
| `confpub skill install` | **Yes** | Install confpub skill into coding agents |
| `confpub skill inspect` | No | Detect agents and show skill status |
| **Trust** | | |
| `confpub page score` | No | Score a page for trustworthiness |
| `confpub trust browse` | No | Interactive TUI browser for cached scores |
| `confpub trust anchor set` | **Yes** | Declare a trust level for a space or page |
| `confpub trust anchor list` | No | List all trust anchors |
| `confpub trust anchor remove` | **Yes** | Remove a trust anchor |
| `confpub trust cache inspect` | No | Show cache statistics |
| `confpub trust cache purge` | **Yes** | Clear cached scores |
| `confpub trust profile inspect` | No | Show scoring profiles |
| **Config / Auth** | | |
| `confpub auth inspect` | No | Show credential status |
| `confpub config set` | **Yes** | Write a config value |
| `confpub config inspect` | No | Show current config |

---

## Structured Envelope

Every command — success or failure — returns this exact shape on stdout:

```json
{
  "schema_version": "1.0",
  "request_id": "req_20260228_143000_7f3a",
  "ok": true,
  "command": "page.publish",
  "target": {
    "space": "DEV",
    "title": "Architecture Overview"
  },
  "result": { "..." : "..." },
  "warnings": [],
  "errors": [],
  "metrics": {
    "duration_ms": 842
  }
}
```

On failure, `ok` is `false`, `result` is `null`, and `errors` contains structured error objects:

```json
{
  "ok": false,
  "errors": [
    {
      "code": "ERR_CONFLICT_FINGERPRINT",
      "message": "Page was modified externally since plan was created",
      "retryable": false,
      "suggested_action": "fix_input",
      "details": {
        "page_id": "123456",
        "plan_fingerprint": "sha256:abc123",
        "current_fingerprint": "sha256:def456"
      }
    }
  ]
}
```

**Invariants:**
- `stdout` is exclusively JSON — one object, no preamble, no epilogue
- `errors` and `warnings` are always arrays (possibly empty)
- `result` is always present (`null` on failure)
- `stderr` gets progress events, diagnostics, and debug logs

---

## Pulling Pages

Pull Confluence pages back to local Markdown files:

```bash
# Pull a single page by title
confpub page pull --space DEV --title "Architecture Overview" --output docs/

# Pull a single page by ID
confpub page pull --page-id 123456 --output docs/

# Pull a page and all its children recursively
confpub page pull --space DEV --title "Engineering" --recursive --output docs/

# Generate a manifest even for a single page
confpub page pull --page-id 123456 --manifest --output docs/
```

### Pull flags

| Flag | Description |
|------|-------------|
| `--space` | Confluence space key |
| `--title` | Page title |
| `--page-id` | Confluence page ID (alternative to `--space` + `--title`) |
| `--output` / `-o` | Output directory (default: `.`) |
| `--recursive` / `-r` | Pull child pages recursively |
| `--force` | Overwrite existing local files |
| `--layout` | `flat` (default) or `nested` directory structure |
| `--no-attachments` | Skip downloading attachments |
| `--manifest` | Generate `confpub.yaml` manifest |

Recursive pulls automatically generate a `confpub.yaml` manifest and a `confpub.lock` lockfile for round-tripping back to Confluence.

---

## Searching

Search Confluence content using CQL (Confluence Query Language):

```bash
# Search by CQL
confpub search --cql 'label = "api-docs"'

# Filter by space and type
confpub search --space DEV --type page --limit 10

# Combine CQL with filters
confpub search --space DEV --cql 'title ~ "deploy"'
```

---

## Trust Scoring

Every Confluence page gets a 0–100 trust score estimating how safe it is to rely on as current guidance. Scoring works fully automatically from native Confluence signals — no metadata setup required.

```bash
# Score a page
confpub page score --page-id 123456

# Scores appear in search results automatically
confpub search --space EA --type page --title "architecture"
# → each result includes: trust.score, trust.band, trust.advisory.verdict
```

### How it works

The score combines five subscores:

| Subscore | What it measures (from native Confluence data) |
|----------|------------------------------------------------|
| **Stewardship** (0.30) | Multiple editors, version maturity, edit quality |
| **Freshness** (0.25) | Page age vs class-specific half-life |
| **Evidence** (0.20) | Outbound links, Jira macros, tables, images |
| **Structure** (0.15) | Headings, body length, labels, no placeholders |
| **Corroboration** (0.10) | Views, watchers (future) |

Hard caps prevent bad pages from scoring well: archived pages cap at 10, personal spaces at 50, deprecated content at 25.

Pages you interact with are scored automatically — `page inspect`, `page publish`, `label add`, and other commands warm the cache as a silent side effect.

### Trust anchors

Encode your insider knowledge about which spaces are authoritative:

```bash
confpub trust anchor set --space EA --level high --reason "Architecture team"
confpub trust anchor set --space DOCS --level good --reason "Official docs"
confpub trust anchor set --space '~thomas' --level low --reason "Personal drafts"
```

Anchors persist in `~/.confpub/trust-anchors.json` and apply to every score. An agent using confpub will automatically prefer pages from high-trust spaces.

### Trust-aware agent workflow

When an agent searches Confluence to answer a question, each result includes a trust advisory:

```json
{
  "title": "Deployment Guide",
  "trust": {
    "score": 88,
    "advisory": {
      "verdict": "trustworthy",
      "guidance": "Safe to rely on as current guidance."
    }
  }
}
```

The agent can prefer high-trust sources and warn when only low-trust content is available.

### Interactive browser

```bash
confpub trust browse
```

Opens a Textual TUI showing all cached scores in a sortable table. Press Enter to drill into subscores and signals, `r` to re-score a page, `s` to sort.

---

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| `0` | Success | — |
| `10` | Validation error | Fix input, do not retry |
| `20` | Auth / permission | Re-authenticate or escalate |
| `40` | Conflict | Re-plan, do not blindly retry |
| `50` | I/O error | Retry with backoff |
| `90` | Internal error | File a bug |

---

## Error Codes

Stable across versions. An agent can branch on these without parsing messages.

```
ERR_VALIDATION_REQUIRED          Missing required argument
ERR_VALIDATION_MANIFEST          Manifest fails schema validation
ERR_VALIDATION_MARKDOWN          Unparseable Markdown
ERR_VALIDATION_ASSET_MISSING     Referenced image not found on disk
ERR_VALIDATION_NOT_FOUND         Page or resource not found
ERR_VALIDATION_SPACE_MISMATCH    Space key mismatch between manifest and target
ERR_VALIDATION_LABEL             Invalid label format
ERR_VALIDATION_SPACE_KEY         Space key looks like expanded shell path

ERR_AUTH_REQUIRED                No credentials configured
ERR_AUTH_EXPIRED                 Token has expired
ERR_AUTH_FORBIDDEN               Lacks permission to write

ERR_CONFLICT_FINGERPRINT         Page changed since plan was created
ERR_CONFLICT_LOCK                Another confpub process holds the lock
ERR_CONFLICT_PAGE_EXISTS         Title exists with unexpected ID
ERR_CONFLICT_FILE_EXISTS         Local file already exists (pull)

ERR_IO_FILE_NOT_FOUND            Source file missing
ERR_IO_CONNECTION                Confluence unreachable
ERR_IO_TIMEOUT                   Request timed out

ERR_INTERNAL_CONVERTER           Markdown → Confluence conversion crashed
ERR_INTERNAL_REVERSE_CONVERTER   Confluence → Markdown conversion crashed
ERR_INTERNAL_SDK                 Unexpected API response

ERR_VALIDATION_TRUST_PROFILE     Unknown scoring profile
ERR_VALIDATION_TRUST_DOC_CLASS   Unknown document class
ERR_IO_TRUST_METADATA            Core page metadata unavailable
ERR_INTERNAL_TRUST_CACHE         Trust cache corrupted
```

---

## Authentication

Credentials are resolved in this order (highest precedence first):

```
CLI flags     →  --token / --user
Env vars      →  CONFPUB_TOKEN / CONFPUB_USER / CONFPUB_URL
Config file   →  ~/.config/confpub/config.json
OS keychain   →  via keyring
```

Cloud vs Server is auto-detected from the URL: `*.atlassian.net` uses token + email auth; everything else uses PAT.

```bash
# Check current auth status
confpub auth inspect

# Set config values
confpub config set base_url https://yourorg.atlassian.net/wiki
confpub config set user you@example.com
```

When `LLM=true` or stdin is non-interactive, confpub never prompts — it returns a structured `ERR_AUTH_REQUIRED` error instead.

---

## Markdown Conversion

confpub converts Markdown to Confluence Storage Format (and back via `page pull`):

| Markdown | Confluence Output |
|----------|-------------------|
| `# Heading` | `<h1>Heading</h1>` |
| `**bold**` | `<strong>bold</strong>` |
| `` `code` `` | `<code>code</code>` |
| Fenced code block | `<ac:structured-macro ac:name="code">` with language param |
| `> [!NOTE]` | Confluence Info macro |
| `> [!WARNING]` | Confluence Warning macro |
| `> [!TIP]` | Confluence Tip macro |
| `![img](photo.png)` | Upload attachment + `<ac:image>` reference |
| Tables | Standard XHTML `<table>` |
| `~~strikethrough~~` | `<del>strikethrough</del>` |
| `- [ ] task` / `- [x] done` | `<ac:task-list>` with task status |
| `$E=mc^2$` | LaTeX math macro (inline) |
| `$$...$$` | LaTeX math macro (block) |
| `Term` + `: Definition` | `<dl><dt><dd>` definition list |
| `[^1]` footnotes | Superscript links + numbered list |
| `::: panel Title` | Confluence Panel macro |
| `::: expand Title` | Confluence Expand macro |
| `:::: layout two-equal` | Confluence page layout |
| `---yaml---` front matter | Silently stripped |
| `{status:Done\|colour=Green}` | Confluence Status lozenge |
| `{toc}` | Table of Contents macro |
| `{anchor:name}` | Anchor macro |
| `{children}` | Children Display macro |
| `{jira:PROJECT-123}` | Jira issue link/table |
| `{recently-updated}` | Recently Updated macro |
| `{excerpt-include:Page}` | Excerpt Include macro |
| `{include:Page}` | Include Page macro |
| `::: excerpt` | Excerpt macro (body) |
| `::: html` | HTML macro (preserves `<style>`, `<script>`, `<iframe>`) |

---

## HTML Macro

Confluence strips `<style>`, `<script>`, `<iframe>`, and other tags from normal page content. The **HTML macro** is the only way to embed arbitrary HTML. confpub supports it via `::: html` fenced blocks:

```markdown
::: html
<style>
  .card { border: 2px solid #0052CC; border-radius: 8px; padding: 16px; }
  .card h3 { color: #0052CC; margin-top: 0; }
</style>
<div class="card">
  <h3>Custom Styled Card</h3>
  <p>This HTML is preserved verbatim by the HTML macro.</p>
</div>
:::
```

The macro name is selected from your Confluence type: `html` for Data Center/Server and `html-macro` as the Cloud fallback. Confluence Cloud HTML macro apps can register different macro keys, including `macro-html`, so override per publish with `--html-macro-name` or `html_macro_name` in front-matter when needed. To persist the setting, run `confpub config set html_macro_name macro-html` or set `CONFPUB_HTML_MACRO_NAME`.

Forge-based Cloud HTML apps, such as Appfire "HTML for Confluence", use a different storage shape (`ac:adf-extension`) rather than the classic `ac:structured-macro`. For those sites, also set `--html-macro-format forge-adf-extension` and provide the Forge `extension-key` and `extension-id` copied from a working macro:

```bash
confpub config set html_macro_name macro-html
confpub config set html_macro_format forge-adf-extension
confpub config set html_macro_forge_extension_key "7dc8a3ac/.../static/macro-html"
confpub config set html_macro_forge_extension_id "ari:cloud:ecosystem::extension/7dc8a3ac/.../static/macro-html"
confpub config set html_macro_forge_cloud_id "CLOUD_ID"
confpub config set html_macro_forge_context_ids "ari:cloud:confluence:site/CLOUD_ID"
confpub config set html_macro_forge_account_id "ACCOUNT_ID"
```

### Interactive JavaScript Applications

`::: html` blocks can reference external JavaScript and CSS files. confpub automatically:

1. **Discovers** `<script src="...">` and `<link href="...">` references inside `::: html` blocks
2. **Uploads** the referenced files as page attachments
3. **Rewrites** the URLs in the published HTML to point to the Confluence attachment download path

```markdown
::: html
<div id="dashboard"></div>
<script src="app.js"></script>
:::
```

Place `app.js` next to the `.md` file. This pattern works for any single-file JavaScript application — bundle your TypeScript, React, or Vue app into a single `.js` file and reference it from a `::: html` block.

Missing files produce warnings (not errors), so partial publishes still succeed.

---

## Manifest Format

```yaml
schema_version: "1.0"
space: DEV
parent: "Architecture Notes"

confluence:
  base_url: https://yourorg.atlassian.net/wiki
  auth:
    type: token  # Credentials via CONFPUB_TOKEN + CONFPUB_USER

conflict_strategy: fail     # fail | overwrite | skip
on_removal: leave           # leave | delete
version_comment: "Published by confpub @ {timestamp}"

labels:
  - architecture
  - auto-published

assertions:
  - type: page.exists
    title: "Overview"
  - type: page.parent
    title: "Components"
    expected_parent: "Overview"

pages:
  - title: "Overview"
    file: overview.md

  - title: "Component Design"
    file: components/design.md
    assets:
      - components/diagrams/*.png
    children:
      - title: "API Reference"
        file: components/api.md
```

---

## Lockfile

After the first successful apply, confpub writes `confpub.lock` alongside the manifest. Commit this to version control — it maps page titles to Confluence page IDs for idempotent re-publishing.

```json
{
  "schema_version": "1.0",
  "last_updated": "2026-02-28T14:35:00Z",
  "pages": {
    "Overview":          { "page_id": "123456", "version": 5 },
    "Component Design":  { "page_id": "123457", "version": 1 },
    "API Reference":     { "page_id": "123458", "version": 1 }
  }
}
```

---

## Agent Integration

An LLM agent can drive confpub entirely from one bootstrap call:

```bash
# Step 1: Learn the CLI
confpub guide

# Step 2: Check credentials
confpub auth inspect

# Step 3: Explore
confpub space list
confpub page list --space DEV

# Step 4: Publish
confpub page publish doc.md --space DEV --parent "Docs" --dry-run
confpub page publish doc.md --space DEV --parent "Docs"
```

The `guide` command returns the complete schema — all commands with flags, all error codes with exit codes and retry hints, auth precedence, and concurrency rules:

```bash
confpub guide                          # Full schema
confpub guide --section auth           # Just auth info
confpub guide --section error_codes    # Just error codes
confpub guide --section commands       # Just commands
```

### Environment variables for agents

| Variable | Effect |
|----------|--------|
| `LLM=true` | Suppress interactive prompts; return structured errors instead |
| `CONFPUB_TOKEN` | API token |
| `CONFPUB_USER` | Email / username |
| `CONFPUB_URL` | Confluence base URL |
| `CONFPUB_SPACE` | Default space key |
| `CONFPUB_SSL_VERIFY` | SSL verification (`true`/`false` or CA bundle path) |
| `CONFPUB_HTML_MACRO_NAME` | HTML macro key for `::: html` blocks, if your Confluence Cloud app differs from the built-in fallback |
| `CONFPUB_HTML_MACRO_FORMAT` | HTML macro storage format: `classic` or `forge-adf-extension` |
| `CONFPUB_HTML_MACRO_FORGE_EXTENSION_KEY` | Forge HTML macro `extension-key` copied from a working macro |
| `CONFPUB_HTML_MACRO_FORGE_EXTENSION_ID` | Forge HTML macro `extension-id` copied from a working macro |
| `CONFPUB_HTML_MACRO_FORGE_CLOUD_ID` | Optional Forge `cloud-id` copied from a working macro |
| `CONFPUB_HTML_MACRO_FORGE_CONTEXT_IDS` | Optional Forge `context-ids` copied from a working macro |
| `CONFPUB_HTML_MACRO_FORGE_ACCOUNT_ID` | Optional Forge `account-id` copied from a working macro |

---

## Skills

confpub ships an installable skill that teaches coding agents how to write professional Confluence pages — including extended syntax, design principles, and 14 ready-to-use document templates.

### Installing the skill

```bash
# Auto-detect agents in the current repo and install
confpub skill install

# Install for specific agents
confpub skill install --agent claude --agent copilot

# Preview without writing files
confpub skill install --dry-run

# Check which agents are detected
confpub skill inspect
```

### Supported agents

| Agent | Detection |
|-------|-----------|
| Claude Code | `.claude/` directory or `CLAUDE.md` |
| GitHub Copilot | `.github/copilot-instructions.md` |
| Cursor | `.cursor/rules/` or `.cursorrules` |
| Windsurf | `.windsurfrules` or `.windsurf/` |
| AGENTS.md | `AGENTS.md` in repo root |

### What the skill includes

The skill installs a main `SKILL.md` with a syntax cheat sheet and design philosophy, plus a `references/` directory with detailed guides and document templates:

**Syntax and design references** — containers (panels, expand, admonitions, excerpts), macros (status, TOC, children, Jira, anchors, includes), formatting (code blocks, math, footnotes, tasks), HTML macro, layouts, design principles, design styling, page management, and publishing workflow.

**Document templates** — ADR, API docs, change request, design doc, meeting notes, onboarding guide, post-mortem, RAID log, release notes, retrospective, RFC, runbook, service catalog, and sprint status.

Once installed, agents can create polished Confluence pages that use the full range of confpub's extended Markdown syntax — panels, status lozenges, layouts, macros, and more — without the user needing to explain the syntax.

---

## Development

```bash
# Clone and install with dev dependencies
git clone https://github.com/ThomasRohde/confpub-cli.git
cd confpub-cli
uv pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=confpub
```

### Releasing

Version is defined in `confpub/__init__.py`. Use `uvx hatch` to bump it:

```bash
uvx hatch version patch    # 0.2.1 → 0.2.2
uvx hatch version minor    # 0.2.1 → 0.3.0
uvx hatch version major    # 0.2.1 → 1.0.0
```

Then commit and push to `main` — GitHub Actions will publish to PyPI automatically.

### Project Structure

```
confpub/
├── cli.py                # Typer app, commands, envelope wrapping
├── envelope.py           # Pydantic envelope model
├── errors.py             # Error codes, exit codes, ConfpubError
├── output.py             # TOON / LLM=true / isatty logic
├── config.py             # Credential precedence
├── confluence.py         # atlassian-python-api wrapper
├── converter.py          # Markdown → Confluence Storage Format
├── reverse_converter.py  # Confluence Storage Format → Markdown
├── manifest.py           # Manifest + plan artifact models
├── lockfile.py           # confpub.lock persistence
├── front_matter.py       # YAML front-matter parsing
├── html_macro_plugin.py  # ::: html block parser plugin
├── macro_plugin.py       # {macro} inline syntax parser
├── assets.py             # Asset discovery, upload, URL rewriting
├── planner.py            # plan.create
├── validator.py          # plan.validate
├── applier.py            # plan.apply
├── verifier.py           # plan.verify
├── publish.py            # page.publish shortcut
├── puller.py             # page.pull workflow
├── guide.py              # Machine-readable CLI schema
├── skill_installer.py    # Skill installation logic
├── skill_data/           # Skill content (SKILL.md + references/)
└── trust/                # Trust scoring engine
    ├── models.py         # Classification taxonomy, score models
    ├── profiles.py       # Built-in scoring profiles
    ├── scoring.py        # Signal collection, subscores, hard caps
    ├── body_parser.py    # HTML body analysis (BeautifulSoup4)
    ├── cache.py          # SQLite cache (~/.confpub/)
    ├── anchors.py        # User-declared trust levels
    └── tui.py            # Textual interactive browser
```

### Technology Stack

| Concern | Choice |
|---------|--------|
| CLI framework | [Typer](https://typer.tiangolo.com) |
| Confluence API | [atlassian-python-api](https://github.com/atlassian-api/atlassian-python-api) |
| Markdown parsing | [markdown-it-py](https://github.com/executablebooks/markdown-it-py) |
| HTML → Markdown | [markdownify](https://github.com/matthewwithanm/python-markdownify) + [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) |
| Validation | [Pydantic v2](https://docs.pydantic.dev) |
| JSON serialization | [orjson](https://github.com/ijl/orjson) |
| Credentials | [keyring](https://github.com/jaraco/keyring) + env vars |
| Trust cache | SQLite (stdlib) |
| TUI | [Textual](https://github.com/Textualize/textual) |

---

## License

MIT
