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
                "flags": ["--cql", "--space", "--title", "--type", "--limit", "--start", "--include-archived", "--excerpt-length", "--no-score"],
                "agent_hint": (
                    "Most agent workflows should include --type page to exclude attachments and space entities from results. "
                    "Use --start and --limit for pagination: first call with --start 0 --limit 25, "
                    "then if has_more is true, call again with --start 25 --limit 25, and so on. "
                    "Search results include cached trust scores by default (trust.score, trust.band, trust.confidence, trust.primary_class). "
                    "Pages without cached scores omit the trust field. Use --no-score to disable."
                ),
                "result_schema": {
                    "cql_query": "string — effective CQL sent to the API",
                    "results": "list of {id, type, title, excerpt, url, space_key, status, last_modified, container_title, trust?}",
                    "results[].trust": "{score, band, confidence, primary_class, stale} — present when a cached trust score exists (omit with --no-score)",
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
                    "(includes extensions, metadata, restrictions, version history — useful for debugging or advanced introspection). "
                    "Also warms the trust score cache for the inspected page."
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
                "flags": ["--space", "--parent", "--title", "--title-from-h1", "--page-id", "--dry-run", "--backup", "--label", "--html-macro-name"],
                "agent_hint": (
                    "Title precedence: explicit --title > --title-from-h1 > front-matter title > filename inference. "
                    "Space precedence: --space > front-matter space > CONFPUB_SPACE env var. "
                    "Parent precedence: --parent > front-matter parent. "
                    "Labels: CLI --label merged with front-matter labels (union, deduplicated). "
                    "When writing Markdown files for publication, include YAML front-matter to embed metadata: "
                    "---\\ntitle: Page Title\\nspace: SPACEKEY\\nparent: Parent Title\\nlabels:\\n  - tag1\\n---\\n "
                    "For personal spaces, quote the tilde: --space '~username' "
                    "(PowerShell expands unquoted ~). Or set CONFPUB_SPACE env var. "
                    "HTML macro name: auto-detected from Confluence type (Cloud=html-macro, DC=html). "
                    "Override with --html-macro-name or html_macro_name in front-matter. "
                    "After a successful publish (not dry-run), the trust score cache is warmed for the published page."
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
                "agent_hint": "Use --label for each label (repeatable): --label api --label docs. Labels must not contain spaces and max 255 characters. Also warms the trust score cache (labels affect classification).",
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
            "comment.list": {
                "group": "read",
                "mutates": False,
                "description": "List comments on a Confluence page",
                "flags": ["--page-id", "--limit"],
                "result_schema": {
                    "comments": "list of {id, body_storage, created_by, created_date, version}",
                    "count": "int",
                },
            },
            "property.list": {
                "group": "read",
                "mutates": False,
                "description": "List all properties on a Confluence page",
                "flags": ["--page-id"],
                "result_schema": {
                    "properties": "list of {key, value, version}",
                    "count": "int",
                },
                "agent_hint": "Properties are key-value metadata on pages. Values can be any JSON type. Queryable via CQL: content.property[key].value = \"val\".",
            },
            "property.get": {
                "group": "read",
                "mutates": False,
                "description": "Get a single property from a Confluence page",
                "flags": ["--page-id", "--key"],
                "result_schema": {"key": "string", "value": "any", "version": "int", "page_id": "string"},
            },
            "property.set": {
                "group": "write",
                "mutates": True,
                "description": "Set a property on a Confluence page (create or update)",
                "flags": ["--page-id", "--key", "--value"],
                "agent_hint": "--value accepts a JSON string (parsed) or plain text (stored as string). Use JSON for structured data: --value '{\"status\":\"draft\"}'. Also warms the trust score cache — especially useful after setting confpub.meta.v1.",
                "result_schema": {"key": "string", "value": "any", "version": "int", "page_id": "string", "created": "bool"},
            },
            "property.delete": {
                "group": "write",
                "mutates": True,
                "description": "Delete a property from a Confluence page",
                "flags": ["--page-id", "--key"],
                "result_schema": {"deleted": "bool", "key": "string", "page_id": "string"},
            },
            "page.history": {
                "group": "read",
                "mutates": False,
                "description": "Show version history of a Confluence page",
                "flags": ["--page-id", "--limit"],
                "result_schema": {
                    "versions": "list of {number, when, by, message}",
                    "count": "int",
                },
            },
            "page.version": {
                "group": "read",
                "mutates": False,
                "description": "Get a specific version of a Confluence page",
                "flags": ["--page-id", "--version-number"],
                "result_schema": {"id": "string", "title": "string", "version": "int", "body_storage": "string", "when": "string", "by": "string"},
            },
            "page.export": {
                "group": "read",
                "mutates": False,
                "description": "Export a Confluence page as PDF or Word",
                "flags": ["--page-id", "--format", "--output"],
                "agent_hint": "--format accepts 'pdf' or 'word'. The file is written to --output path.",
                "result_schema": {"exported": "bool", "page_id": "string", "format": "string", "output_path": "string", "file_size": "int"},
            },
            "attachment.download": {
                "group": "read",
                "mutates": False,
                "description": "Download an attachment from a Confluence page",
                "flags": ["--page-id", "--filename", "--output"],
                "result_schema": {"downloaded": "bool", "page_id": "string", "filename": "string", "output_path": "string", "file_size": "int"},
            },
            "attachment.delete": {
                "group": "write",
                "mutates": True,
                "description": "Delete an attachment from a Confluence page",
                "flags": ["--page-id", "--filename"],
                "result_schema": {"deleted": "bool", "page_id": "string", "filename": "string", "attachment_id": "string"},
            },
            "space.inspect": {
                "group": "read",
                "mutates": False,
                "description": "Get detailed information about a Confluence space",
                "flags": ["--space"],
                "result_schema": {"key": "string", "name": "string", "type": "string", "description": "string", "homepage_id": "string", "homepage_title": "string", "webui": "string"},
            },
            "plan.create": {
                "group": "transactional",
                "mutates": False,
                "description": "Generate a plan artifact from a manifest or file",
                "flags": ["--manifest", "--output", "--space", "--parent", "--html-macro-name"],
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
                    "--skip-fingerprint-check", "--cascade", "--html-macro-name",
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
            "skill.install": {
                "group": "skill",
                "mutates": True,
                "description": "Install the confpub publishing skill into the current repo",
                "flags": ["--agent", "--force", "--dry-run"],
                "agent_hint": (
                    "Auto-detects coding agents (Claude, Copilot, Cursor, Windsurf, AGENTS.md) "
                    "in CWD and installs the skill in each agent's format. "
                    "Use --agent to target specific agents. No Confluence credentials needed."
                ),
                "result_schema": {
                    "dry_run": "bool",
                    "agents": "list of {name, detected_by, skill_dir, files_written, entry_file}",
                    "total_files_written": "int",
                    "version": "string",
                },
            },
            "skill.inspect": {
                "group": "skill",
                "mutates": False,
                "description": "Detect coding agents and show skill installation status",
                "flags": [],
                "result_schema": {
                    "detected_agents": "list of {name, detected_by, installed, installed_version}",
                    "skill_version": "string",
                    "skill_files": "int",
                },
            },
            "page.score": {
                "group": "read",
                "mutates": False,
                "description": "Score a page's operational trustworthiness",
                "flags": [
                    "--page-id", "--space", "--title",
                    "--profile", "--doc-class",
                    "--explain", "--refresh",
                    "--include-signals", "--include-missing",
                ],
                "agent_hint": (
                    "Scores governance, freshness, evidence, structure, and corroboration. "
                    "Returns score (0-100), band, confidence, subscores, and resolved classification "
                    "(primary_class, subtype, lifecycle_state). "
                    "Use --explain full --include-signals for detailed breakdown. "
                    "Use --refresh to bypass cache. "
                    "--doc-class accepts both new primary classes (governance, instruction, decision, ...) "
                    "and legacy values (policy, runbook, adr — auto-mapped). "
                    "Reads confpub.meta.v1 content property for governance metadata. "
                    "See SCORE.md for the full scoring algorithm specification."
                ),
                "result_schema": {
                    "algorithm_version": "string",
                    "profile": "string",
                    "primary_class": "string — resolved primary class (hub, governance, instruction, ...)",
                    "subtype": "string | null — optional subtype (policy, runbook, adr, ...)",
                    "lifecycle_state": "string | null — resolved lifecycle state (draft, active, approved, deprecated, ...)",
                    "score": "int (0-100)",
                    "band": "string (high|good|caution|low)",
                    "confidence": "float (0-1)",
                    "hard_caps": "list of {name, cap, reason} — active hard cap rules",
                    "subscores": "{stewardship, freshness, evidence, structure, corroboration} — each float 0-1",
                    "signals": "list of {id, status, weight, value, source} (when --include-signals)",
                    "missing_signals": "list of string (when --include-missing)",
                    "classification": "{source, matched_value, evaluated_title_patterns} — classification reasoning (when --explain summary or full)",
                },
                "examples": [
                    "confpub page score --page-id 123456",
                    'confpub page score --space EA --title "Target Architecture"',
                    "confpub page score --page-id 123456 --explain full --include-signals",
                    "confpub page score --page-id 123456 --profile working-area --refresh",
                ],
            },
            "trust.browse": {
                "group": "read",
                "mutates": False,
                "description": "Interactive TUI browser for cached trust scores",
                "flags": [],
                "agent_hint": (
                    "Opens an interactive terminal UI showing all cached trust scores in a sortable table. "
                    "Press Enter for detail view, r to re-score, d to delete, s to sort, / to search, q to quit. "
                    "Requires cached scores — run page score or trust cache warm first."
                ),
                "examples": [
                    "confpub trust browse",
                ],
            },
            "trust.profile.inspect": {
                "group": "read",
                "mutates": False,
                "description": "Show built-in or custom scoring profiles",
                "flags": [],
            },
            "trust.cache.inspect": {
                "group": "read",
                "mutates": False,
                "description": "Show trust cache stats, TTLs, and hit rate",
                "flags": [],
            },
            "trust.cache.purge": {
                "group": "write",
                "mutates": True,
                "description": "Clear trust cache entries",
                "flags": ["--space", "--page-id", "--older-than", "--all"],
                "examples": [
                    "confpub trust cache purge --space EA",
                    "confpub trust cache purge --all",
                    "confpub trust cache purge --older-than 24",
                ],
            },
            "trust.cache.warm": {
                "group": "write",
                "mutates": True,
                "description": "Precompute trust scores for a space or CQL result set",
                "flags": ["--space", "--cql", "--profile"],
                "agent_hint": (
                    "Iterates all pages in a space or CQL result set and scores each one. "
                    "Use this to pre-populate the cache before browsing with trust browse. "
                    "Progress is reported on stderr."
                ),
                "examples": [
                    "confpub trust cache warm --space EA",
                    'confpub trust cache warm --cql \'label = "official-knowledge"\'',
                ],
            },
            "trust.anchor.set": {
                "group": "write",
                "mutates": True,
                "description": "Declare a trust level for a space or page",
                "flags": ["--space", "--page-id", "--level", "--reason", "--recursive"],
                "agent_hint": (
                    "Anchors override computed scores. Use --level high/good for trusted spaces, "
                    "caution/low for unreliable ones, exclude to hide entirely. "
                    "Use --recursive with --space to include all child pages."
                ),
                "examples": [
                    'confpub trust anchor set --space EA --level high --reason "Architecture team"',
                    "confpub trust anchor set --page-id 123456 --level caution --reason \"Needs review\"",
                ],
            },
            "trust.anchor.list": {
                "group": "read",
                "mutates": False,
                "description": "List all declared trust anchors",
                "flags": [],
                "examples": ["confpub trust anchor list"],
            },
            "trust.anchor.remove": {
                "group": "write",
                "mutates": True,
                "description": "Remove a trust anchor",
                "flags": ["--space", "--page-id"],
                "examples": [
                    "confpub trust anchor remove --space EA",
                    "confpub trust anchor remove --page-id 123456",
                ],
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
        "trust_scoring": {
            "description": (
                "Trust scoring estimates how safe it is to rely on a page as current guidance. "
                "Scores are cached locally in ~/.confpub/trust-cache.sqlite3 (override via CONFPUB_CACHE_DIR)."
            ),
            "auto_warming": {
                "description": (
                    "Trust scores are automatically computed and cached whenever confpub interacts with a page. "
                    "This happens as a silent side effect — it never delays or disrupts the primary command."
                ),
                "commands_that_warm": [
                    "page.inspect",
                    "page.publish",
                    "property.set",
                    "label.add",
                    "label.remove",
                    "page.history",
                ],
                "behavior": [
                    "If a fresh cache entry already exists for the page, scoring is skipped (zero cost)",
                    "If no fresh entry exists, the page is scored and the result is cached",
                    "Failures are silently ignored — the primary command always succeeds",
                    "Cache TTL is 15 minutes; after that the next interaction re-scores",
                ],
            },
            "search_enrichment": {
                "description": (
                    "Search results include cached trust scores by default. "
                    "Each page-type result gets a 'trust' field with score, band, confidence, and primary_class. "
                    "Pages without cached scores omit the trust field. Use --no-score to disable."
                ),
            },
            "classification": {
                "description": (
                    "Pages are classified across five orthogonal dimensions: "
                    "primary_class, subtype, domain, lifecycle_state, and generation_mode. "
                    "Classification is resolved from confpub.meta.v1 properties, labels, and title patterns. "
                    "Legacy doc_class values (policy, runbook, adr, etc.) are auto-mapped."
                ),
                "primary_classes": [
                    "hub", "governance", "instruction", "reference", "specification",
                    "decision", "analysis", "plan", "report", "record",
                    "people_org", "scaffold", "unknown",
                ],
            },
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
                "html_macro": (
                    "::: html\\n<raw HTML>\\n::: → ac:structured-macro html (DC) or html-macro (Cloud). "
                    "Content is wrapped in CDATA and passed verbatim — Confluence does NOT strip "
                    "<style>, <script>, <iframe>, or any other tags inside the HTML macro. "
                    "Use this for custom CSS styling, dashboards, diagrams, embedded widgets, "
                    "or any HTML that Confluence would otherwise sanitize. "
                    "The macro name is auto-detected (Cloud=html-macro, DC=html) but can be "
                    "overridden via --html-macro-name flag or html_macro_name front-matter field. "
                    "ASSET AUTO-DISCOVERY: <script src=\"app.js\"> and <link href=\"style.css\"> "
                    "references inside ::: html blocks are automatically detected. The referenced "
                    "files are uploaded as page attachments and the src/href URLs in the CDATA "
                    "are rewritten to point to the Confluence attachment download path. "
                    "This enables interactive JavaScript applications — bundle your app into a "
                    "single .js file, reference it from a ::: html block, and confpub handles "
                    "the rest. Missing files produce warnings (not errors) so partial publishes "
                    "still succeed."
                ),
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
                "Macros on their own line become block-level (no <p> wrapping). "
                "IMPORTANT: When the user needs custom styling, CSS, embedded widgets, iframes, "
                "or any HTML that Confluence normally strips, use ::: html blocks. "
                "Confluence strips <style>, <script>, <iframe> etc. from normal content, "
                "but the HTML macro preserves them. This is the ONLY way to embed arbitrary HTML. "
                "Example: ::: html\\n<style>.box { border: 1px solid blue; }</style>\\n"
                "<div class=\"box\">Styled content</div>\\n::: "
                "Multiple ::: html blocks can appear on the same page. "
                "The macro name auto-detects Cloud vs DC — no configuration needed. "
                "INTERACTIVE APPS: To embed a JavaScript application, place the bundled .js file "
                "next to the .md file, then reference it: ::: html\\n<div id=\"app\"></div>\\n"
                "<script src=\"app.js\"></script>\\n::: — confpub auto-discovers the <script src>, "
                "uploads app.js as a page attachment, and rewrites the URL in the CDATA block. "
                "The same works for <link href=\"style.css\"> for external CSS. "
                "Missing files produce warnings, not errors — the page still publishes."
            ),
            "html_macro_examples": [
                {
                    "description": "Custom styled card with CSS",
                    "markdown": (
                        "::: html\n"
                        "<style>\n"
                        "  .info-card { border: 2px solid #0052CC; border-radius: 8px; padding: 16px; }\n"
                        "  .info-card h3 { color: #0052CC; margin-top: 0; }\n"
                        "</style>\n"
                        "<div class=\"info-card\">\n"
                        "  <h3>Key Metric</h3>\n"
                        "  <p>Value: <strong>99.9%</strong></p>\n"
                        "</div>\n"
                        ":::"
                    ),
                },
                {
                    "description": "Flexbox dashboard layout",
                    "markdown": (
                        "::: html\n"
                        "<style>\n"
                        "  .dash { display: flex; gap: 16px; }\n"
                        "  .dash-card { flex: 1; padding: 16px; border-radius: 8px; color: #fff; }\n"
                        "</style>\n"
                        "<div class=\"dash\">\n"
                        "  <div class=\"dash-card\" style=\"background:#0052CC\">Users: 1,234</div>\n"
                        "  <div class=\"dash-card\" style=\"background:#36B37E\">Revenue: $56K</div>\n"
                        "</div>\n"
                        ":::"
                    ),
                },
                {
                    "description": "Embedded iframe (e.g. external dashboard)",
                    "markdown": (
                        "::: html\n"
                        "<iframe src=\"https://example.com/dashboard\" "
                        "width=\"100%\" height=\"400\" frameborder=\"0\"></iframe>\n"
                        ":::"
                    ),
                },
                {
                    "description": "Interactive JavaScript app (file auto-discovered and uploaded as attachment)",
                    "markdown": (
                        "::: html\n"
                        "<div id=\"my-app\"></div>\n"
                        "<script src=\"app.js\"></script>\n"
                        ":::"
                    ),
                    "note": (
                        "Place app.js next to the .md file. confpub auto-discovers the "
                        "<script src>, uploads app.js as a page attachment, and rewrites "
                        "the src URL to the Confluence attachment download path. "
                        "Works with any bundled JS — TypeScript, React, Vue, etc."
                    ),
                },
                {
                    "description": "External CSS loaded from attachment",
                    "markdown": (
                        "::: html\n"
                        "<link rel=\"stylesheet\" href=\"dashboard.css\" />\n"
                        "<div class=\"dashboard\">\n"
                        "  <div class=\"widget\">Content here</div>\n"
                        "</div>\n"
                        ":::"
                    ),
                    "note": (
                        "Place dashboard.css next to the .md file. confpub uploads it "
                        "and rewrites the href to the attachment URL."
                    ),
                },
                {
                    "description": "Progress bar with CSS gradients",
                    "markdown": (
                        "::: html\n"
                        "<div style=\"background:#DFE1E6; border-radius:12px; overflow:hidden; height:24px;\">\n"
                        "  <div style=\"width:75%; height:100%; background:linear-gradient(90deg,#0052CC,#4C9AFF); "
                        "border-radius:12px; color:#fff; font-size:12px; display:flex; align-items:center; "
                        "justify-content:flex-end; padding-right:8px; font-weight:600;\">75%</div>\n"
                        "</div>\n"
                        ":::"
                    ),
                },
            ],
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
                "html_macro_name": "HTML macro name override (string; 'html' for DC, 'html-macro' for Cloud; auto-detected by default)",
            },
            "precedence": {
                "title": "--title > --title-from-h1 > front-matter > filename",
                "space": "--space > front-matter > CONFPUB_SPACE",
                "parent": "--parent > front-matter",
                "page_id": "--page-id > front-matter",
                "labels": "CLI --label + front-matter labels merged (deduplicated)",
                "html_macro_name": "--html-macro-name > front-matter > auto-detect (Cloud=html-macro, DC=html)",
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
