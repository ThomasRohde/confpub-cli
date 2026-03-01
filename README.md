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
- **Markdown → Confluence** — code blocks become code macros, `> [!NOTE]` becomes Info panels, tables stay tables
- **Asset handling** — images are uploaded as attachments and URLs are rewritten automatically
- **Idempotent** — a lockfile tracks page IDs so re-publishing updates in place
- **Agent-ready** — `confpub guide` returns the full CLI schema; `LLM=true` suppresses interactive behavior
- **Cloud + Server** — works with Confluence Cloud (*.atlassian.net) and Server/Data Center

---

## Commands

All commands follow a `noun verb` pattern. Verbs telegraph mutation intent.

| Command | Mutates | Description |
|---------|---------|-------------|
| `confpub guide` | No | Machine-readable CLI schema |
| `confpub page list` | No | List pages in a space |
| `confpub page inspect` | No | Detailed view of one page |
| `confpub page publish` | **Yes** | Publish a single Markdown file |
| `confpub page delete` | **Yes** | Delete a page |
| `confpub space list` | No | List accessible spaces |
| `confpub attachment list` | No | List attachments on a page |
| `confpub attachment upload` | **Yes** | Upload a file as an attachment |
| `confpub plan create` | No | Generate a plan artifact from a manifest |
| `confpub plan validate` | No | Check a plan against current state |
| `confpub plan apply` | **Yes** | Execute a plan (supports `--dry-run`) |
| `confpub plan verify` | No | Assert post-conditions hold |
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

ERR_AUTH_REQUIRED                No credentials configured
ERR_AUTH_EXPIRED                 Token has expired
ERR_AUTH_FORBIDDEN               Lacks permission to write

ERR_CONFLICT_FINGERPRINT         Page changed since plan was created
ERR_CONFLICT_LOCK                Another confpub process holds the lock
ERR_CONFLICT_PAGE_EXISTS         Title exists with unexpected ID

ERR_IO_FILE_NOT_FOUND            Source file missing
ERR_IO_CONNECTION                Confluence unreachable
ERR_IO_TIMEOUT                   Request timed out

ERR_INTERNAL_CONVERTER           Conversion crashed
ERR_INTERNAL_SDK                 Unexpected API response
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

confpub converts Markdown to Confluence Storage Format:

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

Version is defined in `confpub/__init__.py`. Use `hatch version` to bump it:

```bash
hatch version patch    # 0.2.1 → 0.2.2
hatch version minor    # 0.2.1 → 0.3.0
hatch version major    # 0.2.1 → 1.0.0
```

Then commit and push to `main` — GitHub Actions will publish to PyPI automatically.

### Project Structure

```
confpub/
├── cli.py              # Typer app, commands, envelope wrapping
├── envelope.py         # Pydantic envelope model
├── errors.py           # Error codes, exit codes, ConfpubError
├── output.py           # TOON / LLM=true / isatty logic
├── config.py           # Credential precedence
├── confluence.py       # atlassian-python-api wrapper
├── converter.py        # Markdown → Confluence Storage Format
├── manifest.py         # Manifest + plan artifact models
├── lockfile.py         # confpub.lock persistence
├── assets.py           # Asset discovery, upload, URL rewriting
├── planner.py          # plan.create
├── validator.py        # plan.validate
├── applier.py          # plan.apply
├── verifier.py         # plan.verify
├── publish.py          # page.publish shortcut
└── guide.py            # Machine-readable CLI schema
```

### Technology Stack

| Concern | Choice |
|---------|--------|
| CLI framework | [Typer](https://typer.tiangolo.com) |
| Confluence API | [atlassian-python-api](https://github.com/atlassian-api/atlassian-python-api) |
| Markdown parsing | [markdown-it-py](https://github.com/executablebooks/markdown-it-py) |
| Validation | [Pydantic v2](https://docs.pydantic.dev) |
| JSON serialization | [orjson](https://github.com/ijl/orjson) |
| Credentials | [keyring](https://github.com/jaraco/keyring) + env vars |

---

## License

MIT
