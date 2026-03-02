"""Tests for confpub.confluence module."""

from unittest.mock import MagicMock, patch

import pytest

from confpub.config import ResolvedConfig
from confpub.confluence import ConfluenceClient, _slim_page, _slim_search_result, _webui_base, build_page_url
from confpub.errors import (
    ERR_AUTH_FORBIDDEN,
    ERR_AUTH_REQUIRED,
    ERR_CONFLICT_PAGE_EXISTS,
    ERR_IO_CONNECTION,
    ERR_IO_FILE_NOT_FOUND,
    ERR_VALIDATION_NOT_FOUND,
    ERR_INTERNAL_SDK,
    ERR_VALIDATION_REQUIRED,
    ConfpubError,
)


@pytest.fixture
def mock_config():
    return ResolvedConfig(
        base_url="https://test.atlassian.net/wiki",
        user="user@test.com",
        token="test_token",
        token_source="env_var",
    )


@pytest.fixture
def client(mock_config):
    with patch("confpub.confluence.ConfluenceClient._build_api") as mock_build:
        mock_api = MagicMock()
        mock_build.return_value = mock_api
        c = ConfluenceClient(mock_config)
        c._mock_api = mock_api
        return c


class TestClientConstruction:
    def test_requires_credentials(self):
        config = ResolvedConfig()
        with pytest.raises(ConfpubError) as exc_info:
            ConfluenceClient(config)
        assert exc_info.value.code == ERR_AUTH_REQUIRED


class TestGetPage:
    def test_returns_page(self, client):
        client._mock_api.get_page_by_title.return_value = {"id": "123", "title": "Test"}
        result = client.get_page("DEV", "Test")
        assert result["id"] == "123"
        client._mock_api.get_page_by_title.assert_called_once_with(
            "DEV", "Test", expand="version,body.storage,space,ancestors"
        )

    def test_returns_none_when_not_found(self, client):
        client._mock_api.get_page_by_title.return_value = None
        result = client.get_page("DEV", "Missing")
        assert result is None

    def test_handles_auth_error(self, client):
        client._mock_api.get_page_by_title.side_effect = Exception("401 Unauthorized")
        with pytest.raises(ConfpubError) as exc_info:
            client.get_page("DEV", "Test")
        assert exc_info.value.code == ERR_AUTH_FORBIDDEN


class TestCreatePage:
    def test_creates_page(self, client):
        client._mock_api.create_page.return_value = {"id": "456", "title": "New"}
        result = client.create_page("DEV", "New", "<p>body</p>")
        assert result["id"] == "456"

    def test_conflict_on_existing(self, client):
        client._mock_api.create_page.side_effect = Exception("409 already exists")
        with pytest.raises(ConfpubError) as exc_info:
            client.create_page("DEV", "Existing", "<p>body</p>")
        assert exc_info.value.code == ERR_CONFLICT_PAGE_EXISTS


class TestUpdatePage:
    def test_updates_page(self, client):
        client._mock_api.update_page.return_value = {"id": "123", "version": {"number": 2}}
        result = client.update_page("123", "Test", "<p>updated</p>")
        assert result["id"] == "123"


class TestDeletePage:
    def test_deletes_page(self, client):
        client._mock_api.remove_page.return_value = None
        result = client.delete_page("123")
        assert result["deleted"] is True


class TestCascadeDelete:
    def test_cascade_deletes_three_level_tree(self, client):
        """Cascade should delete grandchildren before children (depth-first)."""
        # Root -> Child -> Grandchild
        client._mock_api.get_page_by_title.return_value = {"id": "1", "title": "Root"}

        def get_children(page_id, **kwargs):
            if page_id == "1":
                return [{"id": "2", "title": "Child"}]
            if page_id == "2":
                return [{"id": "3", "title": "Grandchild"}]
            return []

        client._mock_api.get_page_child_by_type.side_effect = get_children
        client._mock_api.remove_page.return_value = None

        result = client.delete_page_by_title("DEV", "Root", cascade=True)

        assert result["deleted"] is True
        # Verify deletion order: grandchild first, then child, then root
        delete_calls = [str(call.args[0]) for call in client._mock_api.remove_page.call_args_list]
        assert delete_calls == ["3", "2", "1"]


