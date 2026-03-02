"""Integration tests — end-to-end CLI with mocked Confluence."""

import json

from typer.testing import CliRunner

from confpub.cli import app


runner = CliRunner()


class TestCLIHelp:
    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "confpub" in result.output
        assert "guide" in result.output
        assert "page" in result.output
        assert "plan" in result.output

    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "confpub" in result.output

    def test_page_help(self):
        result = runner.invoke(app, ["page", "--help"])
        assert result.exit_code == 0
        assert "publish" in result.output
        assert "list" in result.output
        assert "inspect" in result.output
        assert "delete" in result.output
        assert "pull" in result.output

    def test_page_pull_help(self):
        result = runner.invoke(app, ["page", "pull", "--help"])
        assert result.exit_code == 0
        assert "--space" in result.output
        assert "--title" in result.output
        assert "--page-id" in result.output
        assert "--recursive" in result.output
        assert "--force" in result.output
        assert "--layout" in result.output
        assert "--no-attachments" in result.output
        assert "--output" in result.output

    def test_plan_help(self):
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "validate" in result.output
        assert "apply" in result.output
        assert "verify" in result.output


class TestGuideCommand:
    def test_full_guide(self):
        result = runner.invoke(app, ["guide"])
        assert result.exit_code == 0
        # stdout should be valid JSON
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["command"] == "guide"
        assert "commands" in data["result"]
        assert "error_codes" in data["result"]

    def test_guide_section_auth(self):
        result = runner.invoke(app, ["guide", "--section", "auth"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "precedence" in data["result"]

    def test_guide_section_error_codes(self):
        result = runner.invoke(app, ["guide", "--section", "error_codes"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "ERR_AUTH_REQUIRED" in data["result"]

    def test_guide_section_commands(self):
        result = runner.invoke(app, ["guide", "--section", "commands"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "page.publish" in data["result"]

    def test_guide_invalid_section(self):
        result = runner.invoke(app, ["guide", "--section", "nonexistent"])
        assert result.exit_code == 10  # Validation error
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["errors"][0]["code"] == "ERR_VALIDATION_REQUIRED"


class TestPagePullValidation:
    def test_pull_without_args_returns_validation_error(self):
        result = runner.invoke(app, ["page", "pull"])
        assert result.exit_code == 10
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["errors"][0]["code"] == "ERR_VALIDATION_REQUIRED"


class TestPersonalSpaceKeyCLI:
    """Ensure ~username personal space keys (e.g. ~thro) pass through CLI correctly."""

    def test_space_tilde_in_page_list(self, monkeypatch):
        """--space ~thro must arrive as literal '~thro' in the command handler."""
        captured = {}

        def fake_list_pages(self, space, **kwargs):
            captured["space"] = space
            return {"pages": [], "start": 0, "limit": 25, "size": 0, "has_more": False}

        from confpub.confluence import ConfluenceClient
        monkeypatch.setattr(ConfluenceClient, "list_pages", fake_list_pages)
        monkeypatch.setattr("confpub.confluence.build_client", lambda: ConfluenceClient.__new__(ConfluenceClient))

        result = runner.invoke(app, ["page", "list", "--space", "~thro"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert captured["space"] == "~thro"


class TestSearchCommand:
    def test_search_help(self):
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "--cql" in result.output
        assert "--space" in result.output
        assert "--type" in result.output
        assert "--limit" in result.output
        assert "--start" in result.output
        assert "--include-archived" in result.output

    def test_search_no_args_validation_error(self):
        result = runner.invoke(app, ["search"])
        assert result.exit_code == 10
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["errors"][0]["code"] == "ERR_VALIDATION_REQUIRED"

    def test_search_cql_echoed_in_result(self, monkeypatch):
        def fake_search(self, cql, *, start=0, limit=25, include_archived_spaces=False, excerpt_length=200):
            return {"results": [], "total": 0, "start": start, "limit": limit, "has_more": False}

        from confpub.confluence import ConfluenceClient
        monkeypatch.setattr(ConfluenceClient, "search", fake_search)
        monkeypatch.setattr("confpub.confluence.build_client", lambda: ConfluenceClient.__new__(ConfluenceClient))

        result = runner.invoke(app, ["search", "--space", "DEV", "--cql", 'label = "api-docs"'])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["cql_query"] == 'space = "DEV" AND (label = "api-docs")'

    def test_search_in_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "search" in result.output


class TestQuietFlagPosition:
    """Bug 1: --quiet and --verbose should work between group name and subcommand."""

    def test_quiet_before_group(self):
        result = runner.invoke(app, ["--quiet", "page", "--help"])
        assert result.exit_code == 0

    def test_quiet_between_group_and_command(self):
        result = runner.invoke(app, ["page", "--quiet", "--help"])
        assert result.exit_code == 0

    def test_verbose_between_group_and_command(self):
        result = runner.invoke(app, ["page", "--verbose", "--help"])
        assert result.exit_code == 0

    def test_quiet_on_plan_group(self):
        result = runner.invoke(app, ["plan", "--quiet", "--help"])
        assert result.exit_code == 0


class TestDeleteCascadeResult:
    """Bug 3: Delete result should include deleted_ids and deleted_count."""

    def test_delete_result_has_deleted_ids(self, monkeypatch):
        from confpub.confluence import ConfluenceClient

        mock_client = ConfluenceClient.__new__(ConfluenceClient)
        monkeypatch.setattr("confpub.confluence.build_client", lambda: mock_client)
        monkeypatch.setattr(mock_client, "get_descendant_ids", lambda pid: ["child1", "child2"])
        monkeypatch.setattr(mock_client, "_delete_descendants", lambda pid: None)
        monkeypatch.setattr(mock_client, "delete_page", lambda pid: {"status": "deleted"})

        # Prevent lockfile I/O
        monkeypatch.setattr("confpub.lockfile.load_lockfile", lambda p: None)

        result = runner.invoke(app, ["page", "delete", "--page-id", "123", "--cascade"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "deleted_ids" in data["result"]
        assert "deleted_count" in data["result"]
        assert data["result"]["deleted_count"] == 3  # page + 2 children
        assert sorted(data["result"]["deleted_ids"]) == ["123", "child1", "child2"]


class TestLabelCommandHelp:
    def test_label_help(self):
        result = runner.invoke(app, ["label", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "add" in result.output
        assert "remove" in result.output

    def test_label_list_help(self):
        result = runner.invoke(app, ["label", "list", "--help"])
        assert result.exit_code == 0
        assert "--page-id" in result.output

    def test_label_add_help(self):
        result = runner.invoke(app, ["label", "add", "--help"])
        assert result.exit_code == 0
        assert "--page-id" in result.output
        assert "--label" in result.output

    def test_label_remove_help(self):
        result = runner.invoke(app, ["label", "remove", "--help"])
        assert result.exit_code == 0
        assert "--page-id" in result.output
        assert "--label" in result.output

    def test_label_in_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "label" in result.output


class TestCommentCommandHelp:
    def test_comment_help(self):
        result = runner.invoke(app, ["comment", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output

    def test_comment_add_help(self):
        result = runner.invoke(app, ["comment", "add", "--help"])
        assert result.exit_code == 0
        assert "--page-id" in result.output
        assert "--text" in result.output
        assert "--file" in result.output

    def test_comment_in_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "comment" in result.output


class TestPageMoveHelp:
    def test_page_move_help(self):
        result = runner.invoke(app, ["page", "move", "--help"])
        assert result.exit_code == 0
        assert "--page-id" in result.output
        assert "--target-parent" in result.output
        assert "--space" in result.output
        assert "--target-parent-id" in result.output

    def test_page_move_in_page_help(self):
        result = runner.invoke(app, ["page", "--help"])
        assert result.exit_code == 0
        assert "move" in result.output


class TestPagePublishLabelFlag:
    def test_publish_help_shows_label(self):
        result = runner.invoke(app, ["page", "publish", "--help"])
        assert result.exit_code == 0
        assert "--label" in result.output


class TestCommentValidation:
    def test_comment_add_requires_text_or_file(self):
        result = runner.invoke(app, ["comment", "add", "--page-id", "123"])
        assert result.exit_code == 10
        data = json.loads(result.output)
        assert data["ok"] is False

    def test_comment_add_rejects_both_text_and_file(self):
        result = runner.invoke(app, ["comment", "add", "--page-id", "123", "--text", "hi", "--file", "f.md"])
        assert result.exit_code == 10
        data = json.loads(result.output)
        assert data["ok"] is False


class TestPageMoveValidation:
    def test_move_requires_target(self):
        result = runner.invoke(app, ["page", "move", "--page-id", "123"])
        assert result.exit_code == 10
        data = json.loads(result.output)
        assert data["ok"] is False

    def test_move_target_parent_requires_space(self):
        result = runner.invoke(app, ["page", "move", "--page-id", "123", "--target-parent", "Root"])
        assert result.exit_code == 10
        data = json.loads(result.output)
        assert data["ok"] is False
        assert "space" in data["errors"][0]["message"].lower()


class TestCompactFlag:
    """Suggestion 4: --compact should produce single-line JSON output."""

    def test_compact_produces_single_line(self):
        result = runner.invoke(app, ["--compact", "guide"])
        assert result.exit_code == 0
        # Compact output should be a single line (no newlines within the JSON)
        lines = result.output.strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["ok"] is True

    def test_compact_between_group_and_command(self, monkeypatch):
        """--compact should work between group name and subcommand."""
        def fake_list_pages(self, space, **kwargs):
            return {"pages": [], "start": 0, "limit": 25, "size": 0, "has_more": False}

        from confpub.confluence import ConfluenceClient
        monkeypatch.setattr(ConfluenceClient, "list_pages", fake_list_pages)
        monkeypatch.setattr("confpub.confluence.build_client", lambda: ConfluenceClient.__new__(ConfluenceClient))

        result = runner.invoke(app, ["page", "--compact", "list", "--space", "DEV"])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert len(lines) == 1

    def test_without_compact_is_multiline(self):
        result = runner.invoke(app, ["guide"])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert len(lines) > 1


class TestVerboseDiagnostics:
    """Bug 6: --verbose should include rich diagnostics."""

    def test_verbose_includes_diagnostics(self):
        result = runner.invoke(app, ["--verbose", "guide"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "diagnostics" in data["metrics"]
        diag = data["metrics"]["diagnostics"]
        assert "duration_ms" in diag
        assert "confpub_version" in diag
        assert "command" in diag

    def test_verbose_with_client_includes_api_call_count(self, monkeypatch):
        """When a client is used, diagnostics should include api_call_count."""
        def fake_list_pages(self, space, **kwargs):
            self._call_count += 1
            return {"pages": [], "start": 0, "limit": 25, "size": 0, "has_more": False}

        from confpub.confluence import ConfluenceClient
        from confpub.config import ResolvedConfig
        from unittest.mock import patch, MagicMock

        mock_config = ResolvedConfig(
            base_url="https://test.atlassian.net/wiki",
            user="user@test.com",
            token="test_token",
            token_source="env_var",
        )

        with patch("confpub.confluence.ConfluenceClient._build_api") as mock_build:
            mock_build.return_value = MagicMock()
            real_client = ConfluenceClient(mock_config)

        monkeypatch.setattr(ConfluenceClient, "list_pages", fake_list_pages)
        monkeypatch.setattr("confpub.confluence.build_client", lambda: real_client)

        result = runner.invoke(app, ["page", "--verbose", "list", "--space", "DEV"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "diagnostics" in data["metrics"]
        diag = data["metrics"]["diagnostics"]
        assert "api_call_count" in diag
        assert diag["api_call_count"] >= 1


class TestPageListPagination:
    """Suggestion 1: page.list should return pagination metadata."""

    def test_page_list_has_pagination_fields(self, monkeypatch):
        def fake_list_pages(self, space, **kwargs):
            return {
                "pages": [{"id": "1", "title": "P1"}],
                "start": 0, "limit": 25, "size": 1, "has_more": False,
            }

        from confpub.confluence import ConfluenceClient
        from confpub.config import ResolvedConfig
        from unittest.mock import patch, MagicMock

        mock_config = ResolvedConfig(
            base_url="https://test.atlassian.net/wiki",
            user="user@test.com",
            token="test_token",
            token_source="env_var",
        )
        with patch("confpub.confluence.ConfluenceClient._build_api") as mock_build:
            mock_build.return_value = MagicMock()
            real_client = ConfluenceClient(mock_config)

        monkeypatch.setattr(ConfluenceClient, "list_pages", fake_list_pages)
        monkeypatch.setattr("confpub.confluence.build_client", lambda: real_client)

        result = runner.invoke(app, ["page", "list", "--space", "DEV"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        r = data["result"]
        assert "pages" in r
        assert "start" in r
        assert "limit" in r
        assert "size" in r
        assert "has_more" in r


class TestTitleFromH1Flag:
    """Suggestion 2: --title-from-h1 flag should be available on page publish."""

    def test_title_from_h1_in_help(self):
        result = runner.invoke(app, ["page", "publish", "--help"])
        assert result.exit_code == 0
        assert "--title-from-h1" in result.output


class TestEnvelopeContract:
    def test_guide_returns_full_envelope(self):
        result = runner.invoke(app, ["guide"])
        data = json.loads(result.output)
        # Check all required envelope fields
        for key in ("schema_version", "request_id", "ok", "command", "result", "errors", "warnings", "metrics"):
            assert key in data, f"Missing envelope field: {key}"
        assert isinstance(data["errors"], list)
        assert isinstance(data["warnings"], list)
        assert isinstance(data["metrics"], dict)
        assert "duration_ms" in data["metrics"]
        assert data["request_id"].startswith("req_")
