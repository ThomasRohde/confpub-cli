# confpub — Product Requirements Document

**Version:** 1.0  
**Date:** 2026-02-28  
**Status:** Draft

-----

## Table of Contents

1. [Overview](#overview)
1. [Goals & Non-Goals](#goals--non-goals)
1. [User Stories](#user-stories)
1. [Architecture](#architecture)
1. [Command Taxonomy](#command-taxonomy)
1. [Agent-First Contract (CLI-MANIFEST Compliance)](#agent-first-contract)
1. [Structured Envelope](#structured-envelope)
1. [Error Code Taxonomy](#error-code-taxonomy)
1. [Exit Code Contract](#exit-code-contract)
1. [Transactional Workflow: Plan → Validate → Apply → Verify](#transactional-workflow)
1. [Manifest Format](#manifest-format)
1. [Single-File Shortcut](#single-file-shortcut)
1. [TOON & LLM=true](#toon--llmtrue)
1. [Auth Contract](#auth-contract)
1. [guide Command](#guide-command)
1. [Observability](#observability)
1. [Project Structure](#project-structure)
1. [Technology Stack](#technology-stack)
1. [Open Questions](#open-questions)

-----

## Overview

`confpub` is an agent-first CLI tool that publishes Markdown files to Confluence Cloud and Server. It accepts either a single Markdown file or a structured manifest declaring a page tree with assets, and converts the content to Confluence Storage Format before uploading.

The CLI is designed according to the CLI-MANIFEST specification, making it fully drivable by LLM agents and automation pipelines with zero additional tooling — while remaining equally usable by humans at the terminal.

-----

## Goals & Non-Goals

### Goals

- Publish one or more Markdown files to Confluence Cloud or Server/Data Center
- Support asset (image) upload and URL rewriting in the converted output
- Maintain a lockfile of page IDs for idempotent re-publishing
- Implement a full plan → validate → apply → verify workflow for safe mutation
- Emit a single structured JSON envelope on stdout for every command, success or failure
- Be fully drivable by an LLM agent from `confpub guide` alone
- Respect `LLM=true`, `isatty()`, and `--quiet` for noise suppression

### Non-Goals

- Pulling content back from Confluence into Markdown (no sync/pull)
- Full Confluence admin operations (space creation, user management, permissions)
- Real-time collaborative editing or watch-mode live reload (future consideration)
- Supporting Confluence markup formats other than Storage Format

-----

## User Stories

|Actor       |Story                                                                                              |
|------------|---------------------------------------------------------------------------------------------------|
|Human author|I want to publish a single Markdown file to a Confluence space with one command                    |
|Human author|I want to publish a whole documentation tree from a manifest, preserving page hierarchy            |
|Human author|I want to preview what would change before committing any writes                                   |
|LLM agent   |I want to call `confpub guide` once and have everything I need to publish without external docs    |
|LLM agent   |I want every response in a stable JSON shape so I can write one parser                             |
|LLM agent   |I want structured error codes with retry hints so I know whether to retry, fix input, or escalate  |
|CI pipeline |I want distinct exit codes per error category so I can branch in shell scripts without parsing JSON|
|CI pipeline |I want `--dry-run` to always return structured change records, not prose                           |

-----

## Architecture

```
confpub/
├── confpub/
│   ├── cli.py              # Typer app — all commands, envelope output, exit codes
│   ├── envelope.py         # Pydantic envelope model, request_id generation
│   ├── errors.py           # Error code constants, exit code mapping, retry hints
│   ├── guide.py            # guide command — full schema serialization
│   ├── manifest.py         # Manifest + plan artifact Pydantic models
│   ├── planner.py          # plan.create — fingerprinting, diff, plan artifact
│   ├── validator.py        # plan.validate — re-fingerprint, check source files
│   ├── applier.py          # plan.apply — Confluence writes, change records
│   ├── verifier.py         # plan.verify — structured assertions
│   ├── converter.py        # Markdown → Confluence Storage Format
│   ├── assets.py           # Asset discovery, upload, URL rewriting
│   ├── lockfile.py         # confpub.lock — page ID persistence
│   ├── confluence.py       # atlassian-python-api wrapper
│   ├── output.py           # TOON/LLM=true/isatty logic, stderr progress events
│   └── config.py           # Credential precedence, keychain, env vars
├── tests/
├── pyproject.toml
└── README.md
```

-----

## Command Taxonomy

All commands follow the `noun verb` dotted-ID pattern. Verbs telegraph mutation intent — an agent can determine from the verb alone whether a command is safe to run speculatively.

```
confpub guide                    # Full machine-readable CLI schema

# Read commands (safe, idempotent, parallelizable)
confpub page list                # page.list
confpub page inspect             # page.inspect
confpub space list               # space.list
confpub attachment list          # attachment.list

# Write commands (require safety rails)
confpub page publish             # page.publish  (sugar: runs full workflow internally)
confpub page delete              # page.delete
confpub attachment upload        # attachment.upload

# Transactional workflow
confpub plan create              # plan.create   — no writes
confpub plan validate            # plan.validate — no writes
confpub plan apply               # plan.apply    — writes, supports --dry-run
confpub plan verify              # plan.verify   — no writes

# Auth & config
confpub auth inspect             # auth.inspect
confpub config set               # config.set
confpub config inspect           # config.inspect
```

### Standard Verb Semantics

|Verb      |Mutates?|Notes                                           |
|----------|--------|------------------------------------------------|
|`list`    |No      |Enumerate resources                             |
|`inspect` |No      |Detailed view of one resource                   |
|`create`  |Yes     |Generate a new artifact (plan file)             |
|`validate`|No      |Check without mutating                          |
|`apply`   |Yes     |Execute a plan; supports `--dry-run`            |
|`verify`  |No      |Assert post-conditions hold                     |
|`publish` |Yes     |Shortcut: full workflow in one call             |
|`delete`  |Yes     |Destructive; requires explicit confirmation flag|
|`upload`  |Yes     |Write an asset to Confluence                    |
|`set`     |Yes     |Write a config value                            |

-----

## Agent-First Contract

`confpub` fully implements the CLI-MANIFEST specification:

|Part                            |Principles Applied                                                                                                                                       |
|--------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
|**I — Foundations**             |Structured envelope, error codes, exit codes, `guide` command, consistent naming, examples in help, TOON, `LLM=true`, observability, schema versioning   |
|**II — Read & Discover**        |Read/write separation, rich structured metadata from `page.inspect` and `space.list`                                                                     |
|**III — Safe Mutation**         |`--dry-run` on every write, before/after change records, explicit safety flags, `--backup`, atomic writes via temp-file rename                           |
|**IV — Transactional Workflows**|Fingerprint-based conflict detection, plan → validate → apply → verify, structured assertions in `plan.verify`, manifest as workflow composition artifact|

-----

## Structured Envelope

**Every command — success or failure — returns this exact shape.** No exceptions.

```jsonc
{
  "schema_version": "1.0",
  "request_id": "req_20260228_143000_7f3a",
  "ok": true,
  "command": "page.publish",
  "target": {
    "space": "DEV",
    "title": "Architecture Overview"
  },
  "result": { ... },
  "warnings": [],
  "errors": [],
  "metrics": {
    "duration_ms": 842,
    "pages_published": 1,
    "attachments_uploaded": 3,
    "bytes_transferred": 48210
  }
}
```

### Envelope Invariants

- `schema_version`, `request_id`, `ok`, `command`, `result`, `errors`, `warnings`, and `metrics` are **always** present
- `errors` and `warnings` are **always arrays** (possibly empty), never omitted
- `result` is **always present**; on failure it is `null`, never missing
- `command` is the canonical dotted command ID regardless of user-facing aliases
- `request_id` is unique per invocation and appears in stderr diagnostics for correlation

### Failure Envelope Example

```jsonc
{
  "schema_version": "1.0",
  "request_id": "req_20260228_143001_a2b9",
  "ok": false,
  "command": "page.publish",
  "target": { "space": "DEV", "title": "Architecture Overview" },
  "result": null,
  "warnings": [],
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
  ],
  "metrics": { "duration_ms": 210 }
}
```

-----

## Error Code Taxonomy

### Error Prefixes & Exit Codes

|Code prefix       |Exit code|Meaning                                                |`retryable`|`suggested_action`    |
|------------------|---------|-------------------------------------------------------|-----------|----------------------|
|`ERR_VALIDATION_*`|10       |Bad input, schema mismatch, missing required field     |`false`    |`fix_input`           |
|`ERR_AUTH_*`      |20       |Token invalid, permission denied, space not accessible |Varies     |`reauth` or `escalate`|
|`ERR_CONFLICT_*`  |40       |Fingerprint mismatch, stale lock, plan out of date     |`false`    |`fix_input`           |
|`ERR_IO_*`        |50       |File not found, network timeout, Confluence unreachable|`true`     |`retry`               |
|`ERR_INTERNAL_*`  |90       |Unexpected converter failure, SDK bug                  |`false`    |`escalate`            |

### Specific Error Codes

```
ERR_VALIDATION_REQUIRED          Missing --space, --parent, or file argument
ERR_VALIDATION_MANIFEST          Manifest YAML fails schema validation
ERR_VALIDATION_MARKDOWN          Unparseable Markdown block
ERR_VALIDATION_ASSET_MISSING     Referenced image file not found on disk

ERR_AUTH_REQUIRED                No credentials configured
ERR_AUTH_EXPIRED                 Token has expired
ERR_AUTH_FORBIDDEN               Token valid but lacks write permission to space

ERR_CONFLICT_FINGERPRINT         Page changed since plan was created
ERR_CONFLICT_LOCK                Another confpub process holds the lock
ERR_CONFLICT_PAGE_EXISTS         Page title exists with unexpected ID

ERR_IO_FILE_NOT_FOUND            Source Markdown file missing
ERR_IO_CONNECTION                Confluence unreachable
ERR_IO_TIMEOUT                   Request timed out

ERR_INTERNAL_CONVERTER           Markdown → Storage Format conversion crashed
ERR_INTERNAL_SDK                 atlassian-python-api unexpected response
```

Error codes are **stable across versions**. New codes may be added freely; existing codes are never renamed or removed without a major schema bump.

-----

## Exit Code Contract

```
0   Success
10  Validation error    — fix input, do not retry
20  Auth / permission   — reauth or escalate
40  Conflict            — re-plan, do not blindly retry
50  I/O error           — retry with backoff
90  Internal error      — file a bug
```

-----

## Transactional Workflow

The full workflow is: **plan.create → plan.validate → plan.apply → plan.verify**

Each phase is a separate command. An agent can stop at any phase. Plans are first-class artifacts — JSON files that can be reviewed, diffed, version-controlled, and passed between agents and humans.

### Phase 1: `confpub plan create`

Reads all source files, resolves the page tree, fingerprints every page that already exists in Confluence, and writes a **plan artifact**. No Confluence writes occur.

```bash
confpub plan create \
  --manifest confpub.yaml \
  --output confpub-plan.json
```

**Plan artifact (`confpub-plan.json`):**

```jsonc
{
  "schema_version": "1.0",
  "created_at": "2026-02-28T14:30:00Z",
  "space": "DEV",
  "parent": "Architecture Notes",
  "pages": [
    {
      "id": "plan_1",
      "title": "Overview",
      "source_file": "overview.md",
      "confluence_page_id": "123456",
      "current_fingerprint": "sha256:abc123",
      "operation": "update",
      "attachments": [
        {
          "file": "diagrams/arch.png",
          "confluence_attachment_id": null,
          "operation": "upload"
        }
      ]
    },
    {
      "id": "plan_2",
      "title": "Component Design",
      "source_file": "components/design.md",
      "confluence_page_id": null,
      "current_fingerprint": null,
      "operation": "create",
      "attachments": []
    }
  ],
  "summary": {
    "create": 2,
    "update": 1,
    "noop": 3,
    "attachments_to_upload": 4
  }
}
```

**Envelope result:**

```jsonc
{
  "ok": true,
  "command": "plan.create",
  "result": {
    "plan_file": "./confpub-plan.json",
    "summary": { "create": 2, "update": 1, "noop": 3, "attachments_to_upload": 4 }
  }
}
```

-----

### Phase 2: `confpub plan validate`

Re-reads the plan file, checks that all source files still exist, and re-fingerprints existing Confluence pages to detect external edits since planning. **No writes.**

```bash
confpub plan validate --plan confpub-plan.json
```

```jsonc
{
  "ok": false,
  "command": "plan.validate",
  "result": {
    "valid": false,
    "checks": [
      {
        "page_id": "plan_1",
        "title": "Overview",
        "passed": false,
        "issue": "ERR_CONFLICT_FINGERPRINT",
        "detail": "Page modified externally since plan was created — re-run plan.create"
      },
      { "page_id": "plan_2", "title": "Component Design", "passed": true }
    ]
  }
}
```

-----

### Phase 3: `confpub plan apply`

Executes the plan. Refuses if validation would fail unless `--skip-fingerprint-check` is explicitly passed. Always supports `--dry-run`.

```bash
# Preview (no writes)
confpub plan apply --plan confpub-plan.json --dry-run

# Real apply (with automatic backup)
confpub plan apply --plan confpub-plan.json --backup
```

**Dry-run result:**

```jsonc
{
  "ok": true,
  "command": "plan.apply",
  "result": {
    "dry_run": true,
    "changes": [
      {
        "type": "page.create",
        "title": "New Component Guide",
        "before": null,
        "after": { "title": "New Component Guide", "parent": "Architecture Notes" }
      },
      {
        "type": "page.update",
        "title": "Overview",
        "confluence_page_id": "123456",
        "before": { "version": 4 },
        "after": { "version": 5 },
        "attachments_added": ["diagrams/arch.png"]
      }
    ],
    "summary": { "create": 1, "update": 1, "attachments_upload": 1 }
  }
}
```

On real apply, every change record includes page IDs, versions, and attachment IDs before and after. The lockfile is updated with any new page IDs.

**Safety flags for `plan.apply`:**

|Flag                      |Risk bypassed                                                                    |
|--------------------------|---------------------------------------------------------------------------------|
|`--skip-fingerprint-check`|Allows applying a plan even if Confluence pages changed since planning           |
|`--cascade`               |Allows deletes that affect child pages                                           |
|`--backup`                |*(Recommended, not dangerous)* Snapshots existing page content before overwriting|

-----

### Phase 4: `confpub plan verify`

Declarative post-condition assertions. Accepts a list of assertion objects and returns structured pass/fail results.

```bash
confpub plan verify --assertions verify.json
```

**Input assertions:**

```jsonc
[
  { "type": "page.exists",      "space": "DEV", "title": "Overview" },
  { "type": "page.parent",      "title": "Components", "expected_parent": "Overview" },
  { "type": "attachment.exists","page": "Overview", "filename": "arch.png" }
]
```

**Result:**

```jsonc
{
  "ok": true,
  "command": "plan.verify",
  "result": {
    "all_passed": true,
    "results": [
      { "type": "page.exists",       "passed": true, "title": "Overview" },
      { "type": "page.parent",       "passed": true, "title": "Components" },
      { "type": "attachment.exists", "passed": true, "page": "Overview", "filename": "arch.png" }
    ]
  }
}
```

Assertions can also be declared inline in the manifest and are run automatically at the end of a `page.publish` call.

-----

## Manifest Format

```yaml
schema_version: "1.0"
space: DEV
parent: "Architecture Notes"

confluence:
  base_url: https://yourorg.atlassian.net/wiki
  auth:
    type: token            # token | basic | env
    # Credentials via env: CONFPUB_TOKEN + CONFPUB_USER
    # Never store credentials directly in the manifest

conflict_strategy: fail    # fail | overwrite | skip
on_removal: leave          # leave | delete
version_comment: "Published by confpub @ {timestamp}"

labels:
  - architecture
  - auto-published

# Run automatically as plan.verify step after apply
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

### Lockfile

After the first successful apply, `confpub` writes a `confpub.lock` file alongside the manifest. This maps page titles to Confluence page IDs, enabling idempotent re-publishing on subsequent runs.

```jsonc
// confpub.lock — commit to version control
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

-----

## Single-File Shortcut

`confpub page publish` is sugar that runs the full plan → validate → apply → verify pipeline internally. It returns the same structured envelope with full change records.

```bash
confpub page publish overview.md \
  --space DEV \
  --parent "Architecture Notes" \
  --title "Architecture Overview" \
  --dry-run
```

`--dry-run` always works, always returns structured change records. There is no confirmation prompt. Interactive prompts are never used.

-----

## TOON & `LLM=true`

### Output Modes

|Flag / Env |stdout                            |stderr           |
|-----------|----------------------------------|-----------------|
|`--quiet`  |Envelope only                     |Errors only      |
|*(default)*|Envelope only                     |Errors + warnings|
|`--verbose`|Envelope + diagnostics in `result`|Full debug log   |

### Precedence (highest → lowest)

1. Explicit CLI flags (`--quiet`, `--verbose`, `--output json`)
1. Environment variables (`LLM=true`, `NO_COLOR=1`, `CI=true`)
1. `isatty()` detection
1. Defaults

### Implementation

```python
import sys, os

llm_mode = os.environ.get("LLM") == "true"
is_tty   = sys.stdout.isatty()
quiet    = llm_mode or not is_tty

# stdout: structured JSON only — always, no exceptions
# stderr: progress, spinners, banners — only when quiet is False
```

### Progress Events (stderr)

Long-running commands emit newline-delimited JSON events to stderr:

```json
{"event": "progress", "step": 1, "total": 4, "message": "Fingerprinting existing pages"}
{"event": "progress", "step": 2, "total": 4, "message": "Uploading arch.png"}
{"event": "progress", "step": 3, "total": 4, "message": "Publishing Overview"}
{"event": "progress", "step": 4, "total": 4, "message": "Running assertions"}
```

For long runs, `result` also includes a `log_file` path:

```jsonc
{
  "ok": true,
  "result": {
    "pages_published": 5,
    "log_file": "/tmp/confpub-20260228T143000Z.log"
  }
}
```

### Rules

- stdout is **exclusively** for the structured JSON response — one object, no preamble, no epilog
- stderr is for progress, debug logs, banners, diagnostics
- Update notifications and decorative output are never printed to stdout
- `LLM=true` suppresses interactive prompts; instead of blocking, `confpub` returns a structured error

-----

## Auth Contract

Credentials are **never** prompted for interactively when stdin/stdout is non-interactive or `LLM=true`. Instead, a structured error is returned immediately.

### Credential Precedence

```
--token / --user  →  CONFPUB_TOKEN / CONFPUB_USER  →  config file  →  OS keychain
```

### Auth Error Example

```jsonc
{
  "ok": false,
  "command": "page.list",
  "result": null,
  "errors": [
    {
      "code": "ERR_AUTH_REQUIRED",
      "message": "No credentials configured",
      "retryable": false,
      "suggested_action": "reauth",
      "details": {
        "methods": ["env_var", "config_file", "cli_flag"],
        "env_vars": ["CONFPUB_TOKEN", "CONFPUB_USER"],
        "docs": "confpub guide --section auth"
      }
    }
  ]
}
```

### `confpub auth inspect`

Returns current credential status without attempting any Confluence operation:

```jsonc
{
  "ok": true,
  "command": "auth.inspect",
  "result": {
    "base_url": "https://yourorg.atlassian.net/wiki",
    "user": "thomas@example.com",
    "auth_type": "token",
    "token_source": "env_var",
    "token_valid": true,
    "token_expires_at": null
  }
}
```

-----

## `guide` Command

`confpub guide` returns the full CLI schema in a single call. An agent calls this once, caches the result, and can drive the entire CLI zero-shot.

```bash
confpub guide
confpub guide --section auth
confpub guide --section error_codes
confpub guide --section commands.plan.apply
```

### Abbreviated Guide Output

```jsonc
{
  "schema_version": "1.0",
  "compatibility": {
    "additive_changes": "minor",
    "breaking_changes": "major"
  },
  "commands": {
    "plan.create": {
      "group": "transactional",
      "mutates": false,
      "description": "Generate a plan artifact from a manifest or file",
      "flags": ["--manifest", "--output", "--space", "--parent"]
    },
    "plan.validate": {
      "group": "transactional",
      "mutates": false,
      "flags": ["--plan"]
    },
    "plan.apply": {
      "group": "transactional",
      "mutates": true,
      "flags": ["--plan", "--dry-run", "--backup", "--skip-fingerprint-check", "--cascade"],
      "safety_flags": {
        "--skip-fingerprint-check": "Bypasses stale-state detection — use only if you know the page changed intentionally",
        "--cascade": "Allows deletes that affect child pages"
      }
    },
    "plan.verify": {
      "group": "transactional",
      "mutates": false,
      "flags": ["--assertions", "--plan"]
    },
    "page.publish": {
      "group": "write",
      "mutates": true,
      "flags": ["--space", "--parent", "--title", "--dry-run", "--backup"]
    },
    "page.list": { "group": "read", "mutates": false },
    "page.inspect": { "group": "read", "mutates": false }
  },
  "error_codes": {
    "ERR_CONFLICT_FINGERPRINT": {
      "exit_code": 40, "retryable": false, "suggested_action": "fix_input"
    },
    "ERR_IO_CONNECTION": {
      "exit_code": 50, "retryable": true, "retry_after_ms": 2000, "suggested_action": "retry"
    },
    "ERR_AUTH_REQUIRED": {
      "exit_code": 20, "retryable": false, "suggested_action": "reauth"
    }
  },
  "concurrency": {
    "rule": "Never run multiple write commands against the same space and page in parallel",
    "safe_patterns": [
      "Read commands (page.list, page.inspect) can parallelize freely",
      "Writes to DIFFERENT spaces can parallelize",
      "Use plan.apply with a single manifest for multi-page publishes — do not run parallel applies"
    ],
    "lock_behavior": "plan.apply acquires a local lockfile; concurrent applies to the same workspace return ERR_CONFLICT_LOCK"
  },
  "auth": {
    "precedence": ["--token + --user", "CONFPUB_TOKEN + CONFPUB_USER", "config_file", "os_keychain"],
    "non_interactive": "Never prompts when LLM=true or stdin is non-interactive",
    "inspect_command": "confpub auth inspect"
  }
}
```

-----

## Observability

Every response includes a `metrics` block:

```jsonc
{
  "metrics": {
    "duration_ms": 842,
    "pages_published": 3,
    "pages_skipped": 2,
    "attachments_uploaded": 4,
    "bytes_transferred": 98432,
    "confluence_api_calls": 11
  }
}
```

-----

## Technology Stack

|Concern                 |Choice                    |Rationale                                                                                               |
|------------------------|--------------------------|--------------------------------------------------------------------------------------------------------|
|CLI framework           |**Typer**                 |Type-annotated, modern, excellent `--help` generation, `typer.Exit(code=N)` for exit codes              |
|Confluence API          |**atlassian-python-api**  |Supports Cloud and Server/DC, well-maintained, handles auth variants                                    |
|Markdown parsing        |**markdown-it-py**        |CommonMark-compliant, extensible renderer                                                               |
|Storage Format rendering|Custom renderer           |Pluggable via markdown-it-py token stream; handles code blocks, images, admonitions as Confluence macros|
|Manifest validation     |**Pydantic v2**           |Schema validation, serialization, lockfile models                                                       |
|JSON serialization      |**orjson**                |Fast, handles datetime/UUID natively                                                                    |
|Credential storage      |**keyring** + env vars    |OS keychain with env var override                                                                       |
|Hashing / fingerprinting|**hashlib** (stdlib)      |SHA-256 of page Storage Format bytes                                                                    |
|Atomic file writes      |**tempfile** + `os.rename`|POSIX atomic; Windows near-atomic                                                                       |

### Markdown → Storage Format Conversion

Key conversion targets:

|Markdown element            |Confluence Storage Format output                                                  |
|----------------------------|----------------------------------------------------------------------------------|
|Fenced code block           |`<ac:structured-macro ac:name="code">` with `ac:parameter ac:name="language">`    |
|Image reference             |Upload attachment first; rewrite to `<ac:image><ri:attachment ri:filename="..."/>`|
|`> [!NOTE]` / `> [!WARNING]`|Confluence Info / Warning macro                                                   |
|Table                       |Standard XHTML `<table>`                                                          |
|Internal page link          |`<ac:link><ri:page ri:content-title="..."/>`                                      |
|Heading                     |`<h1>` – `<h6>` XHTML                                                             |

-----

## Open Questions

|#|Question                                                                                                                                                     |Impact                 |Recommendation                                                                                 |
|-|-------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------|-----------------------------------------------------------------------------------------------|
|1|**Conflict strategy on title change** — if a page title changes in the manifest, should confpub delete the old page and create a new one, or update in place?|Lockfile design        |Update in place via page ID; log a warning that the title changed                              |
|2|**Deletion on manifest removal** — if a page is removed from the manifest, should confpub delete it from Confluence?                                         |`on_removal` config key|Default to `leave`; require `on_removal: delete` + `--cascade` flag for destructive removes    |
|3|**Confluence Cloud vs Server auth** — Cloud uses API token + email; Server uses PAT or basic auth. Should this be auto-detected from the URL?                |Auth flow              |Auto-detect: `*.atlassian.net` → Cloud token auth; anything else → PAT with basic auth fallback|
|4|**Watch mode** — `confpub watch` for live republish on file save during authoring                                                                            |Scope                  |Post-1.0; implement as a separate `confpub watch` command using `watchfiles`                   |
|5|**Admonition syntax** — which Markdown admonition syntax to support? GitHub-flavored `> [!NOTE]`, or a custom syntax?                                        |Converter              |Support GitHub-flavored admonitions as primary; add Obsidian callout syntax as secondary       |
|6|**Idempotency keys** — should `plan.apply` support `--idempotency-key` for safe retries after timeout?                                                       |Reliability in CI      |Yes; store applied key in lockfile with 24h TTL                                                |
|7|**Page ordering** — Confluence doesn’t guarantee child page order by default. Should confpub enforce order?                                                  |Publisher complexity   |Yes; use Confluence’s `position` parameter on page create/move                                 |

-----

*Build CLIs like APIs. If an LLM can’t drive it zero-shot from `guide` + `--help`, it’s not agent-ready.*
