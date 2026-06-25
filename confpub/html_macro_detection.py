"""HTML macro detection and Forge adoption helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from confpub.config import (
    DEFAULT_HTML_MACRO_FORGE_ENVIRONMENT,
    HTML_MACRO_FORMAT_CLASSIC,
    HTML_MACRO_FORMAT_FORGE_ADF_EXTENSION,
    HtmlMacroSettings,
)
from confpub.errors import ConfpubError, ERR_VALIDATION_NOT_FOUND, ERR_VALIDATION_REQUIRED

_HTML_OPEN_RE = re.compile(r"^:{3,}\s+html\s*$", re.IGNORECASE)
_HTML_CLOSE_RE = re.compile(r"^:{3,}\s*$")
_KNOWN_CLASSIC_HTML_MACROS = {"html", "html-macro", "macro-html"}
_CQL_MACRO_NAMES = ("html", "html-macro", "macro-html")


@dataclass(frozen=True)
class HtmlMacroCandidate:
    """Detected site-specific HTML macro settings from Confluence storage."""

    format: str
    html_macro_name: str | None = None
    html_macro_forge_extension_key: str | None = None
    html_macro_forge_extension_id: str | None = None
    html_macro_forge_environment: str | None = None
    html_macro_forge_cloud_id: str | None = None
    html_macro_forge_context_ids: str | None = None
    html_macro_forge_account_id: str | None = None
    page_id: str | None = None
    title: str | None = None

    @property
    def storage_shape(self) -> str:
        if self.format == HTML_MACRO_FORMAT_FORGE_ADF_EXTENSION:
            return "ac:adf-extension"
        return "ac:structured-macro"

    def config_values(self) -> dict[str, str]:
        """Return config keys needed to reproduce this candidate."""
        values: dict[str, str] = {"html_macro_format": self.format}
        if self.html_macro_name:
            values["html_macro_name"] = self.html_macro_name
        for key, value in (
            ("html_macro_forge_extension_key", self.html_macro_forge_extension_key),
            ("html_macro_forge_extension_id", self.html_macro_forge_extension_id),
            ("html_macro_forge_environment", self.html_macro_forge_environment),
            ("html_macro_forge_cloud_id", self.html_macro_forge_cloud_id),
            ("html_macro_forge_context_ids", self.html_macro_forge_context_ids),
            ("html_macro_forge_account_id", self.html_macro_forge_account_id),
        ):
            if value:
                values[key] = value
        return values

    def config_commands(self) -> list[str]:
        return [
            f"confpub config set {key} {_shell_quote(value)}"
            for key, value in self.config_values().items()
        ]

    def to_dict(self, *, index: int | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "format": self.format,
            "storage_shape": self.storage_shape,
            "config": self.config_values(),
            "config_commands": self.config_commands(),
        }
        if index is not None:
            result["index"] = index
        if self.html_macro_name:
            result["html_macro_name"] = self.html_macro_name
        if self.page_id:
            result["page_id"] = self.page_id
        if self.title:
            result["title"] = self.title
        return result

    def dedupe_key(self) -> tuple[str, str | None, str | None, str | None, str | None, str | None, str | None, str | None]:
        return (
            self.format,
            self.html_macro_name,
            self.html_macro_forge_extension_key,
            self.html_macro_forge_extension_id,
            self.html_macro_forge_environment,
            self.html_macro_forge_cloud_id,
            self.html_macro_forge_context_ids,
            self.html_macro_forge_account_id,
        )


def has_html_macro_blocks(markdown: str) -> bool:
    """Return true when Markdown contains a closed ``::: html`` block."""
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if not _HTML_OPEN_RE.match(line):
            continue
        for candidate in lines[index + 1:]:
            if _HTML_CLOSE_RE.match(candidate):
                return True
    return False


def classic_cloud_fallback_warning(settings: HtmlMacroSettings) -> str:
    return (
        "This Cloud publish contains ::: html but is using the default classic "
        "HTML macro storage fallback. Forge HTML macro apps can accept the page "
        "save and still render \"Error loading extension\". Run "
        "confpub html-macro detect --from-page <WORKING_PAGE_ID> and persist "
        "the detected forge-adf-extension settings if this site uses a Forge app."
    )


def html_macro_fallback_warnings(
    markdown: str,
    *,
    is_cloud: bool,
    settings: HtmlMacroSettings,
) -> list[str]:
    """Warn when Cloud HTML blocks rely on the unverified classic fallback."""
    if (
        is_cloud
        and settings.format == HTML_MACRO_FORMAT_CLASSIC
        and settings.format_source == "default"
        and has_html_macro_blocks(markdown)
    ):
        return [classic_cloud_fallback_warning(settings)]
    return []


def extract_html_macro_candidates(
    storage: str,
    *,
    page_id: str | None = None,
    title: str | None = None,
) -> list[HtmlMacroCandidate]:
    """Extract classic and Forge HTML macro settings from storage format."""
    soup = BeautifulSoup(storage or "", "html.parser")
    candidates: list[HtmlMacroCandidate] = []

    for macro in soup.find_all("ac:structured-macro"):
        macro_name = macro.get("ac:name") or macro.get("name")
        if not macro_name or macro_name not in _KNOWN_CLASSIC_HTML_MACROS:
            continue
        candidates.append(
            HtmlMacroCandidate(
                format=HTML_MACRO_FORMAT_CLASSIC,
                html_macro_name=macro_name,
                page_id=page_id,
                title=title,
            )
        )

    for adf in soup.find_all("ac:adf-extension"):
        body = _find_adf_param(adf, "__body-content")
        extension_key = _find_adf_attr(adf, "extension-key")
        extension_id = _find_adf_param(adf, "extension-id")
        if not body or not extension_key or not extension_id:
            continue
        candidates.append(
            HtmlMacroCandidate(
                format=HTML_MACRO_FORMAT_FORGE_ADF_EXTENSION,
                html_macro_name=_infer_macro_name(extension_key, extension_id),
                html_macro_forge_extension_key=extension_key,
                html_macro_forge_extension_id=extension_id,
                html_macro_forge_environment=(
                    _find_adf_param(adf, "forge-environment")
                    or DEFAULT_HTML_MACRO_FORGE_ENVIRONMENT
                ),
                html_macro_forge_cloud_id=_find_adf_param(adf, "cloud-id"),
                html_macro_forge_context_ids=_find_adf_param(adf, "context-ids"),
                html_macro_forge_account_id=_find_adf_param(adf, "account-id"),
                page_id=page_id,
                title=title,
            )
        )

    return dedupe_html_macro_candidates(candidates)


def detect_html_macro_candidates(
    client: Any,
    *,
    from_page: str | None = None,
    space: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Detect HTML macro settings from a known page or CQL macro search."""
    if limit < 1:
        raise ConfpubError(ERR_VALIDATION_REQUIRED, "limit must be a positive integer (>= 1)")

    if from_page:
        page = client.get_page_by_id(from_page)
        candidates = extract_html_macro_candidates(
            _page_storage(page),
            page_id=str(page.get("id") or from_page),
            title=page.get("title"),
        )
        return _detection_result(
            source={"type": "page", "page_id": from_page},
            candidates=candidates,
        )

    cql = _macro_usage_cql(space)
    search_result = client.search(cql, limit=limit)
    candidates: list[HtmlMacroCandidate] = []
    inspected_pages = 0
    for item in search_result.get("results", []):
        page_id = item.get("id")
        if not page_id:
            continue
        inspected_pages += 1
        page = client.get_page_by_id(str(page_id))
        candidates.extend(
            extract_html_macro_candidates(
                _page_storage(page),
                page_id=str(page.get("id") or page_id),
                title=page.get("title") or item.get("title"),
            )
        )

    return _detection_result(
        source={
            "type": "cql",
            "space": space,
            "cql": cql,
            "limit": limit,
            "inspected_pages": inspected_pages,
        },
        candidates=dedupe_html_macro_candidates(candidates),
    )


