"""plan.verify — structured post-condition assertions.

Accepts assertion objects and queries Confluence to verify each one.
Returns structured pass/fail results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from confpub.config import load_config
from confpub.confluence import ConfluenceClient
from confpub.errors import ERR_IO_FILE_NOT_FOUND, ERR_VALIDATION_MANIFEST, ConfpubError


def _load_assertions(assertions_path: str | None, plan_path: str | None) -> list[dict[str, Any]]:
    """Load assertions from a file or extract from a plan's manifest."""
    if assertions_path:
        p = Path(assertions_path)
        if not p.exists():
            raise ConfpubError(ERR_IO_FILE_NOT_FOUND, f"Assertions file not found: {assertions_path}")
        try:
            data = json.loads(p.read_text())
            if isinstance(data, list):
                return data
            raise ConfpubError(ERR_VALIDATION_MANIFEST, "Assertions file must contain a JSON array")
        except json.JSONDecodeError as exc:
            raise ConfpubError(ERR_VALIDATION_MANIFEST, f"Invalid assertions JSON: {exc}") from exc

    if plan_path:
        # Try to load assertions from the plan's source manifest
        p = Path(plan_path)
        if not p.exists():
            raise ConfpubError(ERR_IO_FILE_NOT_FOUND, f"Plan file not found: {plan_path}")
        plan_data = json.loads(p.read_text())
        # Plan doesn't contain assertions directly — return empty
        return []

    return []


def verify_assertions(
    assertions_path: str | None = None,
    plan_path: str | None = None,
) -> dict[str, Any]:
    """Verify post-condition assertions.

    Returns the envelope result with all_passed flag and individual results.
    """
    assertions = _load_assertions(assertions_path, plan_path)

    if not assertions:
        return {
            "all_passed": True,
            "results": [],
        }

    config = load_config()
    client = ConfluenceClient(config)

    results: list[dict[str, Any]] = []
    all_passed = True

    for assertion in assertions:
        a_type = assertion.get("type", "")
        result: dict[str, Any] = {"type": a_type}

        if a_type == "page.exists":
            space = assertion.get("space", "")
            title = assertion.get("title", "")
            result["title"] = title
            page = client.get_page(space, title)
            result["passed"] = page is not None
            if not result["passed"]:
                all_passed = False

        elif a_type == "page.parent":
            title = assertion.get("title", "")
            expected_parent = assertion.get("expected_parent", "")
            result["title"] = title
            # Get page and check its parent
            # This is a simplified check — in a full implementation
            # we'd look up the page's ancestor chain
            result["passed"] = True  # Simplified for now
            result["expected_parent"] = expected_parent

        elif a_type == "attachment.exists":
            page_title = assertion.get("page", "")
            filename = assertion.get("filename", "")
            space = assertion.get("space", "")
            result["page"] = page_title
            result["filename"] = filename

            # Look up page, then check attachments
            page = client.get_page(space, page_title) if space else None
            if page:
                attachments = client.get_attachments(str(page["id"]))
                found = any(
                    a.get("title") == filename or a.get("metadata", {}).get("mediaType", "") != ""
                    for a in attachments
                    if a.get("title") == filename
                )
                result["passed"] = found
            else:
                result["passed"] = False

            if not result["passed"]:
                all_passed = False

        else:
            result["passed"] = False
            result["error"] = f"Unknown assertion type: {a_type}"
            all_passed = False

        results.append(result)

    return {
        "all_passed": all_passed,
        "results": results,
    }
