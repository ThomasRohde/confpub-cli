"""guide command — full machine-readable CLI schema.

An agent calls `confpub guide` once, caches the result, and can drive
the entire CLI zero-shot. Supports --section for filtering.
"""

from __future__ import annotations

from typing import Any

from confpub import __version__
from confpub.errors import (
    ERR_AUTH_EXPIRED,
    ERR_AUTH_FORBIDDEN,
    ERR_AUTH_REQUIRED,
    ERR_CONFLICT_FILE_EXISTS,
    ERR_CONFLICT_FINGERPRINT,
    ERR_CONFLICT_LOCK,
    ERR_CONFLICT_PAGE_EXISTS,
    ERR_INTERNAL_CONVERTER,
    ERR_INTERNAL_REVERSE_CONVERTER,
    ERR_INTERNAL_SDK,
    ERR_IO_CONNECTION,
    ERR_IO_FILE_NOT_FOUND,
    ERR_IO_TIMEOUT,
    ERR_VALIDATION_ASSET_MISSING,
    ERR_VALIDATION_LABEL,
    ERR_VALIDATION_SPACE_KEY,
    ERR_VALIDATION_MANIFEST,
    ERR_VALIDATION_MARKDOWN,
    ERR_VALIDATION_NOT_FOUND,
    ERR_VALIDATION_REQUIRED,
    ERR_VALIDATION_SPACE_MISMATCH,
    exit_code_for,
    retryable_for,
    suggested_action_for,
)


def _error_code_entry(code: str, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "exit_code": exit_code_for(code),
        "retryable": retryable_for(code),
        "suggested_action": suggested_action_for(code),
    }
    entry.update(extra)
    return entry


