"""Tests for confpub.config module."""

import json
from pathlib import Path

import pytest

from confpub.config import (
    ConfigModel,
    ENV_HTML_MACRO_FORGE_ACCOUNT_ID,
    ENV_HTML_MACRO_FORGE_CLOUD_ID,
    ENV_HTML_MACRO_FORGE_CONTEXT_IDS,
    ENV_HTML_MACRO_FORMAT,
    ENV_HTML_MACRO_FORGE_EXTENSION_ID,
    ENV_HTML_MACRO_FORGE_EXTENSION_KEY,
    ENV_HTML_MACRO_NAME,
    ResolvedConfig,
    default_html_macro_name,
    load_config,
    resolve_html_macro_format,
    resolve_html_macro_name,
    resolve_html_macro_settings,
    set_config_value,
)
from confpub.errors import ConfpubError, ERR_AUTH_REQUIRED


class TestResolvedConfig:
    def test_cloud_detection(self):
        cfg = ResolvedConfig(base_url="https://myorg.atlassian.net/wiki")
        assert cfg.is_cloud is True
        assert cfg.auth_type == "token"

    def test_server_detection(self):
        cfg = ResolvedConfig(base_url="https://confluence.internal.com")
        assert cfg.is_cloud is False
        assert cfg.auth_type == "pat"

    def test_no_url(self):
        cfg = ResolvedConfig()
        assert cfg.is_cloud is False
        assert cfg.has_credentials is False

    def test_has_credentials(self):
        cfg = ResolvedConfig(base_url="https://x.atlassian.net/wiki", token="abc")
        assert cfg.has_credentials is True

    def test_require_credentials_no_url(self):
        cfg = ResolvedConfig()
        with pytest.raises(ConfpubError) as exc_info:
            cfg.require_credentials()
        assert exc_info.value.code == ERR_AUTH_REQUIRED
        assert "URL" in exc_info.value.error_message

    def test_require_credentials_no_token(self):
        cfg = ResolvedConfig(base_url="https://x.atlassian.net/wiki")
        with pytest.raises(ConfpubError) as exc_info:
            cfg.require_credentials()
        assert exc_info.value.code == ERR_AUTH_REQUIRED

    def test_auth_status(self):
        cfg = ResolvedConfig(
            base_url="https://x.atlassian.net/wiki",
            user="me@example.com",
            token="tok",
            token_source="env_var",
        )
        status = cfg.auth_status()
        assert status["base_url"] == "https://x.atlassian.net/wiki"
        assert status["user"] == "me@example.com"
        assert status["auth_type"] == "token"
        assert status["token_source"] == "env_var"
        assert status["token_valid"] is True

    def test_to_display_dict_masks_token(self):
        cfg = ResolvedConfig(token="secret123")
        d = cfg.to_display_dict()
        assert d["token"] == "***"

    def test_to_display_dict_includes_html_macro_resolution(self):
        cfg = ResolvedConfig(base_url="https://x.atlassian.net/wiki")
        d = cfg.to_display_dict()
        assert d["html_macro_name"] is None
        assert d["effective_html_macro_name"] == "html-macro"
        assert d["effective_html_macro_format"] == "classic"
        assert d["html_macro_resolution"]["name"]["source"] == "default"
        assert d["html_macro_resolution"]["name"]["site_verified"] is False
        assert d["html_macro_resolution"]["format"]["source"] == "default"
        assert d["html_macro_resolution"]["format"]["site_verified"] is False


