"""Error codes, exit codes, and ConfpubError exception."""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Error code constants (stable across versions)
# ---------------------------------------------------------------------------

# Validation (exit 10)
ERR_VALIDATION_REQUIRED = "ERR_VALIDATION_REQUIRED"
ERR_VALIDATION_MANIFEST = "ERR_VALIDATION_MANIFEST"
ERR_VALIDATION_MARKDOWN = "ERR_VALIDATION_MARKDOWN"
ERR_VALIDATION_ASSET_MISSING = "ERR_VALIDATION_ASSET_MISSING"
ERR_VALIDATION_SPACE_MISMATCH = "ERR_VALIDATION_SPACE_MISMATCH"
ERR_VALIDATION_NOT_FOUND = "ERR_VALIDATION_NOT_FOUND"
ERR_VALIDATION_LABEL = "ERR_VALIDATION_LABEL"
ERR_VALIDATION_SPACE_KEY = "ERR_VALIDATION_SPACE_KEY"

# Auth (exit 20)
ERR_AUTH_REQUIRED = "ERR_AUTH_REQUIRED"
ERR_AUTH_EXPIRED = "ERR_AUTH_EXPIRED"
ERR_AUTH_FORBIDDEN = "ERR_AUTH_FORBIDDEN"

# Conflict (exit 40)
ERR_CONFLICT_FINGERPRINT = "ERR_CONFLICT_FINGERPRINT"
ERR_CONFLICT_LOCK = "ERR_CONFLICT_LOCK"
ERR_CONFLICT_PAGE_EXISTS = "ERR_CONFLICT_PAGE_EXISTS"
ERR_CONFLICT_FILE_EXISTS = "ERR_CONFLICT_FILE_EXISTS"

# I/O (exit 50)
ERR_IO_FILE_NOT_FOUND = "ERR_IO_FILE_NOT_FOUND"
ERR_IO_CONNECTION = "ERR_IO_CONNECTION"
ERR_IO_TIMEOUT = "ERR_IO_TIMEOUT"

# Internal (exit 90)
ERR_INTERNAL_CONVERTER = "ERR_INTERNAL_CONVERTER"
ERR_INTERNAL_REVERSE_CONVERTER = "ERR_INTERNAL_REVERSE_CONVERTER"
ERR_INTERNAL_SDK = "ERR_INTERNAL_SDK"

# ---------------------------------------------------------------------------
# Exit code mapping by prefix
# ---------------------------------------------------------------------------

EXIT_CODES: dict[str, int] = {
    "ERR_VALIDATION": 10,
    "ERR_AUTH": 20,
    "ERR_CONFLICT": 40,
    "ERR_IO": 50,
    "ERR_INTERNAL": 90,
}

# Default suggested_action by prefix
_DEFAULT_ACTIONS: dict[str, str] = {
    "ERR_VALIDATION": "fix_input",
    "ERR_AUTH": "reauth",
    "ERR_CONFLICT": "fix_input",
    "ERR_IO": "retry",
    "ERR_INTERNAL": "escalate",
}

# Default retryable by prefix
_DEFAULT_RETRYABLE: dict[str, bool] = {
    "ERR_VALIDATION": False,
    "ERR_AUTH": False,
    "ERR_CONFLICT": False,
    "ERR_IO": True,
    "ERR_INTERNAL": False,
}


def _prefix(code: str) -> str:
    """Extract the prefix (first two underscore-separated parts) from an error code."""
    parts = code.split("_")
    if len(parts) >= 3:
        return f"{parts[0]}_{parts[1]}"
    return code


def exit_code_for(error_code: str) -> int:
    """Return the exit code for a given error code string."""
    prefix = _prefix(error_code)
    return EXIT_CODES.get(prefix, 90)


def suggested_action_for(error_code: str) -> str:
    """Return the default suggested_action for a given error code."""
    prefix = _prefix(error_code)
    return _DEFAULT_ACTIONS.get(prefix, "escalate")


def retryable_for(error_code: str) -> bool:
    """Return the default retryable flag for a given error code."""
    prefix = _prefix(error_code)
    return _DEFAULT_RETRYABLE.get(prefix, False)


class ConfpubError(Exception):
    """Structured error raised by confpub domain logic.

    Carries all fields needed to populate the error envelope.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool | None = None,
        suggested_action: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.error_message = message
        self.retryable = retryable if retryable is not None else retryable_for(code)
        self.suggested_action = (
            suggested_action if suggested_action is not None else suggested_action_for(code)
        )
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to the error object shape used in the envelope."""
        d: dict[str, Any] = {
            "code": self.code,
            "message": self.error_message,
            "retryable": self.retryable,
            "suggested_action": self.suggested_action,
        }
        if self.details:
            d["details"] = self.details
        return d


# ---------------------------------------------------------------------------
# Builder helpers — convenient constructors for common patterns
# ---------------------------------------------------------------------------


def validation_error(
    code: str = ERR_VALIDATION_REQUIRED,
    message: str = "Validation failed",
    **details: Any,
) -> ConfpubError:
    return ConfpubError(code, message, details=details if details else None)


def auth_error(
    code: str = ERR_AUTH_REQUIRED,
    message: str = "Authentication required",
    **details: Any,
) -> ConfpubError:
    return ConfpubError(code, message, details=details if details else None)


def conflict_error(
    code: str = ERR_CONFLICT_FINGERPRINT,
    message: str = "Conflict detected",
    **details: Any,
) -> ConfpubError:
    return ConfpubError(code, message, details=details if details else None)


def io_error(
    code: str = ERR_IO_FILE_NOT_FOUND,
    message: str = "I/O error",
    **details: Any,
) -> ConfpubError:
    return ConfpubError(code, message, details=details if details else None)


def validate_space_key(space: str | None) -> None:
    """Reject space values that look like shell-expanded paths.

    PowerShell expands unquoted ``~username`` to a Windows home path
    (e.g. ``C:\\Users\\username``).  Catching this early gives the caller an
    actionable error instead of a confusing Confluence API failure.
    """
    if space is None:
        return
    import re
    if "\\" in space or "/" in space or re.match(r"^[A-Za-z]:", space):
        raise ConfpubError(
            ERR_VALIDATION_SPACE_KEY,
            (
                f"Space key '{space}' appears to be a shell-expanded path. "
                "Quote the value: --space '~username' or set CONFPUB_SPACE=~username"
            ),
            details={
                "fix_options": [
                    "Quote the --space value: --space '~username'",
                    "Set the CONFPUB_SPACE environment variable instead",
                    "Use the space key without shell-expandable characters",
                ],
            },
        )


def internal_error(
    code: str = ERR_INTERNAL_CONVERTER,
    message: str = "Internal error",
    **details: Any,
) -> ConfpubError:
    return ConfpubError(code, message, details=details if details else None)
