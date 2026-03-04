"""Manifest and plan artifact Pydantic models.

The manifest (confpub.yaml) declares a page tree. The plan artifact
is the JSON file produced by plan.create and consumed by plan.apply.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from confpub.errors import ERR_VALIDATION_MANIFEST, ConfpubError


# ---------------------------------------------------------------------------
# Manifest models
# ---------------------------------------------------------------------------


class ManifestAssertion(BaseModel):
    """A single verification assertion."""

    type: str  # page.exists | page.parent | attachment.exists
    title: Optional[str] = None
    space: Optional[str] = None
    expected_parent: Optional[str] = None
    page: Optional[str] = None
    filename: Optional[str] = None


class ManifestAuth(BaseModel):
    """Auth section of the manifest."""

    type: str = "token"  # token | basic | env


class ManifestConfluence(BaseModel):
    """Confluence connection settings in manifest."""

    base_url: Optional[str] = None
    auth: Optional[ManifestAuth] = None


class ManifestPage(BaseModel):
    """A page in the manifest tree. Supports recursive children."""

    title: str
    file: str
    assets: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    children: list[ManifestPage] = Field(default_factory=list)


class Manifest(BaseModel):
    """The confpub.yaml manifest model."""

    schema_version: str = "1.0"
    space: str
    parent: str
    confluence: Optional[ManifestConfluence] = None
    conflict_strategy: Literal["fail", "overwrite", "skip"] = "fail"
    on_removal: Literal["leave", "delete"] = "leave"
    version_comment: str = "Published by confpub @ {timestamp}"
    labels: list[str] = Field(default_factory=list)
    assertions: list[ManifestAssertion] = Field(default_factory=list)
    pages: list[ManifestPage] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Plan artifact models
# ---------------------------------------------------------------------------


class PlanAttachment(BaseModel):
    """An attachment in the plan."""

    file: str
    confluence_attachment_id: Optional[str] = None
    operation: Literal["upload", "update", "noop"] = "upload"


class PlanPage(BaseModel):
    """A page entry in the plan artifact."""

    id: str
    title: str
    source_file: str
    confluence_page_id: Optional[str] = None
    current_fingerprint: Optional[str] = None
    operation: Literal["create", "update", "noop"]
    parent_title: Optional[str] = None
    attachments: list[PlanAttachment] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)


class PlanSummary(BaseModel):
    """Summary counts for the plan."""

    create: int = 0
    update: int = 0
    noop: int = 0
    attachments_to_upload: int = 0
    labels_to_apply: int = 0


class PlanArtifact(BaseModel):
    """The plan artifact JSON file."""

    schema_version: str = "1.0"
    created_at: str = ""
    space: str
    parent: str
    pages: list[PlanPage] = Field(default_factory=list)
    summary: PlanSummary = Field(default_factory=PlanSummary)


# ---------------------------------------------------------------------------
# FlatPage — used internally after resolving the manifest tree
# ---------------------------------------------------------------------------


class FlatPage(BaseModel):
    """A flattened page with explicit parent reference."""

    title: str
    file: str
    assets: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)  # merged global + per-page
    parent_title: str  # The parent page title (from manifest parent or parent page)


# ---------------------------------------------------------------------------
# Loading and resolving
# ---------------------------------------------------------------------------


def load_manifest(path: str) -> Manifest:
    """Load and validate a manifest YAML file."""
    p = Path(path)
    if not p.exists():
        from confpub.errors import ERR_IO_FILE_NOT_FOUND
        raise ConfpubError(
            ERR_IO_FILE_NOT_FOUND,
            f"Manifest not found: {path}",
            retryable=False,
            suggested_action="fix_input",
        )
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ConfpubError(
                ERR_VALIDATION_MANIFEST,
                f"Manifest must be a YAML mapping, got {type(data).__name__}",
            )
        return Manifest(**data)
    except ConfpubError:
        raise
    except ValidationError as exc:
        details = {
            "validation_errors": [
                {"field": ".".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
                for e in exc.errors()
            ]
        }
        raise ConfpubError(
            ERR_VALIDATION_MANIFEST,
            f"Invalid manifest: {len(exc.errors())} validation error(s)",
            details=details,
        ) from exc
    except Exception as exc:
        raise ConfpubError(
            ERR_VALIDATION_MANIFEST,
            f"Invalid manifest: {exc}",
        ) from exc


def generate_manifest_yaml(
    space: str,
    parent: str,
    page_tree: list[dict[str, Any]],
) -> str:
    """Generate a confpub.yaml manifest string from a pulled page tree.

    Each entry in page_tree should have: title, file, children (list of same shape).
    """
    def _build_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for p in pages:
            entry: dict[str, Any] = {"title": p["title"], "file": p["file"]}
            assets = p.get("assets", [])
            if assets:
                entry["assets"] = assets
            labels = p.get("labels", [])
            if labels:
                entry["labels"] = labels
            children = p.get("children", [])
            if children:
                entry["children"] = _build_pages(children)
            result.append(entry)
        return result

    manifest_data: dict[str, Any] = {
        "schema_version": "1.0",
        "space": space,
        "parent": parent,
        "pages": _build_pages(page_tree),
    }
    return yaml.dump(manifest_data, default_flow_style=False, sort_keys=False)


def resolve_page_tree(manifest: Manifest) -> list[FlatPage]:
    """Flatten the recursive page tree into a list with parent references.

    Pages are returned in tree order (parents before children) to ensure
    correct creation order. Labels are merged: global (manifest.labels)
    first, then per-page, deduplicated while preserving order.
    """
    flat: list[FlatPage] = []
    global_labels = manifest.labels

    def _walk(pages: list[ManifestPage], parent_title: str) -> None:
        for page in pages:
            merged = list(dict.fromkeys(global_labels + page.labels))
            flat.append(FlatPage(
                title=page.title,
                file=page.file,
                assets=page.assets,
                labels=merged,
                parent_title=parent_title,
            ))
            if page.children:
                _walk(page.children, page.title)

    _walk(manifest.pages, manifest.parent)
    return flat
