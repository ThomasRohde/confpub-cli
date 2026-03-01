"""Confluence API wrapper using atlassian-python-api.

Provides a clean interface that translates library exceptions into ConfpubError.
"""

from __future__ import annotations

import hashlib
from typing import Any

from confpub.config import ResolvedConfig, load_config
from confpub.errors import (
    ERR_AUTH_FORBIDDEN,
    ERR_CONFLICT_PAGE_EXISTS,
    ERR_IO_CONNECTION,
    ERR_IO_TIMEOUT,
    ERR_INTERNAL_SDK,
    ConfpubError,
)


class ConfluenceClient:
    """Wrapper around atlassian.Confluence that raises ConfpubError."""

    def __init__(self, config: ResolvedConfig) -> None:
        config.require_credentials()
        self._config = config
        self._api = self._build_api(config)

    @staticmethod
    def _build_api(config: ResolvedConfig) -> Any:
        from atlassian import Confluence

        kwargs: dict[str, Any] = {"url": config.base_url}
        if config.is_cloud:
            kwargs["username"] = config.user
            kwargs["password"] = config.token
            kwargs["cloud"] = True
        else:
            kwargs["token"] = config.token
        return Confluence(**kwargs)

    def _handle_error(self, exc: Exception, context: str = "") -> None:
        """Translate atlassian-python-api exceptions to ConfpubError."""
        msg = str(exc)
        if "401" in msg or "Unauthorized" in msg:
            raise ConfpubError(
                ERR_AUTH_FORBIDDEN,
                f"Authentication failed: {msg}",
                suggested_action="reauth",
            ) from exc
        if "403" in msg or "Forbidden" in msg:
            raise ConfpubError(
                ERR_AUTH_FORBIDDEN,
                f"Permission denied: {msg}",
                suggested_action="escalate",
            ) from exc
        if "timeout" in msg.lower() or "Timeout" in msg:
            raise ConfpubError(ERR_IO_TIMEOUT, f"Request timed out: {msg}") from exc
        if "ConnectionError" in msg or "connection" in msg.lower():
            raise ConfpubError(ERR_IO_CONNECTION, f"Connection failed: {msg}") from exc
        # Permission denied (e.g., nonexistent space, restricted content)
        if "permission" in msg.lower() or "not permitted" in msg.lower():
            raise ConfpubError(
                ERR_AUTH_FORBIDDEN,
                f"Permission denied ({context}): {msg}",
                suggested_action="escalate",
            ) from exc
        # Not found (404 or explicit "not found")
        if "404" in msg or "not found" in msg.lower():
            from confpub.errors import ERR_IO_FILE_NOT_FOUND
            raise ConfpubError(
                ERR_IO_FILE_NOT_FOUND,
                f"Resource not found ({context}): {msg}",
            ) from exc
        raise ConfpubError(ERR_INTERNAL_SDK, f"Unexpected API error ({context}): {msg}") from exc

    # ------------------------------------------------------------------
    # Page operations
    # ------------------------------------------------------------------

    def get_page(self, space: str, title: str) -> dict[str, Any] | None:
        """Get a page by space key and title."""
        try:
            result = self._api.get_page_by_title(space, title, expand="version,body.storage")
            return result if result else None
        except Exception as exc:
            self._handle_error(exc, "get_page")
            return None  # unreachable, but satisfies type checker

    def get_page_by_id(self, page_id: str) -> dict[str, Any]:
        """Get a page by its Confluence ID."""
        try:
            return self._api.get_page_by_id(page_id, expand="version,body.storage,space")
        except Exception as exc:
            self._handle_error(exc, "get_page_by_id")
            return {}

    def create_page(
        self,
        space: str,
        title: str,
        body: str,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new page."""
        try:
            return self._api.create_page(
                space=space,
                title=title,
                body=body,
                parent_id=parent_id,
                type="page",
                representation="storage",
            )
        except Exception as exc:
            msg = str(exc)
            if "already exists" in msg.lower() or "409" in msg:
                raise ConfpubError(
                    ERR_CONFLICT_PAGE_EXISTS,
                    f"Page '{title}' already exists in space '{space}'",
                    details={"space": space, "title": title},
                ) from exc
            self._handle_error(exc, "create_page")
            return {}

    def update_page(
        self,
        page_id: str,
        title: str,
        body: str,
        *,
        version_comment: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing page."""
        try:
            return self._api.update_page(
                page_id=page_id,
                title=title,
                body=body,
                representation="storage",
                minor_edit=False,
            )
        except Exception as exc:
            self._handle_error(exc, "update_page")
            return {}

    def delete_page(self, page_id: str) -> dict[str, Any]:
        """Delete a page by ID."""
        try:
            self._api.remove_page(page_id)
            return {"deleted": True, "page_id": page_id}
        except Exception as exc:
            self._handle_error(exc, "delete_page")
            return {}

    def delete_page_by_title(
        self, space: str, title: str, *, cascade: bool = False,
    ) -> dict[str, Any]:
        """Delete a page by space and title."""
        page = self.get_page(space, title)
        if not page:
            from confpub.errors import ERR_IO_FILE_NOT_FOUND
            raise ConfpubError(
                ERR_IO_FILE_NOT_FOUND,
                f"Page '{title}' not found in space '{space}'",
            )
        page_id = str(page["id"])
        if cascade:
            children = self.get_page_children(page_id)
            for child in children:
                self.delete_page(str(child["id"]))
        return self.delete_page(page_id)

    def get_page_children(self, page_id: str) -> list[dict[str, Any]]:
        """Get child pages of a page."""
        try:
            result = self._api.get_page_child_by_type(page_id, type="page")
            return result if isinstance(result, list) else []
        except Exception as exc:
            self._handle_error(exc, "get_page_children")
            return []

    # ------------------------------------------------------------------
    # Space operations
    # ------------------------------------------------------------------

    def list_spaces(self) -> list[dict[str, Any]]:
        """List accessible spaces."""
        try:
            result = self._api.get_all_spaces(expand="description.plain")
            if isinstance(result, dict):
                return result.get("results", [])
            return result if isinstance(result, list) else []
        except Exception as exc:
            self._handle_error(exc, "list_spaces")
            return []

    def list_pages(self, space: str) -> list[dict[str, Any]]:
        """List pages in a space."""
        try:
            result = self._api.get_all_pages_from_space(space, expand="version")
            return result if isinstance(result, list) else []
        except Exception as exc:
            self._handle_error(exc, "list_pages")
            return []

    # ------------------------------------------------------------------
    # Attachment operations
    # ------------------------------------------------------------------

    def get_attachments(self, page_id: str) -> list[dict[str, Any]]:
        """List attachments on a page."""
        try:
            result = self._api.get_attachments_from_content(page_id)
            if isinstance(result, dict):
                return result.get("results", [])
            return result if isinstance(result, list) else []
        except Exception as exc:
            self._handle_error(exc, "get_attachments")
            return []

    def upload_attachment(self, page_id: str, filepath: str) -> dict[str, Any]:
        """Upload an attachment to a page."""
        try:
            result = self._api.attach_file(filepath, page_id=page_id)
            return result if isinstance(result, dict) else {"uploaded": True, "file": filepath}
        except Exception as exc:
            self._handle_error(exc, "upload_attachment")
            return {}

    # ------------------------------------------------------------------
    # Fingerprinting
    # ------------------------------------------------------------------

    def fingerprint_page(self, page_id: str) -> str | None:
        """Get SHA-256 fingerprint of a page's storage format body."""
        try:
            page = self._api.get_page_by_id(page_id, expand="body.storage")
            body = page.get("body", {}).get("storage", {}).get("value", "")
            return hashlib.sha256(body.encode("utf-8")).hexdigest()
        except Exception:
            return None


def _slim_page(page: dict[str, Any]) -> dict[str, Any]:
    """Extract agent-relevant fields from a raw Confluence page object."""
    result: dict[str, Any] = {
        "id": page.get("id"),
        "title": page.get("title"),
    }
    version = page.get("version")
    if isinstance(version, dict):
        result["version"] = {
            "number": version.get("number"),
            "when": version.get("when"),
            "by": version.get("by", {}).get("displayName") if isinstance(version.get("by"), dict) else None,
        }
    body = page.get("body", {}).get("storage", {}).get("value")
    if body is not None:
        result["body_storage"] = body
    links = page.get("_links", {})
    if "webui" in links:
        base = links.get("base", "")
        result["webui"] = base + links["webui"]
    return result


def build_client(
    cli_url: str | None = None,
    cli_user: str | None = None,
    cli_token: str | None = None,
) -> ConfluenceClient:
    """Build a ConfluenceClient from resolved config."""
    config = load_config(cli_url=cli_url, cli_user=cli_user, cli_token=cli_token)
    return ConfluenceClient(config)
