# Blackbox Test Report

**Tool**: confpub v1.12.0
**Date**: 2026-03-26
**Tester**: Automated blackbox QA via CLI exploration
**Environment**: Windows 11, Confluence Cloud (thomasklokrohde.atlassian.net), Space: SD

---

## Tool Summary

`confpub` is an agent-first CLI tool for publishing Markdown content to Atlassian Confluence. It supports:

- **Page operations**: publish (create/update from Markdown), inspect, list, pull (download to local Markdown), delete, move, history, version retrieval, and export (PDF/Word).
- **Plan workflow**: A transactional multi-page publish pipeline (create plan from YAML manifest, validate, apply, verify).
- **Attachment operations**: upload, list, download, delete attachments on pages.
- **Label operations**: add, list, remove labels on pages.
- **Comment operations**: add and list comments on pages.
- **Property operations**: set, get, list, delete page properties.
- **Search**: CQL-based Confluence content search.
- **Configuration**: config set/inspect, auth inspect.
- **Space operations**: list and inspect spaces.
- **Skill management**: Install agent skills for coding assistants (Claude, Copilot, Cursor, etc.).
- **Guide**: Machine-readable CLI schema for agent consumption.

All output is structured JSON with a consistent envelope (`schema_version`, `request_id`, `ok`, `command`, `target`, `result`, `warnings`, `errors`, `metrics`). The tool supports global flags (`--quiet`, `--verbose`, `--compact`) and uses YAML front matter in Markdown files for metadata. Exit codes are categorized: 0=success, 10=validation, 20=auth, 50=IO.

---

## Bugs Found

### 1. `attachment download` always fails with "not found" for existing attachments
- **Severity**: critical
- **Reproduction**:
  ```bash
  # Upload an attachment
  confpub attachment upload test-attachment.txt --page-id <PAGE_ID>
  # Confirm it exists
  confpub attachment list --page-id <PAGE_ID>
  # Try to download it
  confpub attachment download --page-id <PAGE_ID> --filename "test-attachment.txt" --output "out.txt"
  ```
- **Expected**: The attachment is downloaded to the specified output path.
- **Actual**: Error `ERR_VALIDATION_NOT_FOUND: Attachment 'test-attachment.txt' not found on page <PAGE_ID>` (exit code 10), even though `attachment list` confirms the attachment exists with that exact filename. Tested on two different pages with consistent failure.

### 2. `--compact` flag ignored when placed at root level (`confpub --compact`)
- **Severity**: high
- **Reproduction**:
  ```bash
  # Root level: produces 32 lines (standard indented JSON)
  confpub --compact page list --space SD --limit 1 2>&1 | wc -l
  # Subcommand level: produces 1 line (correct compact JSON)
  confpub page --compact list --space SD --limit 1 2>&1 | wc -l
  ```
- **Expected**: `confpub --compact page list ...` should produce single-line JSON, as documented in the root-level help text.
- **Actual**: `--compact` is silently ignored at root level. Only works when placed at the subcommand group level (e.g., `confpub page --compact list`).

### 3. `--verbose` flag ignored when placed at root level (`confpub --verbose`)
- **Severity**: high
- **Reproduction**:
  ```bash
  # Root level: no diagnostics section in metrics
  confpub --verbose page list --space SD --limit 1
  # Subcommand level: includes diagnostics section in metrics
  confpub page --verbose list --space SD --limit 1
  ```
- **Expected**: `confpub --verbose page list ...` should include diagnostics in the output.
- **Actual**: `--verbose` is silently ignored at root level. Only works at subcommand group level.

### 4. Unhandled exception (crash) when publishing a binary file
- **Severity**: high
- **Reproduction**:
  ```bash
  printf '\x00\x01\x02\x03\x89PNG\r\n' > binary.md
  confpub page publish binary.md --space SD --parent "Software Development" --title "Test"
  ```
- **Expected**: A structured JSON error message indicating the file is not valid UTF-8 Markdown.
- **Actual**: Raw Python traceback is printed to stderr: `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x89 in position 4: invalid start byte`. Exit code 1 (not a standard error code). The error bypasses the JSON envelope entirely.

### 5. `--limit 0` causes the command to hang indefinitely
- **Severity**: medium
- **Reproduction**:
  ```bash
  timeout 15 confpub page list --space SD --limit 0
  ```