class TestListSpaces:
    def test_returns_spaces(self, client):
        client._mock_api.get_all_spaces.return_value = {
            "results": [{"key": "DEV", "name": "Development"}]
        }
        spaces = client.list_spaces()
        assert len(spaces) == 1
        assert spaces[0]["key"] == "DEV"


class TestListPages:
    def test_returns_pages(self, client):
        client._mock_api.get_all_pages_from_space.return_value = [
            {"id": "1", "title": "Page A"},
            {"id": "2", "title": "Page B"},
        ]
        result = client.list_pages("DEV")
        assert len(result["pages"]) == 2
        assert result["size"] == 2
        assert result["start"] == 0
        assert result["limit"] == 25
        assert result["has_more"] is False

    def test_has_more_when_full_batch(self, client):
        """has_more should be True when batch size equals limit."""
        client._mock_api.get_all_pages_from_space.return_value = [
            {"id": str(i), "title": f"Page {i}"} for i in range(5)
        ]
        result = client.list_pages("DEV", limit=5)
        assert result["has_more"] is True
        assert result["size"] == 5

    def test_has_more_false_when_partial_batch(self, client):
        """has_more should be False when fewer results than limit."""
        client._mock_api.get_all_pages_from_space.return_value = [
            {"id": "1", "title": "Only Page"},
        ]
        result = client.list_pages("DEV", limit=25)
        assert result["has_more"] is False
        assert result["size"] == 1

    def test_pagination_params_passed_through(self, client):
        """start and limit should be passed through to the result."""
        client._mock_api.get_all_pages_from_space.return_value = []
        result = client.list_pages("DEV", start=50, limit=10)
        assert result["start"] == 50
        assert result["limit"] == 10


class TestAttachments:
    def test_get_attachments(self, client):
        client._mock_api.get_attachments_from_content.return_value = {
            "results": [{"title": "image.png"}]
        }
        result = client.get_attachments("123")
        assert len(result) == 1

    def test_upload_attachment(self, client):
        client._mock_api.attach_file.return_value = {"title": "file.png"}
        result = client.upload_attachment("123", "/tmp/file.png")
        assert result["title"] == "file.png"

    def test_upload_attachment_passes_content_type(self, client):
        """Suggestion 3: upload_attachment should detect and pass content_type for known types."""
        client._mock_api.attach_file.return_value = {"title": "readme.txt"}
        client.upload_attachment("123", "/tmp/readme.txt")
        call_kwargs = client._mock_api.attach_file.call_args
        assert call_kwargs[1].get("content_type") == "text/plain"

    def test_upload_attachment_png_content_type(self, client):
        """MIME type detection for .png files."""
        client._mock_api.attach_file.return_value = {"title": "image.png"}
        client.upload_attachment("123", "/tmp/image.png")
        call_kwargs = client._mock_api.attach_file.call_args
        assert call_kwargs[1].get("content_type") == "image/png"


