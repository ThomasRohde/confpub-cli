"""Tests for confpub.applier module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from confpub.applier import apply_plan
from confpub.config import ResolvedConfig
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
    def _get_page(space, title, **kw):
        if title == "Root":
            return {"id": "root_id"}
        return None
    client.get_page.side_effect = _get_page
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

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_warns_for_cloud_default_classic_html_macro(self, MockClient, mock_config, plan_dir, mock_client):
        (plan_dir / "new.md").write_text("::: html\n<div>ok</div>\n:::", encoding="utf-8")
        MockClient.return_value = mock_client
        mock_config.return_value = ResolvedConfig(base_url="https://test.atlassian.net/wiki")

        result = apply_plan(str(plan_dir / "plan.json"), dry_run=True)

        assert "warnings" in result
        assert "new.md: This Cloud publish contains ::: html" in result["warnings"][0]


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


class TestApplyLockfileFingerprints:
    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_lockfile_entries_have_fingerprints(self, MockClient, mock_config, plan_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_dir / "plan.json"), dry_run=False)

        lockfile_path = plan_dir / "confpub.lock"
        assert lockfile_path.exists()
        lock_data = json.loads(lockfile_path.read_text())
        for title in ("New Page", "Existing Page"):
            entry = lock_data["pages"][title]
            assert entry["content_fingerprint"] is not None, f"{title} has null fingerprint"
            assert len(entry["content_fingerprint"]) == 64  # SHA-256 hex digest

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_lockfile_updated_in_result(self, MockClient, mock_config, plan_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_dir / "plan.json"), dry_run=False)
        assert result["lockfile_updated"] is True

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_lockfile_updated_false_on_dry_run(self, MockClient, mock_config, plan_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_dir / "plan.json"), dry_run=True)
        assert result["lockfile_updated"] is False


class TestApplyLockfilePath:
    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_lockfile_path_present_on_real_apply(self, MockClient, mock_config, plan_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_dir / "plan.json"), dry_run=False)
        assert result["lockfile_path"] is not None
        assert "confpub.lock" in result["lockfile_path"]

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_lockfile_path_null_on_dry_run(self, MockClient, mock_config, plan_dir, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_dir / "plan.json"), dry_run=True)
        assert result["lockfile_path"] is None


PLAN_WITH_LABELS = {
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
            "labels": ["api", "docs"],
        },
        {
            "id": "plan_2",
            "title": "Existing Page",
            "source_file": "existing.md",
            "confluence_page_id": "456",
            "current_fingerprint": "fp_abc",
            "operation": "update",
            "attachments": [],
            "labels": ["updated"],
        },
    ],
    "summary": {"create": 1, "update": 1, "noop": 0, "attachments_to_upload": 0, "labels_to_apply": 3},
}


class TestApplyLabels:
    @pytest.fixture
    def plan_dir_labels(self, tmp_path):
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(PLAN_WITH_LABELS))
        (tmp_path / "new.md").write_text("# New Page\n\nContent here.")
        (tmp_path / "existing.md").write_text("# Existing Page\n\nUpdated content.")
        return tmp_path

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_labels_applied_on_real_apply(self, MockClient, mock_config, plan_dir_labels, mock_client):
        mock_client.set_labels.return_value = []
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_dir_labels / "plan.json"), dry_run=False)

        assert mock_client.set_labels.call_count == 2
        # Create page sets labels on new ID
        mock_client.set_labels.assert_any_call("789", ["api", "docs"])
        # Update page sets labels on existing ID
        mock_client.set_labels.assert_any_call("456", ["updated"])
        assert result["summary"]["labels_applied"] == 3

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_labels_in_change_records(self, MockClient, mock_config, plan_dir_labels, mock_client):
        mock_client.set_labels.return_value = []
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_dir_labels / "plan.json"), dry_run=False)

        create_change = result["changes"][0]
        assert create_change["labels_added"] == ["api", "docs"]
        update_change = result["changes"][1]
        assert update_change["labels_added"] == ["updated"]

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_labels_dry_run_reports_but_no_apply(self, MockClient, mock_config, plan_dir_labels, mock_client):
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_dir_labels / "plan.json"), dry_run=True)

        mock_client.set_labels.assert_not_called()
        create_change = result["changes"][0]
        assert create_change["labels_to_apply"] == ["api", "docs"]
        update_change = result["changes"][1]
        assert update_change["labels_to_apply"] == ["updated"]


class TestApplyAssets:
    @patch("confpub.applier.upload_assets")
    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_uploads_planned_manifest_asset_not_referenced_in_markdown(
        self, MockClient, mock_config, mock_upload_assets, tmp_path, mock_client
    ):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        (tmp_path / "dashboard.md").write_text("# Dashboard\n\nNo static script tag.", encoding="utf-8")
        (assets_dir / "dashboard-data.js").write_text("window.__dataReady({rows: []});", encoding="utf-8")
        plan_data = {
            "schema_version": "1.0",
            "created_at": "2026-02-28T14:30:00Z",
            "space": "DEV",
            "parent": "Root",
            "pages": [
                {
                    "id": "plan_1",
                    "title": "Dashboard",
                    "source_file": "dashboard.md",
                    "confluence_page_id": None,
                    "current_fingerprint": None,
                    "operation": "create",
                    "attachments": [
                        {"file": "assets/dashboard-data.js", "operation": "upload"},
                    ],
                },
            ],
            "summary": {"create": 1, "update": 0, "noop": 0, "attachments_to_upload": 1},
        }
        (tmp_path / "plan.json").write_text(json.dumps(plan_data), encoding="utf-8")

        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()
        mock_upload_assets.return_value = []

        result = apply_plan(str(tmp_path / "plan.json"), dry_run=False)

        assert result["summary"]["attachments_upload"] == 1
        asset = mock_upload_assets.call_args[0][2][0]
        assert asset.source_path == "assets/dashboard-data.js"
        assert asset.filename == "dashboard-data.js"


class TestNoopAttachments:
    @patch("confpub.applier.upload_assets")
    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_noop_page_still_uploads_planned_attachments(
        self, MockClient, mock_config, mock_upload_assets, tmp_path, mock_client,
    ):
        (tmp_path / "page.md").write_text("# Page", encoding="utf-8")
        (tmp_path / "diagram-source").write_text("flowchart LR", encoding="utf-8")
        plan_data = {
            "schema_version": "1.0",
            "created_at": "2026-08-04T00:00:00Z",
            "space": "DEV",
            "parent": "Root",
            "pages": [{
                "id": "plan_1",
                "title": "Page",
                "source_file": "page.md",
                "confluence_page_id": "123",
                "current_fingerprint": "same",
                "operation": "noop",
                "attachments": [{"file": "diagram-source", "operation": "upload"}],
            }],
            "summary": {"noop": 1, "attachments_to_upload": 1},
        }
        (tmp_path / "plan.json").write_text(json.dumps(plan_data), encoding="utf-8")
        mock_client.fingerprint_page.return_value = "same"
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()
        mock_upload_assets.return_value = []

        result = apply_plan(str(tmp_path / "plan.json"), dry_run=False)

        assert result["summary"]["attachments_upload"] == 1
        mock_upload_assets.assert_called_once()
        assert result["changes"][0]["attachments_added"] == ["diagram-source"]


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


class TestDryRunReEvaluation:
    """Bug 4: dry-run should re-evaluate operations against current state."""

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_dry_run_detects_already_created_page_via_lockfile(self, MockClient, mock_config, tmp_path, mock_client):
        """When lockfile says a page exists, dry-run should show update/noop not create."""
        plan_data = {
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
            ],
            "summary": {"create": 1, "update": 0, "noop": 0, "attachments_to_upload": 0},
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan_data))
        (tmp_path / "new.md").write_text("# New Page\n\nContent here.")

        # Lockfile says this page already exists
        from confpub.lockfile import Lockfile, LockPageEntry, save_lockfile
        lock = Lockfile()
        lock.pages["New Page"] = LockPageEntry(page_id="999", version=1, content_fingerprint="different_fp")
        save_lockfile(tmp_path / "confpub.lock", lock)

        mock_client.fingerprint_page.return_value = "different_fp"
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_file), dry_run=True)

        assert result["dry_run"] is True
        assert any(c["type"] == "page.update" for c in result["changes"])
        assert not any(c["type"] == "page.create" for c in result["changes"])

    @patch("confpub.applier.load_config")
    @patch("confpub.applier.ConfluenceClient")
    def test_dry_run_detects_already_created_page_via_confluence(self, MockClient, mock_config, tmp_path, mock_client):
        """When Confluence has the page (no lockfile), dry-run should show update not create."""
        plan_data = {
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
            ],
            "summary": {"create": 1, "update": 0, "noop": 0, "attachments_to_upload": 0},
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan_data))
        (tmp_path / "new.md").write_text("# New Page\n\nContent here.")

        def fake_get_page(space, title, **kwargs):
            if title == "Root":
                return {"id": "root_id"}
            if title == "New Page":
                return {"id": "existing_999"}
            return None

        mock_client.get_page.side_effect = fake_get_page
        mock_client.fingerprint_page.return_value = "different_fp"
        MockClient.return_value = mock_client
        mock_config.return_value = MagicMock()

        result = apply_plan(str(plan_file), dry_run=True)

        assert result["dry_run"] is True
        assert any(c["type"] == "page.update" for c in result["changes"])
        assert not any(c["type"] == "page.create" for c in result["changes"])
