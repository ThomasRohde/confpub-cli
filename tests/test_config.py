"""Tests for confpub.config module."""

import json
from pathlib import Path

import pytest

from confpub.config import (
    ConfigModel,
    ResolvedConfig,
    load_config,
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
        cfg = load_config()
        assert cfg.base_url == "https://env.atlassian.net/wiki"
        assert cfg.token == "env_token"
        assert cfg.user == "user@example.com"
        assert cfg.token_source == "env_var"

    def test_no_config(self, monkeypatch):
        monkeypatch.delenv("CONFPUB_URL", raising=False)
        monkeypatch.delenv("CONFPUB_TOKEN", raising=False)
        monkeypatch.delenv("CONFPUB_USER", raising=False)
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
