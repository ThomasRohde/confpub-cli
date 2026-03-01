"""Tests for confpub.confluence module."""

from unittest.mock import MagicMock, patch

import pytest

from confpub.config import ResolvedConfig
from confpub.confluence import ConfluenceClient, _slim_page
from confpub.errors import (
    ERR_AUTH_FORBIDDEN,
    ERR_AUTH_REQUIRED,
    ERR_CONFLICT_PAGE_EXISTS,
    ERR_IO_CONNECTION,
    ERR_IO_FILE_NOT_FOUND,
    ERR_INTERNAL_SDK,
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
            "DEV", "Test", expand="version,body.storage"
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
        pages = client.list_pages("DEV")
        assert len(pages) == 2


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
        assert exc_info.value.code == ERR_IO_FILE_NOT_FOUND

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

    def test_omits_missing_optional_fields(self):
        page = {"id": "1", "title": "T"}
        result = _slim_page(page)
        assert "version" not in result
        assert "body_storage" not in result
        assert "webui" not in result