class TestDownloadAttachment:
    def test_relative_url_uses_api_url(self, client, tmp_path):
        """Relative _links.download paths are prefixed with self._api.url."""
        client._mock_api.get_attachments_from_content.return_value = {
            "results": [{"title": "doc.pdf", "_links": {"download": "/download/attachments/99/doc.pdf"}}]
        }
        client._mock_api.url = "https://test.atlassian.net/wiki"
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"PDF_DATA"]
        client._mock_api._session.get.return_value = mock_resp

        dest = str(tmp_path / "doc.pdf")
        result = client.download_attachment("99", "doc.pdf", dest)

        assert result is True
        called_url = client._mock_api._session.get.call_args[0][0]
        assert called_url == "https://test.atlassian.net/wiki/download/attachments/99/doc.pdf"

    def test_absolute_url_used_directly(self, client, tmp_path):
        """If _links.download is already absolute, do not prepend base URL."""
        abs_url = "https://cdn.corp.com/files/doc.pdf"
        client._mock_api.get_attachments_from_content.return_value = {
            "results": [{"title": "doc.pdf", "_links": {"download": abs_url}}]
        }
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"DATA"]
        client._mock_api._session.get.return_value = mock_resp

        dest = str(tmp_path / "doc.pdf")
        result = client.download_attachment("99", "doc.pdf", dest)

        assert result is True
        called_url = client._mock_api._session.get.call_args[0][0]
        assert called_url == abs_url

    def test_dc_context_path_preserved(self, client, tmp_path):
        """DC behind /confluence context path must produce correct download URL."""
        client._mock_api.get_attachments_from_content.return_value = {
            "results": [{"title": "img.png", "_links": {"download": "/download/attachments/1/img.png"}}]
        }
        client._mock_api.url = "https://corp.com/confluence"
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"PNG"]
        client._mock_api._session.get.return_value = mock_resp

        dest = str(tmp_path / "img.png")
        result = client.download_attachment("1", "img.png", dest)

        assert result is True
        called_url = client._mock_api._session.get.call_args[0][0]
        assert called_url == "https://corp.com/confluence/download/attachments/1/img.png"

    def test_download_failure_returns_false(self, client, tmp_path):
        """HTTP errors during download should return False, not raise."""
        client._mock_api.get_attachments_from_content.return_value = {
            "results": [{"title": "bad.zip", "_links": {"download": "/download/bad.zip"}}]
        }
        client._mock_api.url = "https://test.atlassian.net/wiki"
        client._mock_api._session.get.side_effect = Exception("500 Server Error")

        dest = str(tmp_path / "bad.zip")
        result = client.download_attachment("1", "bad.zip", dest)

        assert result is False

    def test_attachment_not_found_returns_false(self, client, tmp_path):
        """Requesting a filename not in the attachments list returns False."""
        client._mock_api.get_attachments_from_content.return_value = {
            "results": [{"title": "other.png", "_links": {"download": "/dl/other.png"}}]
        }
        result = client.download_attachment("1", "missing.png", str(tmp_path / "x"))
        assert result is False


class TestLabels:
    def test_get_labels(self, client):
        client._mock_api.get_page_labels.return_value = {
            "results": [
                {"name": "api", "prefix": "global", "id": "1"},
                {"name": "docs", "prefix": "global", "id": "2"},
            ]
        }
        labels = client.get_labels("123")
        assert len(labels) == 2
        assert labels[0]["name"] == "api"
        assert labels[1]["name"] == "docs"
        assert labels[0]["prefix"] == "global"

    def test_get_labels_list_response(self, client):
        """Some API versions return a list directly instead of {results: [...]}."""
        client._mock_api.get_page_labels.return_value = [
            {"name": "tag1", "prefix": "global", "id": "10"},
        ]
        labels = client.get_labels("123")
        assert len(labels) == 1
        assert labels[0]["name"] == "tag1"

    def test_set_labels(self, client):
        client._mock_api.set_page_label.return_value = {"name": "api", "prefix": "global", "id": "1"}
        results = client.set_labels("123", ["api", "docs"])
        assert client._mock_api.set_page_label.call_count == 2
        assert len(results) == 2

    def test_set_labels_empty_response_falls_back(self, client):
        """When API returns empty/malformed dict, fall back to input label name."""
        client._mock_api.set_page_label.return_value = {}
        results = client.set_labels("123", ["my-label"])
        assert len(results) == 1
        assert results[0]["name"] == "my-label"
        assert results[0]["prefix"] == "global"
        assert results[0]["id"] is None

    def test_set_labels_list_response_with_empty_entries(self, client):
        """When API returns a list with empty entries, fall back to input label name."""
        client._mock_api.set_page_label.return_value = [{}]
        results = client.set_labels("123", ["tag1"])
        assert len(results) == 1
        assert results[0]["name"] == "tag1"

    def test_set_labels_call_count(self, client):
        """Each label should increment _call_count."""
        initial = client._call_count
        client._mock_api.set_page_label.return_value = {"name": "x", "prefix": "global", "id": "1"}
        client.set_labels("123", ["a", "b", "c"])
        assert client._call_count == initial + 3

    def test_remove_label(self, client):
        client._mock_api.remove_page_label.return_value = None
        result = client.remove_label("123", "old-tag")
        assert result["removed"] is True
        assert result["label"] == "old-tag"
        client._mock_api.remove_page_label.assert_called_once_with("123", "old-tag")

    def test_get_labels_error(self, client):
        client._mock_api.get_page_labels.side_effect = Exception("401 Unauthorized")
        with pytest.raises(ConfpubError) as exc_info:
            client.get_labels("123")
        assert exc_info.value.code == ERR_AUTH_FORBIDDEN

    def test_remove_label_error(self, client):
        client._mock_api.remove_page_label.side_effect = Exception("404 Not Found")
        with pytest.raises(ConfpubError) as exc_info:
            client.remove_label("123", "missing")
        assert exc_info.value.code == ERR_VALIDATION_NOT_FOUND


