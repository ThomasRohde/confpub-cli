# confpub-cli v0.5.0 — Blind Test Feedback

Tested by: Claude Code (Opus 4.6) on 2026-03-01, Windows 11, via `uvx confpub-cli`.

---

## Summary

confpub v0.5.0 is a well-designed, agent-friendly CLI. The structured JSON envelope, clear error taxonomy, and comprehensive `guide` command make it straightforward for an LLM agent to drive programmatically. The full publish/pull/delete lifecycle works correctly, and round-trip Markdown fidelity is excellent. This review covers what works well, what could be improved, and specific bugs encountered.

---

## What Works Well

### Structured JSON Envelope
Every command returns the same `{ ok, command, target, result, warnings, errors, metrics }` shape. This is the single most important design decision for agent consumption — no output parsing required.

### Error Taxonomy
Typed error codes (`ERR_VALIDATION_*`, `ERR_AUTH_*`, `ERR_IO_*`, `ERR_CONFLICT_*`) with `retryable` and `suggested_action` fields make programmatic error handling trivial. Exit codes are consistent with the documented schema.

### `guide` Command
The machine-readable schema is comprehensive: command metadata, flags, safety annotations, concurrency rules, error codes, and auth precedence. The `--section` flag works for top-level keys (`commands`, `auth`, `error_codes`, `concurrency`).

### Markdown Round-Trip Fidelity
Published a file with headings, bullet lists, tables, blockquotes, and fenced code blocks. Pulled it back — the Markdown was virtually identical (only trivial whitespace differences in table alignment `| --- |` vs `|---------|`). This is a strong result.

### Publish Lifecycle
- `page.publish` with `--dry-run` correctly reports what would happen before writing.
- Re-publishing an existing page updates it in-place with version increment.
- `--backup` flag saves the previous HTML to `.confpub-backup-{id}.html`.
- `--title` override works as expected.
- `page.delete` cleanly removes the page.

### Recursive Pull + Manifest Generation
`page pull --recursive --manifest` correctly traverses child pages and generates a well-structured `confpub.yaml` manifest. The flat layout manifest correctly represents the page hierarchy with `children:` nesting.

### Plan Workflow
The `plan create` / `plan validate` / `plan apply --dry-run` workflow functions correctly. Plans include fingerprints for stale-state detection, which is a nice safety feature.

### Lock File
`confpub.lock` tracks page IDs and versions, providing local state awareness across commands.

### Auth & Config
`auth inspect` and `config inspect` return clear, useful information. Token masking in `config inspect` is a good security practice.

---

## Bugs

### 1. Stderr Message Leaks on Expected "Not Found" Lookups
**Severity: Medium**

When publishing a new page (or doing a dry-run), the CLI prints `Can't find '<title>' page on ...` to stderr before the JSON output. This happens because the tool checks whether the page exists first. For a *new* page, not finding it is the expected path — not an error. The message is confusing, especially during `--dry-run` where the user explicitly wants to preview a creation.

`--quiet` suppresses it, but agents shouldn't need `--quiet` for expected behavior.

**Suggestion:** Only emit this message at `--verbose` level, or suppress it when the subsequent operation succeeds.

### 2. Relative Paths Fail for `plan validate` and `plan apply`
**Severity: Medium**

```
uvx confpub-cli plan validate --plan plan-test/test-plan.json
# ERR_IO_FILE_NOT_FOUND: Plan file not found: plan-test/test-plan.json

uvx confpub-cli plan validate --plan "C:/Users/.../test-plan.json"
# Works fine
```

Relative paths resolve correctly for `page publish` (the FILE argument) but not for `--plan` in plan commands. This is likely a `Path.resolve()` vs `Path()` issue.

### 3. `page inspect` `webui` Field Inconsistent Format
**Severity: Low**

- With `--space SD --title "..."`: returns relative URL `/spaces/SD/pages/327981/Test+Page`
- With `--page-id 327981`: returns absolute URL `https://...atlassian.net/wiki/spaces/SD/pages/327981/Test+Page`

Should be consistent — preferably always absolute, since the agent may not know the base URL.

### 4. `ERR_AUTH_FORBIDDEN` for Nonexistent Space
**Severity: Low**

```
uvx confpub-cli page inspect --space FAKESPACE --title "Test"
# ERR_AUTH_FORBIDDEN: "Permission denied (get_page)"
# suggested_action: "escalate"
```

A nonexistent space key returns a permission error rather than a "space not found" validation error. The `suggested_action` is `"escalate"` but the guide says ERR_AUTH_FORBIDDEN should suggest `"reauth"`. An agent following the guide would incorrectly attempt to re-authenticate.

### 5. `guide --section` Does Not List Valid Sections on Error
**Severity: Low**