- **Expected**: Either an error message ("limit must be positive") or an empty result set returned quickly.
- **Actual**: The command hangs indefinitely, requiring a manual kill/timeout. Exit code 124 (timeout).

### 6. Negative `--limit` returns wrong error code (`ERR_IO_FILE_NOT_FOUND`)
- **Severity**: medium
- **Reproduction**:
  ```bash
  confpub page list --space SD --limit -5
  ```
- **Expected**: A validation error (ERR_VALIDATION_REQUIRED, exit code 10) indicating the limit must be positive.
- **Actual**: Returns `ERR_IO_FILE_NOT_FOUND` with message "File error (list_pages): java.lang.IllegalArgumentException: limit cannot be less than zero" (exit code 50). The error code is semantically wrong -- this is not a file I/O error.

### 7. `page list --label` returns different response schema than regular `page list`
- **Severity**: medium
- **Reproduction**:
  ```bash
  # Without label filter: returns pages with {id, title, version{}, webui}
  confpub page list --space SD --limit 1
  # With label filter: returns pages with {id, type, title, status, url, excerpt}
  confpub page list --space SD --label "test"
  ```
- **Expected**: Both invocations should return pages in the same schema format.
- **Actual**: When `--label` is used, the response uses a different schema (likely the search API internally) with different field names (`url` vs `webui`, includes `excerpt`, `type`, `status`, omits `version`). This is inconsistent and breaks consumers expecting a stable schema.

### 8. Nonexistent version returns wrong error code (`ERR_IO_FILE_NOT_FOUND`)
- **Severity**: low
- **Reproduction**:
  ```bash
  confpub page version --page-id <VALID_ID> --version-number 999
  ```
- **Expected**: A not-found error like `ERR_VALIDATION_NOT_FOUND`.
- **Actual**: Returns `ERR_IO_FILE_NOT_FOUND` with a raw Java exception message: `com.atlassian.confluence.api.service.exceptions.api.NotFoundException`. Exit code 50 instead of a more appropriate code.

### 9. Nonexistent property delete returns raw Java exception in error message
- **Severity**: low
- **Reproduction**:
  ```bash
  confpub property delete --page-id <VALID_ID> --key "nonexistent-key"
  ```
- **Expected**: A clean error like "Property 'nonexistent-key' not found on page <ID>".
- **Actual**: Returns `ERR_IO_FILE_NOT_FOUND` with a verbose raw Java exception: `com.atlassian.confluence.api.service.exceptions.api.PermissionException: Cannot delete content property: JsonContentProperty{id='null', key='nonexistent-key', ...}`. The error code is also wrong (IO_FILE_NOT_FOUND instead of NOT_FOUND or VALIDATION).

---

## Bugs Fixed During Testing

None. All bugs found were reproducible and confirmed.

---

## UX Issues

1. **`-h` and `-v` short flags not supported**: Running `confpub -h` or `confpub -v` returns an error "No such option". Users commonly expect `-h` for help and `-v` for version. Only `--help` and `--version` work.

2. **`config set` silently succeeds when env var overrides the value**: Running `confpub config set base_url "https://new.url"` reports success, but `confpub config inspect` still shows the old value because the environment variable takes precedence. No warning is emitted about the override.

3. **`--title-from-h1` silently falls back to filename when no H1 exists**: When using `--title-from-h1` on a file with no H1 heading, the tool silently falls back to deriving the title from the filename. A warning should be emitted indicating the fallback occurred.

4. **`--title` and `--title-from-h1` used together silently ignores `--title-from-h1`**: These should either be mutually exclusive (with an error) or the behavior should be documented. Currently `--title` wins silently.

5. **Empty and whitespace-only Markdown files publish silently**: Publishing an empty file or a whitespace-only file creates a page with no content and no warning. A warning would be helpful.

6. **No stdin/pipe support**: `confpub page publish - ...` and `echo "..." | confpub page publish /dev/stdin ...` both fail. For a CLI tool, pipe support would be a valuable feature.

7. **Duplicate flags silently use last value**: `--limit 2 --limit 3` silently uses 3 with no warning about the duplicate.

8. **No confirmation prompt for `page delete`**: Deleting a page happens immediately without any confirmation. For a destructive operation against a live system, some safeguard (like `--force` or `--yes`) would be helpful. The `--cascade` flag exists but doesn't provide a pre-deletion summary.