class TestComments:
    def test_add_comment(self, client):
        client._mock_api.add_comment.return_value = {"id": "comment_1"}
        result = client.add_comment("123", "<p>Nice page!</p>")
        assert result["created"] is True
        assert result["id"] == "comment_1"
        assert result["page_id"] == "123"
        client._mock_api.add_comment.assert_called_once_with("123", "<p>Nice page!</p>")

    def test_add_comment_error(self, client):
        client._mock_api.add_comment.side_effect = Exception("403 Forbidden")
        with pytest.raises(ConfpubError) as exc_info:
            client.add_comment("123", "<p>text</p>")
        assert exc_info.value.code == ERR_AUTH_FORBIDDEN


class TestMovePage:
    def test_move_page_by_title(self, client):
        client._mock_api.move_page.return_value = {"page": {"id": "123"}}
        result = client.move_page("DEV", "123", target_title="New Parent")
        assert result["moved"] is True
        assert result["page_id"] == "123"
        assert result["target_parent"] == "New Parent"
        client._mock_api.move_page.assert_called_once_with(
            "DEV", "123", target_title="New Parent", target_id=None, position="append",
        )

    def test_move_page_by_id(self, client):
        client._mock_api.move_page.return_value = {"page": {"id": "123"}}
        result = client.move_page("DEV", "123", target_id="456")
        assert result["moved"] is True
        assert result["target_parent"] == "456"
        client._mock_api.move_page.assert_called_once_with(
            "DEV", "123", target_title=None, target_id="456", position="append",
        )

    def test_move_page_returns_normalized_page(self, client):
        """Bug 3: move_page should return a 'page' key with slim page data, not raw 'result'."""
        client._mock_api.move_page.return_value = {
            "page": {"id": "123", "title": "My Page", "version": {"number": 3, "when": "2026-01-01"}}
        }
        result = client.move_page("DEV", "123", target_title="New Parent")
        assert "result" not in result
        assert "page" in result
        assert result["page"]["id"] == "123"
        assert result["page"]["title"] == "My Page"
        assert result["moved"] is True

    def test_move_page_not_found(self, client):
        client._mock_api.move_page.side_effect = Exception("404 Not Found")
        with pytest.raises(ConfpubError) as exc_info:
            client.move_page("DEV", "999", target_title="Missing")
        assert exc_info.value.code == ERR_VALIDATION_NOT_FOUND


class TestFingerprint:
    def test_fingerprint_page(self, client):
        client._mock_api.get_page_by_id.return_value = {
            "body": {"storage": {"value": "<p>hello</p>"}}
        }
        fp = client.fingerprint_page("123")
        assert fp is not None
        assert len(fp) == 64  # SHA-256 hex

    def test_fingerprint_returns_none_on_error(self, client):
        client._mock_api.get_page_by_id.side_effect = Exception("err")
        fp = client.fingerprint_page("123")
        assert fp is None