def select_html_macro_candidate(
    candidates: list[HtmlMacroCandidate],
    *,
    candidate_index: int | None = None,
) -> HtmlMacroCandidate:
    """Select a candidate for adoption, using 1-based indexing."""
    if not candidates:
        raise ConfpubError(
            ERR_VALIDATION_NOT_FOUND,
            "No HTML macro settings were found on the source page",
            details={"hint": "Use --from-page with a page that contains a working HTML macro"},
        )
    if candidate_index is None:
        if len(candidates) == 1:
            return candidates[0]
        raise ConfpubError(
            ERR_VALIDATION_REQUIRED,
            "Multiple HTML macro setting candidates were found; pass --candidate",
            details={"candidate_count": len(candidates), "candidate_indexes": list(range(1, len(candidates) + 1))},
        )
    if candidate_index < 1 or candidate_index > len(candidates):
        raise ConfpubError(
            ERR_VALIDATION_REQUIRED,
            f"--candidate must be between 1 and {len(candidates)}",
            details={"candidate_count": len(candidates), "candidate": candidate_index},
        )
    return candidates[candidate_index - 1]


def dedupe_html_macro_candidates(candidates: list[HtmlMacroCandidate]) -> list[HtmlMacroCandidate]:
    """Keep one candidate per unique site setting."""
    seen: set[tuple[str, str | None, str | None, str | None, str | None, str | None, str | None, str | None]] = set()
    deduped: list[HtmlMacroCandidate] = []
    for candidate in candidates:
        key = candidate.dedupe_key()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _find_adf_attr(adf: Any, key: str) -> str | None:
    tag = adf.find("ac:adf-attribute", attrs={"key": key})
    return _tag_text(tag)


def _find_adf_param(adf: Any, key: str) -> str | None:
    tag = adf.find("ac:adf-parameter", attrs={"key": key})
    return _tag_text(tag)


def _tag_text(tag: Any) -> str | None:
    if tag is None:
        return None
    text = tag.get_text()
    value = text.strip()
    return value or None


def _infer_macro_name(extension_key: str, extension_id: str | None) -> str | None:
    for raw in (extension_key, extension_id):
        if not raw:
            continue
        segment = raw.rstrip("/").split("/")[-1].strip()
        if segment and segment.lower() not in {"html", "static"}:
            return segment
    return None


def _shell_quote(value: str) -> str:
    if re.match(r"^[A-Za-z0-9_.:/@-]+$", value):
        return value
    return '"' + value.replace('"', '\\"') + '"'


def _page_storage(page: dict[str, Any]) -> str:
    return page.get("body", {}).get("storage", {}).get("value", "")


def _macro_usage_cql(space: str | None) -> str:
    macro_list = ", ".join(f'"{name}"' for name in _CQL_MACRO_NAMES)
    fragments = ["type = page"]
    if space:
        fragments.append(f'space = "{space}"')
    fragments.append(f"macro in ({macro_list})")
    return " AND ".join(fragments)


def _detection_result(
    *,
    source: dict[str, Any],
    candidates: list[HtmlMacroCandidate],
) -> dict[str, Any]:
    return {
        "source": source,
        "candidate_count": len(candidates),
        "candidates": [
            candidate.to_dict(index=index)
            for index, candidate in enumerate(candidates, start=1)
        ],
    }
