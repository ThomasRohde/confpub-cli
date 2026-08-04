"""Site-scoped discovery and persistence for learned Confluence macros."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from confpub.assets import AssetRef
from confpub.errors import ConfpubError, ERR_VALIDATION_NOT_FOUND, ERR_VALIDATION_REQUIRED
from confpub.macro_plugin import parse_macro_params


MacroStorageFormat = Literal["structured-macro", "forge-adf-extension"]
MacroBodyType = Literal["none", "attachment", "plain-text", "rich-text", "adf-body"]


class MacroProfile(BaseModel):
    """A learned, site-specific macro storage contract."""

    alias: str
    storage_format: MacroStorageFormat
    macro_name: str | None = None
    body_type: MacroBodyType = "none"
    attributes: dict[str, str] = Field(default_factory=dict)
    default_parameters: dict[str, str] = Field(default_factory=dict)
    attachment_parameter: str | None = None
    attachment_media_type: str | None = None
    storage_template: str | None = None
    source_page_id: str | None = None
    source_page_title: str | None = None
    learned_at: str | None = None

    @property
    def publish_supported(self) -> bool:
        if self.storage_format == "structured-macro":
            return bool(self.macro_name)
        return bool(self.storage_template)

    def to_display_dict(self, *, index: int | None = None) -> dict[str, Any]:
        result = self.model_dump(exclude_none=True, exclude={"storage_template"})
        result["publish_supported"] = self.publish_supported
        if self.storage_template:
            result["has_storage_template"] = True
        if index is not None:
            result["index"] = index
        return result


class MacroProfileStore(BaseModel):
    schema_version: str = "1.0"
    sites: dict[str, dict[str, MacroProfile]] = Field(default_factory=dict)


@dataclass
class PreparedMacros:
    assets: list[AssetRef]
    sources: dict[str, str]
    warnings: list[str]


_INVOCATION_RE = re.compile(r"\{macro(?::([^}]*))?\}")
_VOLATILE_ATTRIBUTES = {"ac:local-id", "ac:macro-id"}


def _profiles_file() -> Path:
    from confpub import config

    return config.CONFIG_DIR / "macros.json"


def _site_key(base_url: str) -> str:
    return base_url.strip().rstrip("/").lower()


def _load_store() -> MacroProfileStore:
    path = _profiles_file()
    if not path.exists():
        return MacroProfileStore()
    try:
        return MacroProfileStore.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ConfpubError(
            ERR_VALIDATION_REQUIRED,
            f"Invalid learned macro profile file: {path}",
            details={"file": str(path), "error": str(exc)},
        ) from exc


def load_macro_profiles(base_url: str | None) -> dict[str, MacroProfile]:
    if not base_url:
        return {}
    return dict(_load_store().sites.get(_site_key(base_url), {}))


def save_macro_profile(base_url: str, profile: MacroProfile) -> Path:
    if not base_url:
        raise ConfpubError(ERR_VALIDATION_REQUIRED, "A configured Confluence base URL is required")
    store = _load_store()
    site = store.sites.setdefault(_site_key(base_url), {})
    site[profile.alias] = profile

    path = _profiles_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(store.model_dump(mode="json"), indent=2, ensure_ascii=False)
    fd, temp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return path


def extract_macro_candidates(
    storage: str,
    *,
    attachments: list[dict[str, Any]] | None = None,
    page_id: str | None = None,
    title: str | None = None,
) -> list[MacroProfile]:
    """Classify macros from a known-good page without assuming an app vendor."""
    soup = BeautifulSoup(storage or "", "html.parser")
    attachment_types = {
        str(item.get("title")): str(item.get("metadata", {}).get("mediaType") or item.get("media_type") or "")
        for item in (attachments or [])
        if item.get("title")
    }
    candidates: list[MacroProfile] = []

    for macro in soup.find_all("ac:structured-macro"):
        macro_name = str(macro.get("ac:name") or macro.get("name") or "").strip()
        if not macro_name:
            continue
        params: dict[str, str] = {}
        for parameter in macro.find_all("ac:parameter", recursive=False):
            key = str(parameter.get("ac:name") or parameter.get("name") or "")
            params[key] = parameter.get_text()

        attachment_parameter = None
        attachment_media_type = None
        for key, value in params.items():
            if value in attachment_types:
                attachment_parameter = key
                attachment_media_type = attachment_types[value] or None
                break

        plain_body = macro.find("ac:plain-text-body", recursive=False)
        rich_body = macro.find("ac:rich-text-body", recursive=False)
        if plain_body is not None:
            body_type: MacroBodyType = "plain-text"
        elif rich_body is not None:
            body_type = "rich-text"
        elif attachment_parameter:
            body_type = "attachment"
        else:
            body_type = "none"

        attrs = {
            str(key): str(value)
            for key, value in macro.attrs.items()
            if key not in _VOLATILE_ATTRIBUTES and key not in {"ac:name", "name"}
        }
        candidates.append(MacroProfile(
            alias=macro_name,
            storage_format="structured-macro",
            macro_name=macro_name,
            body_type=body_type,
            attributes=attrs,
            default_parameters=params,
            attachment_parameter=attachment_parameter,
            attachment_media_type=attachment_media_type,
            source_page_id=page_id,
            source_page_title=title,
        ))

    for adf in soup.find_all("ac:adf-extension"):
        extension_key_tag = adf.find("ac:adf-attribute", attrs={"key": "extension-key"})
        extension_key = extension_key_tag.get_text().strip() if extension_key_tag else ""
        inferred_name = extension_key.rstrip("/").split("/")[-1] if extension_key else "forge-macro"
        body_param = adf.find("ac:adf-parameter", attrs={"key": "__body-content"})
        candidates.append(MacroProfile(
            alias=inferred_name,
            storage_format="forge-adf-extension",
            macro_name=inferred_name,
            body_type="adf-body" if body_param is not None else "none",
            storage_template=_sanitize_adf_template(adf),
            source_page_id=page_id,
            source_page_title=title,
        ))

    return candidates


def _sanitize_adf_template(adf: Any) -> str:
    """Remove sample body content and volatile identity before persisting a Forge shape."""
    soup = BeautifulSoup(str(adf), "html.parser")
    root = soup.find("ac:adf-extension")
    if root is None:
        return ""
    body = root.find("ac:adf-parameter", attrs={"key": "__body-content"})
    if body is not None:
        body.clear()
    local_id = root.find("ac:adf-attribute", attrs={"key": "local-id"})
    if local_id is not None:
        local_id.clear()
    return str(root)


def detect_macro_candidates(client: Any, from_page: str) -> dict[str, Any]:
    page = client.get_page_by_id(from_page)
    storage = page.get("body", {}).get("storage", {}).get("value", "")
    attachments = client.get_attachments(from_page)
    candidates = extract_macro_candidates(
        storage,
        attachments=attachments,
        page_id=str(page.get("id") or from_page),
        title=page.get("title"),
    )
    return {
        "source": {"type": "page", "page_id": from_page, "title": page.get("title")},
        "candidate_count": len(candidates),
        "candidates": [
            candidate.to_display_dict(index=index)
            for index, candidate in enumerate(candidates, start=1)
        ],
    }


def select_macro_candidate(
    candidates: list[MacroProfile],
    *,
    candidate_index: int | None = None,
) -> MacroProfile:
    if not candidates:
        raise ConfpubError(
            ERR_VALIDATION_NOT_FOUND,
            "No macros were found on the source page",
        )
    if candidate_index is None:
        if len(candidates) == 1:
            return candidates[0]
        raise ConfpubError(
            ERR_VALIDATION_REQUIRED,
            "Multiple macros were found; pass --candidate",
            details={"candidate_count": len(candidates)},
        )
    if candidate_index < 1 or candidate_index > len(candidates):
        raise ConfpubError(
            ERR_VALIDATION_REQUIRED,
            f"--candidate must be between 1 and {len(candidates)}",
        )
    return candidates[candidate_index - 1]


def learn_macro_profile(
    client: Any,
    *,
    base_url: str,
    from_page: str,
    alias: str,
    candidate_index: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    page = client.get_page_by_id(from_page)
    attachments = client.get_attachments(from_page)
    candidates = extract_macro_candidates(
        page.get("body", {}).get("storage", {}).get("value", ""),
        attachments=attachments,
        page_id=str(page.get("id") or from_page),
        title=page.get("title"),
    )
    selected = select_macro_candidate(candidates, candidate_index=candidate_index)
    profile = selected.model_copy(update={
        "alias": alias.strip(),
        "learned_at": datetime.now(timezone.utc).isoformat(),
    })
    if not profile.alias:
        raise ConfpubError(ERR_VALIDATION_REQUIRED, "--alias must not be blank")
    path = None if dry_run else save_macro_profile(base_url, profile)
    return {
        "dry_run": dry_run,
        "learned": not dry_run,
        "profile": profile.to_display_dict(),
        "profile_file": str(path) if path else str(_profiles_file()),
        "syntax": f"{{macro:{profile.alias}|source=<local-file>}}",
    }


def prepare_macros(
    markdown: str,
    base_dir: str | Path,
    profiles: dict[str, MacroProfile],
) -> PreparedMacros:
    """Resolve learned-macro sources and attachment uploads before conversion."""
    base = Path(base_dir)
    assets: list[AssetRef] = []
    sources: dict[str, str] = {}
    warnings: list[str] = []
    seen_assets: set[str] = set()

    for match in _INVOCATION_RE.finditer(markdown):
        alias, params = parse_macro_params(match.group(1))
        profile = profiles.get(alias)
        if not profile:
            warnings.append(
                f"Learned macro alias '{alias}' is not configured for this Confluence site. "
                "Run confpub macro learn --from-page <WORKING_PAGE_ID> --alias " + alias + "."
            )
            continue
        source = params.get("source")
        if not source:
            if profile.body_type != "none":
                warnings.append(f"Learned macro '{alias}' requires source=<local-file>.")
            continue
        resolved = (base / source).resolve()
        if not resolved.is_file():
            warnings.append(
                f"Learned macro '{alias}' references missing source file: {source} "
                f"(resolved to {resolved})"
            )
            continue
        try:
            sources[source] = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            warnings.append(f"Learned macro '{alias}' source must be UTF-8 text: {source}")
            continue
        if profile.body_type == "attachment":
            key = str(resolved)
            if key not in seen_assets:
                seen_assets.add(key)
                assets.append(AssetRef(
                    source_path=source,
                    resolved_path=str(resolved),
                    filename=resolved.name,
                ))

    return PreparedMacros(assets=assets, sources=sources, warnings=warnings)


def find_profile_for_macro(
    profiles: dict[str, MacroProfile],
    *,
    storage_format: MacroStorageFormat,
    macro_name: str | None,
) -> MacroProfile | None:
    for profile in profiles.values():
        if profile.storage_format == storage_format and profile.macro_name == macro_name:
            return profile
    return None