class TestErrorTranslation:
    def test_connection_error(self, client):
        client._mock_api.get_all_spaces.side_effect = Exception("ConnectionError: refused")
        with pytest.raises(ConfpubError) as exc_info:
            client.list_spaces()
        assert exc_info.value.code == ERR_IO_CONNECTION

    def test_403_has_check_input_action(self, client):
        """Bug 5: 403 errors should have suggested_action='check_input'."""
        client._mock_api.get_all_spaces.side_effect = Exception("403 Forbidden")
        with pytest.raises(ConfpubError) as exc_info:
            client.list_spaces()
        assert exc_info.value.code == ERR_AUTH_FORBIDDEN
        assert exc_info.value.suggested_action == "check_input"

    def test_permission_denied_has_check_input_action(self, client):
        """Bug 5: permission-denied errors should have suggested_action='check_input'."""
        client._mock_api.get_all_spaces.side_effect = Exception(
            "User does not have permission to view the content"
        )
        with pytest.raises(ConfpubError) as exc_info:
            client.list_spaces()
        assert exc_info.value.code == ERR_AUTH_FORBIDDEN
        assert exc_info.value.suggested_action == "check_input"

    def test_permission_error(self, client):
        client._mock_api.get_all_spaces.side_effect = Exception(
            "User does not have permission to view the content"
        )
        with pytest.raises(ConfpubError) as exc_info:
            client.list_spaces()
        assert exc_info.value.code == ERR_AUTH_FORBIDDEN

    def test_not_found_error(self, client):
        client._mock_api.get_all_spaces.side_effect = Exception("404 Not Found")
        with pytest.raises(ConfpubError) as exc_info:
            client.list_spaces()
        assert exc_info.value.code == ERR_VALIDATION_NOT_FOUND

    def test_generic_error(self, client):
        client._mock_api.get_all_spaces.side_effect = Exception("Something weird happened")
        with pytest.raises(ConfpubError) as exc_info:
            client.list_spaces()
        assert exc_info.value.code == ERR_INTERNAL_SDK


class TestSlimPage:
    def test_extracts_basic_fields(self):
        page = {"id": "123", "title": "Test Page", "_expandable": {"stuff": "..."}}
        result = _slim_page(page)
        assert result == {"id": "123", "title": "Test Page"}
        assert "_expandable" not in result

    def test_extracts_version(self):
        page = {
            "id": "123",
            "title": "Test",
            "version": {
                "number": 5,
                "when": "2025-01-01T00:00:00Z",
                "by": {"displayName": "Alice", "profilePicture": "/avatar.png"},
                "minorEdit": False,
            },
        }
        result = _slim_page(page)
        assert result["version"] == {
            "number": 5,
            "when": "2025-01-01T00:00:00Z",
            "by": "Alice",
        }

    def test_extracts_body_storage(self):
        page = {
            "id": "1",
            "title": "T",
            "body": {"storage": {"value": "<p>hi</p>", "representation": "storage"}},
        }
        result = _slim_page(page)
        assert result["body_storage"] == "<p>hi</p>"

    def test_extracts_webui_link(self):
        page = {
            "id": "1",
            "title": "T",
            "_links": {"base": "https://wiki.example.com", "webui": "/spaces/DEV/pages/1"},
        }
        result = _slim_page(page)
        assert result["webui"] == "https://wiki.example.com/spaces/DEV/pages/1"

    def test_cloud_webui_adds_wiki_prefix(self):
        """Cloud URLs need /wiki between base and webui path."""
        page = {
            "id": "1",
            "title": "T",
            "_links": {"webui": "/spaces/SD/pages/98376/What+Works+Well"},
        }
        result = _slim_page(page, base_url="https://myorg.atlassian.net", is_cloud=True)
        assert result["webui"] == "https://myorg.atlassian.net/wiki/spaces/SD/pages/98376/What+Works+Well"

    def test_cloud_webui_no_double_wiki(self):
        """If base_url already ends with /wiki, don't duplicate it."""
        page = {
            "id": "1",
            "title": "T",
            "_links": {"webui": "/spaces/SD/pages/1"},
        }
        result = _slim_page(page, base_url="https://myorg.atlassian.net/wiki", is_cloud=True)
        assert result["webui"] == "https://myorg.atlassian.net/wiki/spaces/SD/pages/1"

    def test_dc_webui_no_wiki_prefix(self):
        """DC/Server URLs should NOT get /wiki prefix."""
        page = {
            "id": "1",
            "title": "T",
            "_links": {"webui": "/spaces/DEV/pages/1"},
        }
        result = _slim_page(page, base_url="https://confluence.corp.com", is_cloud=False)
        assert result["webui"] == "https://confluence.corp.com/spaces/DEV/pages/1"

    def test_omits_missing_optional_fields(self):
        page = {"id": "1", "title": "T"}
        result = _slim_page(page)
        assert "version" not in result
        assert "body_storage" not in result
        assert "webui" not in result


