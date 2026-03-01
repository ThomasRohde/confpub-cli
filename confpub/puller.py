"""Pull workflow — download Confluence pages to local Markdown files.

Orchestrates fetching pages, converting to Markdown, downloading attachments,
and generating manifest/lockfile artifacts.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from confpub.confluence import ConfluenceClient, build_client
from confpub.output import emit_progress
from confpub.errors import (
    ERR_CONFLICT_FILE_EXISTS,
    ERR_VALIDATION_NOT_FOUND,
    ERR_VALIDATION_REQUIRED,
    ConfpubError,
)
from confpub.lockfile import Lockfile, load_lockfile, save_lockfile, update_lockfile
from confpub.manifest import generate_manifest_yaml
from confpub.reverse_converter import convert_storage_to_markdown


def _slugify(title: str) -> str:
    """Convert a page title to a filename-safe slug.

    "My Cool Page" → "my-cool-page"
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _collect_tree(
    client: ConfluenceClient,
    page_id: str,
    recursive: bool,
) -> list[dict[str, Any]]:
    """Collect pages to pull. Returns flat list with parent_id info."""
    pages: list[dict[str, Any]] = []

    def _walk(pid: str, parent_id: str | None) -> None:
        children = client.get_page_children_deep(pid)
        if children:
            emit_progress(0, 0, f"Found {len(children)} child page(s) under {pid}")
        for child in children:
            child_id = str(child["id"])
            pages.append({
                "page": child,
                "parent_id": pid,
            })
            if recursive:
                _walk(child_id, pid)

    # The root page itself
    root = client.get_page_by_id(page_id)
    if not root or not root.get("id"):
        raise ConfpubError(
            ERR_VALIDATION_NOT_FOUND,
            f"Page not found: {page_id}",
        )
    pages.append({"page": root, "parent_id": None})

    if recursive:
        _walk(page_id, None)

    return pages


def _compute_file_paths(
    pages: list[dict[str, Any]],
    output_dir: str,
    layout: str,
    root_page_id: str,
) -> dict[str, str]:
    """Compute output file paths for each page. Returns {page_id: file_path}."""
    paths: dict[str, str] = {}
    root_slug: str | None = None

    # Build parent lookup
    id_to_slug: dict[str, str] = {}
    id_to_parent: dict[str, str | None] = {}

    for entry in pages:
        page = entry["page"]
        pid = str(page["id"])
        slug = _slugify(page.get("title", pid))
        id_to_slug[pid] = slug
        id_to_parent[pid] = str(entry["parent_id"]) if entry["parent_id"] else None
        if pid == root_page_id:
            root_slug = slug

    for entry in pages:
        page = entry["page"]
        pid = str(page["id"])
        slug = id_to_slug[pid]

        if layout == "nested":
            # Build path from root
            chain: list[str] = []
            current = pid
            while current and current != root_page_id:
                chain.append(id_to_slug.get(current, current))
                current = id_to_parent.get(current)  # type: ignore[assignment]
            # Always include root as the outermost directory
            if root_slug:
                chain.append(root_slug)
            chain.reverse()
            rel_path = os.path.join(*chain, "index.md") if len(chain) > 0 else f"{slug}/index.md"
            paths[pid] = os.path.join(output_dir, rel_path)
        else:
            # Flat layout
            paths[pid] = os.path.join(output_dir, f"{slug}.md")

    return paths


def _check_conflicts(file_paths: dict[str, str], force: bool) -> None:
    """Raise ERR_CONFLICT_FILE_EXISTS if any output files already exist."""
    if force:
        return
    existing = [p for p in file_paths.values() if os.path.exists(p)]
    if existing:
        raise ConfpubError(
            ERR_CONFLICT_FILE_EXISTS,
            f"Output files already exist: {', '.join(existing[:5])}"
            + (f" (and {len(existing) - 5} more)" if len(existing) > 5 else ""),
            details={"existing_files": existing, "hint": "Use --force to overwrite existing files"},
            suggested_action="retry_with_flag",
        )


def _posix_join(*parts: str) -> str:
    """Join path components with forward slashes (for use in Markdown refs)."""
    return "/".join(parts)


def _download_page_attachments(
    client: ConfluenceClient,
    page_id: str,
    slug: str,
    output_dir: str,
    layout: str,
    warnings: list[str],
) -> dict[str, str]:
    """Download attachments for a page. Returns {attachment_name: local_path}.

    Failed downloads are recorded in *warnings* but do not abort the pull.
    """
    attachment_map: dict[str, str] = {}
    attachments = client.get_attachments(page_id)

    if not attachments:
        return attachment_map

    if layout == "nested":
        assets_dir = os.path.join(output_dir, slug, "assets")
    else:
        assets_dir = os.path.join(output_dir, "assets", slug)

    for att in attachments:
        filename = att.get("title", "")
        if not filename:
            continue
        download_path = os.path.join(assets_dir, filename)
        success = client.download_attachment(page_id, filename, download_path)
        if success:
            # Use forward slashes so the path works in Markdown on every OS
            if layout == "nested":
                rel_path = _posix_join("assets", filename)
            else:
                rel_path = _posix_join("assets", slug, filename)
            attachment_map[filename] = rel_path
        else:
            warnings.append(f"Failed to download attachment '{filename}' from page {page_id}")

    return attachment_map


