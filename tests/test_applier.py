"""Tests for confpub.applier module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from confpub.applier import apply_plan
from confpub.errors import ConfpubError, ERR_CONFLICT_FINGERPRINT


SAMPLE_PLAN = {
    "schema_version": "1.0",
    "created_at": "2026-02-28T14:30:00Z",
    "space": "DEV",
    "parent": "Root",
    "pages": [
        {
            "id": "plan_1",
            "title": "New Page",
            "source_file": "new.md",
            "confluence_page_id": None,
            "current_fingerprint": None,
            "operation": "create",
            "attachments": [],
        },
        {
            "id": "plan_2",
            "title": "Existing Page",
            "source_file": "existing.md",
            "confluence_page_id": "456",
            "current_fingerprint": "fp_abc",
            "operation": "update",
            "attachments": [],
        },
    ],
    "summary": {"create": 1, "update": 1, "noop": 0, "attachments_to_upload": 0},
}


@pytest.fixture
def plan_dir(tmp_path):
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(SAMPLE_PLAN))
    (tmp_path / "new.md").write_text("# New Page\n\nContent here.")
    (tmp_path / "existing.md").write_text("# Existing Page\n\nUpdated content.")
    return tmp_path


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_page.return_value = {"id": "root_id"}
    client.create_page.return_value = {"id": "789", "version": {"number": 1}}
    client.update_page.return_value = {"id": "456", "version": {"number": 3}}
    client.get_page_by_id.return_value = {
        "id": "456",
        "version": {"number": 2},
        "body": {"storage": {"value": "<p>old</p>"}},
    }
    client.fingerprint_page.return_value = "fp_abc"  # Matches plan
    return client


class TestApplyPlanDryRun:
    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_dry_run_returns_changes(self, MockClient, mock_config, plan_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_dir / "plan.json"), dry_run=True)

        assert result["dry_run"] is True
        assert result["summary"]["create"] == 1
        assert result["summary"]["update"] == 1
        assert len(result["changes"]) == 2

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_dry_run_no_api_writes(self, MockClient, mock_config, plan_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        apply_plan(str(plan_dir / "plan.json"), dry_run=True)

        mock_client.create_page.assert_not_called()
        mock_client.update_page.assert_not_called()

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_dry_run_no_lockfile(self, MockClient, mock_config, plan_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        apply_plan(str(plan_dir / "plan.json"), dry_run=True)

        assert not (plan_dir / "confpub.lock").exists()


class TestApplyPlanReal:
    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_creates_and_updates(self, MockClient, mock_config, plan_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_dir / "plan.json"), dry_run=False)

        assert result["dry_run"] is False
        mock_client.create_page.assert_called_once()
        mock_client.update_page.assert_called_once()

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_updates_lockfile(self, MockClient, mock_config, plan_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        apply_plan(str(plan_dir / "plan.json"), dry_run=False)

        lockfile_path = plan_dir / "confpub.lock"
        assert lockfile_path.exists()
        lock_data = json.loads(lockfile_path.read_text())
        assert "New Page" in lock_data["pages"]
        assert "Existing Page" in lock_data["pages"]


class TestFingerprintCheck:
    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_fails_on_fingerprint_mismatch(self, MockClient, mock_config, plan_dir, mock_client):
        mock_client.fingerprint_page.return_value = "different_fp"  # Mismatch!
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        with pytest.raises(ConfpubError) as exc_info:
            apply_plan(str(plan_dir / "plan.json"), dry_run=False)
        assert exc_info.value.code == ERR_CONFLICT_FINGERPRINT

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_skip_fingerprint_check(self, MockClient, mock_config, plan_dir, mock_client):
        mock_client.fingerprint_page.return_value = "different_fp"
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        # Should not raise with skip flag
        result = apply_plan(
            str(plan_dir / "plan.json"),
            dry_run=False,
            skip_fingerprint_check=True,
        )
        assert result["summary"]["update"] == 1
