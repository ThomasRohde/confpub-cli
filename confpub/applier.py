"""plan.apply — execute a plan by writing to Confluence.

Supports --dry-run for previewing changes without writes.
Updates the lockfile after each successful page write.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from confpub.assets import AssetRef, discover_assets, rewrite_html_macro_urls, rewrite_image_urls, upload_assets
from confpub.config import load_config, resolve_html_macro_name
from confpub.confluence import ConfluenceClient, build_page_url
from confpub.converter import convert_markdown, fingerprint_content
from confpub.errors import ERR_CONFLICT_FINGERPRINT, ERR_IO_FILE_NOT_FOUND, ConfpubError
from confpub.lockfile import Lockfile, load_lockfile, save_lockfile, update_lockfile
from confpub.manifest import PlanArtifact
from confpub.validator import _load_plan


def apply_plan(
    plan_path: str,
    dry_run: bool = False,
    backup: bool = False,
    skip_fingerprint_check: bool = False,
    cascade: bool = False,
    html_macro_name: str | None = None,
) -> dict[str, Any]:
    """Apply a plan to Confluence.

    Returns the envelope result with change records and summary.
    """
    plan = _load_plan(plan_path)
    plan_dir = Path(plan_path).parent

    config = load_config()
    client = ConfluenceClient(config)

    # Resolve html_macro_name: explicit > config/env > platform default
    effective_html_macro = resolve_html_macro_name(config, html_macro_name)

    # Load or create lockfile
    lockfile_path = plan_dir / "confpub.lock"
    lockfile = load_lockfile(lockfile_path) or Lockfile()

    changes: list[dict[str, Any]] = []
    counts = {"create": 0, "update": 0, "attachments_upload": 0, "labels_applied": 0}

    # Resolve parent page IDs by title
    parent_ids: dict[str, str] = {}  # title → page_id

    # Try to find the root parent
    root_parent = client.get_page(plan.space, plan.parent)
    if root_parent:
        parent_ids[plan.parent] = str(root_parent["id"])

    for page in plan.pages:
        if page.operation == "noop":
            continue

        source_path = plan_dir / page.source_file
        if not source_path.exists():
            raise ConfpubError(
                ERR_IO_FILE_NOT_FOUND,
                f"Source file missing: {page.source_file}",
                retryable=False,
                suggested_action="fix_input",
            )

        # Fingerprint check (unless skipped)
        if (
            not skip_fingerprint_check
            and page.confluence_page_id
            and page.current_fingerprint
        ):
            current_fp = client.fingerprint_page(page.confluence_page_id)
            if current_fp and current_fp != page.current_fingerprint:
                raise ConfpubError(
                    ERR_CONFLICT_FINGERPRINT,
                    f"Page '{page.title}' was modified externally since plan was created",
                    details={
                        "page_id": page.confluence_page_id,
                        "plan_fingerprint": page.current_fingerprint,
                        "current_fingerprint": current_fp,
                    },
                )

        # Read and convert
        md_text = source_path.read_text(encoding="utf-8")
        storage = convert_markdown(md_text, html_macro_name=effective_html_macro)

        # Discover and process assets
        assets = discover_assets(md_text, source_path.parent, None)

        # Get parent ID
        parent_title = page.parent_title or plan.parent
        parent_id = parent_ids.get(parent_title)

        # Re-evaluate operation during dry-run based on current state
        effective_operation = page.operation
        effective_page_id = page.confluence_page_id
        if dry_run and page.operation == "create":
            local_fp = fingerprint_content(storage)
            if page.title in lockfile.pages:
                effective_page_id = lockfile.pages[page.title].page_id
                remote_fp = client.fingerprint_page(effective_page_id)
                if remote_fp is not None:
                    effective_operation = "noop" if remote_fp == local_fp else "update"
            else:
                existing = client.get_page(plan.space, page.title)
                if existing:
                    effective_page_id = str(existing["id"])
                    remote_fp = client.fingerprint_page(effective_page_id)
                    effective_operation = "noop" if remote_fp == local_fp else "update"

        if effective_operation == "noop":
            changes.append({
                "type": "page.noop",
                "title": page.title,
                "confluence_page_id": effective_page_id,
            })
            continue

        if effective_operation == "create":
            change: dict[str, Any] = {
                "type": "page.create",
                "title": page.title,
                "before": None,
                "after": {"title": page.title, "parent": parent_title},
            }

            if not dry_run:
                result = client.create_page(
                    plan.space, page.title, storage, parent_id=parent_id,
                )
                new_id = str(result.get("id", ""))
                new_version = result.get("version", {})
                if isinstance(new_version, dict):
                    new_version = new_version.get("number", 1)
                change["after"]["page_id"] = new_id
                change["after"]["version"] = new_version
                change["after"]["webui"] = build_page_url(
                    config.base_url or "", config.is_cloud,
                    plan.space, new_id, page.title,
                )

                # Upload attachments
                if assets:
                    uploaded = upload_assets(client, new_id, assets)
                    storage = rewrite_image_urls(storage, uploaded)
                    storage = rewrite_html_macro_urls(
                        storage, uploaded,
                        base_url=config.base_url or "",
                        is_cloud=config.is_cloud,
                        page_id=new_id,
                    )
                    # Re-update page with rewritten URLs
                    if uploaded:
                        client.update_page(new_id, page.title, storage)
                    change["attachments_added"] = [a.source_path for a in assets]
                    counts["attachments_upload"] += len(assets)

                # Apply labels
                if page.labels:
                    client.set_labels(new_id, page.labels)
                    change["labels_added"] = page.labels
                    counts["labels_applied"] += len(page.labels)

                # Update lockfile and parent tracking
                update_lockfile(lockfile, page.title, new_id, new_version if isinstance(new_version, int) else 1, content_fingerprint=fingerprint_content(storage))
                parent_ids[page.title] = new_id
            else:
                # Dry-run: report labels
                if page.labels:
                    change["labels_to_apply"] = page.labels

            counts["create"] += 1
            changes.append(change)

        elif effective_operation == "update":
            before_version = None
            backup_path = None
            if not dry_run and page.confluence_page_id:
                # Backup if requested
                if backup:
                    existing = client.get_page_by_id(page.confluence_page_id)
                    # Store backup in plan directory
                    backup_file = plan_dir / f".confpub-backup-{page.confluence_page_id}.html"
                    body = existing.get("body", {}).get("storage", {}).get("value", "")
                    backup_file.write_text(body, encoding="utf-8")
                    backup_path = str(backup_file)
                else:
                    backup_path = None

                existing = client.get_page_by_id(page.confluence_page_id)
                before_version = existing.get("version", {})
                if isinstance(before_version, dict):
                    before_version = before_version.get("number")

            change = {
                "type": "page.update",
                "title": page.title,
                "confluence_page_id": effective_page_id or page.confluence_page_id,
                "before": {"version": before_version} if before_version else None,
                "after": {},
            }
            if not dry_run and backup_path:
                change["backup_path"] = backup_path

            if not dry_run and page.confluence_page_id:
                result = client.update_page(page.confluence_page_id, page.title, storage)
                new_version = result.get("version", {})
                if isinstance(new_version, dict):
                    new_version = new_version.get("number", (before_version or 0) + 1)
                change["after"]["version"] = new_version
                change["after"]["webui"] = build_page_url(
                    config.base_url or "", config.is_cloud,
                    plan.space, page.confluence_page_id, page.title,
                )

                # Upload attachments
                if assets:
                    uploaded = upload_assets(client, page.confluence_page_id, assets)
                    storage = rewrite_image_urls(storage, uploaded)
                    storage = rewrite_html_macro_urls(
                        storage, uploaded,
                        base_url=config.base_url or "",
                        is_cloud=config.is_cloud,
                        page_id=page.confluence_page_id,
                    )
                    client.update_page(page.confluence_page_id, page.title, storage)
                    change["attachments_added"] = [a.source_path for a in assets]
                    counts["attachments_upload"] += len(assets)

                # Apply labels
                if page.labels:
                    client.set_labels(page.confluence_page_id, page.labels)
                    change["labels_added"] = page.labels
                    counts["labels_applied"] += len(page.labels)

                update_lockfile(
                    lockfile, page.title, page.confluence_page_id,
                    new_version if isinstance(new_version, int) else 1,
                    content_fingerprint=fingerprint_content(storage),
                )
                parent_ids[page.title] = page.confluence_page_id
            else:
                # Dry-run: report labels
                if page.labels:
                    change["labels_to_apply"] = page.labels

            counts["update"] += 1
            changes.append(change)

    # Save lockfile (only on real apply)
    if not dry_run:
        save_lockfile(lockfile_path, lockfile)

    return {
        "dry_run": dry_run,
        "changes": changes,
        "summary": counts,
        "lockfile_updated": not dry_run and len(changes) > 0,
        "lockfile_path": str(lockfile_path) if not dry_run else None,
    }
