"""Confluence API wrapper using atlassian-python-api.

Provides a clean interface that translates library exceptions into ConfpubError.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from confpub.config import ResolvedConfig, load_config
from confpub.errors import (
    ERR_AUTH_FORBIDDEN,
    ERR_CONFLICT_PAGE_EXISTS,
    ERR_IO_CONNECTION,
    ERR_IO_TIMEOUT,
    ERR_INTERNAL_SDK,
    ERR_VALIDATION_REQUIRED,
    ConfpubError,
)


class ConfluenceClient:
    """Wrapper around atlassian.Confluence that raises ConfpubError."""

    def __init__(self, config: ResolvedConfig) -> None:
        config.require_credentials()
        self._config = config
        self._api = self._build_api(config)
        self._call_count = 0

        # Suppress noisy atlassian-python-api logging (e.g. "Can't find 'X' page")
        from confpub.output import is_verbose

        atlassian_logger = logging.getLogger("atlassian")
        atlassian_logger.setLevel(logging.WARNING if is_verbose() else logging.CRITICAL)

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

        kwargs["verify_ssl"] = config.ssl_verify

        # Suppress noisy per-request InsecureRequestWarning when SSL
        # verification is disabled (common in corporate environments).
        if not config.ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        return Confluence(**kwargs)

    def _handle_error(self, exc: Exception, context: str = "") -> None:
        """Translate atlassian-python-api exceptions to ConfpubError."""
        msg = str(exc)
        # HTTPError is a subclass of OSError — let it fall through to
        # string matching so we classify by HTTP status, not as a file error.
        try:
            from requests.exceptions import HTTPError
            is_http = isinstance(exc, HTTPError)
        except ImportError:
            is_http = False
        if not is_http and isinstance(exc, (FileNotFoundError, OSError)) and not isinstance(exc, ConnectionError):
            from confpub.errors import ERR_IO_FILE_NOT_FOUND
            raise ConfpubError(
                ERR_IO_FILE_NOT_FOUND,
                f"File error ({context}): {msg}",
                retryable=False,
                suggested_action="fix_input",
            ) from exc
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
                suggested_action="check_input",
                details={"note": "Confluence returns HTTP 403 for both forbidden and nonexistent resources. Verify the resource exists."},
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
                suggested_action="check_input",
                details={"note": "This may indicate a nonexistent resource; Confluence returns 403 for both."},
            ) from exc
        # Not found (404, "not found", or Java NotFoundException)
        lower = msg.lower()
        if "404" in msg or "not found" in lower or "notfound" in lower:
            from confpub.errors import ERR_VALIDATION_NOT_FOUND
            raise ConfpubError(
                ERR_VALIDATION_NOT_FOUND,
                f"Resource not found ({context}): {msg}",
            ) from exc
        raise ConfpubError(ERR_INTERNAL_SDK, f"Unexpected API error ({context}): {msg}") from exc

    # ------------------------------------------------------------------
    # Page operations
    # ------------------------------------------------------------------

    def get_page(self, space: str, title: str) -> dict[str, Any] | None:
        """Get a page by space key and title."""
        self._call_count += 1
        try:
            result = self._api.get_page_by_title(space, title, expand="version,body.storage,space,ancestors")
            return result if result else None
        except Exception as exc:
            self._handle_error(exc, "get_page")
            return None  # unreachable, but satisfies type checker

    def get_page_by_id(self, page_id: str) -> dict[str, Any]:
        """Get a page by its Confluence ID."""
        self._call_count += 1
        try:
            return self._api.get_page_by_id(page_id, expand="version,body.storage,space,ancestors")
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
        self._call_count += 1
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
        self._call_count += 1
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
        self._call_count += 1
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
            from confpub.errors import ERR_VALIDATION_NOT_FOUND
            raise ConfpubError(
                ERR_VALIDATION_NOT_FOUND,
                f"Page '{title}' not found in space '{space}'",
                retryable=False,
            )
        page_id = str(page["id"])
        if cascade:
            self._delete_descendants(page_id)
        return self.delete_page(page_id)

    def get_descendant_ids(self, page_id: str) -> set[str]:
        """Recursively collect all descendant page IDs."""
        ids: set[str] = set()
        children = self.get_page_children(page_id)
        for child in children:
            child_id = str(child["id"])
            ids.add(child_id)
            ids.update(self.get_descendant_ids(child_id))
        return ids

    def _delete_descendants(self, page_id: str) -> None:
        """Recursively delete all descendants depth-first (leaves first)."""
        children = self.get_page_children(page_id)
        for child in children:
            child_id = str(child["id"])
            self._delete_descendants(child_id)
            self.delete_page(child_id)

    def get_page_children(self, page_id: str) -> list[dict[str, Any]]:
        """Get child pages of a page (with pagination)."""
        return self._get_children_paginated(page_id)

    def get_page_children_deep(self, page_id: str) -> list[dict[str, Any]]:
        """Get child pages with version and body.storage expanded (with pagination)."""
        return self._get_children_paginated(page_id, expand="version,body.storage")

    def _get_children_paginated(
        self, page_id: str, *, expand: str | None = None, limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Fetch all child pages, handling pagination."""
        all_children: list[dict[str, Any]] = []
        start = 0
        while True:
            self._call_count += 1
            try:
                kwargs: dict[str, Any] = {
                    "type": "page",
                    "start": start,
                    "limit": limit,
                }
                if expand:
                    kwargs["expand"] = expand
                result = self._api.get_page_child_by_type(page_id, **kwargs)
                batch = result if isinstance(result, list) else []
            except Exception as exc:
                self._handle_error(exc, "get_page_children")
                return all_children
            if not batch:
                break
            all_children.extend(batch)
            if len(batch) < limit:
                break
            start += limit
        return all_children

    def get_page_ancestors(self, page_id: str) -> list[dict[str, Any]]:
        """Get the ancestor chain of a page (root first, immediate parent last)."""
        self._call_count += 1
        try:
            page = self._api.get_page_by_id(page_id, expand="ancestors")
            return page.get("ancestors", [])
        except Exception as exc:
            self._handle_error(exc, "get_page_ancestors")
            return []

    # ------------------------------------------------------------------
    # Space operations
    # ------------------------------------------------------------------

    def list_spaces(self) -> list[dict[str, Any]]:
        """List accessible spaces."""
        self._call_count += 1
        try:
            result = self._api.get_all_spaces(expand="description.plain")
            if isinstance(result, dict):
                raw = result.get("results", [])
            elif isinstance(result, list):
                raw = result
            else:
                raw = []
            base_url = self._config.base_url.rstrip("/") if self._config.base_url else ""
            return [_slim_space(s, base_url=base_url, is_cloud=self._config.is_cloud) for s in raw]
        except Exception as exc:
            self._handle_error(exc, "list_spaces")
            return []

    def list_pages(self, space: str, *, start: int = 0, limit: int = 25) -> dict[str, Any]:
        """List pages in a space.

        Returns a dict with keys: pages, start, limit, size, has_more.
        """
        self._call_count += 1
        try:
            result = self._api.get_all_pages_from_space(
                space, start=start, limit=limit, expand="version",
            )
            pages = result if isinstance(result, list) else []
            return {
                "pages": pages,
                "start": start,
                "limit": limit,
                "size": len(pages),
                "has_more": len(pages) >= limit,
            }
        except Exception as exc:
            self._handle_error(exc, "list_pages")
            return {"pages": [], "start": start, "limit": limit, "size": 0, "has_more": False}

    # ------------------------------------------------------------------
    # Attachment operations
    # ------------------------------------------------------------------

    def get_attachments(self, page_id: str) -> list[dict[str, Any]]:
        """List attachments on a page."""
        self._call_count += 1
        try:
            result = self._api.get_attachments_from_content(page_id)
            if isinstance(result, dict):
                return result.get("results", [])
            return result if isinstance(result, list) else []
        except Exception as exc:
            self._handle_error(exc, "get_attachments")
            return []

    def download_attachment(
        self, page_id: str, filename: str, download_path: str,
        *, raise_on_error: bool = False,
    ) -> bool:
        """Download an attachment from a page to a local file.

        Returns True if the download succeeded, False if the attachment was
        not found or the download failed.  When *raise_on_error* is True,
        raises ConfpubError instead of returning False (used by the CLI
        ``attachment download`` command for clear error reporting).
        """
        self._call_count += 1
        import os

        attachments = self.get_attachments(page_id)
        target = None
        fname_lower = filename.lower()
        for att in attachments:
            if (att.get("title", "").lower() == fname_lower
                    or att.get("filename", "").lower() == fname_lower):
                target = att
                break
        if target is None:
            if raise_on_error:
                from confpub.errors import ERR_VALIDATION_NOT_FOUND
                raise ConfpubError(
                    ERR_VALIDATION_NOT_FOUND,
                    f"Attachment '{filename}' not found on page {page_id}",
                )
            return False

        download_url = target.get("_links", {}).get("download", "")
        if not download_url:
            if raise_on_error:
                from confpub.errors import ERR_VALIDATION_NOT_FOUND
                raise ConfpubError(
                    ERR_VALIDATION_NOT_FOUND,
                    f"Attachment '{filename}' has no download URL on page {page_id}",
                )
            return False

        try:
            # If the API already returned an absolute URL, use it directly.
            # Otherwise, prepend self._api.url which includes the context
            # path (e.g. /wiki on Cloud, or /confluence on some DC setups).
            if download_url.startswith(("http://", "https://")):
                full_url = download_url
            else:
                full_url = self._api.url.rstrip("/") + download_url

            response = self._api._session.get(full_url, stream=True)
            response.raise_for_status()

            os.makedirs(os.path.dirname(download_path), exist_ok=True)
            with open(download_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as exc:
            if raise_on_error:
                from confpub.errors import ERR_IO_CONNECTION
                raise ConfpubError(
                    ERR_IO_CONNECTION,
                    f"Failed to download attachment '{filename}' from page {page_id}: {exc}",
                ) from exc
            # Attachment download failures are non-fatal — the caller
            # records a warning and continues with the remaining files.
            return False

    def upload_attachment(self, page_id: str, filepath: str) -> dict[str, Any]:
        """Upload an attachment to a page."""
        self._call_count += 1
        try:
            import mimetypes
            content_type, _ = mimetypes.guess_type(filepath)
            kwargs: dict[str, Any] = {"page_id": page_id}
            if content_type:
                kwargs["content_type"] = content_type
            result = self._api.attach_file(filepath, **kwargs)
            if isinstance(result, dict):
                # API returns {"results": [...]} wrapper — extract the attachment
                if "results" in result and isinstance(result["results"], list) and result["results"]:
                    return _slim_attachment(result["results"][0])
                return _slim_attachment(result)
            return {"uploaded": True, "file": filepath}
        except Exception as exc:
            self._handle_error(exc, "upload_attachment")
            return {}

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        cql: str,
        *,
        start: int = 0,
        limit: int = 25,
        include_archived_spaces: bool = False,
        excerpt_length: int = 200,
    ) -> dict[str, Any]:
        """Search Confluence using CQL.

        Returns a dict with keys: results, total, start, limit, has_more.
        ``excerpt_length`` caps each excerpt at *n* characters (0 = unlimited).
        """
        self._call_count += 1
        try:
            raw = self._api.get("rest/api/search", params={
                "cql": cql,
                "start": start,
                "limit": limit,
                "excerpt": "highlight",
                "includeArchivedSpaces": include_archived_spaces,
            })
        except Exception as exc:
            msg = str(exc)
            if "400" in msg or "cannot be parsed" in msg.lower():
                raise ConfpubError(
                    ERR_VALIDATION_REQUIRED,
                    f"Invalid CQL query: {msg}",
                    details={"cql": cql},
                ) from exc
            self._handle_error(exc, "search")
            return {}  # unreachable

        base_url = self._config.base_url.rstrip("/")
        results_raw = raw.get("results", []) if isinstance(raw, dict) else []
        total = raw.get("totalSize", 0) if isinstance(raw, dict) else 0

        api_start = raw.get("start", start) if isinstance(raw, dict) else start
        api_limit = raw.get("limit", limit) if isinstance(raw, dict) else limit

        results = [
            _slim_search_result(r, base_url=base_url, is_cloud=self._config.is_cloud, excerpt_length=excerpt_length)
            for r in results_raw
        ]
        return {
            "results": results,
            "total": total,
            "start": api_start,
            "limit": api_limit,
            "has_more": (api_start + api_limit) < total,
        }

    # ------------------------------------------------------------------
    # Label operations
    # ------------------------------------------------------------------

    def get_labels(self, page_id: str) -> list[dict[str, Any]]:
        """Get labels on a page."""
        self._call_count += 1
        try:
            result = self._api.get_page_labels(page_id)
            raw = result.get("results", []) if isinstance(result, dict) else (result if isinstance(result, list) else [])
            return [_slim_label(lbl) for lbl in raw]
        except Exception as exc:
            self._handle_error(exc, "get_labels")
            return []

    def set_labels(self, page_id: str, labels: list[str]) -> list[dict[str, Any]]:
        """Set labels on a page (additive — does not remove existing labels)."""
        results: list[dict[str, Any]] = []
        for lbl in labels:
            self._call_count += 1
            try:
                result = self._api.set_page_label(page_id, lbl)
                if isinstance(result, dict) and result.get("name"):
                    results.append(_slim_label(result))
                elif isinstance(result, list):
                    results.extend(
                        _slim_label(r) if isinstance(r, dict) and r.get("name")
                        else {"name": lbl, "prefix": "global", "id": None}
                        for r in result
                    )
                else:
                    results.append({"name": lbl, "prefix": "global", "id": None})
            except Exception as exc:
                self._handle_error(exc, "set_labels")
        return results

    def remove_label(self, page_id: str, label: str) -> dict[str, Any]:
        """Remove a label from a page."""
        self._call_count += 1
        try:
            self._api.remove_page_label(page_id, label)
            return {"removed": True, "label": label, "page_id": page_id}
        except Exception as exc:
            self._handle_error(exc, "remove_label")
            return {}

    # ------------------------------------------------------------------
    # Comment operations
    # ------------------------------------------------------------------

    def get_comments(self, page_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
        """Return comments on a page."""
        self._call_count += 1
        try:
            response = self._api.get_page_comments(
                page_id,
                expand="body.storage,version,history",
                depth="all",
                limit=limit,
            )
            results = response.get("results", []) if isinstance(response, dict) else []
            comments = []
            for c in results:
                history = c.get("history", {})
                created_by = history.get("createdBy", {})
                comments.append({
                    "id": c.get("id"),
                    "body_storage": (c.get("body", {}).get("storage", {}).get("value", "")),
                    "created_by": created_by.get("displayName", created_by.get("username", "")),
                    "created_date": history.get("createdDate", ""),
                    "version": c.get("version", {}).get("number"),
                })
            return comments
        except Exception as exc:
            self._handle_error(exc, "get_comments")
            return []

    def add_comment(self, page_id: str, body: str) -> dict[str, Any]:
        """Add a comment to a page."""
        self._call_count += 1
        try:
            result = self._api.add_comment(page_id, body)
            return {
                "id": result.get("id") if isinstance(result, dict) else None,
                "page_id": page_id,
                "created": True,
            }
        except Exception as exc:
            self._handle_error(exc, "add_comment")
            return {}

    # ------------------------------------------------------------------
    # Page move
    # ------------------------------------------------------------------

    def move_page(
        self,
        space_key: str,
        page_id: str,
        target_title: str | None = None,
        target_id: str | None = None,
        position: str = "append",
    ) -> dict[str, Any]:
        """Move a page under a new parent."""
        self._call_count += 1
        try:
            result = self._api.move_page(
                space_key, page_id,
                target_title=target_title,
                target_id=target_id,
                position=position,
            )
            base_url = self._config.base_url.rstrip("/") if self._config.base_url else ""
            page_data: dict[str, Any] | None = None
            if isinstance(result, dict):
                # The API may return the page directly or nested under a 'page' key
                raw_page = result.get("page", result) if "page" in result else result
                if raw_page.get("id"):
                    page_data = _slim_page(raw_page, base_url=base_url, is_cloud=self._config.is_cloud)
            return {
                "moved": True,
                "page_id": page_id,
                "target_parent": target_title or target_id,
                "page": page_data,
            }
        except Exception as exc:
            self._handle_error(exc, "move_page")
            return {}

    # ------------------------------------------------------------------
    # Page properties
    # ------------------------------------------------------------------

    def get_page_properties(self, page_id: str) -> list[dict[str, Any]]:
        """List all properties on a page."""
        self._call_count += 1
        try:
            response = self._api.get_page_properties(page_id)
            results = response.get("results", []) if isinstance(response, dict) else []
            return [
                {
                    "key": p.get("key"),
                    "value": p.get("value"),
                    "version": p.get("version", {}).get("number") if isinstance(p.get("version"), dict) else None,
                }
                for p in results
            ]
        except Exception as exc:
            self._handle_error(exc, "get_page_properties")
            return []

    def get_page_property(self, page_id: str, key: str) -> dict[str, Any]:
        """Get a single property by key."""
        self._call_count += 1
        try:
            result = self._api.get_page_property(page_id, key)
            return {
                "key": result.get("key"),
                "value": result.get("value"),
                "version": result.get("version", {}).get("number") if isinstance(result.get("version"), dict) else None,
                "page_id": page_id,
            }
        except Exception as exc:
            self._handle_error(exc, "get_page_property")
            return {}

    def set_page_property(self, page_id: str, key: str, value: Any, *, version: int | None = None) -> dict[str, Any]:
        """Create or update a page property.

        If version is provided, performs an update (PUT). Otherwise attempts
        create (POST), falling back to update if the key already exists.
        """
        self._call_count += 1
        try:
            if version is not None:
                # Explicit update
                data = {"key": key, "value": value, "version": {"number": version}}
                self._api.update_page_property(page_id, data)
                return {"key": key, "value": value, "version": version, "page_id": page_id, "created": False}

            # Try create first
            data = {"key": key, "value": value}
            try:
                self._api.set_page_property(page_id, data)
                return {"key": key, "value": value, "version": 1, "page_id": page_id, "created": True}
            except Exception:
                # Key may already exist — fetch current version and update
                self._call_count += 1
                existing = self._api.get_page_property(page_id, key)
                current_version = existing.get("version", {}).get("number", 1) if isinstance(existing, dict) else 1
                new_version = current_version + 1
                update_data = {"key": key, "value": value, "version": {"number": new_version}}
                self._api.update_page_property(page_id, update_data)
                return {"key": key, "value": value, "version": new_version, "page_id": page_id, "created": False}
        except Exception as exc:
            self._handle_error(exc, "set_page_property")
            return {}

    def delete_page_property(self, page_id: str, key: str) -> dict[str, Any]:
        """Delete a page property by key."""
        self._call_count += 1
        try:
            self._api.delete_page_property(page_id, key)
            return {"deleted": True, "key": key, "page_id": page_id}
        except ConfpubError:
            raise
        except Exception as exc:
            msg = str(exc)
            # Confluence returns PermissionException for nonexistent properties
            if "cannot delete" in msg.lower() or ("property" in msg.lower() and "not found" in msg.lower()):
                from confpub.errors import ERR_VALIDATION_NOT_FOUND
                raise ConfpubError(
                    ERR_VALIDATION_NOT_FOUND,
                    f"Property '{key}' not found on page {page_id}",
                    suggested_action="check_input",
                ) from exc
            self._handle_error(exc, "delete_page_property")
            return {}

    # ------------------------------------------------------------------
    # Page history / versions
    # ------------------------------------------------------------------

    def get_page_history(self, page_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
        """Get version history of a page."""
        self._call_count += 1
        try:
            # history() returns the full history object; we also need individual versions
            page = self._api.get_page_by_id(page_id, expand="version,history")
            current_version = page.get("version", {}).get("number", 1) if isinstance(page, dict) else 1

            versions = []
            # Fetch individual versions from newest to oldest
            for v in range(current_version, max(0, current_version - limit), -1):
                self._call_count += 1
                try:
                    ver = self._api.get_content_history_by_version_number(page_id, v)
                    if isinstance(ver, dict):
                        by = ver.get("by", {})
                        versions.append({
                            "number": ver.get("number", v),
                            "when": ver.get("when", ""),
                            "by": by.get("displayName", by.get("username", "")) if isinstance(by, dict) else "",
                            "message": ver.get("message", ""),
                        })
                except Exception:
                    pass  # skip versions we can't access
            return versions
        except Exception as exc:
            self._handle_error(exc, "get_page_history")
            return []

    def get_page_version(self, page_id: str, version_number: int) -> dict[str, Any]:
        """Get a specific version of a page with its body."""
        self._call_count += 1
        try:
            ver = self._api.get_content_history_by_version_number(page_id, version_number)
            if not isinstance(ver, dict):
                from confpub.errors import ERR_VALIDATION_NOT_FOUND
                raise ConfpubError(ERR_VALIDATION_NOT_FOUND, f"Version {version_number} not found for page {page_id}")

            by = ver.get("by", {})
            result: dict[str, Any] = {
                "id": page_id,
                "version": ver.get("number", version_number),
                "when": ver.get("when", ""),
                "by": by.get("displayName", by.get("username", "")) if isinstance(by, dict) else "",
                "message": ver.get("message", ""),
            }

            # Try to get the body at this version
            self._call_count += 1
            try:
                page = self._api.get_page_by_id(page_id, expand="body.storage,version", version=version_number)
                if isinstance(page, dict):
                    result["title"] = page.get("title", "")
                    result["body_storage"] = page.get("body", {}).get("storage", {}).get("value", "")
            except Exception:
                pass  # body retrieval is best-effort

            return result
        except ConfpubError:
            raise
        except Exception as exc:
            self._handle_error(exc, "get_page_version")
            return {}

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_page(self, page_id: str, fmt: str, output_path: str) -> dict[str, Any]:
        """Export a page as PDF or Word and write to output_path."""
        self._call_count += 1
        import os
        try:
            if fmt == "pdf":
                content = self._api.get_page_as_pdf(page_id)
            elif fmt == "word":
                content = self._api.get_page_as_word(page_id)
            else:
                raise ConfpubError(ERR_VALIDATION_REQUIRED, f"Unsupported export format: {fmt}")

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(content)
            file_size = os.path.getsize(output_path)
            return {
                "exported": True,
                "page_id": page_id,
                "format": fmt,
                "output_path": os.path.abspath(output_path),
                "file_size": file_size,
            }
        except ConfpubError:
            raise
        except Exception as exc:
            self._handle_error(exc, "export_page")
            return {}

    # ------------------------------------------------------------------
    # Attachment delete
    # ------------------------------------------------------------------

    def delete_attachment(self, page_id: str, filename: str) -> dict[str, Any]:
        """Delete an attachment from a page by filename."""
        self._call_count += 1
        try:
            # Find the attachment ID by filename (case-insensitive)
            attachments = self.get_attachments(page_id)
            target = None
            fname_lower = filename.lower()
            for att in attachments:
                if (att.get("title", "").lower() == fname_lower
                        or att.get("filename", "").lower() == fname_lower):
                    target = att
                    break
            if target is None:
                from confpub.errors import ERR_VALIDATION_NOT_FOUND
                raise ConfpubError(
                    ERR_VALIDATION_NOT_FOUND,
                    f"Attachment '{filename}' not found on page {page_id}",
                )
            att_id = target.get("id")
            self._api.remove_content(att_id)
            return {"deleted": True, "page_id": page_id, "filename": filename, "attachment_id": att_id}
        except ConfpubError:
            raise
        except Exception as exc:
            self._handle_error(exc, "delete_attachment")
            return {}

    # ------------------------------------------------------------------
    # Space details
    # ------------------------------------------------------------------

    def get_space(self, space_key: str) -> dict[str, Any]:
        """Get detailed information about a space."""
        self._call_count += 1
        try:
            result = self._api.get_space(space_key, expand="description.plain,homepage")
            base_url = self._config.base_url.rstrip("/") if self._config.base_url else ""
            space = _slim_space(result, base_url=base_url, is_cloud=self._config.is_cloud)
            # Add homepage info
            homepage = result.get("homepage", {}) if isinstance(result, dict) else {}
            if isinstance(homepage, dict) and homepage.get("id"):
                space["homepage_id"] = homepage.get("id")
                space["homepage_title"] = homepage.get("title")
            return space
        except Exception as exc:
            self._handle_error(exc, "get_space")
            return {}

    # ------------------------------------------------------------------
    # Fingerprinting
    # ------------------------------------------------------------------

    def fingerprint_page(self, page_id: str) -> str | None:
        """Get SHA-256 fingerprint of a page's storage format body."""
        self._call_count += 1
        try:
            page = self._api.get_page_by_id(page_id, expand="body.storage")
            body = page.get("body", {}).get("storage", {}).get("value", "")
            return hashlib.sha256(body.encode("utf-8")).hexdigest()
        except Exception:
            return None


def _webui_base(base_url: str, is_cloud: bool) -> str:
    """Return the correct base URL for webui links.

    Cloud instances need ``/wiki`` in the path; DC/Server do not.
    Handles base_url configured with or without the ``/wiki`` suffix.
    """
    base = base_url.rstrip("/")
    if is_cloud and not base.endswith("/wiki"):
        base += "/wiki"
    return base


def build_page_url(
    base_url: str, is_cloud: bool, space: str, page_id: str, title: str = "",
) -> str:
    """Construct a full webui URL for a Confluence page."""
    base = _webui_base(base_url, is_cloud)
    if title:
        encoded_title = title.replace(" ", "+")
        return f"{base}/spaces/{space}/pages/{page_id}/{encoded_title}"
    return f"{base}/spaces/{space}/pages/{page_id}"


def _slim_page(page: dict[str, Any], *, base_url: str = "", is_cloud: bool = False) -> dict[str, Any]:
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
    ancestors = page.get("ancestors")
    if isinstance(ancestors, list) and ancestors:
        parent = ancestors[-1]
        result["parent_id"] = parent.get("id")
        result["parent_title"] = parent.get("title")
    links = page.get("_links", {})
    if "webui" in links:
        base = _webui_base(base_url, is_cloud) if base_url else links.get("base", "")
        result["webui"] = base + links["webui"]
    return result


def _slim_space(space: dict[str, Any], *, base_url: str = "", is_cloud: bool = False) -> dict[str, Any]:
    """Extract agent-relevant fields from a raw Confluence space object."""
    result: dict[str, Any] = {
        "id": space.get("id"),
        "key": space.get("key"),
        "name": space.get("name"),
        "type": space.get("type"),
    }
    desc = space.get("description", {})
    if isinstance(desc, dict):
        plain = desc.get("plain", {})
        if isinstance(plain, dict):
            value = plain.get("value", "")
            if value:
                result["description"] = value
    links = space.get("_links", {})
    if "webui" in links:
        webui_path = links.get("webui", "")
        if base_url and webui_path:
            base = _webui_base(base_url, is_cloud)
            result["webui"] = base + webui_path
        else:
            result["webui"] = webui_path
    return result


def _slim_attachment(att: dict[str, Any]) -> dict[str, Any]:
    """Extract agent-relevant fields from a raw Confluence attachment object."""
    result: dict[str, Any] = {
        "id": att.get("id"),
        "title": att.get("title"),
    }
    version = att.get("version")
    if isinstance(version, dict):
        result["version"] = version.get("number")
    extensions = att.get("extensions", {})
    if isinstance(extensions, dict):
        file_size = extensions.get("fileSize")
        if file_size is not None:
            result["file_size"] = file_size
        media_type = extensions.get("mediaType")
        if media_type:
            result["media_type"] = media_type
    metadata = att.get("metadata", {})
    if isinstance(metadata, dict):
        media_type = metadata.get("mediaType")
        if media_type and "media_type" not in result:
            result["media_type"] = media_type
    return result


def _slim_label(lbl: dict[str, Any]) -> dict[str, Any]:
    """Extract agent-relevant fields from a raw Confluence label object."""
    return {
        "name": lbl.get("name", ""),
        "prefix": lbl.get("prefix", "global"),
        "id": lbl.get("id"),
    }


def _slim_search_result(
    item: dict[str, Any],
    *,
    base_url: str = "",
    is_cloud: bool = False,
    excerpt_length: int = 0,
) -> dict[str, Any]:
    """Extract agent-relevant fields from a raw Confluence search result.

    Only includes fields that have a non-None, non-empty value to minimise
    token usage when results are consumed by an LLM.  ``excerpt_length``
    caps the excerpt at *n* characters (0 = unlimited).
    """
    entity_type = item.get("entityType", "content")

    result: dict[str, Any] = {}

    def _set(key: str, value: Any) -> None:
        if value is not None and value != "":
            result[key] = value

    if entity_type == "content":
        content = item.get("content", {})
        _set("id", content.get("id"))
        _set("type", content.get("type"))
        _set("title", item.get("title") or content.get("title"))
        _set("status", content.get("status"))

        webui = content.get("_links", {}).get("webui", "")
        if webui:
            _set("url", _webui_base(base_url, is_cloud) + webui if base_url else webui)

        _set("space_key", content.get("space", {}).get("key"))

        version = content.get("version")
        if isinstance(version, dict):
            _set("last_modified", version.get("when"))

        container = content.get("container")
        if isinstance(container, dict):
            _set("container_title", container.get("title") or container.get("name"))

    elif entity_type == "space":
        space = item.get("space", {})
        _set("id", space.get("id"))
        result["type"] = "space"
        _set("title", item.get("title") or space.get("name"))
        _set("space_key", space.get("key"))

    elif entity_type == "user":
        user = item.get("user", {})
        _set("id", user.get("accountId") or user.get("userKey"))
        result["type"] = "user"
        _set("title", item.get("title") or user.get("displayName"))

    else:
        result["type"] = entity_type
        _set("title", item.get("title"))

    # Only tag entity_type when it differs from the default
    if entity_type != "content":
        result["entity_type"] = entity_type

    # Excerpt — strip HTML tags, then truncate
    excerpt = item.get("excerpt", "")
    if excerpt:
        excerpt = re.sub(r"<[^>]+>", "", excerpt)
        if excerpt_length and len(excerpt) > excerpt_length:
            excerpt = excerpt[:excerpt_length].rsplit(" ", 1)[0] + "…"
    _set("excerpt", excerpt)

    return result


def build_client(
    cli_url: str | None = None,
    cli_user: str | None = None,
    cli_token: str | None = None,
) -> ConfluenceClient:
    """Build a ConfluenceClient from resolved config."""
    config = load_config(cli_url=cli_url, cli_user=cli_user, cli_token=cli_token)
    return ConfluenceClient(config)
