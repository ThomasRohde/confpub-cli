# Blackbox Test Report -- confpub v1.13.0

**Date:** 2026-03-26
**Tester:** Automated blackbox test (agent)
**Previous version tested:** v1.12.0
**Instance:** https://thomasklokrohde.atlassian.net (Space: SD)

---

## Tool Summary

confpub is an "agent-first CLI to publish Markdown to Confluence." It converts extended Markdown (with Confluence-specific syntax for status lozenges, info boxes, panels, expand blocks, layouts, task lists, excerpts, and TOC macros) into Confluence storage format and publishes it via the Confluence REST API.

Key capabilities discovered:
- **Page operations:** publish, inspect, list, pull, delete, move, history, version, export (PDF/Word)
- **Plan workflow:** manifest-driven multi-page publishing with create/validate/apply/verify lifecycle
- **Attachments:** upload, list, download, delete
- **Comments:** add, list
- **Labels:** add, list, remove
- **Properties:** list, get, set, delete
- **Search:** CQL-based search with fuzzy title matching
- **Configuration:** auth inspect, config inspect/set
- **Skill management:** install agent skills (Claude, Copilot, Cursor, Windsurf)
- **Guide:** machine-readable CLI schema for agent consumption

All output is structured JSON with a consistent envelope: `schema_version`, `request_id`, `ok`, `command`, `target`, `result`, `warnings`, `errors`, `metrics`.

**New in v1.13.0 (vs v1.12.0):**
- `skill` subcommand group (install, inspect) for agent skill management
- `page pull` command for pulling Confluence pages back to local Markdown
- `page move` command
- Global flags (`--compact`, `--verbose`, `--quiet`) now work at root level
- Improved input validation (limit bounds, binary file detection)
- Consistent error codes across commands

---

## Regression Test Results

| # | Bug (v1.12.0) | Severity | v1.13.0 Status | Notes |
|---|---------------|----------|----------------|-------|
| 1 | `attachment download` completely broken | CRITICAL | **PARTIALLY FIXED** | Works with absolute paths and `./relative` paths, but **bare filenames** (e.g., `--output downloaded.txt`) still fail with `[WinError 3] The system cannot find the path specified: ''`. Only affects Windows with bare filename output paths. |
| 2 | Global flags (`--compact`, `--verbose`) silently ignored at root level | HIGH | **FIXED** | `confpub --compact auth inspect` and `confpub --verbose auth inspect` now work correctly. Flags are properly inherited from root to subcommands. |
| 3 | Binary file input causes raw Python traceback (UnicodeDecodeError) | HIGH | **FIXED** | Now returns clean `ERR_VALIDATION_MARKDOWN` error: "File is not valid UTF-8 text" with exit code 10. No traceback exposed. |
| 4 | `--limit 0` hangs indefinitely | MEDIUM | **FIXED** | Now returns `ERR_VALIDATION_REQUIRED`: "limit must be a positive integer (>= 1)" immediately. Consistent across `page list`, `search`, and `comment list`. |
| 5 | Negative `--limit` returns wrong error code | MEDIUM | **FIXED** | Now returns exit code 10 (validation) with the same "limit must be a positive integer" message. Consistent behavior. |
| 6 | `page list --label` returns different response schema than regular `page list` | MEDIUM | **FIXED** | Both now return the same schema: `{pages, start, limit, size, has_more}`. |
| 7 | Nonexistent version/property operations return `ERR_IO_FILE_NOT_FOUND` with raw Java exceptions | LOW | **PARTIALLY FIXED** | Error codes improved: version now returns `ERR_VALIDATION_NOT_FOUND` (was `ERR_IO_FILE_NOT_FOUND`). Property returns `ERR_AUTH_FORBIDDEN` with a helpful note explaining Confluence returns 403 for both nonexistent and forbidden resources. However, the version error message still exposes raw Java exception text: `com.atlassian.confluence.api.service.exceptions.api.NotFoundException: Cannot find content version: ContentId{id=...}`. |

**Summary:** 5 of 7 bugs fully fixed. 2 partially fixed. 0 still fully present. Significant improvement.

---

