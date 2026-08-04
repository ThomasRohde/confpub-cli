"""plan.apply — execute a plan by writing to Confluence.

Supports --dry-run for previewing changes without writes.
Updates the lockfile after each successful page write.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from confpub.assets import AssetRef, discover_assets, merge_assets, rewrite_html_macro_urls, rewrite_image_urls, upload_assets
from confpub.config import load_config, resolve_html_macro_settings
from confpub.confluence import ConfluenceClient, build_page_url
from confpub.converter import convert_markdown, detect_unconverted_page_title_links, fingerprint_content
from confpub.errors import ERR_CONFLICT_FINGERPRINT, ERR_IO_FILE_NOT_FOUND, ConfpubError
from confpub.html_macro_detection import html_macro_fallback_warnings
from confpub.lockfile import Lockfile, load_lockfile, save_lockfile, update_lockfile
from confpub.manifest import PlanArtifact
from confpub.validator import _load_plan


def _planned_assets(page: Any, source_path: Path) -> list[AssetRef]:
    """Resolve planned attachments relative to the page source directory."""
    assets: list[AssetRef] = []
    seen: set[str] = set()
    base_dir = source_path.parent
    for attachment in page.attachments:
        if attachment.operation == "noop":
            continue
        raw_path = Path(attachment.file)
        resolved = raw_path if raw_path.is_absolute() else base_dir / raw_path
        resolved = resolved.resolve()
        key = str(resolved)
        if key in seen:
            continue
        if not resolved.is_file():
            raise ConfpubError(
                ERR_IO_FILE_NOT_FOUND,
                f"Planned attachment missing: {attachment.file}",
                details={"file": attachment.file, "page": page.title},
                retryable=False,
                suggested_action="fix_input",
            )
        seen.add(key)
        assets.append(AssetRef(
            source_path=attachment.file,
            resolved_path=str(resolved),
            filename=resolved.name,
        ))
    return assets


def apply_plan(
    plan_path: str,
    dry_run: bool = False,
    backup: bool = False,
    skip_fingerprint_check: bool = False,
    cascade: bool = False,
    html_macro_name: str | None = None,
    html_macro_format: str | None = None,
    html_macro_forge_extension_key: str | None = None,
    html_macro_forge_extension_id: str | None = None,
    html_macro_forge_environment: str | None = None,
    html_macro_forge_cloud_id: str | None = None,
    html_macro_forge_context_ids: str | None = None,
    html_macro_forge_account_id: str | None = None,
) -> dict[str, Any]:
    """Apply a plan to Confluence.

    Returns the envelope result with change records and summary.
    """
    plan = _load_plan(plan_path)
    plan_dir = Path(plan_path).parent

    config = load_config()
    client = ConfluenceClient(config)
    from confpub.macro_profiles import load_macro_profiles
    macro_profiles = load_macro_profiles(config.base_url)

    # Resolve HTML macro settings: explicit > config/env > platform default.
    html_macro_settings = resolve_html_macro_settings(
        config,
        name_override=html_macro_name,
        format_override=html_macro_format,
        forge_extension_key_override=html_macro_forge_extension_key,
        forge_extension_id_override=html_macro_forge_extension_id,
        forge_environment_override=html_macro_forge_environment,
        forge_cloud_id_override=html_macro_forge_cloud_id,
        forge_context_ids_override=html_macro_forge_context_ids,
        forge_account_id_override=html_macro_forge_account_id,
    )

    # Load or create lockfile
    lockfile_path = plan_dir / "confpub.lock"
    lockfile = load_lockfile(lockfile_path) or Lockfile()

    changes: list[dict[str, Any]] = []
    counts = {"create": 0, "update": 0, "attachments_upload": 0, "labels_applied": 0}
    warnings: list[str] = []

    # Resolve parent page IDs by title
    parent_ids: dict[str, str] = {}  # title → page_id

    # Try to find the root parent
    root_parent = client.get_page(plan.space, plan.parent)
    if root_parent:
        parent_ids[plan.parent] = str(root_parent["id"])

    for page in plan.pages:
        if page.operation == "noop" and not page.attachments:
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
        from confpub.macro_profiles import prepare_macros
        prepared_macros = prepare_macros(md_text, source_path.parent, macro_profiles)
        for warning in prepared_macros.warnings:
            warnings.append(f"{page.source_file}: {warning}")
        for warning in detect_unconverted_page_title_links(md_text):
            warnings.append(f"{page.source_file}: {warning}")
        for warning in html_macro_fallback_warnings(
            md_text,
            is_cloud=config.is_cloud,
            settings=html_macro_settings,
        ):
            warnings.append(f"{page.source_file}: {warning}")
        storage = convert_markdown(
            md_text,
            html_macro_name=html_macro_settings.name,
            html_macro_format=html_macro_settings.format,
            html_macro_forge_extension_key=html_macro_settings.forge_extension_key,
            html_macro_forge_extension_id=html_macro_settings.forge_extension_id,
            html_macro_forge_environment=html_macro_settings.forge_environment,
            html_macro_forge_cloud_id=html_macro_settings.forge_cloud_id,
            html_macro_forge_context_ids=html_macro_settings.forge_context_ids,
            html_macro_forge_account_id=html_macro_settings.forge_account_id,
            macro_profiles=macro_profiles,
            macro_sources=prepared_macros.sources,
        )
        local_fingerprint = fingerprint_content(storage)

        # Discover and process assets
        assets = merge_assets(
            _planned_assets(page, source_path) if page.attachments else discover_assets(md_text, source_path.parent, None),
            prepared_macros.assets,
        )

        # Get parent ID
        parent_title = page.parent_title or plan.parent
        parent_id = parent_ids.get(parent_title)

        # Re-evaluate operation during dry-run based on current state
        effective_operation = page.operation
        effective_page_id = page.confluence_page_id
        if dry_run and page.operation == "create":
            if page.title in lockfile.pages:
                effective_page_id = lockfile.pages[page.title].page_id
                remote_fp = client.fingerprint_page(effective_page_id)
                if remote_fp is not None:
                    effective_operation = "noop" if remote_fp == local_fingerprint else "update"
            else:
                existing = client.get_page(plan.space, page.title)
                if existing:
                    effective_page_id = str(existing["id"])
                    remote_fp = client.fingerprint_page(effective_page_id)
                    effective_operation = "noop" if remote_fp == local_fingerprint else "update"

        if effective_operation == "noop":
            noop_change: dict[str, Any] = {
                "type": "page.noop",
                "title": page.title,
                "confluence_page_id": effective_page_id,
            }
            if assets:
                if not dry_run and effective_page_id:
                    upload_assets(client, effective_page_id, assets)
                    noop_change["attachments_added"] = [asset.source_path for asset in assets]
                    counts["attachments_upload"] += len(assets)
                else:
                    noop_change["attachments_to_upload"] = [asset.source_path for asset in assets]
            changes.append(noop_change)
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
                update_lockfile(lockfile, page.title, new_id, new_version if isinstance(new_version, int) else 1, content_fingerprint=local_fingerprint)
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
                    content_fingerprint=local_fingerprint,
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

    result = {
        "dry_run": dry_run,
        "changes": changes,
        "summary": counts,
        "lockfile_updated": not dry_run and len(changes) > 0,
        "lockfile_path": str(lockfile_path) if not dry_run else None,
    }
    if warnings:
        result["warnings"] = warnings
    return result