def build_guide() -> dict[str, Any]:
    """Build the complete guide JSON schema."""
    return {
        "schema_version": "1.0",
        "tool_version": __version__,
        "compatibility": {
            "additive_changes": "minor",
            "breaking_changes": "major",
        },
        "commands": {
            "guide": {
                "group": "meta",
                "mutates": False,
                "description": "Machine-readable CLI schema for agent consumption",
                "flags": ["--section"],
            },
            "search": {
                "group": "read",
                "mutates": False,
                "description": "Search Confluence content using CQL",
                "flags": ["--cql", "--space", "--title", "--type", "--limit", "--start", "--include-archived", "--excerpt-length"],
                "agent_hint": (
                    "Most agent workflows should include --type page to exclude attachments and space entities from results. "
                    "Use --start and --limit for pagination: first call with --start 0 --limit 25, "
                    "then if has_more is true, call again with --start 25 --limit 25, and so on."
                ),
                "result_schema": {
                    "cql_query": "string — effective CQL sent to the API",
                    "results": "list of {id, type, title, excerpt, url, space_key, entity_type, status, last_modified, container_title}",
                    "total": "int — total matching results",
                    "start": "int — current offset",
                    "limit": "int — page size",
                    "has_more": "bool — true if more results available",
                },
                "examples": [
                    'confpub search --cql \'label = "api-docs"\'',
                    "confpub search --space DEV --type page --limit 10",
                    'confpub search --space DEV --cql \'title ~ "deploy"\'',
                    'confpub search --title "deploy guide" --space DEV',
                    "confpub search --space DEV --type page --start 0 --limit 50",
                ],
            },
            "page.list": {
                "group": "read",
                "mutates": False,
                "description": "List pages in a Confluence space",
                "flags": ["--space", "--title", "--label", "--limit", "--start"],
                "result_schema": {
                    "pages": "list of slim page objects",
                    "start": "int — current offset",
                    "limit": "int — page size",
                    "size": "int — number of pages returned in this batch",
                    "has_more": "bool — true if more pages may be available (heuristic: size >= limit)",
                },
                "agent_hint": (
                    "Use --start and --limit for pagination: first call with --start 0 --limit 25, "
                    "then if has_more is true, call again with --start 25 --limit 25, and so on. "
                    "Use --title for client-side substring filtering on page titles. "
                    "Use --label to filter pages by label (uses CQL search). "
                    "For personal spaces, quote the tilde: --space '~username' "
                    "(PowerShell expands unquoted ~). Or set CONFPUB_SPACE env var."
                ),
            },
            "page.inspect": {
                "group": "read",
                "mutates": False,
                "description": "Inspect a Confluence page",
                "flags": ["--space", "--title", "--page-id", "--format", "--raw"],
                "agent_hint": (
                    "Use --format markdown to get the page body as Markdown instead of Confluence storage format. "
                    "Use --raw for the full unprocessed Confluence REST API v2 page response "
                    "(includes extensions, metadata, restrictions, version history — useful for debugging or advanced introspection)."
                ),
                "result_schema": {
                    "page_id": "string",
                    "title": "string",
                    "space_key": "string",
                    "version": "int",
                    "url": "string",
                    "body_storage": "string (when --format storage, the default)",
                    "body_markdown": "string (when --format markdown)",
                    "labels": "list of {name, id, prefix} objects",
                },
                "examples": [
                    'confpub page inspect --space DEV --title "My Page"',
                    "confpub page inspect --page-id 12345 --format markdown",
                    "confpub page inspect --page-id 12345 --raw",
                ],
            },
            "page.publish": {
                "group": "write",
                "mutates": True,
                "description": "Publish a single Markdown file to Confluence",
                "flags": ["--space", "--parent", "--title", "--title-from-h1", "--page-id", "--dry-run", "--backup", "--label"],
                "agent_hint": (
                    "Title precedence: explicit --title > --title-from-h1 > front-matter title > filename inference. "
                    "Space precedence: --space > front-matter space > CONFPUB_SPACE env var. "
                    "Parent precedence: --parent > front-matter parent. "
                    "Labels: CLI --label merged with front-matter labels (union, deduplicated). "
                    "When writing Markdown files for publication, include YAML front-matter to embed metadata: "
                    "---\\ntitle: Page Title\\nspace: SPACEKEY\\nparent: Parent Title\\nlabels:\\n  - tag1\\n---\\n "
                    "For personal spaces, quote the tilde: --space '~username' "
                    "(PowerShell expands unquoted ~). Or set CONFPUB_SPACE env var."
                ),
            },
            "page.move": {
                "group": "write",
                "mutates": True,
                "description": "Move a page under a new parent",
                "flags": ["--page-id", "--target-parent", "--space", "--target-parent-id"],
                "agent_hint": (
                    "Use --target-parent + --space for title-based targeting, "
                    "or --target-parent-id for ID-based targeting. "
                    "The page ID does not change after a move."
                ),
            },
            "page.pull": {
                "group": "read",
                "mutates": False,
                "description": "Pull Confluence pages to local Markdown files",
                "flags": [
                    "--space", "--title", "--page-id",
                    "--output", "--recursive", "--force",
                    "--layout", "--no-attachments", "--manifest",
                ],
                "safety_flags": {
                    "--force": "Overwrites existing local files without confirmation",
                },
                "agent_hint": (
                    "During recursive pulls, NDJSON progress events are emitted on stderr "
                    "with step (running discovery count) and total (0 until known). "
                    "Use --quiet to suppress."
                ),
            },
            "page.delete": {
                "group": "write",
                "mutates": True,
                "description": "Delete a Confluence page",
                "flags": ["--space", "--title", "--page-id", "--cascade"],
                "safety_flags": {
                    "--cascade": "Also deletes child pages",
                },
                "result_schema": {
                    "deleted_ids": "list of string — sorted page IDs that were deleted",
                    "deleted_count": "int — number of pages deleted (including children when --cascade)",
                },
            },
            "space.list": {
                "group": "read",
                "mutates": False,
                "description": "List accessible Confluence spaces",
                "flags": [],
            },
            "attachment.list": {
                "group": "read",
                "mutates": False,
                "description": "List attachments on a Confluence page",
                "flags": ["--page-id"],
            },
            "attachment.upload": {
                "group": "write",
                "mutates": True,
                "description": "Upload an attachment to a Confluence page",
                "flags": ["--page-id"],
            },
            "label.list": {
                "group": "read",
                "mutates": False,
                "description": "List labels on a Confluence page",
                "flags": ["--page-id"],
            },
            "label.add": {
                "group": "write",
                "mutates": True,
                "description": "Add labels to a Confluence page",
                "flags": ["--page-id", "--label"],
                "agent_hint": "Use --label for each label (repeatable): --label api --label docs. Labels must not contain spaces and max 255 characters.",
            },
            "label.remove": {
                "group": "write",
                "mutates": True,
                "description": "Remove labels from a Confluence page",
                "flags": ["--page-id", "--label"],
            },
            "comment.add": {
                "group": "write",
                "mutates": True,
                "description": "Add a comment to a Confluence page",
                "flags": ["--page-id", "--text", "--file"],
                "agent_hint": "Exactly one of --text or --file is required. The body is converted from Markdown to Confluence storage format.",
            },
            "plan.create": {
                "group": "transactional",
                "mutates": False,
                "description": "Generate a plan artifact from a manifest or file",
                "flags": ["--manifest", "--output", "--space", "--parent"],
            },
            "plan.validate": {
                "group": "transactional",
                "mutates": False,
                "description": "Validate a plan artifact against current state",
                "flags": ["--plan"],
            },
            "plan.apply": {
                "group": "transactional",
                "mutates": True,
                "description": "Apply a plan to Confluence",
                "flags": [
                    "--plan", "--dry-run", "--backup",
                    "--skip-fingerprint-check", "--cascade",
                ],
                "safety_flags": {
                    "--skip-fingerprint-check": (
                        "Bypasses stale-state detection — use only if you know "
                        "the page changed intentionally"
                    ),
                    "--cascade": "Allows deletes that affect child pages",
                },
                "result_schema": {
                    "dry_run": "bool",
                    "changes": "list of change records",
                    "summary": "{create: int, update: int, attachments_upload: int}",
                    "lockfile_updated": "bool — true if lockfile was written",
                    "lockfile_path": "string | null — absolute path to lockfile (null on dry-run)",
                },
            },
            "plan.verify": {
                "group": "transactional",
                "mutates": False,
                "description": "Verify post-conditions after apply",
                "flags": ["--assertions", "--plan"],
            },
            "auth.inspect": {
                "group": "auth",
                "mutates": False,
                "description": "Show current credential status",
                "flags": [],
            },
            "config.set": {
                "group": "config",
                "mutates": True,
                "description": "Set a configuration value",
                "flags": [],
                "args": ["KEY", "VALUE"],
                "agent_hint": (
                    "Valid keys: base_url, user, token. "
                    "Values are persisted to the config file (~/.confpub/config.json)."
                ),
                "examples": [
                    "confpub config set base_url https://mysite.atlassian.net/wiki",
                    "confpub config set user alice@example.com",
                    "confpub config set token ATATT...",
                ],
            },
            "config.inspect": {
                "group": "config",
                "mutates": False,
                "description": "Show current configuration",
                "flags": [],
            },
        },
        "error_codes": {
            ERR_VALIDATION_REQUIRED: _error_code_entry(ERR_VALIDATION_REQUIRED),
            ERR_VALIDATION_MANIFEST: _error_code_entry(ERR_VALIDATION_MANIFEST),
            ERR_VALIDATION_MARKDOWN: _error_code_entry(ERR_VALIDATION_MARKDOWN),
            ERR_VALIDATION_ASSET_MISSING: _error_code_entry(ERR_VALIDATION_ASSET_MISSING),
            ERR_VALIDATION_NOT_FOUND: _error_code_entry(ERR_VALIDATION_NOT_FOUND),
            ERR_VALIDATION_SPACE_MISMATCH: _error_code_entry(ERR_VALIDATION_SPACE_MISMATCH),
            ERR_VALIDATION_LABEL: _error_code_entry(ERR_VALIDATION_LABEL),
            ERR_VALIDATION_SPACE_KEY: _error_code_entry(ERR_VALIDATION_SPACE_KEY),
            ERR_AUTH_REQUIRED: _error_code_entry(ERR_AUTH_REQUIRED),
            ERR_AUTH_EXPIRED: _error_code_entry(ERR_AUTH_EXPIRED),
            ERR_AUTH_FORBIDDEN: _error_code_entry(ERR_AUTH_FORBIDDEN),
            ERR_CONFLICT_FINGERPRINT: _error_code_entry(ERR_CONFLICT_FINGERPRINT),
            ERR_CONFLICT_LOCK: _error_code_entry(ERR_CONFLICT_LOCK),
            ERR_CONFLICT_PAGE_EXISTS: _error_code_entry(ERR_CONFLICT_PAGE_EXISTS),
            ERR_CONFLICT_FILE_EXISTS: _error_code_entry(ERR_CONFLICT_FILE_EXISTS),
            ERR_IO_FILE_NOT_FOUND: _error_code_entry(ERR_IO_FILE_NOT_FOUND),
            ERR_IO_CONNECTION: _error_code_entry(
                ERR_IO_CONNECTION, retry_after_ms=2000,
            ),
            ERR_IO_TIMEOUT: _error_code_entry(ERR_IO_TIMEOUT, retry_after_ms=2000),
            ERR_INTERNAL_CONVERTER: _error_code_entry(ERR_INTERNAL_CONVERTER),
            ERR_INTERNAL_REVERSE_CONVERTER: _error_code_entry(ERR_INTERNAL_REVERSE_CONVERTER),
            ERR_INTERNAL_SDK: _error_code_entry(ERR_INTERNAL_SDK),
        },
        "global_flags": {
            "description": "Flags that can be placed at the top level or between group name and subcommand.",
            "flags": {
                "--quiet": "Suppress progress output on stderr",
                "--verbose": "Include diagnostics in result (adds metrics.diagnostics with api_call_count, python_version, confpub_version, config_source, confluence_url, is_cloud; on error includes traceback)",
                "--compact": "Output single-line JSON (no indentation)",
                "--version": "Show version and exit (top-level only)",
            },
            "placement": [
                "confpub --quiet page publish ...  (before the group)",
                "confpub page --quiet publish ...  (between group and command)",
                "Both positions are equivalent; the flag is parsed by the group callback",
            ],
        },
        "concurrency": {
            "rule": (
                "Never run multiple write commands against the same "
                "space and page in parallel"
            ),
            "safe_patterns": [
                "Read commands (search, page.list, page.inspect) can parallelize freely",
                "Writes to DIFFERENT spaces can parallelize",
                (
                    "Use plan.apply with a single manifest for multi-page "
                    "publishes — do not run parallel applies"
                ),
            ],
            "lock_behavior": (
                "plan.apply acquires a local lockfile; concurrent applies "
                "to the same workspace return ERR_CONFLICT_LOCK"
            ),
        },
        "lockfile": {
            "description": "Local state file tracking page IDs and versions from publish/pull operations.",
            "file": "confpub.lock",
            "schema": {
                "schema_version": "Lockfile format version (currently '1.0')",
                "last_updated": "ISO 8601 timestamp of last write",
                "pages": "Map of page title to { page_id, version }",
            },
            "behavior": [
                "Created/updated automatically by page.publish, page.pull, and plan.apply",
                "Entries removed automatically by page.delete (including --cascade)",
                "Written atomically (temp file + rename) for crash safety",
                "Used by plan.create to detect existing pages and versions",
                "Does not prevent concurrent operations — purely local state tracking",
                (
                    "Path resolution: page.publish and page.delete use CWD/confpub.lock; "
                    "page.pull uses <output-dir>/confpub.lock; "
                    "plan.apply uses <plan-dir>/confpub.lock (same directory as the plan artifact)"
                ),
            ],
        },
        "markdown_support": {
            "description": "Markdown features converted to native Confluence Storage Format.",
            "base": "CommonMark with GitHub-flavored extensions",
            "features": {
                "headings":       "# h1 through ###### h6 → <h1>–<h6>",
                "bold_italic":    "**bold**, *italic* → <strong>, <em>",
                "strikethrough":  "~~text~~ → <del>",
                "inline_code":    "`code` → <code>",
                "code_blocks":    "```lang ... ``` → ac:structured-macro code with language param",
                "links":          "[text](url) → <a href>",
                "images":         "![alt](path) → ac:image (local files uploaded as attachments)",
                "tables":         "GFM tables → <table>",
                "lists":          "Ordered and unordered, nested → <ol>, <ul>",
                "blockquotes":    "> text → <blockquote>",
                "admonitions":    "> [!NOTE|TIP|WARNING|CAUTION|IMPORTANT] → info/tip/warning/note macros",
                "task_lists":     "- [ ] / - [x] → ac:task-list with ac:task elements",
                "math_inline":    "$LaTeX$ → ac:structured-macro mathinline",
                "math_block":     "$$...$$ → ac:structured-macro mathblock",
                "definition_lists": "Term\\n: Definition → <dl><dt><dd>",
                "footnotes":      "[^1] + [^1]: text → superscript links with numbered list",
                "front_matter": (
                    "---\\nyaml\\n--- → extracted for page metadata "
                    "(title, space, parent, labels, page_id); "
                    "used by page.publish; ignored when a manifest is used"
                ),
                "panels":         "::: panel Title\\ncontent\\n::: → ac:structured-macro panel",
                "expand":         "::: expand Title\\ncontent\\n::: → ac:structured-macro expand",
                "layouts":        ":::: layout two-equal\\n::: cell\\n...\\n::::\\n → ac:layout with ac:layout-section. Content outside layout blocks is auto-wrapped in a single-column layout (Confluence requires all content in layout cells when layouts are used).",
                "status":           "{status:Title|colour=Color} → ac:structured-macro status",
                "toc":              "{toc} / {toc:maxLevel=N} → ac:structured-macro toc",
                "anchor":           "{anchor:name} → ac:structured-macro anchor",
                "children":         "{children} / {children:depth=N} → ac:structured-macro children",
                "jira":             "{jira:KEY-123} / {jira:jql=...} → ac:structured-macro jira",
                "recently_updated": "{recently-updated} → ac:structured-macro recently-updated",
                "excerpt_include":  "{excerpt-include:Page Title} → ac:structured-macro excerpt-include",
                "include_page":     "{include:Page Title} → ac:structured-macro include",
                "excerpt":          "::: excerpt hidden\\ncontent\\n::: → ac:structured-macro excerpt",
            },
            "layout_types": ["single", "two-equal", "two-left-sidebar", "two-right-sidebar", "three-equal", "three-with-sidebars"],
            "agent_hint": (
                "All features are always-on — the parser simply ignores syntax that isn't used. "
                "Math macros require the Confluence LaTeX Math plugin to be installed on the server. "
                "Layouts use :::: (4 colons) for the outer layout block and ::: (3 colons) for inner cells. "
                "When layouts are used, ALL page content must live inside layout cells — "
                "confpub auto-wraps any content outside layout blocks in a single-column layout to satisfy this Confluence requirement. "
                "Use {macro-name:params} for body-less Confluence macros. "
                "Macros on their own line become block-level (no <p> wrapping)."
            ),
        },
        "front_matter": {
            "description": (
                "YAML front-matter in Markdown files provides default page metadata for page.publish. "
                "When a manifest (confpub.yaml) is used, front-matter is ignored entirely."
            ),
            "fields": {
                "title": "Page title (string)",
                "space": "Confluence space key (string)",
                "parent": "Parent page title (string)",
                "labels": "Labels to apply (list of strings, or single string)",
                "page_id": "Confluence page ID for direct update (string or integer)",
            },
            "precedence": {
                "title": "--title > --title-from-h1 > front-matter > filename",
                "space": "--space > front-matter > CONFPUB_SPACE",
                "parent": "--parent > front-matter",
                "page_id": "--page-id > front-matter",
                "labels": "CLI --label + front-matter labels merged (deduplicated)",
            },
            "example": (
                "---\n"
                "title: API Reference\n"
                "space: DEV\n"
                "parent: Documentation\n"
                "labels:\n"
                "  - api\n"
                "  - public\n"
                "---\n"
                "\n"
                "# API Reference\n"
                "\n"
                "Content here..."
            ),
            "agent_hint": (
                "When creating Markdown files for Confluence publication, always include "
                "front-matter with at least title, space, and parent so the file can be "
                "published with just `confpub page publish <file>` — no extra flags needed. "
                "Unknown front-matter keys (e.g. draft, author) are silently ignored, "
                "so front-matter is compatible with other tools like Jekyll or Hugo."
            ),
        },
        "assertions": {
            "description": "Post-condition assertions verified by plan.verify.",
            "file_format": "JSON array of assertion objects, or embedded in confpub.yaml under the 'assertions' key.",
            "auto_generation": "When --plan is passed without --assertions, plan.verify auto-generates page.exists assertions for every create/update page in the plan.",
            "types": {
                "page.exists": {
                    "description": "Verify that a page exists in the given space.",
                    "required_fields": ["type", "space", "title"],
                    "example": {"type": "page.exists", "space": "DEV", "title": "My Page"},
                },
                "page.parent": {
                    "description": "Verify that a page has the expected parent.",
                    "required_fields": ["type", "space", "title", "expected_parent"],
                    "example": {"type": "page.parent", "space": "DEV", "title": "My Page", "expected_parent": "Parent Page"},
                },
                "attachment.exists": {
                    "description": "Verify that an attachment exists on a page.",
                    "required_fields": ["type", "space", "page", "filename"],
                    "example": {"type": "attachment.exists", "space": "DEV", "page": "My Page", "filename": "diagram.png"},
                },
            },
        },
        "auth": {
            "precedence": [
                "--token + --user",
                "CONFPUB_TOKEN + CONFPUB_USER",
                "config_file",
                "os_keychain",
            ],
            "env_vars": {
                "CONFPUB_URL": "Confluence base URL",
                "CONFPUB_TOKEN": "API token or PAT",
                "CONFPUB_USER": "User email or username",
                "CONFPUB_SSL_VERIFY": "SSL verification (true/false/ca-bundle path)",
                "CONFPUB_SPACE": "Default space key (avoids shell expansion issues with --space)",
            },
            "non_interactive": (
                "Never prompts when LLM=true or stdin is non-interactive"
            ),
            "inspect_command": "confpub auth inspect",
        },
    }
