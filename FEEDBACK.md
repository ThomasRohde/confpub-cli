# confpub-cli v0.2.2 — Blind Test Feedback

**Tester:** Claude Code (Opus 4.6), acting as an LLM agent
**Date:** 2026-03-01
**Method:** Zero-shot exploration starting from `uvx confpub-cli --help`, then progressively deeper testing of every subcommand, error path, and workflow.

---

## Overall Impression

confpub is a **remarkably well-designed agent-first CLI**. The `guide` command as a single bootstrap entry point is a standout idea — I was able to learn the entire CLI schema, error codes, auth precedence, and concurrency rules in one call. The structured JSON envelope on stdout with progress on stderr is exactly right for machine consumption. This is one of the best-designed CLIs I've encountered for agent integration.

**Score: 8.5/10** — excellent foundation, a few rough edges to polish.

---

## What Works Well

### 1. The `guide` command is brilliant
One call to `confpub guide` gave me everything: all commands with flags, mutation indicators, error codes with exit codes and retry hints, auth precedence, and concurrency rules. The `--section` filter is a nice touch. This is the gold standard for agent-discoverability.

### 2. Structured JSON envelope is consistent
Every response — success or failure — follows the same shape: `schema_version`, `request_id`, `ok`, `command`, `target`, `result`, `warnings`, `errors`, `metrics`. I never had to guess the format. The `request_id` is useful for log correlation.

### 3. Error codes are stable and actionable
`ERR_IO_FILE_NOT_FOUND` with `retryable: true` and `suggested_action: "retry"` — that's exactly what an agent needs. The exit code bucketing (10=validation, 20=auth, 40=conflict, 50=IO, 90=internal) is clean. I could build a robust retry/escalation loop from just the `guide --section error_codes` output.

### 4. Transactional plan workflow
The `plan create → validate → apply → verify` pipeline with fingerprint-based conflict detection is a strong design. Separating the plan artifact from execution lets an agent inspect and reason about changes before committing. The `--dry-run` flag on both `page publish` and `plan apply` is essential.

### 5. Safety annotations
The `safety_flags` in the guide output (e.g., `--cascade: "Also deletes child pages"`) are a great signal for agents to ask for human confirmation before using dangerous flags.

### 6. Auth precedence is well-thought-out
CLI flags → env vars → config file → OS keychain, with `LLM=true` suppressing interactive prompts — exactly right.

### 7. Mutation markers
Every command in the guide is tagged with `mutates: true/false` and grouped (`read`, `write`, `transactional`). This makes it trivial for an agent to know which commands are safe to call speculatively.

---

## Issues Found

### Bug: `--quiet` flag does not suppress stderr

**Severity:** Medium
**Steps:** Run `confpub-cli --quiet page publish page.md --space SD --parent "Software Development" --dry-run` and capture stderr.
**Expected:** stderr should be empty (or at least suppress the "Can't find..." message).
**Actual:** The message `Can't find 'Page' page on https://thomasklokrohde.atlassian.net/wiki` still appears on stderr, identical to the non-quiet run.

### Bug: `target.title` shows raw filename instead of resolved title

**Severity:** Low
**Steps:** Run `page publish page.md --space SD --parent "..." --dry-run` (no `--title` flag).
**Expected:** `target.title` should be `"Page"` (the resolved title).
**Actual:** `target.title` is `"page.md"` (the raw filename), while the actual page title used in `result.changes` is `"Page"`. An agent parsing `target.title` would get the wrong value.

### Bug: Nonexistent space returns `ERR_INTERNAL_SDK` (exit 90) instead of a specific error

**Severity:** Medium
**Steps:** Run `page inspect --space NONEXISTENT --title "nope"`.
**Expected:** A specific error like `ERR_AUTH_FORBIDDEN` (exit 20) or a new `ERR_NOT_FOUND` code.
**Actual:** Returns `ERR_INTERNAL_SDK` with exit code 90 and `suggested_action: "escalate"`. The message is `"Unexpected API error (get_page): The calling user does not have permission to view the content"`. This is misleading — it's not an internal error, it's a permissions/not-found issue. An agent following the `escalate` suggestion would file a bug report instead of trying a different space key.

### Rough edge: `--verbose` flag has no visible effect

**Severity:** Low
**Steps:** Compare `auth inspect` output with and without `--verbose`.
**Observation:** The JSON output is identical. No extra diagnostics field, no additional stderr output. Either verbose mode isn't implemented yet, or its effect is too subtle to observe.

### Rough edge: `page.list` and `page.inspect` responses are extremely verbose

**Severity:** Medium (for agent consumption)
**Observation:** These commands return the raw Confluence API response including `_expandable`, `_links`, `macroRenderedOutput`, `profilePicture`, `accountType`, etc. A single `page.list` for 5 pages produced ~300 lines of JSON. For an agent working within a context window, this is wasteful. A slimmed-down response with just `id`, `title`, `version.number`, `version.when`, and `webui` link would be far more token-efficient. The full raw response could be available behind `--verbose` or a `--raw` flag.

### Rough edge: Manifest validation error exposes raw Pydantic internals

**Severity:** Low
**Steps:** Submit a manifest missing `parent` and `pages.0.title`.
**Actual message:**
```
Invalid manifest: 2 validation errors for Manifest
parent
  Field required [type=missing, input_value={'space': 'SD', ...}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing
```
**Suggestion:** Wrap Pydantic errors into a cleaner `details` array, e.g.:
```json
"details": {
  "missing_fields": ["parent", "pages[0].title"]
}
```
The raw Pydantic output with `input_value`, `input_type`, and the pydantic.dev URL leaks implementation details.

---

## Suggestions

### 1. Add a `--compact` or `--slim` output mode
For agent use, return only the fields that matter. The full Confluence API payloads in `page.list` and `page.inspect` are 10x more data than an agent needs. This would significantly reduce token usage.

### 2. Consider a `page.get-body` subcommand (or flag)
`page.inspect` returns the full storage-format body inline, which is great for inspection but makes the response enormous. A `--no-body` flag on inspect (or a separate `page.body` command) would let agents choose when they need content vs. metadata.

### 3. Add `schema_version` to the manifest validation error
When a manifest is missing `schema_version`, the error message mentions `parent` and `pages.0.title` but doesn't flag the missing `schema_version`. (Tested: a manifest without `schema_version` but with `parent` was accepted — so it appears optional. The README says it should be there. Clarify whether it's required.)

### 4. The `config set` subcommand help is sparse
`config set --help` doesn't show what keys are valid or their expected values. Adding a `config list-keys` or including examples in the help text would help.

### 5. Document the title-from-filename behavior
The help text says `--title TEXT  Page title (defaults to filename)` but the actual behavior is "filename without extension, title-cased" (e.g., `test-confpub.md` → `Test Confpub`, `page.md` → `Page`). Document the transformation rule.

---

## Summary

confpub nails the core agent-first design philosophy: structured output, stable error codes, a self-describing `guide` command, mutation markers, safety annotations, and a clean transactional workflow. The main areas for improvement are (1) trimming the verbose Confluence API payloads for agent-friendly output, (2) fixing the `--quiet` bug, and (3) better error classification for permission/not-found cases vs. true internal errors. This is a tool I'd be confident integrating into an autonomous agent workflow today.