9. **Inconsistent field naming in `page list` vs `search` results**: Pages from `page list` use `webui` for URLs, while `search` results use `url`. Both should use the same field name.

10. **Progress messages on stderr mix with JSON output when redirected**: The recursive pull emits `{"event":"progress",...}` to stderr. While sending to stderr is correct, the JSON format may confuse tools trying to parse only the JSON result from stdout when combining stdout+stderr.

---

## What Worked Well

1. **Consistent JSON envelope**: Every response (success and error) uses the same structured JSON format with `schema_version`, `request_id`, `ok`, `command`, `target`, `result`, `warnings`, `errors`, and `metrics`. This is excellent for machine parsing and agent consumption.

2. **Meaningful exit codes**: The categorized exit codes (0/10/20/50) are consistent across most commands and map to clear error types (success/validation/auth/IO).

3. **Excellent error messages for validation**: Missing required arguments, mutually exclusive options, invalid config keys, malformed YAML manifests, and missing files all produce clear, actionable error messages with appropriate `suggested_action` fields.

4. **Full plan workflow**: The create-validate-apply-verify pipeline works flawlessly end-to-end, including lockfile generation and management.

5. **Front matter support**: YAML front matter in Markdown files is properly parsed for title, space, parent, and labels, and properly stripped from the published content.

6. **Round-trip fidelity**: Content published and then pulled back retains formatting (bold, italic, lists, tables, code blocks). The pull command also generates a valid `confpub.yaml` manifest and lockfile.

7. **Guide command**: The machine-readable schema with agent hints, result schemas, and examples is thoughtfully designed for AI agent integration.

8. **Dry-run support**: Both `page publish --dry-run` and `plan apply --dry-run` correctly preview changes without writing.

9. **Content change detection**: The tool detects when content hasn't changed and reports `page.noop` instead of making unnecessary updates.

10. **Export support**: PDF and Word export work reliably.

11. **Labels, comments, properties**: CRUD operations on page metadata all work correctly.

12. **Page move**: Moving pages between parents works cleanly.

13. **Markdown-to-Confluence conversion**: Tables, code blocks with language hints, bold/italic, and lists all convert accurately to Confluence storage format.

---

## Recommendations

### Priority 1 (Critical)
1. **Fix `attachment download`**: This core feature is completely non-functional. The filename lookup logic appears broken -- the attachment exists (confirmed by `list`) but `download` cannot find it.

### Priority 2 (High)
2. **Fix global flags (`--compact`, `--verbose`, `--quiet`) at root level**: These flags are advertised in the root help text but silently ignored when placed there. Either make them work at root level or remove them from root help and document the correct placement.
3. **Handle binary file input gracefully**: Catch `UnicodeDecodeError` and return a proper JSON error instead of crashing with a raw Python traceback. The traceback also leaks internal file paths.

### Priority 3 (Medium)
4. **Validate `--limit` values**: Reject `--limit 0` (currently hangs) and `--limit -N` with proper validation errors (exit code 10, not 50).
5. **Normalize error codes for API errors**: Map Confluence API `NotFoundException` to `ERR_VALIDATION_NOT_FOUND` and `PermissionException` (for nonexistent resources) more carefully. Currently many API errors are incorrectly mapped to `ERR_IO_FILE_NOT_FOUND`.
6. **Consistent `page list` response schema**: Ensure the same field names and structure whether or not `--label` is used.

### Priority 4 (Low)
7. **Add `-h` and `-v` short flags** as aliases for `--help` and `--version`.
8. **Warn when `config set` value is overridden by env var**.
9. **Warn when `--title-from-h1` falls back to filename**.
10. **Consider adding stdin/pipe support** for `page publish`.
11. **Add `--yes`/`--force` confirmation for destructive operations** (`page delete`, `attachment delete`).

---

## Test Log