```
uvx confpub-cli guide --section search
# ERR_VALIDATION_REQUIRED: "Unknown guide section: search"
```

The error doesn't tell you what the valid sections are. Adding `"valid_sections": ["commands", "auth", "error_codes", "concurrency", "compatibility"]` to the error details would save a round-trip.

### 6. Nested Layout Manifest Uses Ambiguous `file: index.md` for All Pages
**Severity: Medium**

When using `--layout nested`, every page gets `file: index.md` in the manifest without a directory prefix:

```yaml
pages:
- title: confpub v0.3.0 Blind Test Report
  file: index.md
  children:
  - title: What Works Well
    file: index.md
  - title: Bugs and Issues
    file: index.md
```

These are all `index.md` — a plan created from this manifest would have no way to distinguish them. The file paths should include the relative directory (e.g., `confpub-v030-blind-test-report/index.md`).

### 7. Nested Layout Doesn't Actually Nest Directories
**Severity: Low**

The `--layout nested` option creates a flat set of directories rather than truly nesting children inside parents:

```
pulled-nested/
  confpub-v030-blind-test-report/index.md   # parent
  what-works-well/index.md                   # child (not nested inside parent dir)
  bugs-and-issues/index.md                   # child
  full-test-matrix/index.md                  # child
```

Expected behavior for "nested" layout would place children inside the parent directory.

### 8. `--layout nested` Generates Manifest Without `--manifest` Flag
**Severity: Low**

Using `page pull --layout nested` generates a `confpub.yaml` even without the `--manifest` flag. The flat layout correctly requires `--manifest` to generate one.

---

## Suggestions (Not Bugs)

### Add `page.inspect --format markdown`
Currently `page inspect` returns raw Confluence storage XML. An option to return the reverse-converted Markdown would be useful for quick content review without pulling to a file.

### Add `search --type page` Default for Agent Usage
Agents almost always want pages, not attachments or space entities. Consider a default or a `--pages-only` shorthand.

### Document `confpub.lock` in `guide`
The lock file is created implicitly but isn't documented in the guide schema. Agents should know it exists and what it tracks.

### `ERR_IO_FILE_NOT_FOUND` Suggestion for Missing Source
When the source file doesn't exist, `retryable: true` with `suggested_action: "retry"` is misleading — a file that doesn't exist won't appear on retry. Consider `retryable: false` with `suggested_action: "fix_input"` for local file-not-found errors (vs. transient network errors).

---

## Test Matrix

| Command | Flags Tested | Result | Notes |
|---|---|---|---|
| `guide` | (none), `--section commands`, `--section auth`, `--section error_codes` | Pass | `--section` works for top-level keys |
| `guide --section` | invalid section name | Pass (with note) | Error lacks valid section list |
| `auth inspect` | (none) | Pass | |
| `config inspect` | (none) | Pass | Token correctly masked |
| `space list` | (none) | Pass | |
| `page list` | `--space` | Pass | |
| `page inspect` | `--space --title`, `--page-id` | Pass | webui format inconsistency |
| `page publish` | `--dry-run`, `--backup`, `--title` | Pass | stderr leak on new page |
| `page publish` (update) | `--backup` | Pass | Version incremented correctly |
| `page pull` | `--output`, `--force`, `--manifest` | Pass | |
| `page pull` | `--recursive`, `--layout flat` | Pass | |
| `page pull` | `--recursive`, `--layout nested` | Pass (with notes) | Manifest ambiguity, not truly nested |
| `page delete` | `--space --title` | Pass | |
| `search` | `--space`, `--limit`, `--cql` | Pass | |
| `plan create` | `--manifest`, `--output` | Pass | |
| `plan validate` | `--plan` (absolute path) | Pass | Relative path fails |
| `plan apply` | `--plan --dry-run` | Pass | |
| `attachment list` | `--page-id` | Pass | |
| `--quiet` | global flag | Pass | Suppresses stderr messages |
| `--verbose` | global flag | Pass | Adds diagnostics to metrics |
| Error: missing file | `page publish nonexistent.md` | Pass | Clear error |
| Error: missing page | `page inspect --title "..."` | Pass | |
| Error: missing args | `page publish` (no file) | Pass | |
| Error: missing space | `--space FAKESPACE` | Fail | Misleading ERR_AUTH_FORBIDDEN |

---

## Overall Assessment

**confpub v0.5.0 is production-ready for the core publish/pull/delete workflow.** The agent-first JSON design, error taxonomy, and guide command set a high bar for CLI ergonomics. The main areas for improvement are:

1. Fix relative path resolution for plan commands (blocks scripted workflows)
2. Fix the nested layout manifest ambiguity (blocks round-trip with nested trees)
3. Suppress the "Can't find" stderr noise on expected new-page creation
4. Normalize the `webui` field format

None of these are blockers for single-page publishing, which is the most common use case.