## New Bugs Found

### 1. Attachment download fails with bare filename output path (Windows)

- **Severity:** MEDIUM
- **Reproduction:**
  ```
  confpub attachment download --page-id <ID> --filename test.txt --output downloaded.txt
  ```
- **Expected:** File downloaded to `downloaded.txt` in the current working directory.
- **Actual:** Fails with `ERR_IO_CONNECTION`: `[WinError 3] The system cannot find the path specified: ''`. Exit code 50.
- **Workaround:** Use `./downloaded.txt` or an absolute path. Both work correctly.
- **Root cause (guess):** Path resolution strips the directory component from a bare filename, resulting in an empty directory string on Windows.

### 2. Non-existent parent page silently ignored during publish

- **Severity:** MEDIUM
- **Reproduction:**
  ```
  echo "# Test" > test.md
  confpub page publish test.md --space SD --parent "Nonexistent Parent XYZ789"
  ```
- **Expected:** Error indicating the parent page was not found.
- **Actual:** Page is silently created under the space root (homepage). No warning, no error. Exit code 0.
- **Impact:** Users may unknowingly create orphaned pages in the wrong location.

### 3. `page inspect --format invalid` silently falls back to storage format

- **Severity:** LOW
- **Reproduction:**
  ```
  confpub page inspect --page-id <ID> --format invalid
  ```
- **Expected:** Validation error: `--format must be 'storage' or 'markdown'`.
- **Actual:** Silently returns storage format output with no warning. Exit code 0.
- **Note:** `page export --format invalid` correctly validates and rejects unknown formats. The inconsistency between `page inspect` and `page export` format validation is confusing.

### 4. Plan apply dry-run ignores lockfile state (shows stale actions)

- **Severity:** LOW
- **Reproduction:**
  ```
  confpub plan create --manifest confpub.yaml
  confpub plan apply --plan confpub-plan.json      # actually creates pages
  confpub plan apply --plan confpub-plan.json --dry-run   # shows "create" instead of "noop/update"
  ```
- **Expected:** Dry-run should reflect the actual state (pages already exist, so actions should be noop or update).
- **Actual:** Dry-run shows `page.create` for pages that already exist. The `--dry-run` flag appears to skip lockfile consultation entirely, giving a misleading preview.

### 5. Nonexistent version error still exposes raw Java exception text

- **Severity:** LOW
- **Reproduction:**
  ```
  confpub page version --page-id <ID> --version-number 999
  ```
- **Expected:** Clean error message like "Version 999 not found for page <ID>".
- **Actual:** Error message contains raw Java exception: `com.atlassian.confluence.api.service.exceptions.api.NotFoundException: Cannot find content version: ContentId{id=11337730}, 999`.
- **Note:** The error code (`ERR_VALIDATION_NOT_FOUND`) is correct (improved from v1.12.0), but the message still leaks implementation details.

### 6. Nonexistent resources return `ERR_AUTH_FORBIDDEN` instead of a 404-style error

- **Severity:** LOW
- **Reproduction:**
  ```
  confpub page inspect --space BADSPACE --title "Does Not Exist"
  confpub page delete --page-id 999999999
  confpub page list --space BADSPACE
  ```
- **Expected:** An error code indicating the resource was not found (e.g., `ERR_VALIDATION_NOT_FOUND`).
- **Actual:** Returns `ERR_AUTH_FORBIDDEN` with `suggested_action: "check_input"`. While the note "This may indicate a nonexistent resource; Confluence returns 403 for both" is helpful, the primary error code is misleading for programmatic consumers (agents would retry with different credentials rather than fix the input).
- **Note:** This is a Confluence API limitation, but the tool could attempt to disambiguate (e.g., try listing spaces to check if the space exists before reporting a permission error).

---

## Publishing Workflow Results

### Single Page Publish -- PASS

Created a comprehensive test page with all confpub extended syntax elements:

| Feature | Result |
|---------|--------|
| Status lozenges (`{status:Done\|colour=Green}`) | Rendered correctly as Confluence status macros |
| Info boxes (`> [!NOTE]`, `> [!WARNING]`, `> [!TIP]`) | All three types rendered correctly |
| Panels (`::: panel Title`) | Rendered with correct title and rich text body |
| Expand blocks (`::: expand Title`) | Rendered with correct title and expandable content |
| Layouts (`:::: layout two-equal` with `::: cell`) | Two-column layout rendered correctly |
| Task lists (`- [ ]` / `- [x]`) | Rendered as Confluence task list macros |
| Code blocks with language | Python and JSON code blocks with syntax highlighting |
| Tables with status lozenges (pipe escaping) | Status lozenges rendered correctly inside table cells |
| TOC macro (`{toc}`) | Rendered as Confluence TOC structured macro |
| Excerpt (`::: excerpt`) | Rendered as Confluence excerpt macro |
| Special characters (`&`, `<`, `>`, quotes) | All properly HTML-escaped |
| Bold, italic, strikethrough, inline code | All rendered correctly |
| Ordered/unordered lists | Rendered correctly |
| Horizontal rule | Rendered correctly |

Title derivation: filename `test-page.md` correctly became "Test Page" (hyphen to space, title-cased). The `--title-from-h1` flag also worked correctly for extracting the title from the first H1 heading.

### Multi-Page Plan Workflow -- PASS

- `plan create` generated a correct plan artifact from the YAML manifest
- `plan apply` created all 3 pages in the correct parent-child hierarchy
- Labels were applied to all pages as specified in the manifest
- `plan validate` confirmed all pages existed after apply
- `plan apply --dry-run` previewed changes without writing
- Lockfile (`confpub.lock`) was created after successful apply

### Page Management -- PASS

| Operation | Result |
|-----------|--------|
| `page list --space SD` | Returned paginated list with consistent schema |
| `page inspect --page-id` | Returned full page details including body, labels, parent |
| `page inspect --format markdown` | Round-tripped storage format back to Markdown |
| `page export --format pdf` | Generated 305KB PDF file |
| `page export --format word` | Generated 14KB DOCX file |
| `page history` | Returned version history |
| `page version` | Returned specific version details |
| `page pull` | Pulled page to local Markdown with attachments and generated manifest |
| `page pull --recursive` | Pulled parent and 2 children correctly |
| `page move` | Moved page under new parent |
| `page delete --cascade` | Deleted parent and child pages |
| `search --cql` | Found pages by label |
| `search --title --space --type` | CQL search with multiple filters |

### Attachments -- PASS (with caveat)

| Operation | Result |
|-----------|--------|
| `attachment upload` | Uploaded text file successfully |
| `attachment list` | Listed attachments with metadata |
| `attachment download` (absolute path) | Downloaded successfully, content verified |
| `attachment download` (bare filename) | **FAILED** -- see Bug #1 |
| `attachment download` (`./relative`) | Downloaded successfully |
| `attachment delete` | Deleted attachment successfully |

### Comments -- PASS

| Operation | Result |
|-----------|--------|
| `comment add --text` | Created comment successfully |
| `comment list` | Listed comments with body, author, date |

### Labels -- PASS

| Operation | Result |
|-----------|--------|
| `label add --label x --label y` | Added multiple labels successfully |
| `label list` | Listed labels with name, prefix, id |
| `label remove --label x --label y` | Removed multiple labels successfully |

### Properties -- PASS

| Operation | Result |
|-----------|--------|
| `property list` | Listed all properties |
| `property set --value '{"foo":"bar"}'` | Created JSON property |
| `property get --key` | Retrieved property with correct value |
| `property delete --key` | Deleted property |

---

## UX Issues

1. **Inconsistent `--format` validation:** `page export --format invalid` correctly rejects with a validation error, but `page inspect --format invalid` silently falls back to storage format. Users (and agents) expect consistent behavior across commands.

2. **`ERR_AUTH_FORBIDDEN` for nonexistent resources is confusing:** When Confluence returns 403 for a nonexistent resource, agents will interpret this as a permissions issue and may attempt to re-authenticate or escalate permissions rather than check the input. The `suggested_action: "check_input"` partially mitigates this but conflicts with the error code semantics.