class TestSearch:
    def test_structured_results(self, client):
        client._mock_api.get.return_value = {
            "results": [
                {
                    "entityType": "content",
                    "title": "API Docs",
                    "excerpt": "<b>REST</b> API documentation",
                    "content": {
                        "id": "123",
                        "type": "page",
                        "title": "API Docs",
                        "status": "current",
                        "space": {"key": "DEV"},
                        "version": {"when": "2026-02-28T09:15:00Z"},
                        "container": {"title": "Development"},
                        "_links": {"webui": "/spaces/DEV/pages/123"},
                    },
                }
            ],
            "totalSize": 1,
        }
        result = client.search('title = "API Docs"', excerpt_length=0)
        assert len(result["results"]) == 1
        r = result["results"][0]
        assert r["id"] == "123"
        assert r["type"] == "page"
        assert r["title"] == "API Docs"
        assert r["excerpt"] == "REST API documentation"
        assert r["url"] == "https://test.atlassian.net/wiki/spaces/DEV/pages/123"
        assert r["space_key"] == "DEV"
        assert "entity_type" not in r  # content is the default, omitted
        assert r["status"] == "current"
        assert r["last_modified"] == "2026-02-28T09:15:00Z"
        assert r["container_title"] == "Development"

    def test_empty_results(self, client):
        client._mock_api.get.return_value = {"results": [], "totalSize": 0}
        result = client.search('title = "nonexistent"')
        assert result["results"] == []
        assert result["total"] == 0
        assert result["has_more"] is False

    def test_has_more_pagination(self, client):
        client._mock_api.get.return_value = {
            "results": [{"entityType": "content", "content": {"id": "1"}, "excerpt": ""}],
            "totalSize": 50,
        }
        result = client.search("type = page", start=0, limit=10)
        assert result["has_more"] is True
        assert result["total"] == 50
        assert result["start"] == 0
        assert result["limit"] == 10

    def test_invalid_cql_raises_validation(self, client):
        client._mock_api.get.side_effect = Exception("400 The query cannot be parsed")
        with pytest.raises(ConfpubError) as exc_info:
            client.search("invalid!!")
        assert exc_info.value.code == ERR_VALIDATION_REQUIRED

    def test_auth_error(self, client):
        client._mock_api.get.side_effect = Exception("401 Unauthorized")
        with pytest.raises(ConfpubError) as exc_info:
            client.search("type = page")
        assert exc_info.value.code == ERR_AUTH_FORBIDDEN

    def test_include_archived_passthrough(self, client):
        client._mock_api.get.return_value = {"results": [], "totalSize": 0}
        client.search("type = page", include_archived_spaces=True)
        client._mock_api.get.assert_called_once_with(
            "rest/api/search",
            params={
                "cql": "type = page",
                "start": 0,
                "limit": 25,
                "excerpt": "highlight",
                "includeArchivedSpaces": True,
            },
        )

    def test_excerpt_truncation(self, client):
        long_excerpt = "word " * 100  # 500 chars
        client._mock_api.get.return_value = {
            "results": [{"entityType": "content", "content": {"id": "1"}, "excerpt": long_excerpt}],
            "totalSize": 1,
        }
        result = client.search("type = page", excerpt_length=50)
        excerpt = result["results"][0]["excerpt"]
        assert len(excerpt) <= 55  # 50 + room for trailing "…"
        assert excerpt.endswith("…")


