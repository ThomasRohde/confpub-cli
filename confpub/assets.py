"""Asset discovery, upload, and URL rewriting.

Finds image references in Markdown and resource references (script, link)
in ::: html blocks, uploads them as Confluence attachments, and rewrites
the Storage Format output to reference the attachments.
"""

from __future__ import annotations

import glob
import re
from html import escape as html_escape
from html import unescape as html_unescape
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


def merge_assets(*groups: list[AssetRef]) -> list[AssetRef]:
    """Merge asset groups by resolved path while preserving discovery order."""
    merged: list[AssetRef] = []
    seen: set[str] = set()
    for group in groups:
        for asset in group:
            if asset.resolved_path in seen:
                continue
            seen.add(asset.resolved_path)
            merged.append(asset)
    return merged


# Regex to find image references in markdown
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


# Regex to find image URLs in storage format (from converter output)
_STORAGE_IMAGE_RE = re.compile(
    r'<ac:image><ri:url ri:value="([^"]+)" /></ac:image>'
)

# Regex to find ::: html ... ::: blocks in markdown
_HTML_BLOCK_RE = re.compile(
    r"^:{3,}\s+html\s*$\n(.*?)^:{3,}\s*$",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# Regex to find <script src="..."> and <link href="..."> in HTML content
_SCRIPT_SRC_RE = re.compile(r'<script\b[^>]*\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)
_LINK_HREF_RE = re.compile(r'<link\b[^>]*\bhref=["\']([^"\']+)["\']', re.IGNORECASE)

# Regex to find local resource references in CDATA blocks (for rewriting)
_CDATA_BLOCK_RE = re.compile(r"(<!\[CDATA\[)(.*?)(\]\]>)", re.DOTALL)
_ADF_BODY_CONTENT_RE = re.compile(
    r'(<ac:adf-parameter key="__body-content">)(.*?)(</ac:adf-parameter>)',
    re.DOTALL,
)

def _is_local_path(src: str) -> bool:
    """Check if a path is a local file reference (not a URL)."""
    return not src.startswith(("http://", "https://", "//", "data:"))


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
        if not _is_local_path(src):
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

    # Find script/link references in ::: html blocks
    for block_match in _HTML_BLOCK_RE.finditer(md_text):
        html_content = block_match.group(1)
        for pattern in (_SCRIPT_SRC_RE, _LINK_HREF_RE):
            for ref_match in pattern.finditer(html_content):
                src = ref_match.group(1)
                if not _is_local_path(src):
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


def discover_html_macro_warnings(
    md_text: str,
    base_dir: str | Path,
) -> list[str]:
    """Check ::: html blocks for local file references that don't exist on disk.

    Returns a list of warning messages for missing files.
    """
    base = Path(base_dir)
    warnings: list[str] = []

    for block_match in _HTML_BLOCK_RE.finditer(md_text):
        html_content = block_match.group(1)
        for pattern, tag in ((_SCRIPT_SRC_RE, "script src"), (_LINK_HREF_RE, "link href")):
            for ref_match in pattern.finditer(html_content):
                src = ref_match.group(1)
                if not _is_local_path(src):
                    continue
                resolved = (base / src).resolve()
                if not resolved.is_file():
                    warnings.append(
                        f"HTML macro references missing file: <{tag}=\"{src}\"> "
                        f"(resolved to {resolved})"
                    )

    return warnings


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


def build_attachment_url(base_url: str, is_cloud: bool, page_id: str, filename: str) -> str:
    """Build a download URL for a Confluence page attachment.

    Args:
        base_url: Confluence base URL (e.g. https://mysite.atlassian.net).
        is_cloud: True for Confluence Cloud, False for DC/Server.
        page_id: Confluence page ID.
        filename: Attachment filename.

    Returns:
        Full download URL for the attachment.
    """
    base = base_url.rstrip("/")
    if is_cloud:
        if not base.endswith("/wiki"):
            base += "/wiki"
    return f"{base}/download/attachments/{page_id}/{filename}"


def rewrite_html_macro_urls(
    storage_format: str,
    uploaded_assets: list[UploadedAsset],
    base_url: str,
    is_cloud: bool,
    page_id: str,
) -> str:
    """Rewrite local file references inside HTML macro bodies to attachment URLs.

    Transforms script src and link href pointing to local files into full
    Confluence attachment download URLs. Handles classic HTML macro CDATA
    bodies and Forge ADF ``__body-content`` values.
    """
    if not uploaded_assets:
        return storage_format

    # Build lookups
    by_source: dict[str, UploadedAsset] = {}
    by_filename: dict[str, UploadedAsset] = {}
    for asset in uploaded_assets:
        by_source[asset.source_path] = asset
        by_filename[asset.filename] = asset

    def _find_asset(src: str) -> UploadedAsset | None:
        asset = by_source.get(src)
        if not asset:
            asset = by_filename.get(Path(src).name)
        return asset

    def _rewrite_refs(content: str) -> str:
        def _rewrite_attr(attr_match: re.Match) -> str:
            full = attr_match.group(0)
            src = attr_match.group(1)
            if not _is_local_path(src):
                return full
            asset = _find_asset(src)
            if asset:
                url = build_attachment_url(base_url, is_cloud, page_id, asset.filename)
                return full.replace(src, url)
            return full

        content = _SCRIPT_SRC_RE.sub(_rewrite_attr, content)
        return _LINK_HREF_RE.sub(_rewrite_attr, content)

    def _rewrite_cdata(match: re.Match) -> str:
        prefix = match.group(1)  # <![CDATA[
        content = _rewrite_refs(match.group(2))
        suffix = match.group(3)  # ]]>
        return prefix + content + suffix

    def _rewrite_adf_body(match: re.Match) -> str:
        prefix = match.group(1)
        content = html_unescape(match.group(2))
        content = _rewrite_refs(content)
        suffix = match.group(3)
        return prefix + html_escape(content, quote=False) + suffix

    storage_format = _CDATA_BLOCK_RE.sub(_rewrite_cdata, storage_format)
    return _ADF_BODY_CONTENT_RE.sub(_rewrite_adf_body, storage_format)


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