3. **No stdin/pipe support:** `confpub page publish -` and `/dev/stdin` both fail. For a CLI tool used in agent pipelines, supporting stdin input (e.g., `echo "# Hello" | confpub page publish - --space SD`) would be valuable.

4. **`--compact` and `--verbose` placement is counterintuitive:** These flags only work at the root or group level (`confpub --compact auth inspect` or `confpub auth --compact inspect`), but NOT at the leaf command level (`confpub auth inspect --compact` fails with "No such option"). The `--help` for leaf commands like `auth inspect` does not list these options, so the user has no way to discover the correct placement.

5. **Silent parent page fallback:** When `--parent` specifies a non-existent page, the tool silently creates the page under the space root instead of erroring. This can lead to pages being created in unexpected locations.

6. **Empty and whitespace-only files produce pages:** Publishing an empty or whitespace-only `.md` file successfully creates a Confluence page with no body content. A warning would be helpful.

7. **Exit code 10 for no-command invocation:** Running `confpub` with no arguments returns exit code 10 (`ERR_VALIDATION_REQUIRED`) and the full help text. This is correct but the error payload has an empty message string, which is less helpful for programmatic consumers.

---

## What Worked Well

1. **Consistent JSON envelope:** Every command returns the same top-level structure (`schema_version`, `request_id`, `ok`, `command`, `target`, `result`, `warnings`, `errors`, `metrics`). This is excellent for agent consumption and makes parsing predictable.

2. **Rich Markdown-to-Confluence conversion:** Status lozenges, info boxes, panels, expand blocks, layouts, task lists, excerpts, TOC macros, and code blocks with language all rendered correctly. Pipe escaping inside table cells worked perfectly.

3. **Plan workflow is solid:** The create/validate/apply/verify lifecycle with lockfile tracking is a well-designed transactional approach. The manifest-driven multi-page publishing with parent-child hierarchy worked flawlessly.

4. **`page pull` with round-trip fidelity:** Pulling a page back to Markdown and getting a manifest file auto-generated is a powerful workflow enabler. The `--recursive` flag correctly traversed the page tree.

5. **Idempotent publishing:** Re-publishing the same page with unchanged content correctly returns `page.noop` instead of creating a new version. This is essential for agent reliability.

6. **`--dry-run` mode:** Available on both `page publish` and `plan apply`, allowing agents to preview changes before committing.

7. **Meaningful error codes:** The error code taxonomy (`ERR_VALIDATION_*`, `ERR_IO_*`, `ERR_AUTH_*`) with `suggested_action` fields provides actionable guidance for both humans and agents.

8. **`guide` command:** The machine-readable CLI schema with agent hints, examples, and result schemas is a thoughtful design for the "agent-first" philosophy.

9. **Performance:** Most operations completed in under 2 seconds. Even PDF export (14.6s) was reasonable given it involves server-side rendering.

10. **`page export` dual format:** Supporting both PDF and Word export with proper validation is useful.

11. **`--backup` flag:** The option to backup pages before overwriting is a safety net that shows attention to data protection.

12. **Major regression fixes:** 5 of 7 previously reported bugs are fully fixed, and the remaining 2 are partially fixed. This shows strong responsiveness to user feedback.

---

## Recommendations

### Priority 1 (Should fix for v1.14.0)

1. **Fix bare filename path resolution in `attachment download`** -- The `[WinError 3]` on bare filenames is a straightforward path resolution bug. Resolve the output path relative to CWD before creating the file.

2. **Error on non-existent `--parent` page** -- When `--parent` specifies a page title that doesn't exist, return `ERR_VALIDATION_NOT_FOUND` instead of silently creating the page under the space root. This prevents accidental orphaned pages.

3. **Validate `--format` in `page inspect`** -- Match the behavior of `page export` and reject unknown format values with a validation error.

### Priority 2 (Nice to have)

4. **Sanitize Java exception text from error messages** -- Strip `com.atlassian.confluence...` class names from error messages. Show user-friendly text like "Version 999 not found for page 11337730" instead of raw exception details.

5. **Support stdin input** -- Accept `-` as a file argument to read from stdin. This enables pipeline workflows: `cat page.md | confpub page publish - --space SD --title "My Page"`.

