"""page.publish — single-file shortcut that runs the full workflow.

Internally: read file → convert → plan (in-memory) → apply → verify.
Returns structured change records.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from confpub.assets import discover_assets, rewrite_image_urls, upload_assets
from confpub.config import load_config
from confpub.confluence import ConfluenceClient, build_page_url
from confpub.converter import convert_markdown, fingerprint_content
from confpub.errors import (
    ERR_IO_FILE_NOT_FOUND,
    ERR_VALIDATION_REQUIRED,
    ERR_VALIDATION_SPACE_MISMATCH,
    ConfpubError,
)
from confpub.lockfile import Lockfile, load_lockfile, save_lockfile, update_lockfile


def derive_title(file: str, title: str | None = None, *, title_from_h1: bool = False) -> str:
    """Derive page title from explicit title, H1 heading, or filename.

    Precedence: explicit --title > --title-from-h1 > filename inference.
    """
    if title:
        return title
    if title_from_h1:
        from confpub.converter import extract_h1_title
        md_text = Path(file).read_text(encoding="utf-8")
        h1 = extract_h1_title(md_text)
        if h1:
            return h1
    return Path(file).stem.replace("-", " ").replace("_", " ").title()


def publish_page(
    file: str,
    space: str,
    parent: str,
    title: str | None = None,
    page_id: str | None = None,
    dry_run: bool = False,
    backup: bool = False,
    progress_callback: Any = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Publish a single Markdown file to Confluence.

    This is sugar that runs: read → convert → check existing → create/update.
    """
    source_path = Path(file)
    if not source_path.exists():
        raise ConfpubError(
            ERR_IO_FILE_NOT_FOUND,
            f"Source file not found: {file}",
            details={"file": file},
            retryable=False,
            suggested_action="fix_input",
        )

    # Derive title from filename if not provided
    page_title = derive_title(file, title)

    # Read and convert
    md_text = source_path.read_text(encoding="utf-8")
    storage = convert_markdown(md_text)
    local_fingerprint = fingerprint_content(storage)

    # Build client
    config = load_config()
    client = ConfluenceClient(config)

    # Load lockfile (from file's directory)
    lockfile_path = source_path.parent / "confpub.lock"
    lockfile = load_lockfile(lockfile_path) or Lockfile()

    # Check if page exists
    existing_page_id = None
    current_version = None

    if page_id:
        # Direct page ID provided — skip lockfile/title lookup
        existing_page_id = page_id
        page_data = client.get_page_by_id(existing_page_id)
        if page_data:
            version = page_data.get("version", {})
            current_version = version.get("number") if isinstance(version, dict) else version
    elif page_title in lockfile.pages:
        existing_page_id = lockfile.pages[page_title].page_id
        page_data = client.get_page_by_id(existing_page_id)
        if page_data:
            page_space = page_data.get("space", {}).get("key")
            if page_space and page_space != space:
                raise ConfpubError(
                    ERR_VALIDATION_SPACE_MISMATCH,
                    f"Page '{page_title}' exists in space '{page_space}', not '{space}'",
                    details={"expected_space": space, "actual_space": page_space, "page_id": existing_page_id},
                )
            version = page_data.get("version", {})
            current_version = version.get("number") if isinstance(version, dict) else version
    else:
        existing = client.get_page(space, page_title)
        if existing:
            existing_page_id = str(existing["id"])
            version = existing.get("version", {})
            current_version = version.get("number") if isinstance(version, dict) else version

    # Discover assets
    assets = discover_assets(md_text, source_path.parent)

    # Determine operation
    operation = "update" if existing_page_id else "create"

    # Detect noop — skip update when content is unchanged
    if operation == "update":
        # Check lockfile fingerprint first (avoids Confluence normalization mismatch)
        if page_title in lockfile.pages:
            entry = lockfile.pages[page_title]
            if entry.content_fingerprint and entry.content_fingerprint == local_fingerprint:
                operation = "noop"
        # Fallback: compare against remote fingerprint
        if operation == "update":
            remote_fingerprint = client.fingerprint_page(existing_page_id)
            if remote_fingerprint and remote_fingerprint == local_fingerprint:
                operation = "noop"

    if dry_run:
        change: dict[str, Any] = {
            "type": f"page.{operation}",
            "title": page_title,
            "before": {"version": current_version} if current_version else None,
            "after": {"title": page_title, "parent": parent},
        }
        if assets:
            change["attachments_to_upload"] = [a.source_path for a in assets]
        if labels:
            change["labels_to_apply"] = labels

        warnings: list[str] = []
        parent_page = client.get_page(space, parent)
        if not parent_page:
            warnings.append(f"Parent page '{parent}' not found in space '{space}' — publish will fail")

        result_dict: dict[str, Any] = {
            "dry_run": True,
            "changes": [change],
            "summary": {operation: 1, "attachments_upload": len(assets)},
        }
        if warnings:
            result_dict["warnings"] = warnings
        return result_dict

    # Real publish
    if operation == "noop":
        noop_change: dict[str, Any] = {
            "type": "page.noop",
            "title": page_title,
            "confluence_page_id": existing_page_id,
            "before": {"version": current_version} if current_version else None,
        }
        # Labels may still need applying even when content is unchanged
        if labels and existing_page_id:
            client.set_labels(existing_page_id, labels)
            noop_change["labels_added"] = labels
        return {
            "dry_run": False,
            "changes": [noop_change],
            "summary": {"noop": 1},
        }

    backup_file_path: str | None = None
    if operation == "create":
        # Find parent page
        parent_page = client.get_page(space, parent)
        parent_id = str(parent_page["id"]) if parent_page else None

        result = client.create_page(space, page_title, storage, parent_id=parent_id)
        page_id = str(result.get("id", ""))
        new_version = result.get("version", {})
        if isinstance(new_version, dict):
            new_version = new_version.get("number", 1)
    else:
        # Backup if requested
        if backup and existing_page_id:
            existing_data = client.get_page_by_id(existing_page_id)
            body = existing_data.get("body", {}).get("storage", {}).get("value", "")
            backup_file = source_path.parent / f".confpub-backup-{existing_page_id}.html"
            backup_file.write_text(body, encoding="utf-8")
            backup_file_path = str(backup_file)

        result = client.update_page(existing_page_id, page_title, storage)
        page_id = existing_page_id
        new_version = result.get("version", {})
        if isinstance(new_version, dict):
            new_version = new_version.get("number", (current_version or 0) + 1)

    # Upload assets
    uploaded_attachments = []
    if assets:
        uploaded = upload_assets(client, page_id, assets)
        storage = rewrite_image_urls(storage, uploaded)
        # Re-update with rewritten URLs
        client.update_page(page_id, page_title, storage)
        uploaded_attachments = [a.source_path for a in assets]

    # Apply labels
    if labels:
        client.set_labels(page_id, labels)

    # Update lockfile
    new_version_int = new_version if isinstance(new_version, int) else 1
    update_lockfile(lockfile, page_title, page_id, new_version_int, content_fingerprint=local_fingerprint)
    save_lockfile(lockfile_path, lockfile)

    change = {
        "type": f"page.{operation}",
        "title": page_title,
        "confluence_page_id": page_id,
        "before": {"version": current_version} if current_version else None,
        "after": {
            "version": new_version,
            "page_id": page_id,
            "webui": build_page_url(
                config.base_url or "", config.is_cloud,
                space, page_id, page_title,
            ),
        },
    }
    if backup_file_path:
        change["backup_path"] = backup_file_path
    if uploaded_attachments:
        change["attachments_added"] = uploaded_attachments
    if labels:
        change["labels_added"] = labels

    return {
        "dry_run": False,
        "changes": [change],
        "summary": {operation: 1, "attachments_upload": len(uploaded_attachments)},
    }
