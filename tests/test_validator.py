"""Tests for confpub.validator module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from confpub.errors import ConfpubError, ERR_IO_FILE_NOT_FOUND
from confpub.validator import validate_plan


SAMPLE_PLAN = {
    "schema_version": "1.0",
    "created_at": "2026-02-28T14:30:00Z",
    "space": "DEV",
    "parent": "Root",
    "pages": [
        {
            "id": "plan_1",
            "title": "Overview",
            "source_file": "overview.md",
            "confluence_page_id": "123",
            "current_fingerprint": "abc123",
            "operation": "update",
            "attachments": [],
        },
        {
            "id": "plan_2",
            "title": "Guide",
            "source_file": "guide.md",
            "confluence_page_id": None,
            "current_fingerprint": None,
            "operation": "create",
            "attachments": [],
        },
    ],
    "summary": {"create": 1, "update": 1, "noop": 0, "attachments_to_upload": 0},
}


@pytest.fixture
def plan_dir(tmp_path):
    """Create a directory with a plan file and source files."""
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(SAMPLE_PLAN))
    (tmp_path / "overview.md").write_text("# Overview")
    (tmp_path / "guide.md").write_text("# Guide")
    return tmp_path


class TestValidatePlan:
    @patch("confpub.validator.load_config")
    @patch("confpub.validator.ConfluenceClient")
    def test_all_valid(self, MockClient, mock_config, plan_dir):
        mock_client = MagicMock()
        mock_client.fingerprint_page.return_value = "abc123"  # Matches plan
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = validate_plan(str(plan_dir / "plan.json"))
        assert result["valid"] is True
        assert len(result["checks"]) == 2
        assert all(c["passed"] for c in result["checks"])

    @patch("confpub.validator.load_config")
    @patch("confpub.validator.ConfluenceClient")
    def test_fingerprint_mismatch(self, MockClient, mock_config, plan_dir):
        mock_client = MagicMock()
        mock_client.fingerprint_page.return_value = "different_hash"  # Changed!
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = validate_plan(str(plan_dir / "plan.json"))
        assert result["valid"] is False
        # The update page should fail
        overview_check = result["checks"][0]
        assert overview_check["passed"] is False
        assert overview_check["issue"] == "ERR_CONFLICT_FINGERPRINT"

    @patch("confpub.validator.load_config")
    @patch("confpub.validator.ConfluenceClient")
    def test_missing_source_file(self, MockClient, mock_config, plan_dir):
        mock_client = MagicMock()
        mock_client.fingerprint_page.return_value = "abc123"
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        # Remove a source file
        (plan_dir / "guide.md").unlink()

        result = validate_plan(str(plan_dir / "plan.json"))
        assert result["valid"] is False
        guide_check = result["checks"][1]
        assert guide_check["passed"] is False
        assert guide_check["issue"] == "ERR_IO_FILE_NOT_FOUND"

    def test_missing_plan_file(self):
        with pytest.raises(ConfpubError) as exc_info:
            validate_plan("/nonexistent/plan.json")
        assert exc_info.value.code == ERR_IO_FILE_NOT_FOUND