class TestLoadConfig:
    def test_cli_flags_take_precedence(self, monkeypatch):
        monkeypatch.setenv("CONFPUB_URL", "https://env.atlassian.net/wiki")
        monkeypatch.setenv("CONFPUB_TOKEN", "env_token")
        cfg = load_config(cli_url="https://cli.atlassian.net/wiki", cli_token="cli_token")
        assert cfg.base_url == "https://cli.atlassian.net/wiki"
        assert cfg.token == "cli_token"
        assert cfg.token_source == "cli_flag"

    def test_env_vars(self, monkeypatch):
        monkeypatch.setenv("CONFPUB_URL", "https://env.atlassian.net/wiki")
        monkeypatch.setenv("CONFPUB_TOKEN", "env_token")
        monkeypatch.setenv("CONFPUB_USER", "user@example.com")
        monkeypatch.setenv(ENV_HTML_MACRO_NAME, "html-macro")
        monkeypatch.setenv(ENV_HTML_MACRO_FORMAT, "forge-adf-extension")
        monkeypatch.setenv(ENV_HTML_MACRO_FORGE_EXTENSION_KEY, "app/static/macro-html")
        monkeypatch.setenv(ENV_HTML_MACRO_FORGE_EXTENSION_ID, "ari:cloud:ecosystem::extension/app/static/macro-html")
        monkeypatch.setenv(ENV_HTML_MACRO_FORGE_CLOUD_ID, "cloud-123")
        monkeypatch.setenv(ENV_HTML_MACRO_FORGE_CONTEXT_IDS, "ari:cloud:confluence:site/cloud-123")
        monkeypatch.setenv(ENV_HTML_MACRO_FORGE_ACCOUNT_ID, "account-123")
        cfg = load_config()
        assert cfg.base_url == "https://env.atlassian.net/wiki"
        assert cfg.token == "env_token"
        assert cfg.user == "user@example.com"
        assert cfg.token_source == "env_var"
        assert cfg.html_macro_name == "html-macro"
        assert cfg.html_macro_format == "forge-adf-extension"
        assert cfg.html_macro_name_source == "env_var"
        assert cfg.html_macro_format_source == "env_var"
        assert cfg.html_macro_forge_extension_key == "app/static/macro-html"
        assert cfg.html_macro_forge_extension_id == "ari:cloud:ecosystem::extension/app/static/macro-html"
        assert cfg.html_macro_forge_cloud_id == "cloud-123"
        assert cfg.html_macro_forge_context_ids == "ari:cloud:confluence:site/cloud-123"
        assert cfg.html_macro_forge_account_id == "account-123"

    def test_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr("confpub.config.CONFIG_FILE", tmp_path / "missing-config.json")
        monkeypatch.delenv("CONFPUB_URL", raising=False)
        monkeypatch.delenv("CONFPUB_TOKEN", raising=False)
        monkeypatch.delenv("CONFPUB_USER", raising=False)
        monkeypatch.delenv(ENV_HTML_MACRO_NAME, raising=False)
        monkeypatch.delenv(ENV_HTML_MACRO_FORMAT, raising=False)
        monkeypatch.delenv(ENV_HTML_MACRO_FORGE_EXTENSION_KEY, raising=False)
        monkeypatch.delenv(ENV_HTML_MACRO_FORGE_EXTENSION_ID, raising=False)
        monkeypatch.delenv(ENV_HTML_MACRO_FORGE_CLOUD_ID, raising=False)
        monkeypatch.delenv(ENV_HTML_MACRO_FORGE_CONTEXT_IDS, raising=False)
        monkeypatch.delenv(ENV_HTML_MACRO_FORGE_ACCOUNT_ID, raising=False)
        cfg = load_config()
        assert cfg.base_url is None
        assert cfg.token is None


