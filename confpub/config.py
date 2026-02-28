"""Credential precedence, config file, and env var management.

Precedence (highest → lowest):
  CLI flags → env vars → config file → OS keychain
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from confpub.errors import ERR_AUTH_REQUIRED, ConfpubError

CONFIG_DIR = Path.home() / ".config" / "confpub"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Environment variable names
ENV_URL = "CONFPUB_URL"
ENV_TOKEN = "CONFPUB_TOKEN"
ENV_USER = "CONFPUB_USER"


class ConfigModel(BaseModel):
    """Persisted configuration file model."""

    base_url: Optional[str] = None
    user: Optional[str] = None
    token: Optional[str] = None


class ResolvedConfig:
    """Fully resolved configuration with credential status."""

    def __init__(
        self,
        base_url: str | None = None,
        user: str | None = None,
        token: str | None = None,
        token_source: str | None = None,
    ) -> None:
        self.base_url = base_url
        self.user = user
        self.token = token
        self.token_source = token_source

    @property
    def is_cloud(self) -> bool:
        """Auto-detect Cloud vs Server from URL."""
        if not self.base_url:
            return False
        return ".atlassian.net" in self.base_url

    @property
    def auth_type(self) -> str:
        """Return 'token' for Cloud, 'pat' for Server."""
        return "token" if self.is_cloud else "pat"

    @property
    def has_credentials(self) -> bool:
        return bool(self.base_url and self.token)

    def require_credentials(self) -> None:
        """Raise ConfpubError if credentials are missing."""
        if not self.base_url:
            raise ConfpubError(
                ERR_AUTH_REQUIRED,
                "No Confluence URL configured",
                details={
                    "methods": ["env_var", "config_file", "cli_flag"],
                    "env_vars": [ENV_URL],
                    "docs": "confpub guide --section auth",
                },
            )
        if not self.token:
            raise ConfpubError(
                ERR_AUTH_REQUIRED,
                "No credentials configured",
                details={
                    "methods": ["env_var", "config_file", "cli_flag"],
                    "env_vars": [ENV_TOKEN, ENV_USER],
                    "docs": "confpub guide --section auth",
                },
            )

    def auth_status(self) -> dict[str, Any]:
        """Return the auth.inspect result."""
        return {
            "base_url": self.base_url,
            "user": self.user,
            "auth_type": self.auth_type if self.base_url else None,
            "token_source": self.token_source,
            "token_valid": self.has_credentials,
            "token_expires_at": None,
        }

    def to_display_dict(self) -> dict[str, Any]:
        """Return safe-to-display config (token masked)."""
        return {
            "base_url": self.base_url,
            "user": self.user,
            "token": "***" if self.token else None,
            "token_source": self.token_source,
            "is_cloud": self.is_cloud,
        }


def _load_config_file() -> ConfigModel:
    """Load the config file if it exists."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            return ConfigModel(**data)
        except (json.JSONDecodeError, Exception):
            return ConfigModel()
    return ConfigModel()


def _try_keyring(service: str, username: str) -> str | None:
    """Try to get a credential from the OS keychain."""
    try:
        import keyring as kr
        return kr.get_password(service, username)
    except Exception:
        return None


def load_config(
    cli_url: str | None = None,
    cli_user: str | None = None,
    cli_token: str | None = None,
) -> ResolvedConfig:
    """Resolve config using precedence: CLI → env → file → keychain."""
    file_cfg = _load_config_file()

    # URL
    url = cli_url or os.environ.get(ENV_URL) or file_cfg.base_url
    # User
    user = cli_user or os.environ.get(ENV_USER) or file_cfg.user
    # Token
    token = cli_token or os.environ.get(ENV_TOKEN) or file_cfg.token

    # Determine source
    token_source = None
    if cli_token:
        token_source = "cli_flag"
    elif os.environ.get(ENV_TOKEN):
        token_source = "env_var"
    elif file_cfg.token:
        token_source = "config_file"

    # Try keychain as fallback
    if not token and url:
        kr_token = _try_keyring("confpub", user or "default")
        if kr_token:
            token = kr_token
            token_source = "keychain"

    return ResolvedConfig(
        base_url=url,
        user=user,
        token=token,
        token_source=token_source,
    )


def set_config_value(key: str, value: str) -> None:
    """Write a config value to the config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = _load_config_file()

    if key == "base_url":
        cfg.base_url = value
    elif key == "user":
        cfg.user = value
    elif key == "token":
        cfg.token = value
    else:
        from confpub.errors import ERR_VALIDATION_REQUIRED, validation_error
        raise validation_error(
            ERR_VALIDATION_REQUIRED,
            f"Unknown config key: {key}. Valid keys: base_url, user, token",
        )

    CONFIG_FILE.write_text(json.dumps(cfg.model_dump(exclude_none=True), indent=2))
