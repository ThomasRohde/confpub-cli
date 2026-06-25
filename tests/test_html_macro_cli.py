"""CLI tests for html-macro detect/adopt."""

import json
from unittest.mock import MagicMock


FORGE_STORAGE = (
    "<ac:adf-extension>"
    '<ac:adf-node type="extension">'
    '<ac:adf-attribute key="extension-key">ari/app/env/static/macro-html</ac:adf-attribute>'
    '<ac:adf-attribute key="parameters">'
    '<ac:adf-parameter key="extension-id">ari:cloud:ecosystem::extension/app/env/static/macro-html</ac:adf-parameter>'
    '<ac:adf-parameter key="cloud-id">cloud-123</ac:adf-parameter>'
    '<ac:adf-parameter key="context-ids">ari:cloud:confluence:site/cloud-123</ac:adf-parameter>'
    '<ac:adf-parameter key="account-id">account-123</ac:adf-parameter>'
    '<ac:adf-parameter key="guest-params">'
    '<ac:adf-parameter key="__body-content">&lt;div&gt;ok&lt;/div&gt;</ac:adf-parameter>'
    "</ac:adf-parameter>"
    "</ac:adf-attribute>"
    "</ac:adf-node>"
    "</ac:adf-extension>"
)

CLASSIC_STORAGE = (
    '<ac:structured-macro ac:name="html-macro">'
    "<ac:plain-text-body><![CDATA[<b>ok</b>]]></ac:plain-text-body>"
    "</ac:structured-macro>"
)


def _mock_page(storage: str) -> dict:
    return {
        "id": "123",
        "title": "Working HTML Macro",
        "body": {"storage": {"value": storage}},
    }


def test_html_macro_detect_from_page(run_cli, monkeypatch):
    mock_client = MagicMock()
    mock_client.get_page_by_id.return_value = _mock_page(FORGE_STORAGE)
    monkeypatch.setattr("confpub.confluence.build_client", lambda: mock_client)

    result = run_cli("html-macro", "detect", "--from-page", "123")

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["result"]["candidate_count"] == 1
    candidate = data["result"]["candidates"][0]
    assert candidate["format"] == "forge-adf-extension"
    assert candidate["html_macro_name"] == "macro-html"
    assert candidate["config"]["html_macro_forge_extension_key"] == "ari/app/env/static/macro-html"
    assert "confpub config set html_macro_format forge-adf-extension" in candidate["config_commands"]


def test_html_macro_adopt_requires_candidate_when_ambiguous(run_cli, monkeypatch):
    mock_client = MagicMock()
    mock_client.get_page_by_id.return_value = _mock_page(CLASSIC_STORAGE + FORGE_STORAGE)
    monkeypatch.setattr("confpub.confluence.build_client", lambda: mock_client)

    result = run_cli("html-macro", "adopt", "--from-page", "123", "--dry-run")

    assert result.exit_code == 10
    data = json.loads(result.output)
    assert data["ok"] is False
    assert "Multiple HTML macro setting candidates" in data["errors"][0]["message"]


def test_html_macro_adopt_dry_run_does_not_write(run_cli, monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("confpub.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("confpub.config.CONFIG_FILE", config_file)
    mock_client = MagicMock()
    mock_client.get_page_by_id.return_value = _mock_page(FORGE_STORAGE)
    monkeypatch.setattr("confpub.confluence.build_client", lambda: mock_client)

    result = run_cli("html-macro", "adopt", "--from-page", "123", "--dry-run")

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["result"]["dry_run"] is True
    assert data["result"]["adopted"] is False
    assert not config_file.exists()


def test_html_macro_adopt_persists_config(run_cli, monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("confpub.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("confpub.config.CONFIG_FILE", config_file)
    mock_client = MagicMock()
    mock_client.get_page_by_id.return_value = _mock_page(FORGE_STORAGE)
    monkeypatch.setattr("confpub.confluence.build_client", lambda: mock_client)

    result = run_cli("html-macro", "adopt", "--from-page", "123")

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["result"]["adopted"] is True
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved["html_macro_name"] == "macro-html"
    assert saved["html_macro_format"] == "forge-adf-extension"
    assert saved["html_macro_forge_extension_key"] == "ari/app/env/static/macro-html"


def test_page_publish_hoists_domain_warnings_to_envelope(run_cli, monkeypatch, tmp_path):
    md_file = tmp_path / "page.md"
    md_file.write_text("# Page", encoding="utf-8")

    def fake_publish_page(**kwargs):
        return {
            "dry_run": True,
            "changes": [],
            "summary": {},
            "warnings": ["domain warning"],
        }

    monkeypatch.setattr("confpub.publish.publish_page", fake_publish_page)

    result = run_cli(
        "page",
        "publish",
        str(md_file),
        "--space",
        "DEV",
        "--parent",
        "Root",
        "--dry-run",
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["warnings"] == ["domain warning"]
    assert "warnings" not in data["result"]