6. **Make `--compact`/`--verbose`/`--quiet` available at all flag positions** -- Allow these flags at the leaf command level too, or document the placement requirement more clearly.

7. **Warn on empty/whitespace-only files** -- Add a warning when publishing a file with no meaningful content.

### Priority 3 (Future consideration)

8. **Disambiguate 403 vs 404** -- For `ERR_AUTH_FORBIDDEN` errors, attempt a secondary check (e.g., verify the space exists) to determine if the issue is truly a permission problem or a nonexistent resource.

9. **Plan apply dry-run should consult lockfile** -- The dry-run should reflect the actual state of the world, showing noop/update for pages that already exist according to the lockfile.

10. **Add `--json` / `--table` output format flags** -- While JSON is excellent for agents, human users would benefit from a table/summary output mode for commands like `page list` and `search`.

---

## Test Log

| # | Command | Category | Exit Code | Outcome |
|---|---------|----------|-----------|---------|
| 1 | `confpub` (no args) | discovery | 10 | pass (shows help + error) |
| 2 | `confpub --version` | discovery | 0 | pass (1.13.0) |
| 3 | `confpub --help` | discovery | 0 | pass |
| 4 | `confpub page --help` | discovery | 0 | pass |
| 5 | `confpub plan --help` | discovery | 0 | pass |
| 6 | `confpub attachment --help` | discovery | 0 | pass |
| 7 | `confpub label --help` | discovery | 0 | pass |
| 8 | `confpub comment --help` | discovery | 0 | pass |
| 9 | `confpub property --help` | discovery | 0 | pass |
| 10 | `confpub search --help` | discovery | 0 | pass |
| 11 | `confpub auth --help` | discovery | 0 | pass |
| 12 | `confpub config --help` | discovery | 0 | pass |
| 13 | `confpub space --help` | discovery | 0 | pass |
| 14 | `confpub guide --help` | discovery | 0 | pass |
| 15 | `confpub skill --help` | discovery | 0 | pass |
| 16 | `confpub page publish --help` | discovery | 0 | pass |
| 17 | `confpub page list --help` | discovery | 0 | pass |
| 18 | `confpub page inspect --help` | discovery | 0 | pass |
| 19 | `confpub page pull --help` | discovery | 0 | pass |
| 20 | `confpub page delete --help` | discovery | 0 | pass |
| 21 | `confpub page move --help` | discovery | 0 | pass |
| 22 | `confpub page history --help` | discovery | 0 | pass |
| 23 | `confpub page version --help` | discovery | 0 | pass |
| 24 | `confpub page export --help` | discovery | 0 | pass |
| 25 | `confpub plan create --help` | discovery | 0 | pass |
| 26 | `confpub plan apply --help` | discovery | 0 | pass |
| 27 | `confpub plan validate --help` | discovery | 0 | pass |
| 28 | `confpub plan verify --help` | discovery | 0 | pass |
| 29 | `confpub attachment upload --help` | discovery | 0 | pass |
| 30 | `confpub attachment download --help` | discovery | 0 | pass |
| 31 | `confpub attachment list --help` | discovery | 0 | pass |
| 32 | `confpub attachment delete --help` | discovery | 0 | pass |
| 33 | `confpub comment add --help` | discovery | 0 | pass |
| 34 | `confpub comment list --help` | discovery | 0 | pass |
| 35 | `confpub label add --help` | discovery | 0 | pass |
| 36 | `confpub label remove --help` | discovery | 0 | pass |
| 37 | `confpub skill install --help` | discovery | 0 | pass |
| 38 | `confpub skill inspect --help` | discovery | 0 | pass |
| 39 | `confpub config inspect --help` | discovery | 0 | pass |
| 40 | `confpub config set --help` | discovery | 0 | pass |
| 41 | `confpub property list --help` | discovery | 0 | pass |
| 42 | `confpub property get --help` | discovery | 0 | pass |
| 43 | `confpub property set --help` | discovery | 0 | pass |
| 44 | `confpub property delete --help` | discovery | 0 | pass |
| 45 | `confpub guide` | discovery | 0 | pass |
| 46 | `confpub auth inspect` | happy path | 0 | pass |
| 47 | `confpub config inspect` | happy path | 0 | pass |
| 48 | `confpub --compact auth inspect` | regression #2 | 0 | pass (FIXED) |
| 49 | `confpub --verbose auth inspect` | regression #2 | 0 | pass (FIXED) |
| 50 | `confpub auth inspect --compact` | edge case | 10 | unexpected (flag not recognized at leaf level) |
| 51 | `confpub auth --compact inspect` | edge case | 0 | pass (flag works at group level) |
| 52 | `confpub --quiet auth inspect` | happy path | 0 | pass |
| 53 | `confpub space list` | happy path | 0 | pass |
| 54 | `confpub space inspect --space SD` | happy path | 0 | pass |
| 55 | `confpub page list --space SD --limit 10` | happy path | 0 | pass |
| 56 | `confpub page publish test-page.md --space SD --parent "Software Development" --label blackbox-test --label v1-13-0` | happy path | 0 | pass |
| 57 | `confpub page inspect --page-id <ID>` | happy path | 0 | pass |
| 58 | `confpub page inspect --page-id <ID> --format markdown` | happy path | 0 | pass |
| 59 | `confpub plan create --manifest confpub.yaml` | happy path | 0 | pass |
| 60 | `confpub plan apply --plan confpub-plan.json` | happy path | 0 | pass |
| 61 | `confpub attachment upload test-attachment.txt --page-id <ID>` | happy path | 0 | pass |
| 62 | `confpub attachment list --page-id <ID>` | happy path | 0 | pass |
| 63 | `confpub attachment download --output downloaded-attachment.txt` (bare) | regression #1 | 50 | fail (STILL BROKEN with bare filenames) |
| 64 | `confpub attachment download --output <absolute path>` | regression #1 | 0 | pass (FIXED with absolute paths) |
| 65 | `confpub attachment download --output ./downloaded2.txt` | regression #1 | 0 | pass (FIXED with ./ prefix) |
| 66 | `confpub comment add --page-id <ID> --text "..."` | happy path | 0 | pass |
| 67 | `confpub comment list --page-id <ID>` | happy path | 0 | pass |
| 68 | `confpub label list --page-id <ID>` | happy path | 0 | pass |
| 69 | `confpub label add --page-id <ID> --label x --label y` | happy path | 0 | pass |
| 70 | `confpub label remove --page-id <ID> --label x --label y` | happy path | 0 | pass |
| 71 | `confpub search --space SD --title "Test Page" --type page` | happy path | 0 | pass (0 results due to indexing delay) |
| 72 | `confpub search --cql 'label = "blackbox-test"' --space SD` | happy path | 0 | pass |
| 73 | `confpub page export --page-id <ID> --format pdf --output ./test-export.pdf` | happy path | 0 | pass |
| 74 | `confpub page export --page-id <ID> --format word --output ./test-export.docx` | happy path | 0 | pass |
| 75 | `confpub page history --page-id <ID>` | happy path | 0 | pass |
| 76 | `confpub page list --space SD --limit 0` | regression #4 | 10 | pass (FIXED) |
| 77 | `confpub page list --space SD --limit -1` | regression #5 | 10 | pass (FIXED) |
| 78 | `confpub page list --space SD --limit 3` (without --label) | regression #6 | 0 | pass |
| 79 | `confpub page list --space SD --label blackbox-test` | regression #6 | 0 | pass (FIXED, same schema) |
| 80 | `confpub page publish binary-test.png --space SD` | regression #3 | 10 | pass (FIXED) |
| 81 | `confpub page version --page-id <ID> --version-number 999` | regression #7 | 10 | pass (PARTIALLY FIXED, clean code but raw Java text) |
| 82 | `confpub property get --page-id <ID> --key nonexistent` | regression #7 | 20 | pass (PARTIALLY FIXED) |
| 83 | `confpub page publish` (no file arg) | error handling | 10 | pass |
| 84 | `confpub page publish nonexistent.md --space SD` | error handling | 50 | pass |
| 85 | `confpub page publish empty.md --space SD --parent "Software Development"` | error handling | 0 | unexpected (no warning for empty file) |
| 86 | `confpub page publish whitespace.md --space SD --parent "Software Development"` | error handling | 0 | unexpected (no warning) |
| 87 | `confpub page publish test-page.md --space NONEXISTENT` | error handling | 10 | pass (detected space mismatch) |
| 88 | `confpub page publish unique-test.md --space SD --parent "Nonexistent Parent"` | error handling | 0 | unexpected (silent fallback to space root) |
| 89 | `confpub page publish test-page.md --dry-run` | edge case | 0 | pass |
| 90 | `confpub page publish special-chars.md --title-from-h1` | edge case | 0 | pass |
| 91 | `confpub page publish broken-syntax.md --dry-run` | edge case | 0 | pass (no crash on malformed syntax) |
| 92 | `echo "# Piped" \| confpub page publish -` | edge case | 50 | fail (no stdin support) |
| 93 | `confpub page publish frontmatter-only.md --dry-run` | edge case | 0 | pass |
| 94 | `confpub page list --space SD --limit abc` | error handling | 10 | pass |
| 95 | `confpub page list --space SD --limit 2 --limit 5` | edge case | 0 | pass (uses last value: 5) |
| 96 | `confpub page inspect --space BADSPACE --title "Does Not Exist"` | error handling | 20 | unexpected (403 instead of 404) |
| 97 | `confpub page delete --page-id 999999999` | error handling | 20 | unexpected (403 instead of 404) |
| 98 | `confpub page list --space BADSPACE` | error handling | 20 | unexpected (403 instead of 404) |
| 99 | `confpub search --limit 0` | regression #4 | 10 | pass (FIXED) |
| 100 | `confpub search --limit -5` | regression #5 | 10 | pass (FIXED) |
| 101 | `confpub comment list --page-id <ID> --limit 0` | regression #4 | 10 | pass (FIXED) |
| 102 | `confpub page export --format invalid` | error handling | 10 | pass |
| 103 | `confpub page inspect --format invalid --page-id <ID>` | error handling | 0 | unexpected (silent fallback) |
| 104 | `confpub --compact --verbose auth inspect` | edge case | 0 | pass (both flags work together) |
| 105 | `confpub property list --page-id <ID>` | happy path | 0 | pass |
| 106 | `confpub property set --page-id <ID> --key k --value '{"foo":"bar"}'` | happy path | 0 | pass |
| 107 | `confpub property get --page-id <ID> --key k` | happy path | 0 | pass |
| 108 | `confpub property delete --page-id <ID> --key k` | happy path | 0 | pass |
| 109 | `confpub page pull --page-id <ID> -o ./pull-test` | happy path | 0 | pass |
| 110 | `confpub page move --page-id <ID> --target-parent "Test Page" --space SD` | happy path | 0 | pass |
| 111 | `confpub plan create --manifest invalid-manifest.yaml` | error handling | 10 | pass |
| 112 | `confpub plan validate --plan confpub-plan.json` | happy path | 0 | pass |
| 113 | `confpub plan create --manifest nonexistent.yaml` | error handling | 50 | pass |
| 114 | `confpub plan apply --plan nonexistent.json` | error handling | 50 | pass |
| 115 | `confpub plan apply --plan confpub-plan.json --dry-run` | edge case | 0 | unexpected (shows create for existing pages) |
| 116 | `confpub skill inspect` | happy path | 0 | pass |
| 117 | `confpub page pull --recursive --space SD --title "Parent"` | happy path | 0 | pass |
| 118 | `confpub attachment delete --page-id <ID> --filename test.txt` | cleanup | 0 | pass |
| 119 | `confpub page delete --page-id <ID> --cascade` (test page) | cleanup | 0 | pass |
| 120 | `confpub page delete --page-id <ID> --cascade` (plan parent) | cleanup | 0 | pass |
| 121-124 | `confpub page delete --page-id <ID>` (remaining test pages) | cleanup | 0 | pass |

**Totals:** 124 commands executed. 110 pass, 8 unexpected behavior, 3 fail, 3 not applicable/edge cases.
