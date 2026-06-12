"""Pydantic envelope model and request_id generation.

Every confpub command returns exactly one Envelope on stdout.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

import orjson
from pydantic import BaseModel, Field

from confpub.errors import ConfpubError

SCHEMA_VERSION = "1.0"


def generate_request_id() -> str:
    """Generate a unique request ID: req_YYYYMMDD_HHMMSS_xxxxxxxx."""
    now = datetime.now(timezone.utc)
    suffix = uuid.uuid4().hex[:8]
    return f"req_{now:%Y%m%d}_{now:%H%M%S}_{suffix}"


def _json_safe(value: Any) -> Any:
    """Return a JSON-safe value, replacing non-finite floats with null."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


class ErrorDetail(BaseModel):
    """A single error entry in the envelope."""

    code: str
    message: str
    retryable: bool = False
    suggested_action: str = "escalate"
    details: dict[str, Any] = Field(default_factory=dict)


class Envelope(BaseModel):
    """The structured JSON envelope returned by every command."""

    schema_version: str = SCHEMA_VERSION
    request_id: str = Field(default_factory=generate_request_id)
    ok: bool
    command: str
    target: dict[str, Any] | None = None
    result: Any = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def success(
        cls,
        command: str,
        result: Any,
        *,
        target: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> Envelope:
        return cls(
            ok=True,
            command=command,
            target=target,
            result=result,
            warnings=warnings or [],
            metrics=metrics or {},
        )

    @classmethod
    def failure(
        cls,
        command: str,
        errors: list[ConfpubError | ErrorDetail | dict[str, Any]],
        *,
        target: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> Envelope:
        error_details: list[ErrorDetail] = []
        for err in errors:
            if isinstance(err, ConfpubError):
                error_details.append(ErrorDetail(**err.to_dict()))
            elif isinstance(err, ErrorDetail):
                error_details.append(err)
            elif isinstance(err, dict):
                error_details.append(ErrorDetail(**err))
        return cls(
            ok=False,
            command=command,
            target=target,
            result=None,
            errors=error_details,
            warnings=warnings or [],
            metrics=metrics or {},
        )

    def to_json_bytes(self, *, indent: bool = True) -> bytes:
        """Serialize to JSON bytes via orjson."""
        opts = orjson.OPT_NON_STR_KEYS
        if indent:
            opts |= orjson.OPT_INDENT_2
        return orjson.dumps(_json_safe(self.model_dump(mode="json")), option=opts)

    def to_json_str(self, *, indent: bool = True) -> str:
        """Serialize to JSON string."""
        return self.to_json_bytes(indent=indent).decode("utf-8")