| # | Command | Outcome |
|---|---------|---------|
| 1 | `confpub` (no args) | pass - shows help + JSON error |
| 2 | `confpub --help` | pass |
| 3 | `confpub --version` | pass - 1.12.0 |
| 4 | `confpub -h` | fail - "No such option: -h" |
| 5 | `confpub -v` | fail - "No such option: -v" |
| 6 | `confpub search --help` | pass |
| 7 | `confpub guide --help` | pass |
| 8 | `confpub page --help` | pass |
| 9 | `confpub plan --help` | pass |
| 10 | `confpub auth --help` | pass |
| 11 | `confpub config --help` | pass |
| 12 | `confpub space --help` | pass |
| 13 | `confpub attachment --help` | pass |
| 14 | `confpub label --help` | pass |
| 15 | `confpub comment --help` | pass |
| 16 | `confpub property --help` | pass |
| 17 | `confpub skill --help` | pass |
| 18 | All leaf subcommand --help | pass (20+ commands) |
| 19 | `confpub auth inspect` | pass |
| 20 | `confpub config inspect` | pass |
| 21 | `confpub space list` | pass |
| 22 | `confpub space inspect --space SD` | pass |
| 23 | `confpub page list --space SD` | pass |
| 24 | `confpub page publish test-page.md --space SD --parent ... --title ...` | pass - page created |
| 25 | `confpub page inspect --page-id <ID>` | pass |
| 26 | `confpub page inspect --page-id <ID> --format markdown` | pass |
| 27 | `confpub page inspect --space SD --title "..."` | pass |
| 28 | `confpub page inspect --page-id <ID> --raw` | pass |
| 29 | `confpub page history --page-id <ID>` | pass |
| 30 | `confpub page version --page-id <ID> --version-number 1` | pass |
| 31 | `confpub page publish ... --dry-run` | pass |
| 32 | `confpub page publish ... --title-from-h1` | pass |
| 33 | `confpub page publish ... --backup` | pass |
| 34 | `confpub page publish ... --label qa --label automated` | pass |
| 35 | `confpub page publish ... --page-id <ID>` (direct update) | pass |
| 36 | `confpub page publish frontmatter-test.md` (front matter metadata) | pass |
| 37 | `confpub page move --page-id <ID> --target-parent ...` | pass |
| 38 | `confpub page export --page-id <ID> --format pdf --output test.pdf` | pass |
| 39 | `confpub page export --page-id <ID> --format word --output test.docx` | pass |
| 40 | `confpub page pull --page-id <ID> --output dir` | pass |
| 41 | `confpub page pull --page-id <ID> -r` (recursive) | pass |
| 42 | `confpub page pull --page-id <ID> --layout nested` | pass |
| 43 | `confpub page pull --page-id <ID> --no-attachments` | pass |
| 44 | `confpub page pull --space SD --title "..." --output dir` | pass |
| 45 | `confpub page delete --page-id <ID>` | pass |
| 46 | `confpub search --space SD --title "..."` | pass |
| 47 | `confpub search --cql 'space = "SD" AND type = "page"'` | pass |
| 48 | `confpub search --space SD --type page --limit 2` | pass |
| 49 | `confpub search --space SD --type page --excerpt-length 0` | pass |
| 50 | `confpub search --space SD --type page --include-archived` | pass |
| 51 | `confpub label add --page-id <ID> --label test --label blackbox` | pass |
| 52 | `confpub label list --page-id <ID>` | pass |
| 53 | `confpub label remove --page-id <ID> --label blackbox` | pass |
| 54 | `confpub comment add --page-id <ID> --text "..."` | pass |
| 55 | `confpub comment add --page-id <ID> --file comment-body.md` | pass |
| 56 | `confpub comment list --page-id <ID>` | pass |
| 57 | `confpub property set --page-id <ID> --key k --value '{"json":"val"}'` | pass |
| 58 | `confpub property set --page-id <ID> --key k --value "plain text"` | pass |
| 59 | `confpub property get --page-id <ID> --key k` | pass |
| 60 | `confpub property list --page-id <ID>` | pass |
| 61 | `confpub property delete --page-id <ID> --key k` | pass |
| 62 | `confpub attachment upload file.txt --page-id <ID>` | pass |
| 63 | `confpub attachment list --page-id <ID>` | pass |
| 64 | `confpub attachment download --page-id <ID> --filename ... --output ...` | **fail** - bug #1 |
| 65 | `confpub attachment delete --page-id <ID> --filename ...` | pass |
| 66 | `confpub plan create --manifest confpub.yaml` | pass |
| 67 | `confpub plan validate --plan confpub-plan.json` | pass |
| 68 | `confpub plan apply --plan confpub-plan.json` | pass |
| 69 | `confpub plan verify --plan confpub-plan.json` | pass |
| 70 | `confpub config set base_url "..."` | pass (but UX issue) |
| 71 | `confpub config set invalid_key "..."` | pass - proper error |
| 72 | `confpub skill inspect` | pass |
| 73 | `confpub skill install --dry-run` | pass |
| 74 | `confpub guide` | pass |
| 75 | `confpub guide --section commands` | pass |
| 76 | `confpub --compact page list ...` (root level) | **fail** - bug #2 |
| 77 | `confpub page --compact list ...` (subcommand level) | pass |
| 78 | `confpub --verbose page list ...` (root level) | **fail** - bug #3 |
| 79 | `confpub page --verbose list ...` (subcommand level) | pass |
| 80 | `confpub page publish binary.md` | **crash** - bug #4 |
| 81 | `confpub page list --space SD --limit 0` | **fail** - bug #5 (hangs) |
| 82 | `confpub page list --space SD --limit -5` | **fail** - bug #6 (wrong error code) |
| 83 | `confpub page list --space SD --label test` | **unexpected** - bug #7 (different schema) |
| 84 | `confpub page version --page-id <ID> --version-number 999` | **unexpected** - bug #8 (wrong error code) |
| 85 | `confpub property delete --page-id <ID> --key nonexistent` | **unexpected** - bug #9 (raw exception) |
| 86 | `confpub page publish` (no args) | pass - proper error |
| 87 | `confpub page publish nonexistent.md` | pass - proper error |
| 88 | `confpub page list` (no space) | pass - proper error |
| 89 | `confpub page inspect --page-id 99999999999` | pass - proper error |
| 90 | `confpub page list --space NONEXISTENT` | pass - proper error |
| 91 | `confpub space inspect --space NONEXISTENT` | pass - proper error |
| 92 | `confpub page list --space SD --limit abc` | pass - proper error |
| 93 | `confpub page export --format csv ...` | pass - proper error |
| 94 | `confpub page export --output /nonexistent/dir/file.pdf ...` | pass - proper error |
| 95 | `confpub plan create --manifest nonexistent.yaml` | pass - proper error |
| 96 | `confpub plan validate --plan nonexistent.json` | pass - proper error |
| 97 | `confpub plan create --manifest bad-manifest.yaml` (malformed YAML) | pass - proper error |
| 98 | `confpub plan create --manifest incomplete-manifest.yaml` (missing parent) | pass - proper error |
| 99 | `confpub comment add --page-id <ID>` (no text or file) | pass - proper error |
| 100 | `confpub comment add --page-id <ID> --text x --file f` (both) | pass - proper error |
| 101 | `confpub page inspect` (no specifier) | pass - proper error |
| 102 | `confpub page move --page-id <ID>` (no target) | pass - proper error |
| 103 | `confpub page delete --page-id abc123` | pass - proper error |
| 104 | `confpub search` (no args) | pass - proper error |
| 105 | `confpub nonexistent` (bad command) | pass - proper error |
| 106 | `confpub page nonexistent` (bad subcommand) | pass - proper error |
| 107 | `confpub page publish empty.md` | pass (creates empty page, no warning) |
| 108 | `confpub page publish whitespace-only.md` | pass (creates empty page, no warning) |
| 109 | `confpub page publish unicode-test.md` | pass |
| 110 | `echo '...' \| confpub page publish -` (stdin) | fail - no pipe support |
| 111 | `confpub page list --space SD --space SD` (dup flags) | pass (last wins) |
| 112 | `confpub page list --space SD --limit 2 --limit 3` (dup limit) | pass (last wins) |
| 113 | `confpub page list --space SD --start 100` (beyond count) | pass - empty result |
| 114 | `confpub page list --space SD --limit 99999` (huge limit) | pass |
| 115 | `confpub label remove --page-id <ID> --label nonexistent` | pass - error |
| 116 | `confpub attachment delete --page-id <ID> --filename nonexistent.txt` | pass - error |
| 117 | `confpub page publish ... --title-from-h1` (no H1 in file) | pass (silent fallback, UX issue) |
| 118 | `confpub page publish ... --title X --title-from-h1` (both) | pass (--title wins, UX issue) |
| 119 | `confpub page inspect --space SD --title "NonExistent Page"` | pass - proper error |
| 120 | `confpub page delete --space SD --title "NONEXISTENT"` | pass - proper error |

**Summary**: 120 test cases executed. 9 bugs found (1 critical, 3 high, 3 medium, 2 low). 10 UX issues identified. The tool is robust for its core workflows but has a critical broken feature (attachment download) and several inconsistencies in global flag handling and error code mapping.
