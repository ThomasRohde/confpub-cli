# confpub-cli v0.2.3 — Blind Test Feedback

**Tester**: Claude Opus 4.6 (LLM agent)
**Date**: 2026-03-01
**Environment**: Windows 11, bash shell, `uvx confpub-cli`
**Confluence**: Cloud instance (thomasklokrohde.atlassian.net)

---

## Overall Impression

confpub-cli is a remarkably well-designed agent-first CLI. As an LLM agent driving it
zero-shot, I was productive within seconds. The `guide` command gave me everything I
needed to understand the full command surface, error taxonomy, and concurrency rules.
The consistent JSON envelope made it trivial to parse every response. This is one of
the best-designed CLIs I've encountered for agent consumption.

**Rating: 4/5** — Excellent foundation with a handful of rough edges to polish.

---

## What Works Well

### Structured JSON Envelope
Every command returns the same `{ ok, command, target, result, warnings, errors, metrics }`
shape. Parsing is zero-effort. The `request_id` and `metrics.duration_ms` fields are a
nice touch for tracing and diagnostics.

### `guide` Command
Brilliant bootstrapping mechanism. One call gives an agent: every command with its flags,
mutability annotations, error codes with exit codes and retry hints, auth precedence,
and concurrency rules. The `--section` flag is useful for targeted queries. This alone
puts confpub ahead of most CLI tools for agent integration.

### Transactional Plan Workflow
The plan → validate → apply → verify pipeline is well thought out:
- `plan create` generates a readable artifact with clear operation types
- `plan validate` checks for drift before apply
- `plan apply` supports `--dry-run` for preview
- The lockfile (`confpub.lock`) enables idempotent re-publishing

I tested the full cycle and it worked flawlessly: manifest → plan → validate → dry-run → apply → verify.

### Markdown Conversion
Tested headings, bold/italic, inline code, fenced code blocks (with language), tables,
admonitions (`[!NOTE]`, `[!WARNING]`, `[!TIP]`), strikethrough, and horizontal rules.
All converted correctly to Confluence Storage Format. Particularly impressed that
admonitions map to the proper Confluence Info/Warning/Tip macros.

### Error Taxonomy
Stable error codes (`ERR_*`) with structured details, exit codes, and `suggested_action`
hints (`fix_input`, `retry`, `reauth`, `escalate`). An agent can branch on these without
parsing human-readable messages. The `retryable` flag and `retry_after_ms` for I/O errors
are agent-friendly.

### Safety Design
- Write commands are clearly annotated as `mutates: true` in the guide
- `--dry-run` is available on both `page publish` and `plan apply`
- `--cascade` is a separate opt-in for cascading deletes
- `safety_flags` section in the guide calls out dangerous flags

### Auth Resolution
Clean precedence chain (flags → env vars → config file → keychain) with auto-detection
of Cloud vs Server from the URL. `auth inspect` gives a quick status check.

---

## Bugs Found

### BUG-1: `--space` flag ignored during page update (Severity: High)

When I published a page to space `SD`, then re-published with `--space NONEXIST`, the
command succeeded (exit 0) and updated the existing page in the `SD` space. The `--space`
flag was silently ignored on the update path.

**Repro:**
```bash
confpub page publish test.md --space SD --parent "Software Development"
# Creates page in SD, version 1

confpub page publish test.md --space NONEXIST --parent "Software Development"
# Expected: error (space not found or page not found in that space)
# Actual: ok=true, updated page in SD to version 3
```

**Impact**: An agent could accidentally update a page in the wrong space without any
warning. The title-based lookup appears to match globally (or against the lockfile)
rather than scoping to the specified space.

### BUG-2: Nonexistent page returns `ok: true` with `result: null` (Severity: Medium)

```bash
confpub page inspect --space SD --title "nonexistent-page"
# Returns: ok=true, result=null, errors=[]
```

This should return `ok: false` with an appropriate error (e.g., a new `ERR_NOT_FOUND`
code). An agent checking `ok` to determine success would incorrectly think the call
succeeded. Currently the only way to detect "not found" is to check if `result` is null,
which is an undocumented convention.

A `"Can't find ... page"` message also leaks to stderr, suggesting the underlying library
knows it's not found — the CLI just doesn't surface it as a structured error.

