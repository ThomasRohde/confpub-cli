"""Credential precedence, config file, and env var management.

Precedence (highest → lowest):
  CLI flags → env vars → config file → OS keychain
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
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
ENV_SSL_VERIFY = "CONFPUB_SSL_VERIFY"
ENV_SPACE = "CONFPUB_SPACE"
ENV_HTML_MACRO_NAME = "CONFPUB_HTML_MACRO_NAME"
ENV_HTML_MACRO_FORMAT = "CONFPUB_HTML_MACRO_FORMAT"
ENV_HTML_MACRO_FORGE_EXTENSION_KEY = "CONFPUB_HTML_MACRO_FORGE_EXTENSION_KEY"
ENV_HTML_MACRO_FORGE_EXTENSION_ID = "CONFPUB_HTML_MACRO_FORGE_EXTENSION_ID"
ENV_HTML_MACRO_FORGE_ENVIRONMENT = "CONFPUB_HTML_MACRO_FORGE_ENVIRONMENT"
ENV_HTML_MACRO_FORGE_CLOUD_ID = "CONFPUB_HTML_MACRO_FORGE_CLOUD_ID"
ENV_HTML_MACRO_FORGE_CONTEXT_IDS = "CONFPUB_HTML_MACRO_FORGE_CONTEXT_IDS"
ENV_HTML_MACRO_FORGE_ACCOUNT_ID = "CONFPUB_HTML_MACRO_FORGE_ACCOUNT_ID"

DEFAULT_HTML_MACRO_NAME_SERVER = "html"
DEFAULT_HTML_MACRO_NAME_CLOUD = "html-macro"
DEFAULT_HTML_MACRO_FORMAT = "classic"
DEFAULT_HTML_MACRO_FORGE_ENVIRONMENT = "PRODUCTION"
HTML_MACRO_FORMAT_CLASSIC = "classic"
HTML_MACRO_FORMAT_FORGE_ADF_EXTENSION = "forge-adf-extension"
VALID_HTML_MACRO_FORMATS = {
    HTML_MACRO_FORMAT_CLASSIC,
    HTML_MACRO_FORMAT_FORGE_ADF_EXTENSION,
}


@dataclass(frozen=True)
class HtmlMacroSettings:
    """Resolved settings for rendering ::: html blocks."""

    name: str
    format: str
    name_source: str = "default"
    format_source: str = "default"
    forge_extension_key: str | None = None
    forge_extension_id: str | None = None
    forge_environment: str = DEFAULT_HTML_MACRO_FORGE_ENVIRONMENT
    forge_cloud_id: str | None = None
    forge_context_ids: str | None = None
    forge_account_id: str | None = None


class ConfigModel(BaseModel):
    """Persisted configuration file model."""

    base_url: Optional[str] = None
    user: Optional[str] = None
    token: Optional[str] = None
    ssl_verify: Optional[str] = None
    html_macro_name: Optional[str] = None
    html_macro_format: Optional[str] = None
    html_macro_forge_extension_key: Optional[str] = None
    html_macro_forge_extension_id: Optional[str] = None
    html_macro_forge_environment: Optional[str] = None
    html_macro_forge_cloud_id: Optional[str] = None
    html_macro_forge_context_ids: Optional[str] = None
    html_macro_forge_account_id: Optional[str] = None


class ResolvedConfig:
    """Fully resolved configuration with credential status."""

    def __init__(
        self,
        base_url: str | None = None,
        user: str | None = None,
        token: str | None = None,
        token_source: str | None = None,
        ssl_verify: bool | str = False,
        html_macro_name: str | None = None,
        html_macro_format: str | None = None,
        html_macro_forge_extension_key: str | None = None,
        html_macro_forge_extension_id: str | None = None,
        html_macro_forge_environment: str | None = None,
        html_macro_forge_cloud_id: str | None = None,
        html_macro_forge_context_ids: str | None = None,
        html_macro_forge_account_id: str | None = None,
        html_macro_name_source: str | None = None,
        html_macro_format_source: str | None = None,
    ) -> None:
        self.base_url = base_url
        self.user = user
        self.token = token
        self.token_source = token_source
        self.ssl_verify = ssl_verify
        self.html_macro_name = html_macro_name
        self.html_macro_format = html_macro_format
        self.html_macro_forge_extension_key = html_macro_forge_extension_key
        self.html_macro_forge_extension_id = html_macro_forge_extension_id
        self.html_macro_forge_environment = html_macro_forge_environment
        self.html_macro_forge_cloud_id = html_macro_forge_cloud_id
        self.html_macro_forge_context_ids = html_macro_forge_context_ids
        self.html_macro_forge_account_id = html_macro_forge_account_id
        self.html_macro_name_source = html_macro_name_source or (
            "configured" if html_macro_name else "default"
        )
        self.html_macro_format_source = html_macro_format_source or (
            "configured" if html_macro_format else "default"
        )

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
        html_macro_resolution = html_macro_resolution_dict(self)
        return {
            "base_url": self.base_url,
            "user": self.user,
            "token": "***" if self.token else None,
            "token_source": self.token_source,
            "is_cloud": self.is_cloud,
            "html_macro_name": self.html_macro_name,
            "effective_html_macro_name": resolve_html_macro_name(self),
            "html_macro_format": self.html_macro_format,
            "effective_html_macro_format": resolve_html_macro_format(self),
            "html_macro_forge_extension_key": self.html_macro_forge_extension_key,
            "html_macro_forge_extension_id": self.html_macro_forge_extension_id,
            "html_macro_forge_environment": self.html_macro_forge_environment,
            "html_macro_forge_cloud_id": self.html_macro_forge_cloud_id,
            "html_macro_forge_context_ids": self.html_macro_forge_context_ids,
            "html_macro_forge_account_id": self.html_macro_forge_account_id,
            "html_macro_resolution": html_macro_resolution,
        }


def _load_config_file() -> ConfigModel:
    """Load the config file if it exists."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
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


