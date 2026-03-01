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
            raise ConfpubError(
                ERR_IO_FILE_NOT_FOUND,
                f"Assertions file not found: {assertions_path}",
                retryable=False,
                suggested_action="fix_input",
            )
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            raise ConfpubError(ERR_VALIDATION_MANIFEST, "Assertions file must contain a JSON array")
        except json.JSONDecodeError as exc:
            raise ConfpubError(ERR_VALIDATION_MANIFEST, f"Invalid assertions JSON: {exc}") from exc

    if plan_path:
        p = Path(plan_path)
        if not p.exists():
            raise ConfpubError(
                ERR_IO_FILE_NOT_FOUND,
                f"Plan file not found: {plan_path}",
                retryable=False,
                suggested_action="fix_input",
            )

        # Check for confpub.yaml alongside the plan file
        manifest_path = p.parent / "confpub.yaml"
        if manifest_path.exists():
            try:
                import yaml
                manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                if isinstance(manifest_data, dict) and manifest_data.get("assertions"):
                    raw = manifest_data["assertions"]
                    if isinstance(raw, list):
                        return raw
            except Exception:
                pass

        # Auto-generate page.exists assertions from the plan
        plan_data = json.loads(p.read_text(encoding="utf-8"))
        auto: list[dict[str, Any]] = []
        space = plan_data.get("space", "")
        for page in plan_data.get("pages", []):
            op = page.get("operation", "")
            if op in ("create", "update"):
                auto.append({
                    "type": "page.exists",
                    "space": space,
                    "title": page.get("title", ""),
                })
        return auto

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
            "note": "No assertions defined; nothing was verified.",
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
            space = assertion.get("space", "")
            title = assertion.get("title", "")
            expected_parent = assertion.get("expected_parent", "")
            result["title"] = title
            result["expected_parent"] = expected_parent
            page = client.get_page(space, title) if space else None
            if page:
                ancestors = client.get_page_ancestors(str(page["id"]))
                actual_parent = ancestors[-1].get("title", "") if ancestors else ""
                result["actual_parent"] = actual_parent
                result["passed"] = actual_parent == expected_parent
            else:
                result["passed"] = False
                result["error"] = f"Page '{title}' not found"
            if not result["passed"]:
                all_passed = False

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
