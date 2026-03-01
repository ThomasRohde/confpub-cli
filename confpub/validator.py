"""plan.validate — re-fingerprint and check source files.

Loads a plan artifact, verifies all source files still exist,
and re-fingerprints Confluence pages to detect external edits.
No writes occur.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from confpub.config import load_config
from confpub.confluence import ConfluenceClient
from confpub.errors import ERR_IO_FILE_NOT_FOUND, ERR_VALIDATION_MANIFEST, ConfpubError
from confpub.manifest import PlanArtifact, PlanPage


def _load_plan(plan_path: str) -> PlanArtifact:
    """Load and parse a plan artifact JSON file."""
    p = Path(plan_path).resolve()
    if not p.exists():
        raise ConfpubError(
            ERR_IO_FILE_NOT_FOUND,
            f"Plan file not found: {plan_path}",
            retryable=False,
            suggested_action="fix_input",
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return PlanArtifact(**data)
    except ConfpubError:
        raise
    except Exception as exc:
        raise ConfpubError(
            ERR_VALIDATION_MANIFEST,
            f"Invalid plan artifact: {exc}",
        ) from exc


def validate_plan(plan_path: str) -> dict[str, Any]:
    """Validate a plan artifact against current state.

    Returns the envelope result with valid flag and per-page checks.
    """
    plan = _load_plan(plan_path)
    plan_dir = Path(plan_path).parent

    config = load_config()
    client = ConfluenceClient(config)

    checks: list[dict[str, Any]] = []
    all_valid = True

    for page in plan.pages:
        check: dict[str, Any] = {
            "page_id": page.id,
            "title": page.title,
            "passed": True,
        }

        # Check source file exists
        source = plan_dir / page.source_file
        if not source.exists():
            check["passed"] = False
            check["issue"] = "ERR_IO_FILE_NOT_FOUND"
            check["detail"] = f"Source file missing: {page.source_file}"
            all_valid = False
            checks.append(check)
            continue

        # Re-fingerprint Confluence page (only for update/noop operations)
        if page.confluence_page_id and page.current_fingerprint:
            current_fp = client.fingerprint_page(page.confluence_page_id)
            if current_fp and current_fp != page.current_fingerprint:
                check["passed"] = False
                check["issue"] = "ERR_CONFLICT_FINGERPRINT"
                check["detail"] = (
                    "Page modified externally since plan was created — "
                    "re-run plan.create"
                )
                all_valid = False

        checks.append(check)

    return {
        "valid": all_valid,
        "checks": checks,
    }
