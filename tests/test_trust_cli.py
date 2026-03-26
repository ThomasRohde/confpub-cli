"""CLI integration tests for trust scoring commands."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from confpub.cli import app
from confpub.errors import ConfpubError

runner = CliRunner()


class TestPageScoreHelp:
    def test_help_shows_flags(self):
        result = runner.invoke(app, ["page", "score", "--help"])
        assert result.exit_code == 0
        assert "--page-id" in result.output
        assert "--profile" in result.output
        assert "--include-signals" in result.output
        assert "--explain" in result.output


class TestTrustCacheHelp:
    def test_cache_inspect_help(self):
        result = runner.invoke(app, ["trust", "cache", "inspect", "--help"])
        assert result.exit_code == 0
        assert "trust cache" in result.output.lower() or "Show" in result.output

    def test_cache_purge_help(self):
        result = runner.invoke(app, ["trust", "cache", "purge", "--help"])
        assert result.exit_code == 0
        assert "--all" in result.output


class TestTrustProfileHelp:
    def test_profile_inspect_help(self):
        result = runner.invoke(app, ["trust", "profile", "inspect", "--help"])
        assert result.exit_code == 0
        assert "--name" in result.output


class TestPageScoreValidation:
    def test_no_args_returns_error(self):
        result = runner.invoke(app, ["page", "score"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False


class TestTrustProfileInspect:
    def test_list_all_profiles(self):
        result = runner.invoke(app, ["trust", "profile", "inspect"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "official-knowledge" in data["result"]["profiles"]
        assert "working-area" in data["result"]["profiles"]
        assert "historical-record" in data["result"]["profiles"]

    def test_single_profile(self):
        result = runner.invoke(app, ["trust", "profile", "inspect", "--name", "working-area"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["name"] == "working-area"

    def test_invalid_profile_error(self):
        result = runner.invoke(app, ["trust", "profile", "inspect", "--name", "nonexistent"])
        assert result.exit_code == 10
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["errors"][0]["code"] == "ERR_VALIDATION_TRUST_PROFILE"


class TestTrustCacheInspect:
    def test_cache_inspect_returns_stats(self):
        result = runner.invoke(app, ["trust", "cache", "inspect"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "entry_count" in data["result"]
        assert "db_path" in data["result"]


class TestTrustCachePurge:
    def test_purge_all(self):
        result = runner.invoke(app, ["trust", "cache", "purge", "--all"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "deleted_count" in data["result"]


class TestThreeLevelNesting:
    def test_trust_cache_routes(self):
        result = runner.invoke(app, ["trust", "cache", "inspect"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["command"] == "trust.cache.inspect"

    def test_trust_profile_routes(self):
        result = runner.invoke(app, ["trust", "profile", "inspect"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["command"] == "trust.profile.inspect"


class TestPageScoreWithMockedClient:
    @patch("confpub.confluence.build_client")
    @patch("confpub.config.load_config")
    def test_score_returns_envelope(self, mock_config, mock_build):
        mock_config.return_value = MagicMock(base_url="https://x.atlassian.net")
        client = MagicMock()
        mock_build.return_value = client
        client._call_count = 0

        now = datetime.now(timezone.utc).isoformat()
        client.get_page_by_id.return_value = {
            "id": "12345",
            "title": "Test Page",
            "status": "current",
            "version": {"number": 3, "when": now, "by": {"displayName": "user"}},
            "body": {"storage": {"value": "<h2>Title</h2><p>" + "text " * 100 + "</p>"}},
            "space": {"key": "EA"},
            "ancestors": [],
        }
        client.get_labels.return_value = [{"name": "governance"}]
        client.get_page_property.side_effect = ConfpubError("ERR_VALIDATION_NOT_FOUND", "Not found")
        client.get_page_history.return_value = [
            {"number": 3, "when": now, "by": "user", "message": "Updated"},
        ]

        result = runner.invoke(app, [
            "page", "score", "--page-id", "12345", "--refresh",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["command"] == "page.score"
        assert "score" in data["result"]
        assert "band" in data["result"]
        assert "subscores" in data["result"]
        assert 0 <= data["result"]["score"] <= 100