### BUG-3: Missing required options return exit code 2, not JSON envelope (Severity: Medium)

```bash
confpub page list
# Returns Typer's error format: "Missing option '--space'." with exit code 2
```

This breaks the documented invariant: "stdout is exclusively JSON — one object, no
preamble, no epilogue." An agent expecting to always parse JSON on stdout will crash.
Exit code 2 is also undocumented (the error code table only covers 0/10/20/40/50/90).

**Suggestion**: Catch Typer's `MissingParameter` and convert it to an
`ERR_VALIDATION_REQUIRED` envelope with exit code 10.

### BUG-4: `--backup` flag produces no observable output (Severity: Low)

```bash
confpub page publish test.md --space SD --parent "Software Development" --backup
```

The command succeeded but the result JSON contains no mention of a backup being created —
no backup file path, no `backup: true` field, nothing. Either the backup didn't happen,
or it happened silently. An agent has no way to confirm.

### BUG-5: Nonexistent parent accepted in dry-run (Severity: Low)

```bash
confpub page publish test.md --space SD --parent "Nonexistent Parent" --dry-run
# Returns: ok=true, type=page.update
```

Dry-run should ideally validate that the parent page exists, or at least emit a warning.
Currently it plans an update to a nonexistent parent, which would fail on real apply.

---

## Improvement Suggestions

### 1. Normalize attachment command output

`attachment.list` and `attachment.upload` return raw Confluence API responses with
internal fields (`_expandable`, ARIs, `base64EncodedAri`, full user profiles). Every
other command returns a curated result. These should be normalized to the same level
of curation.

**Suggested `attachment.list` shape:**
```json
{
  "attachments": [
    {
      "id": "att262400",
      "title": "test-attachment.txt",
      "media_type": "application/binary",
      "file_size": 27,
      "download_url": "/download/attachments/360459/test-attachment.txt?..."
    }
  ]
}
```

### 2. Add `--format` flag or page count to `page.list`

For spaces with many pages, `page.list` returns everything. Consider:
- A `--limit` / `--offset` for pagination
- A `--format compact` option (just titles + IDs)
- Include total count in the result

### 3. Suppress `"Can't find ... page"` stderr noise

Multiple commands emit `"Can't find 'X' page on ..."` to stderr. This comes from the
underlying `atlassian-python-api` library but leaks through even with `--quiet`. Since
not finding a page is a normal flow (e.g., first publish), this shouldn't appear by
default — maybe only with `--verbose`.

### 4. Add stdin support

`echo "# Hello" | confpub page publish - --space SD --parent "Docs" --title "Hello"`
would be useful for piped workflows and agent-generated content. Currently `-` is treated
as a literal filename.

### 5. `plan verify` with no assertions is a no-op

```bash
confpub plan verify --plan confpub-plan.json
# Returns: all_passed=true, results=[]
```

Without `--assertions`, this always passes vacuously. Consider:
- Auto-generating basic assertions from the plan (pages exist, correct parent, version incremented)
- Emitting a warning when no assertions are provided

### 6. Consider `--json` flag for Typer-level errors

As a bridge until BUG-3 is fully fixed, a `--json` flag could force JSON output even
for framework-level errors (missing options, unknown commands).

### 7. Lockfile includes pages from `page publish` and `plan apply`

The lockfile accumulated entries from both `page publish` (single-file mode) and
`plan apply`. This might be intentional for idempotency, but it could surprise users
who expected the lockfile to only track manifest-managed pages. Consider documenting
this behavior or separating the two.

---

## Summary

| Area | Score |
|------|-------|
| Agent discoverability (`guide`) | 5/5 |
| JSON envelope consistency | 4/5 (BUG-3 breaks it for Typer errors) |
| Error handling | 4/5 (BUG-2 masks not-found) |
| Markdown conversion | 5/5 |
| Plan workflow | 5/5 |
| Write correctness | 3/5 (BUG-1 is a real data integrity risk) |
| Output curation | 3/5 (attachments leak raw API) |
| Documentation (README) | 5/5 |

confpub is production-ready for the core read + plan + publish workflows. The main
blocker is BUG-1 (space flag ignored on updates), which could cause silent cross-space
writes. Fixing that plus normalizing the attachment output would bring this to a
strong 5/5.