class TestSetConfigValue:
    def test_set_base_url(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr("confpub.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("confpub.config.CONFIG_FILE", config_file)
        set_config_value("base_url", "https://test.atlassian.net/wiki")
        data = json.loads(config_file.read_text())
        assert data["base_url"] == "https://test.atlassian.net/wiki"

    def test_set_unknown_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr("confpub.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("confpub.config.CONFIG_FILE", tmp_path / "config.json")
        with pytest.raises(ConfpubError):
            set_config_value("unknown_key", "value")

    def test_set_html_macro_name(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr("confpub.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("confpub.config.CONFIG_FILE", config_file)
        set_config_value("html_macro_name", "html-macro")
        data = json.loads(config_file.read_text())
        assert data["html_macro_name"] == "html-macro"

    def test_set_forge_html_macro_fields(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        monkeypatch.setattr("confpub.config.CONFIG_DIR", tmp_path)
        monkeypatch.setattr("confpub.config.CONFIG_FILE", config_file)

        set_config_value("html_macro_format", "forge-adf-extension")
        set_config_value("html_macro_forge_extension_key", "app/static/macro-html")
        set_config_value(
            "html_macro_forge_extension_id",
            "ari:cloud:ecosystem::extension/app/static/macro-html",
        )
        set_config_value("html_macro_forge_cloud_id", "cloud-123")
        set_config_value("html_macro_forge_context_ids", "ari:cloud:confluence:site/cloud-123")
        set_config_value("html_macro_forge_account_id", "account-123")

        data = json.loads(config_file.read_text())
        assert data["html_macro_format"] == "forge-adf-extension"
        assert data["html_macro_forge_extension_key"] == "app/static/macro-html"
        assert data["html_macro_forge_extension_id"] == "ari:cloud:ecosystem::extension/app/static/macro-html"
        assert data["html_macro_forge_cloud_id"] == "cloud-123"
        assert data["html_macro_forge_context_ids"] == "ari:cloud:confluence:site/cloud-123"
        assert data["html_macro_forge_account_id"] == "account-123"


class TestHtmlMacroNameResolution:
    def test_default_cloud_macro_name(self):
        assert default_html_macro_name(True) == "html-macro"

    def test_default_server_macro_name(self):
        assert default_html_macro_name(False) == "html"

    def test_override_wins_over_config(self):
        cfg = ResolvedConfig(
            base_url="https://x.atlassian.net/wiki",
            html_macro_name="html-macro",
        )
        assert resolve_html_macro_name(cfg, "custom-html") == "custom-html"

    def test_config_wins_over_platform_default(self):
        cfg = ResolvedConfig(
            base_url="https://x.atlassian.net/wiki",
            html_macro_name="html-macro",
        )
        assert resolve_html_macro_name(cfg) == "html-macro"

    def test_file_config_is_loaded(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "base_url": "https://x.atlassian.net/wiki",
            "html_macro_name": "html-macro",
        }))
        monkeypatch.setattr("confpub.config.CONFIG_FILE", config_file)
        monkeypatch.delenv(ENV_HTML_MACRO_NAME, raising=False)

        cfg = load_config()

        assert cfg.html_macro_name == "html-macro"
        assert cfg.html_macro_name_source == "config_file"
        assert resolve_html_macro_name(cfg) == "html-macro"


class TestHtmlMacroFormatResolution:
    def test_default_format_is_classic(self):
        assert resolve_html_macro_format(ResolvedConfig()) == "classic"

    def test_forge_format_from_config(self):
        cfg = ResolvedConfig(html_macro_format="forge-adf-extension")
        assert resolve_html_macro_format(cfg) == "forge-adf-extension"

    def test_invalid_format_raises_validation_error(self):
        cfg = ResolvedConfig(html_macro_format="bad-format")
        with pytest.raises(ConfpubError):
            resolve_html_macro_format(cfg)

    def test_forge_settings_require_identifiers(self):
        cfg = ResolvedConfig(html_macro_format="forge-adf-extension")
        with pytest.raises(ConfpubError) as exc_info:
            resolve_html_macro_settings(cfg)
        assert "html_macro_forge_extension_key" in exc_info.value.details["missing"]
        assert "html_macro_forge_extension_id" in exc_info.value.details["missing"]

    def test_forge_settings_resolved(self):
        cfg = ResolvedConfig(
            base_url="https://x.atlassian.net/wiki",
            html_macro_name="macro-html",
            html_macro_format="forge-adf-extension",
            html_macro_forge_extension_key="app/static/macro-html",
            html_macro_forge_extension_id="ari:cloud:ecosystem::extension/app/static/macro-html",
            html_macro_forge_cloud_id="cloud-123",
            html_macro_forge_context_ids="ari:cloud:confluence:site/cloud-123",
            html_macro_forge_account_id="account-123",
        )

        settings = resolve_html_macro_settings(cfg)

        assert settings.name == "macro-html"
        assert settings.format == "forge-adf-extension"
        assert settings.forge_extension_key == "app/static/macro-html"
        assert settings.forge_extension_id == "ari:cloud:ecosystem::extension/app/static/macro-html"
        assert settings.forge_environment == "PRODUCTION"
        assert settings.forge_cloud_id == "cloud-123"
        assert settings.forge_context_ids == "ari:cloud:confluence:site/cloud-123"
        assert settings.forge_account_id == "account-123"