def _build_page_tree(
    pages: list[dict[str, Any]],
    file_paths: dict[str, str],
    root_page_id: str,
    output_dir: str = ".",
) -> list[dict[str, Any]]:
    """Build a hierarchical page tree for manifest generation."""
    id_to_entry: dict[str, dict[str, Any]] = {}
    children_map: dict[str | None, list[str]] = {}

    for entry in pages:
        page = entry["page"]
        pid = str(page["id"])
        parent_id = str(entry["parent_id"]) if entry["parent_id"] else None
        file_path = file_paths.get(pid, "")

        id_to_entry[pid] = {
            "title": page.get("title", ""),
            "file": os.path.relpath(file_path, output_dir) if file_path else "",
            "children": [],
        }
        children_map.setdefault(parent_id, []).append(pid)

    def _attach_children(parent_id: str) -> list[dict[str, Any]]:
        result = []
        for child_id in children_map.get(parent_id, []):
            entry = id_to_entry[child_id]
            entry["children"] = _attach_children(child_id)
            result.append(entry)
        return result

    root_entry = id_to_entry.get(root_page_id, {})
    root_entry["children"] = _attach_children(root_page_id)
    return [root_entry]


def pull_pages(
    *,
    space: str | None = None,
    title: str | None = None,
    page_id: str | None = None,
    output_dir: str = ".",
    recursive: bool = False,
    force: bool = False,
    layout: str = "flat",
    include_attachments: bool = True,
    generate_manifest: bool = False,
) -> dict[str, Any]:
    """Pull pages from Confluence to local Markdown files.

    Returns a result dict suitable for the envelope.
    """
    client = build_client()

    # Resolve target page
    if page_id:
        root_page = client.get_page_by_id(page_id)
    elif space and title:
        root_page = client.get_page(space, title)
    else:
        raise ConfpubError(
            ERR_VALIDATION_REQUIRED,
            "Either --page-id or both --space and --title are required",
        )

    if not root_page or not root_page.get("id"):
        raise ConfpubError(
            ERR_VALIDATION_NOT_FOUND,
            "Page not found",
            details={"space": space, "title": title, "page_id": page_id},
        )

    root_id = str(root_page["id"])
    root_space = root_page.get("space", {}).get("key", space or "")

    # Collect all pages to pull
    all_pages = _collect_tree(client, root_id, recursive)

    # Compute output file paths
    file_paths = _compute_file_paths(all_pages, output_dir, layout, root_id)

    # Check for conflicts
    _check_conflicts(file_paths, force)

    # Process each page
    files_result: list[dict[str, Any]] = []
    total_attachments = 0
    pull_warnings: list[str] = []

    for entry in all_pages:
        page = entry["page"]
        pid = str(page["id"])
        page_title = page.get("title", "")
        slug = _slugify(page_title)
        version = page.get("version", {})
        version_num = version.get("number", 1) if isinstance(version, dict) else 1

        # Download attachments
        attachment_map: dict[str, str] = {}
        attachments_downloaded = 0
        if include_attachments:
            attachment_map = _download_page_attachments(
                client, pid, slug, output_dir, layout, pull_warnings,
            )
            attachments_downloaded = len(attachment_map)
            total_attachments += attachments_downloaded

        # Convert storage format to markdown
        body_storage = page.get("body", {}).get("storage", {}).get("value", "")
        result = convert_storage_to_markdown(
            body_storage, attachment_map=attachment_map,
        )

        # Write markdown file
        out_path = file_paths[pid]
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        Path(out_path).write_text(result.markdown, encoding="utf-8")

        files_result.append({
            "page_id": pid,
            "title": page_title,
            "file": out_path,
            "version": version_num,
            "attachments_downloaded": attachments_downloaded,
        })

    # Generate manifest if requested or recursive with multiple pages
    manifest_file: str | None = None
    if generate_manifest:
        root_title = root_page.get("title", "")
        # Determine the actual parent of the root page
        ancestors = client.get_page_ancestors(root_id)
        manifest_parent = ancestors[-1].get("title", root_title) if ancestors else root_title
        page_tree = _build_page_tree(all_pages, file_paths, root_id, output_dir)
        manifest_yaml = generate_manifest_yaml(root_space, manifest_parent, page_tree)
        manifest_path = os.path.join(output_dir, "confpub.yaml")
        Path(manifest_path).write_text(manifest_yaml, encoding="utf-8")
        manifest_file = manifest_path

    # Update lockfile
    lockfile_path = os.path.join(output_dir, "confpub.lock")
    lockfile = load_lockfile(lockfile_path) or Lockfile()
    for entry in all_pages:
        page = entry["page"]
        pid = str(page["id"])
        page_title = page.get("title", "")
        version = page.get("version", {})
        version_num = version.get("number", 1) if isinstance(version, dict) else 1
        update_lockfile(lockfile, page_title, pid, version_num)
    save_lockfile(lockfile_path, lockfile)

    return {
        "output_dir": output_dir,
        "layout": layout,
        "files": files_result,
        "manifest_file": manifest_file,
        "warnings": pull_warnings,
        "summary": {
            "pages_pulled": len(files_result),
            "attachments_downloaded": total_attachments,
            "manifest_generated": manifest_file is not None,
        },
    }
