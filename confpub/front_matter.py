"""Front-matter extraction and validation for single-file publish.

Parses YAML front-matter from Markdown files into a typed dataclass.
Used only by `page publish`; manifest flows ignore front-matter entirely.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

import yaml

from confpub.converter import extract_front_matter
from confpub.errors import ERR_VALIDATION_MARKDOWN, ConfpubError


@dataclass
class FrontMatterData:
    """Validated front-matter fields."""

    title: str | None = None
    space: str | None = None
    parent: str | None = None
    labels: list[str] = field(default_factory=list)
    page_id: str | None = None
    html_macro_name: str | None = None

    def to_yaml_block(self) -> str:
        """Serialize to a YAML front matter block (``--- ... ---``)."""
        data: dict[str, Any] = {}
        if self.title is not None:
            data["title"] = self.title
        if self.page_id is not None:
            data["page_id"] = self.page_id
        if self.space is not None:
            data["space"] = self.space
        if self.parent is not None:
            data["parent"] = self.parent
        if self.labels:
            data["labels"] = self.labels
        if self.html_macro_name is not None:
            data["html_macro_name"] = self.html_macro_name
        yaml_str = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return f"---\n{yaml_str}---\n\n"


def _validate_string(raw: dict[str, Any], key: str) -> str | None:
    """Extract and validate a string field, or None if absent."""
    val = raw.get(key)
    if val is None:
        return None
    if not isinstance(val, str):
        raise ConfpubError(
            ERR_VALIDATION_MARKDOWN,
            f"Front-matter field '{key}' must be a string, got {type(val).__name__}",
            details={"field": key, "value_type": type(val).__name__},
        )
    return val


def parse_front_matter(md_text: str) -> FrontMatterData | None:
    """Extract and validate front-matter from Markdown text.

    Returns a FrontMatterData with validated fields, or None if no
    front-matter is present.  Unknown keys are silently ignored.

    Raises ConfpubError (ERR_VALIDATION_MARKDOWN) on type errors.
    """
    raw = extract_front_matter(md_text)
    if raw is None:
        return None

    title = _validate_string(raw, "title")
    space = _validate_string(raw, "space")
    parent = _validate_string(raw, "parent")

    # labels: list[str] or single string → list[str]
    labels_raw = raw.get("labels")
    labels: list[str] = []
    if labels_raw is not None:
        if isinstance(labels_raw, str):
            labels = [labels_raw]
        elif isinstance(labels_raw, list):
            for item in labels_raw:
                if not isinstance(item, str):
                    raise ConfpubError(
                        ERR_VALIDATION_MARKDOWN,
                        f"Front-matter 'labels' items must be strings, got {type(item).__name__}",
                        details={"field": "labels", "value_type": type(item).__name__},
                    )
            labels = labels_raw
        else:
            raise ConfpubError(
                ERR_VALIDATION_MARKDOWN,
                f"Front-matter 'labels' must be a list or string, got {type(labels_raw).__name__}",
                details={"field": "labels", "value_type": type(labels_raw).__name__},
            )

    # page_id: string or int → string
    page_id_raw = raw.get("page_id")
    page_id: str | None = None
    if page_id_raw is not None:
        if isinstance(page_id_raw, (str, int)):
            page_id = str(page_id_raw)
        else:
            raise ConfpubError(
                ERR_VALIDATION_MARKDOWN,
                f"Front-matter 'page_id' must be a string or integer, got {type(page_id_raw).__name__}",
                details={"field": "page_id", "value_type": type(page_id_raw).__name__},
            )

    html_macro_name = _validate_string(raw, "html_macro_name")

    return FrontMatterData(
        title=title,
        space=space,
        parent=parent,
        labels=labels,
        page_id=page_id,
        html_macro_name=html_macro_name,
    )