def _resolve_ssl_verify(raw: str | None) -> bool | str:
    """Parse an ssl_verify value into bool or CA-bundle path.

    Accepts "true"/"false" (case-insensitive) or a filesystem path.
    Returns False (default) when *raw* is None or empty.
    """
    if not raw:
        return False
    lower = raw.strip().lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    # Treat as CA bundle path
    return raw.strip()


def _normalize_optional_string(raw: str | None) -> str | None:
    """Return a stripped string, or None for missing/blank values."""
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def default_html_macro_name(is_cloud: bool) -> str:
    """Return the built-in HTML macro fallback for a Confluence deployment."""
    return DEFAULT_HTML_MACRO_NAME_CLOUD if is_cloud else DEFAULT_HTML_MACRO_NAME_SERVER


def resolve_html_macro_name(config: Any, override: str | None = None) -> str:
    """Resolve the HTML macro name for Markdown conversion.

    Precedence is caller override, resolved config, then platform default.
    The Cloud default is only a fallback; Marketplace apps can register
    different macro names.
    """
    override_value = _normalize_optional_string(override)
    if override_value:
        return override_value

    configured = getattr(config, "html_macro_name", None)
    if isinstance(configured, str):
        configured_value = _normalize_optional_string(configured)
        if configured_value:
            return configured_value

    return default_html_macro_name(bool(getattr(config, "is_cloud", False)))


def resolve_html_macro_format(config: Any, override: str | None = None) -> str:
    """Resolve the storage format used for ::: html blocks."""
    override_value = _normalize_optional_string(override)
    configured = getattr(config, "html_macro_format", None)
    value = override_value or (
        _normalize_optional_string(configured) if isinstance(configured, str) else None
    ) or DEFAULT_HTML_MACRO_FORMAT
    normalized = value.lower()
    if normalized not in VALID_HTML_MACRO_FORMATS:
        from confpub.errors import ERR_VALIDATION_REQUIRED, validation_error
        raise validation_error(
            ERR_VALIDATION_REQUIRED,
            f"Unknown html_macro_format: {value}. Valid values: classic, forge-adf-extension",
            value=value,
            valid_values=sorted(VALID_HTML_MACRO_FORMATS),
        )
    return normalized


def resolve_html_macro_name_source(config: Any, override: str | None = None) -> str:
    """Return where the effective HTML macro name came from."""
    if _normalize_optional_string(override):
        return "override"
    configured = getattr(config, "html_macro_name", None)
    if isinstance(configured, str) and _normalize_optional_string(configured):
        return str(getattr(config, "html_macro_name_source", None) or "configured")
    return "default"


def resolve_html_macro_format_source(config: Any, override: str | None = None) -> str:
    """Return where the effective HTML macro format came from."""
    if _normalize_optional_string(override):
        return "override"
    configured = getattr(config, "html_macro_format", None)
    if isinstance(configured, str) and _normalize_optional_string(configured):
        return str(getattr(config, "html_macro_format_source", None) or "configured")
    return "default"


