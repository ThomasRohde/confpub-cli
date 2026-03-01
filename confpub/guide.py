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
                "agent_hint": "Most agent workflows should include --type page to exclude attachments and space entities from results.",
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
                ],
            },
            "page.list": {
                "group": "read",
                "mutates": False,
                "description": "List pages in a Confluence space",
                "flags": ["--space", "--limit", "--start"],
            },
            "page.inspect": {
                "group": "read",
                "mutates": False,
                "description": "Inspect a Confluence page",
                "flags": ["--space", "--title", "--page-id", "--format"],
            },
            "page.publish": {
                "group": "write",
                "mutates": True,
                "description": "Publish a single Markdown file to Confluence",
                "flags": ["--space", "--parent", "--title", "--page-id", "--dry-run", "--backup"],
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
            },
            "page.delete": {
                "group": "write",
                "mutates": True,
                "description": "Delete a Confluence page",
                "flags": ["--space", "--title", "--page-id", "--cascade"],
                "safety_flags": {
                    "--cascade": "Also deletes child pages",
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
            ],
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
            "non_interactive": (
                "Never prompts when LLM=true or stdin is non-interactive"
            ),
            "inspect_command": "confpub auth inspect",
        },
    }
