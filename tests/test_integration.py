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

        def fake_list_pages(self, space):
            captured["space"] = space
            return []

        from confpub.confluence import ConfluenceClient
        monkeypatch.setattr(ConfluenceClient, "list_pages", fake_list_pages)
        monkeypatch.setattr("confpub.confluence.build_client", lambda: ConfluenceClient.__new__(ConfluenceClient))

        result = runner.invoke(app, ["page", "list", "--space", "~thro"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert captured["space"] == "~thro"


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
