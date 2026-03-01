"""Asset discovery, upload, and URL rewriting.

Finds image references in Markdown, uploads them as Confluence attachments,
and rewrites the Storage Format output to reference the attachments.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class AssetRef(BaseModel):
    """A reference to a local asset file."""

    source_path: str  # Relative or absolute path as found in markdown/manifest
    resolved_path: str  # Absolute path on disk
    filename: str  # Just the filename


class UploadedAsset(BaseModel):
    """An asset that has been uploaded to Confluence."""

    source_path: str
    filename: str
    confluence_attachment_id: str | None = None


# Regex to find image references in markdown
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


# Regex to find image URLs in storage format (from converter output)
_STORAGE_IMAGE_RE = re.compile(
    r'<ac:image><ri:url ri:value="([^"]+)" /></ac:image>'
)


def discover_assets(
    md_text: str,
    base_dir: str | Path,
    asset_globs: list[str] | None = None,
) -> list[AssetRef]:
    """Discover all asset references from Markdown text and optional glob patterns.

    Args:
        md_text: Raw Markdown text.
        base_dir: Base directory for resolving relative paths.
        asset_globs: Additional glob patterns from the manifest.

    Returns:
        List of unique AssetRef objects.
    """
    base = Path(base_dir)
    seen: set[str] = set()
    assets: list[AssetRef] = []

    # Find images in markdown, only include files that exist on disk
    for match in _MD_IMAGE_RE.finditer(md_text):
        src = match.group(2)
        # Skip URLs
        if src.startswith(("http://", "https://", "//")):
            continue
        resolved = (base / src).resolve()
        key = str(resolved)
        if key not in seen and resolved.is_file():
            seen.add(key)
            assets.append(AssetRef(
                source_path=src,
                resolved_path=str(resolved),
                filename=resolved.name,
            ))

    # Expand glob patterns from manifest
    if asset_globs:
        for pattern in asset_globs:
            full_pattern = str(base / pattern)
            for path_str in glob.glob(full_pattern, recursive=True):
                resolved = Path(path_str).resolve()
                key = str(resolved)
                if key not in seen and resolved.is_file():
                    seen.add(key)
                    rel = str(resolved.relative_to(base)) if resolved.is_relative_to(base) else str(resolved)
                    assets.append(AssetRef(
                        source_path=rel,
                        resolved_path=str(resolved),
                        filename=resolved.name,
                    ))

    return assets


def rewrite_image_urls(storage_format: str, uploaded_assets: list[UploadedAsset]) -> str:
    """Replace image URLs in Storage Format with Confluence attachment references.

    Transforms:
        <ac:image><ri:url ri:value="image.png" /></ac:image>
    Into:
        <ac:image><ri:attachment ri:filename="image.png" /></ac:image>
    """
    # Build a lookup from source path / filename to uploaded asset
    by_source: dict[str, UploadedAsset] = {}
    by_filename: dict[str, UploadedAsset] = {}
    for asset in uploaded_assets:
        by_source[asset.source_path] = asset
        by_filename[asset.filename] = asset

    def _replace(match: re.Match) -> str:
        url = match.group(1)
        # Try exact source match, then filename
        asset = by_source.get(url)
        if not asset:
            filename = Path(url).name
            asset = by_filename.get(filename)
        if asset:
            return f'<ac:image><ri:attachment ri:filename="{asset.filename}" /></ac:image>'
        # Keep original if no matching upload
        return match.group(0)

    return _STORAGE_IMAGE_RE.sub(_replace, storage_format)


def upload_assets(
    client: Any,  # ConfluenceClient
    page_id: str,
    assets: list[AssetRef],
) -> list[UploadedAsset]:
    """Upload asset files to Confluence as attachments.

    Args:
        client: ConfluenceClient instance.
        page_id: Confluence page ID to attach to.
        assets: List of AssetRef objects to upload.

    Returns:
        List of UploadedAsset objects.
    """
    uploaded: list[UploadedAsset] = []
    for asset in assets:
        result = client.upload_attachment(page_id, asset.resolved_path)
        att_id = None
        if isinstance(result, dict):
            att_id = str(result.get("id", ""))
        uploaded.append(UploadedAsset(
            source_path=asset.source_path,
            filename=asset.filename,
            confluence_attachment_id=att_id,
        ))
    return uploaded