def html_macro_resolution_dict(config: Any) -> dict[str, Any]:
    """Return display metadata that distinguishes defaults from configured values."""
    name_source = resolve_html_macro_name_source(config)
    format_source = resolve_html_macro_format_source(config)
    return {
        "name": {
            "value": resolve_html_macro_name(config),
            "source": name_source,
            "site_verified": False,
        },
        "format": {
            "value": resolve_html_macro_format(config),
            "source": format_source,
            "site_verified": False,
        },
    }


def _resolve_configured_string(config: Any, attr: str, override: str | None = None) -> str | None:
    override_value = _normalize_optional_string(override)
    if override_value:
        return override_value
    configured = getattr(config, attr, None)
    if isinstance(configured, str):
        return _normalize_optional_string(configured)
    return None


def resolve_html_macro_settings(
    config: Any,
    *,
    name_override: str | None = None,
    format_override: str | None = None,
    forge_extension_key_override: str | None = None,
    forge_extension_id_override: str | None = None,
    forge_environment_override: str | None = None,
    forge_cloud_id_override: str | None = None,
    forge_context_ids_override: str | None = None,
    forge_account_id_override: str | None = None,
) -> HtmlMacroSettings:
    """Resolve and validate all HTML macro rendering settings."""
    name = resolve_html_macro_name(config, name_override)
    macro_format = resolve_html_macro_format(config, format_override)
    name_source = resolve_html_macro_name_source(config, name_override)
    format_source = resolve_html_macro_format_source(config, format_override)
    forge_extension_key = _resolve_configured_string(
        config, "html_macro_forge_extension_key", forge_extension_key_override,
    )
    forge_extension_id = _resolve_configured_string(
        config, "html_macro_forge_extension_id", forge_extension_id_override,
    )
    forge_environment = (
        _resolve_configured_string(
            config, "html_macro_forge_environment", forge_environment_override,
        )
        or DEFAULT_HTML_MACRO_FORGE_ENVIRONMENT
    )
    forge_cloud_id = _resolve_configured_string(
        config, "html_macro_forge_cloud_id", forge_cloud_id_override,
    )
    forge_context_ids = _resolve_configured_string(
        config, "html_macro_forge_context_ids", forge_context_ids_override,
    )
    forge_account_id = _resolve_configured_string(
        config, "html_macro_forge_account_id", forge_account_id_override,
    )

    if macro_format == HTML_MACRO_FORMAT_FORGE_ADF_EXTENSION and (
        not forge_extension_key or not forge_extension_id
    ):
        from confpub.errors import ERR_VALIDATION_REQUIRED, validation_error
        missing = []
        if not forge_extension_key:
            missing.append("html_macro_forge_extension_key")
        if not forge_extension_id:
            missing.append("html_macro_forge_extension_id")
        raise validation_error(
            ERR_VALIDATION_REQUIRED,
            "Forge HTML macro format requires extension key and extension ID from a working macro",
            missing=missing,
            how_to_find=(
                "Inspect a page with a working Forge HTML macro using "
                "confpub page inspect --page-id <id> --raw and copy extension-key and extension-id"
            ),
        )

    return HtmlMacroSettings(
        name=name,
        format=macro_format,
        name_source=name_source,
        format_source=format_source,
        forge_extension_key=forge_extension_key,
        forge_extension_id=forge_extension_id,
        forge_environment=forge_environment,
        forge_cloud_id=forge_cloud_id,
        forge_context_ids=forge_context_ids,
        forge_account_id=forge_account_id,
    )


