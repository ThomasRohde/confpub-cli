"""plan.create — fingerprinting, diff, plan artifact generation.

Reads a manifest, resolves the page tree, fingerprints existing pages,
and produces a plan artifact (JSON file) with no Confluence writes.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from confpub.assets import discover_assets, merge_assets
from confpub.config import load_config, resolve_html_macro_settings
from confpub.confluence import ConfluenceClient
from confpub.converter import convert_markdown, detect_unconverted_page_title_links, fingerprint_content
from confpub.errors import ERR_IO_FILE_NOT_FOUND, ERR_VALIDATION_REQUIRED, ConfpubError
from confpub.html_macro_detection import html_macro_fallback_warnings
from confpub.lockfile import load_lockfile
from confpub.manifest import (
    FlatPage,
    PlanArtifact,
    PlanAttachment,
    PlanPage,
    PlanSummary,
    load_manifest,
    resolve_page_tree,
)


def create_plan(
    manifest_path: str,
    output_path: str | None = None,
    space_override: str | None = None,
    parent_override: str | None = None,
    html_macro_name: str | None = None,
    html_macro_format: str | None = None,
    html_macro_forge_extension_key: str | None = None,
    html_macro_forge_extension_id: str | None = None,
    html_macro_forge_environment: str | None = None,
    html_macro_forge_cloud_id: str | None = None,
    html_macro_forge_context_ids: str | None = None,
    html_macro_forge_account_id: str | None = None,
) -> dict[str, Any]:
    """Create a plan artifact from a manifest.

    Returns the envelope result dict with plan_file and summary.
    """
    manifest = load_manifest(manifest_path)
    space = space_override or manifest.space
    parent = parent_override or manifest.parent
    manifest_dir = Path(manifest_path).parent

    # Load lockfile if it exists
    lockfile_path = manifest_dir / "confpub.lock"
    lockfile = load_lockfile(lockfile_path)

    # Build Confluence client
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

    # Resolve page tree
    flat_pages = resolve_page_tree(manifest)

    # Build plan pages
    plan_pages: list[PlanPage] = []
    counts = {"create": 0, "update": 0, "noop": 0, "attachments_to_upload": 0, "labels_to_apply": 0}
    warnings: list[str] = []

    for i, fp in enumerate(flat_pages):
        plan_id = f"plan_{i + 1}"
        source_path = manifest_dir / fp.file

        # Check source file exists
        if not source_path.exists():
            raise ConfpubError(
                ERR_IO_FILE_NOT_FOUND,
                f"Source file not found: {fp.file}",
                details={"file": fp.file},
                retryable=False,
                suggested_action="fix_input",
            )

        # Read and convert markdown
        md_text = source_path.read_text(encoding="utf-8")
        from confpub.macro_profiles import prepare_macros
        prepared_macros = prepare_macros(md_text, source_path.parent, macro_profiles)
        for warning in prepared_macros.warnings:
            warnings.append(f"{fp.file}: {warning}")
        for warning in detect_unconverted_page_title_links(md_text):
            warnings.append(f"{fp.file}: {warning}")
        for warning in html_macro_fallback_warnings(
            md_text,
            is_cloud=config.is_cloud,
            settings=html_macro_settings,
        ):
            warnings.append(f"{fp.file}: {warning}")
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

        # Look up existing page
        confluence_page_id = None
        current_fingerprint = None
        operation = "create"

        # Check lockfile first
        if lockfile and fp.title in lockfile.pages:
            entry = lockfile.pages[fp.title]
            page_id = entry.page_id
            if entry.content_fingerprint and entry.content_fingerprint == local_fingerprint:
                confluence_page_id = page_id
                current_fingerprint = entry.content_fingerprint
                operation = "noop"
            else:
                remote_fp = client.fingerprint_page(page_id)
                if remote_fp is not None:
                    confluence_page_id = page_id
                    current_fingerprint = remote_fp
                    if remote_fp == local_fingerprint:
                        operation = "noop"
                    else:
                        operation = "update"

        # If not in lockfile, try title search
        if confluence_page_id is None:
            existing = client.get_page(space, fp.title)
            if existing:
                page_id = str(existing["id"])
                remote_fp = client.fingerprint_page(page_id)
                confluence_page_id = page_id
                current_fingerprint = remote_fp
                if remote_fp == local_fingerprint:
                    operation = "noop"
                else:
                    operation = "update"

        # Discover attachments
        assets = merge_assets(
            discover_assets(md_text, source_path.parent, fp.assets or None),
            prepared_macros.assets,
        )
        plan_attachments = [
            PlanAttachment(file=a.source_path, operation="upload")
            for a in assets
        ]

        counts[operation] += 1
        counts["attachments_to_upload"] += len(plan_attachments)
        if fp.labels:
            counts["labels_to_apply"] += len(fp.labels)

        plan_pages.append(PlanPage(
            id=plan_id,
            title=fp.title,
            source_file=fp.file,
            confluence_page_id=confluence_page_id,
            current_fingerprint=current_fingerprint,
            operation=operation,
            parent_title=fp.parent_title,
            attachments=plan_attachments,
            labels=fp.labels,
        ))

    # Build plan artifact
    plan = PlanArtifact(
        created_at=datetime.now(timezone.utc).isoformat(),
        space=space,
        parent=parent,
        pages=plan_pages,
        summary=PlanSummary(**counts),
    )

    # Write plan to disk
    if output_path is None:
        output_path = str(manifest_dir / "confpub-plan.json")

    plan_json = json.dumps(plan.model_dump(mode="json"), indent=2, allow_nan=False)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write
    fd, tmp = tempfile.mkstemp(dir=str(out_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(plan_json)
        os.replace(tmp, str(out_path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    result = {
        "plan_file": str(out_path),
        "summary": counts,
    }
    if warnings:
        result["warnings"] = warnings
    return result
