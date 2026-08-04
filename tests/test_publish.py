"""Tests for confpub.publish module (page.publish shortcut)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from confpub.config import ResolvedConfig
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

    def test_title_from_h1(self, tmp_path):
        """Suggestion 2: derive_title with title_from_h1=True extracts H1."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# My Custom Title\n\nContent here.")
        assert derive_title(str(md_file), title_from_h1=True) == "My Custom Title"

    def test_title_from_h1_falls_back_to_filename(self, tmp_path):
        """When no H1 is found, fall back to filename inference."""
        md_file = tmp_path / "api-docs.md"
        md_file.write_text("## Only H2\n\nNo H1 here.")
        assert derive_title(str(md_file), title_from_h1=True) == "Api Docs"

    def test_explicit_title_beats_h1(self, tmp_path):
        """Explicit --title should win over --title-from-h1."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# H1 Title\n\nContent here.")
        assert derive_title(str(md_file), "Explicit Title", title_from_h1=True) == "Explicit Title"


class TestDeriveTitleFrontMatter:
    def test_front_matter_title_used_as_fallback(self):
        assert derive_title("some-file.md", front_matter_title="FM Title") == "FM Title"

    def test_cli_title_wins_over_front_matter(self):
        assert derive_title("some-file.md", "CLI Title", front_matter_title="FM Title") == "CLI Title"

    def test_h1_wins_over_front_matter(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# H1 Title\n\nContent here.")
        result = derive_title(str(md_file), title_from_h1=True, front_matter_title="FM Title")
        assert result == "H1 Title"

    def test_front_matter_beats_filename(self):
        assert derive_title("my-cool-page.md", front_matter_title="Better Title") == "Better Title"

    def test_no_front_matter_falls_through_to_filename(self):
        assert derive_title("my-cool-page.md", front_matter_title=None) == "My Cool Page"


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
    def test_cloud_default_html_macro_is_html_macro(self, MockClient, mock_config, tmp_path, mock_client):
        md_file = tmp_path / "html.md"
        md_file.write_text("::: html\n<b>bold</b>\n:::")

        def get_page_side_effect(space, title):
            if title == "Root":
                return {"id": "root_1"}
            return None

        mock_client.get_page.side_effect = get_page_side_effect
        MockClient.return_value = mock_client
        mock_config.return_value = ResolvedConfig(base_url="https://test.atlassian.net/wiki")

        publish_page(
            file=str(md_file),
            space="DEV",
            parent="Root",
        )

        storage = mock_client.create_page.call_args[0][2]
        assert '<ac:structured-macro ac:name="html-macro">' in storage

    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_configured_html_macro_name_overrides_cloud_default(self, MockClient, mock_config, tmp_path, mock_client):
        md_file = tmp_path / "html.md"
        md_file.write_text("::: html\n<b>bold</b>\n:::")

        def get_page_side_effect(space, title):
            if title == "Root":
                return {"id": "root_1"}
            return None

        mock_client.get_page.side_effect = get_page_side_effect
        MockClient.return_value = mock_client
        mock_config.return_value = ResolvedConfig(
            base_url="https://test.atlassian.net/wiki",
            html_macro_name="macro-html",
        )

        publish_page(
            file=str(md_file),
            space="DEV",
            parent="Root",
        )

        storage = mock_client.create_page.call_args[0][2]
        assert '<ac:structured-macro ac:name="macro-html">' in storage

    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_forge_html_macro_format(self, MockClient, mock_config, tmp_path, mock_client):
        md_file = tmp_path / "html.md"
        md_file.write_text('::: html\n<div id="out">waiting</div>\n:::')

        def get_page_side_effect(space, title):
            if title == "Root":
                return {"id": "root_1"}
            return None

        mock_client.get_page.side_effect = get_page_side_effect
        MockClient.return_value = mock_client
        mock_config.return_value = ResolvedConfig(base_url="https://test.atlassian.net/wiki")

        publish_page(
            file=str(md_file),
            space="DEV",
            parent="Root",
            html_macro_name="macro-html",
            html_macro_format="forge-adf-extension",
            html_macro_forge_extension_key="app/static/macro-html",
            html_macro_forge_extension_id="ari:cloud:ecosystem::extension/app/static/macro-html",
            html_macro_forge_cloud_id="cloud-123",
            html_macro_forge_context_ids="ari:cloud:confluence:site/cloud-123",
            html_macro_forge_account_id="account-123",
        )

        storage = mock_client.create_page.call_args[0][2]
        assert "<ac:adf-extension>" in storage
        assert '<ac:adf-attribute key="extension-key">app/static/macro-html</ac:adf-attribute>' in storage
        assert '<ac:adf-parameter key="cloud-id">cloud-123</ac:adf-parameter>' in storage
        assert '<ac:adf-parameter key="account-id">account-123</ac:adf-parameter>' in storage
        assert '<ac:adf-parameter key="source-type">MacroBody</ac:adf-parameter>' in storage
        assert '&lt;div id="out"&gt;waiting&lt;/div&gt;' in storage

    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_warns_for_cloud_default_classic_html_macro(self, MockClient, mock_config, tmp_path, mock_client):
        md_file = tmp_path / "html.md"
        md_file.write_text("::: html\n<b>bold</b>\n:::")

        def get_page_side_effect(space, title):
            if title == "Root":
                return {"id": "root_1"}
            return None

        mock_client.get_page.side_effect = get_page_side_effect
        MockClient.return_value = mock_client
        mock_config.return_value = ResolvedConfig(base_url="https://test.atlassian.net/wiki")

        result = publish_page(
            file=str(md_file),
            space="DEV",
            parent="Root",
            dry_run=True,
        )

        assert "warnings" in result
        assert "default classic" in result["warnings"][0]

    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_no_warning_for_explicit_classic_html_macro_format(self, MockClient, mock_config, tmp_path, mock_client):
        md_file = tmp_path / "html.md"
        md_file.write_text("::: html\n<b>bold</b>\n:::")

        def get_page_side_effect(space, title):
            if title == "Root":
                return {"id": "root_1"}
            return None

        mock_client.get_page.side_effect = get_page_side_effect
        MockClient.return_value = mock_client
        mock_config.return_value = ResolvedConfig(base_url="https://test.atlassian.net/wiki")

        result = publish_page(
            file=str(md_file),
            space="DEV",
            parent="Root",
            dry_run=True,
            html_macro_format="classic",
        )

        assert "warnings" not in result

    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_updates_lockfile(self, MockClient, mock_config, source_dir, mock_client):
        def get_page_side_effect(space, title):
            if title == "Root":
                return {"id": "root_1"}
            return None
        mock_client.get_page.side_effect = get_page_side_effect
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


class TestPublishLabels:
    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_labels_applied_on_create(self, MockClient, mock_config, source_dir, mock_client):
        def get_page_side_effect(space, title):
            if title == "Root":
                return {"id": "root_1"}
            return None
        mock_client.get_page.side_effect = get_page_side_effect
        mock_client.set_labels.return_value = []
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = publish_page(
            file=str(source_dir / "readme.md"),
            space="DEV",
            parent="Root",
            labels=["api", "docs"],
        )

        assert result["dry_run"] is False
        mock_client.set_labels.assert_called_once_with("new_123", ["api", "docs"])
        assert result["changes"][0]["labels_added"] == ["api", "docs"]

    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_labels_reported_on_dry_run(self, MockClient, mock_config, source_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = publish_page(
            file=str(source_dir / "readme.md"),
            space="DEV",
            parent="Root",
            dry_run=True,
            labels=["api"],
        )

        assert result["dry_run"] is True
        assert result["changes"][0]["labels_to_apply"] == ["api"]
        mock_client.set_labels.assert_not_called()

    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_labels_applied_on_noop(self, MockClient, mock_config, source_dir, mock_client):
        """Labels should be applied even when content is unchanged (noop)."""
        # Setup: page exists and fingerprint matches
        mock_client.get_page.return_value = {"id": "existing_456", "version": {"number": 1}}
        mock_client.fingerprint_page.return_value = None  # Force lockfile check
        mock_client.set_labels.return_value = []
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        # Write lockfile with matching fingerprint
        from confpub.converter import convert_markdown, fingerprint_content
        md_text = (source_dir / "readme.md").read_text()
        storage = convert_markdown(md_text)
        fp = fingerprint_content(storage)

        from confpub.lockfile import Lockfile, LockPageEntry, save_lockfile
        lockfile = Lockfile()
        lockfile.pages["Readme"] = LockPageEntry(page_id="existing_456", version=1, content_fingerprint=fp)
        save_lockfile(source_dir / "confpub.lock", lockfile)

        result = publish_page(
            file=str(source_dir / "readme.md"),
            space="DEV",
            parent="Root",
            labels=["tag1"],
        )

        assert result["changes"][0]["type"] == "page.noop"
        mock_client.set_labels.assert_called_once_with("existing_456", ["tag1"])
        assert result["changes"][0]["labels_added"] == ["tag1"]

    @patch("confpub.publish.load_config")
    @patch("confpub.publish.ConfluenceClient")
    def test_attachments_uploaded_on_noop(self, MockClient, mock_config, source_dir, mock_client):
        """Attachment content can change even when the page storage fingerprint is unchanged."""
        source = source_dir / "diagram-source"
        source.write_text("flowchart LR\nA --> B\n", encoding="utf-8")
        markdown_file = source_dir / "readme.md"
        markdown_file.write_text("![source](diagram-source)", encoding="utf-8")
        mock_client.get_page.return_value = {"id": "existing_456", "version": {"number": 1}}
        mock_client.fingerprint_page.return_value = None
        mock_client.upload_attachment.return_value = {"id": "att_1"}
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        from confpub.converter import convert_markdown, fingerprint_content
        from confpub.lockfile import Lockfile, LockPageEntry, save_lockfile
        fingerprint = fingerprint_content(convert_markdown(markdown_file.read_text(encoding="utf-8")))
        lockfile = Lockfile()
        lockfile.pages["Readme"] = LockPageEntry(
            page_id="existing_456",
            version=1,
            content_fingerprint=fingerprint,
        )
        save_lockfile(source_dir / "confpub.lock", lockfile)

        result = publish_page(file=str(markdown_file), space="DEV", parent="Root")

        assert result["changes"][0]["type"] == "page.noop"
        assert result["summary"]["attachments_upload"] == 1
        mock_client.upload_attachment.assert_called_once_with("existing_456", str(source.resolve()))


class TestPublishErrors:
    def test_missing_file(self):
        with pytest.raises(ConfpubError) as exc_info:
            publish_page(
                file="/nonexistent/file.md",
                space="DEV",
                parent="Root",
            )
        assert exc_info.value.code == ERR_IO_FILE_NOT_FOUND
