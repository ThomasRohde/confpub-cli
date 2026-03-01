"""Tests for confpub.publish module (page.publish shortcut)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from confpub.errors import ConfpubError, ERR_IO_FILE_NOT_FOUND
from confpub.publish import derive_title, publish_page


@pytest.fixture
def source_dir(tmp_path):
    (tmp_path / "readme.md").write_text("# My Page\n\nSome content here.")
    return tmp_path


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_page.return_value = None  # Page doesn't exist
    client.create_page.return_value = {"id": "new_123", "version": {"number": 1}}
    client.update_page.return_value = {"id": "new_123", "version": {"number": 2}}
    client.get_page_by_id.return_value = {
        "id": "existing_456",
        "version": {"number": 1},
        "body": {"storage": {"value": "<p>old</p>"}},
    }
    return client


class TestDeriveTitle:
    def test_explicit_title_wins(self):
        assert derive_title("some-file.md", "My Custom Title") == "My Custom Title"

    def test_derives_from_filename(self):
        assert derive_title("my-cool-page.md") == "My Cool Page"

    def test_underscores_to_spaces(self):
        assert derive_title("api_reference.md") == "Api Reference"

    def test_mixed_separators(self):
        assert derive_title("my-api_docs.md") == "My Api Docs"

    def test_path_uses_stem_only(self):
        assert derive_title("docs/subfolder/overview.md") == "Overview"


class TestPublishDryRun:
    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_dry_run_new_page(self, MockClient, mock_config, source_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = publish_page(
            file=str(source_dir / "readme.md"),
            space="DEV",
            parent="Root",
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert result["changes"][0]["type"] == "page.create"
        assert result["changes"][0]["title"] == "Readme"

    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_dry_run_with_title(self, MockClient, mock_config, source_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = publish_page(
            file=str(source_dir / "readme.md"),
            space="DEV",
            parent="Root",
            title="Custom Title",
            dry_run=True,
        )

        assert result["changes"][0]["title"] == "Custom Title"

    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_dry_run_no_writes(self, MockClient, mock_config, source_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        publish_page(
            file=str(source_dir / "readme.md"),
            space="DEV",
            parent="Root",
            dry_run=True,
        )

        mock_client.create_page.assert_not_called()
        mock_client.update_page.assert_not_called()


class TestPublishCreate:
    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_creates_new_page(self, MockClient, mock_config, source_dir, mock_client):
        mock_client.get_page.return_value = None  # Parent lookup returns None for page
        # Override to return parent for the parent lookup
        def get_page_side_effect(space, title):
            if title == "Root":
                return {"id": "root_1"}
            return None
        mock_client.get_page.side_effect = get_page_side_effect
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = publish_page(
            file=str(source_dir / "readme.md"),
            space="DEV",
            parent="Root",
        )

        assert result["dry_run"] is False
        assert result["changes"][0]["type"] == "page.create"
        mock_client.create_page.assert_called_once()

    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_updates_lockfile(self, MockClient, mock_config, source_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        publish_page(
            file=str(source_dir / "readme.md"),
            space="DEV",
            parent="Root",
        )

        lockfile = source_dir / "confpub.lock"
        assert lockfile.exists()
        data = json.loads(lockfile.read_text())
        assert "Readme" in data["pages"]


class TestPublishErrors:
    def test_missing_file(self):
        with pytest.raises(ConfpubError) as exc_info:
            publish_page(
                file="/nonexistent/file.md",
                space="DEV",
                parent="Root",
            )
        assert exc_info.value.code == ERR_IO_FILE_NOT_FOUND