class TestSlimSearchResult:
    def test_content_result(self):
        item = {
            "entityType": "content",
            "title": "My Page",
            "excerpt": "<em>highlighted</em> text",
            "content": {
                "id": "42",
                "type": "page",
                "title": "My Page",
                "status": "current",
                "space": {"key": "PROJ"},
                "version": {"when": "2026-01-01T00:00:00Z"},
                "container": {"title": "Project Space"},
                "_links": {"webui": "/spaces/PROJ/pages/42"},
            },
        }
        result = _slim_search_result(item, base_url="https://wiki.example.com", excerpt_length=0)
        assert result["id"] == "42"
        assert result["type"] == "page"
        assert "entity_type" not in result  # content is default, omitted
        assert result["url"] == "https://wiki.example.com/spaces/PROJ/pages/42"
        assert result["excerpt"] == "highlighted text"

    def test_space_result(self):
        item = {
            "entityType": "space",
            "title": "Dev Space",
            "excerpt": "",
            "space": {"id": "100", "key": "DEV", "name": "Dev Space"},
        }
        result = _slim_search_result(item)
        assert result["entity_type"] == "space"
        assert result["type"] == "space"
        assert result["space_key"] == "DEV"
        assert result["title"] == "Dev Space"

    def test_user_result(self):
        item = {
            "entityType": "user",
            "title": "Alice",
            "excerpt": "",
            "user": {"accountId": "abc123", "displayName": "Alice"},
        }
        result = _slim_search_result(item)
        assert result["entity_type"] == "user"
        assert result["type"] == "user"
        assert result["id"] == "abc123"
        assert result["title"] == "Alice"

    def test_html_stripping(self):
        item = {
            "entityType": "content",
            "excerpt": "Hello <b>world</b> and <a href='#'>link</a> text",
            "content": {"id": "1"},
        }
        result = _slim_search_result(item, excerpt_length=0)
        assert result["excerpt"] == "Hello world and link text"

    def test_missing_fields_omitted(self):
        """Null/empty fields should be omitted entirely, not set to None."""
        item = {"entityType": "content", "content": {}, "excerpt": ""}
        result = _slim_search_result(item)
        assert "id" not in result
        assert "type" not in result
        assert "title" not in result
        assert "url" not in result
        assert "space_key" not in result
        assert "last_modified" not in result
        assert "container_title" not in result
        assert "excerpt" not in result
        assert "entity_type" not in result  # content is default

    def test_excerpt_truncation(self):
        long_text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        item = {
            "entityType": "content",
            "excerpt": long_text,
            "content": {"id": "1"},
        }
        result = _slim_search_result(item, excerpt_length=30)
        assert result["excerpt"].endswith("…")
        assert len(result["excerpt"]) <= 35


class TestWebuiBase:
    def test_cloud_without_wiki(self):
        assert _webui_base("https://myorg.atlassian.net", True) == "https://myorg.atlassian.net/wiki"

    def test_cloud_with_wiki(self):
        assert _webui_base("https://myorg.atlassian.net/wiki", True) == "https://myorg.atlassian.net/wiki"

    def test_cloud_trailing_slash(self):
        assert _webui_base("https://myorg.atlassian.net/", True) == "https://myorg.atlassian.net/wiki"

    def test_dc_plain(self):
        assert _webui_base("https://confluence.corp.com", False) == "https://confluence.corp.com"

    def test_dc_context_path(self):
        assert _webui_base("https://corp.com/confluence", False) == "https://corp.com/confluence"


class TestBuildPageUrl:
    def test_cloud_with_title(self):
        url = build_page_url("https://myorg.atlassian.net", True, "SD", "12345", "My Page")
        assert url == "https://myorg.atlassian.net/wiki/spaces/SD/pages/12345/My+Page"

    def test_cloud_without_title(self):
        url = build_page_url("https://myorg.atlassian.net", True, "SD", "12345")
        assert url == "https://myorg.atlassian.net/wiki/spaces/SD/pages/12345"

    def test_dc_with_title(self):
        url = build_page_url("https://confluence.corp.com", False, "DEV", "456", "Test Page")
        assert url == "https://confluence.corp.com/spaces/DEV/pages/456/Test+Page"

    def test_dc_without_title(self):
        url = build_page_url("https://confluence.corp.com", False, "DEV", "456")
        assert url == "https://confluence.corp.com/spaces/DEV/pages/456"