def load_config(
    cli_url: str | None = None,
    cli_user: str | None = None,
    cli_token: str | None = None,
    cli_ssl_verify: str | None = None,
) -> ResolvedConfig:
    """Resolve config using precedence: CLI → env → file → keychain."""
    file_cfg = _load_config_file()

    # URL
    url = cli_url or os.environ.get(ENV_URL) or file_cfg.base_url
    # User
    user = cli_user or os.environ.get(ENV_USER) or file_cfg.user
    # Token
    token = cli_token or os.environ.get(ENV_TOKEN) or file_cfg.token

    # SSL verification
    ssl_raw = cli_ssl_verify or os.environ.get(ENV_SSL_VERIFY) or file_cfg.ssl_verify
    ssl_verify = _resolve_ssl_verify(ssl_raw)

    # HTML macro name (for ::: html blocks)
    env_html_macro_name = _normalize_optional_string(os.environ.get(ENV_HTML_MACRO_NAME))
    file_html_macro_name = _normalize_optional_string(file_cfg.html_macro_name)
    html_macro_name = env_html_macro_name or file_html_macro_name
    html_macro_name_source = (
        "env_var" if env_html_macro_name else "config_file" if file_html_macro_name else "default"
    )
    env_html_macro_format = _normalize_optional_string(os.environ.get(ENV_HTML_MACRO_FORMAT))
    file_html_macro_format = _normalize_optional_string(file_cfg.html_macro_format)
    html_macro_format = env_html_macro_format or file_html_macro_format
    html_macro_format_source = (
        "env_var" if env_html_macro_format else "config_file" if file_html_macro_format else "default"
    )
    html_macro_forge_extension_key = (
        _normalize_optional_string(os.environ.get(ENV_HTML_MACRO_FORGE_EXTENSION_KEY))
        or _normalize_optional_string(file_cfg.html_macro_forge_extension_key)
    )
    html_macro_forge_extension_id = (
        _normalize_optional_string(os.environ.get(ENV_HTML_MACRO_FORGE_EXTENSION_ID))
        or _normalize_optional_string(file_cfg.html_macro_forge_extension_id)
    )
    html_macro_forge_environment = (
        _normalize_optional_string(os.environ.get(ENV_HTML_MACRO_FORGE_ENVIRONMENT))
        or _normalize_optional_string(file_cfg.html_macro_forge_environment)
    )
    html_macro_forge_cloud_id = (
        _normalize_optional_string(os.environ.get(ENV_HTML_MACRO_FORGE_CLOUD_ID))
        or _normalize_optional_string(file_cfg.html_macro_forge_cloud_id)
    )
    html_macro_forge_context_ids = (
        _normalize_optional_string(os.environ.get(ENV_HTML_MACRO_FORGE_CONTEXT_IDS))
        or _normalize_optional_string(file_cfg.html_macro_forge_context_ids)
    )
    html_macro_forge_account_id = (
        _normalize_optional_string(os.environ.get(ENV_HTML_MACRO_FORGE_ACCOUNT_ID))
        or _normalize_optional_string(file_cfg.html_macro_forge_account_id)
    )

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
        ssl_verify=ssl_verify,
        html_macro_name=html_macro_name,
        html_macro_format=html_macro_format,
        html_macro_forge_extension_key=html_macro_forge_extension_key,
        html_macro_forge_extension_id=html_macro_forge_extension_id,
        html_macro_forge_environment=html_macro_forge_environment,
        html_macro_forge_cloud_id=html_macro_forge_cloud_id,
        html_macro_forge_context_ids=html_macro_forge_context_ids,
        html_macro_forge_account_id=html_macro_forge_account_id,
        html_macro_name_source=html_macro_name_source,
        html_macro_format_source=html_macro_format_source,
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
    elif key == "ssl_verify":
        cfg.ssl_verify = value
    elif key == "html_macro_name":
        cfg.html_macro_name = value
    elif key == "html_macro_format":
        cfg.html_macro_format = value
    elif key == "html_macro_forge_extension_key":
        cfg.html_macro_forge_extension_key = value
    elif key == "html_macro_forge_extension_id":
        cfg.html_macro_forge_extension_id = value
    elif key == "html_macro_forge_environment":
        cfg.html_macro_forge_environment = value
    elif key == "html_macro_forge_cloud_id":
        cfg.html_macro_forge_cloud_id = value
    elif key == "html_macro_forge_context_ids":
        cfg.html_macro_forge_context_ids = value
    elif key == "html_macro_forge_account_id":
        cfg.html_macro_forge_account_id = value
    else:
        from confpub.errors import ERR_VALIDATION_REQUIRED, validation_error
        raise validation_error(
            ERR_VALIDATION_REQUIRED,
            "Unknown config key: "
            f"{key}. Valid keys: base_url, user, token, ssl_verify, html_macro_name, "
            "html_macro_format, html_macro_forge_extension_key, "
            "html_macro_forge_extension_id, html_macro_forge_environment, "
            "html_macro_forge_cloud_id, html_macro_forge_context_ids, "
            "html_macro_forge_account_id",
        )

    CONFIG_FILE.write_text(json.dumps(cfg.model_dump(exclude_none=True), indent=2), encoding="utf-8")
