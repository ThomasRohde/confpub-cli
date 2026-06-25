"""Tests for confpub.planner module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from confpub.errors import ConfpubError, ERR_IO_FILE_NOT_FOUND
from confpub.planner import create_plan
from confpub.config import ResolvedConfig


SAMPLE_MANIFEST = """\
schema_version: "1.0"
space: DEV
parent: "Root"
pages:
  - title: "Overview"
    file: overview.md
  - title: "Guide"
    file: guide.md
"""


@pytest.fixture
def manifest_dir(tmp_path):
    """Create a temporary directory with a manifest and source files."""
    manifest = tmp_path / "confpub.yaml"
    manifest.write_text(SAMPLE_MANIFEST)
    (tmp_path / "overview.md").write_text("# Overview\n\nThis is the overview.")
    (tmp_path / "guide.md").write_text("# Guide\n\nThis is the guide.")
    return tmp_path


@pytest.fixture
def mock_client():
    """Mock ConfluenceClient for testing without real API calls."""
    client = MagicMock()
    client.get_page.return_value = None  # Pages don't exist yet
    client.fingerprint_page.return_value = None
    return client


class TestCreatePlan:
    @patch("confpub.planner.load_config")
    @patch("confpub.planner.ConfluenceClient")
    def test_creates_new_pages(self, MockClient, mock_config, manifest_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = create_plan(
            manifest_path=str(manifest_dir / "confpub.yaml"),
            output_path=str(manifest_dir / "plan.json"),
        )

        assert result["summary"]["create"] == 2
        assert result["summary"]["update"] == 0
        assert result["summary"]["noop"] == 0
        assert Path(result["plan_file"]).exists()

        # Verify plan artifact content
        plan = json.loads(Path(result["plan_file"]).read_text())
        assert plan["space"] == "DEV"
        assert plan["parent"] == "Root"
        assert len(plan["pages"]) == 2
        assert plan["pages"][0]["title"] == "Overview"
        assert plan["pages"][0]["operation"] == "create"

    @patch("confpub.planner.load_config")
    @patch("confpub.planner.ConfluenceClient")
    def test_detects_existing_pages(self, MockClient, mock_config, manifest_dir, mock_client):
        # Simulate page already exists
        mock_client.get_page.side_effect = lambda space, title: (
            {"id": "123", "title": title} if title == "Overview" else None
        )
        mock_client.fingerprint_page.return_value = "different_fingerprint"
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = create_plan(
            manifest_path=str(manifest_dir / "confpub.yaml"),
            output_path=str(manifest_dir / "plan.json"),
        )

        assert result["summary"]["update"] == 1
        assert result["summary"]["create"] == 1

    @patch("confpub.planner.load_config")
    @patch("confpub.planner.ConfluenceClient")
    def test_missing_source_file(self, MockClient, mock_config, manifest_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        # Remove a source file
        (manifest_dir / "guide.md").unlink()

        with pytest.raises(ConfpubError) as exc_info:
            create_plan(
                manifest_path=str(manifest_dir / "confpub.yaml"),
                output_path=str(manifest_dir / "plan.json"),
            )
        assert exc_info.value.code == ERR_IO_FILE_NOT_FOUND

    @patch("confpub.planner.load_config")
    @patch("confpub.planner.ConfluenceClient")
    def test_space_override(self, MockClient, mock_config, manifest_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = create_plan(
            manifest_path=str(manifest_dir / "confpub.yaml"),
            output_path=str(manifest_dir / "plan.json"),
            space_override="PROD",
        )

        plan = json.loads(Path(result["plan_file"]).read_text())
        assert plan["space"] == "PROD"

    @patch("confpub.planner.load_config")
    @patch("confpub.planner.ConfluenceClient")
    def test_default_output_path(self, MockClient, mock_config, manifest_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = create_plan(
            manifest_path=str(manifest_dir / "confpub.yaml"),
        )

        expected = str(manifest_dir / "confpub-plan.json")
        assert result["plan_file"] == expected
        assert Path(expected).exists()

    @patch("confpub.planner.load_config")
    @patch("confpub.planner.ConfluenceClient")
    def test_overwrites_existing_plan_file(self, MockClient, mock_config, manifest_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()
        plan_file = manifest_dir / "confpub-plan.json"
        plan_file.write_text('{"stale": true}', encoding="utf-8")

        result = create_plan(manifest_path=str(manifest_dir / "confpub.yaml"))

        assert result["plan_file"] == str(plan_file)
        data = json.loads(plan_file.read_text(encoding="utf-8"))
        assert data["space"] == "DEV"
        assert "stale" not in data

    @patch("confpub.planner.load_config")
    @patch("confpub.planner.ConfluenceClient")
    def test_lockfile_matching_fingerprint_reports_noop(self, MockClient, mock_config, manifest_dir, mock_client):
        from confpub.converter import convert_markdown, fingerprint_content
        from confpub.lockfile import Lockfile, LockPageEntry, save_lockfile

        md_text = (manifest_dir / "overview.md").read_text(encoding="utf-8")
        lock = Lockfile()
        lock.pages["Overview"] = LockPageEntry(
            page_id="page_123",
            version=1,
            content_fingerprint=fingerprint_content(convert_markdown(md_text)),
        )
        save_lockfile(manifest_dir / "confpub.lock", lock)

        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = create_plan(
            manifest_path=str(manifest_dir / "confpub.yaml"),
            output_path=str(manifest_dir / "plan.json"),
        )

        assert result["summary"]["noop"] == 1
        plan = json.loads((manifest_dir / "plan.json").read_text(encoding="utf-8"))
        overview = next(p for p in plan["pages"] if p["title"] == "Overview")
        assert overview["operation"] == "noop"
        assert overview["confluence_page_id"] == "page_123"

    @patch("confpub.planner.load_config")
    @patch("confpub.planner.ConfluenceClient")
    def test_warns_for_unparsed_page_title_links(self, MockClient, mock_config, manifest_dir, mock_client):
        (manifest_dir / "overview.md").write_text(
            "# Overview\n\n[Dashboard](Aurora — Live Operations Dashboard)",
            encoding="utf-8",
        )
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = create_plan(
            manifest_path=str(manifest_dir / "confpub.yaml"),
            output_path=str(manifest_dir / "plan.json"),
        )

        assert "warnings" in result
        assert "may publish as literal Markdown" in result["warnings"][0]

    @patch("confpub.planner.load_config")
    @patch("confpub.planner.ConfluenceClient")
    def test_warns_for_cloud_default_classic_html_macro(self, MockClient, mock_config, manifest_dir, mock_client):
        (manifest_dir / "overview.md").write_text(
            "::: html\n<div>ok</div>\n:::",
            encoding="utf-8",
        )
        MockClient.return_value = mock_client
        mock_config.return_value = ResolvedConfig(base_url="https://test.atlassian.net/wiki")

        result = create_plan(
            manifest_path=str(manifest_dir / "confpub.yaml"),
            output_path=str(manifest_dir / "plan.json"),
        )

        assert "warnings" in result
        assert "overview.md: This Cloud publish contains ::: html" in result["warnings"][0]
