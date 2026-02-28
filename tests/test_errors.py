"""Tests for confpub.errors module."""

from confpub.errors import (
    ERR_AUTH_REQUIRED,
    ERR_CONFLICT_FINGERPRINT,
    ERR_INTERNAL_CONVERTER,
    ERR_IO_CONNECTION,
    ERR_IO_FILE_NOT_FOUND,
    ERR_VALIDATION_MANIFEST,
    ERR_VALIDATION_REQUIRED,
    ConfpubError,
    auth_error,
    conflict_error,
    exit_code_for,
    internal_error,
    io_error,
    retryable_for,
    suggested_action_for,
    validation_error,
)


class TestExitCodes:
    def test_validation_exit_code(self):
        assert exit_code_for(ERR_VALIDATION_REQUIRED) == 10
        assert exit_code_for(ERR_VALIDATION_MANIFEST) == 10

    def test_auth_exit_code(self):
        assert exit_code_for(ERR_AUTH_REQUIRED) == 20

    def test_conflict_exit_code(self):
        assert exit_code_for(ERR_CONFLICT_FINGERPRINT) == 40

    def test_io_exit_code(self):
        assert exit_code_for(ERR_IO_CONNECTION) == 50
        assert exit_code_for(ERR_IO_FILE_NOT_FOUND) == 50

    def test_internal_exit_code(self):
        assert exit_code_for(ERR_INTERNAL_CONVERTER) == 90

    def test_unknown_code_defaults_to_90(self):
        assert exit_code_for("ERR_UNKNOWN_THING") == 90


class TestSuggestedActions:
    def test_validation_action(self):
        assert suggested_action_for(ERR_VALIDATION_REQUIRED) == "fix_input"

    def test_auth_action(self):
        assert suggested_action_for(ERR_AUTH_REQUIRED) == "reauth"

    def test_io_action(self):
        assert suggested_action_for(ERR_IO_CONNECTION) == "retry"

    def test_internal_action(self):
        assert suggested_action_for(ERR_INTERNAL_CONVERTER) == "escalate"


class TestRetryable:
    def test_io_is_retryable(self):
        assert retryable_for(ERR_IO_CONNECTION) is True

    def test_validation_not_retryable(self):
        assert retryable_for(ERR_VALIDATION_REQUIRED) is False

    def test_conflict_not_retryable(self):
        assert retryable_for(ERR_CONFLICT_FINGERPRINT) is False


class TestConfpubError:
    def test_basic_construction(self):
        err = ConfpubError(ERR_VALIDATION_REQUIRED, "Missing --space")
        assert err.code == ERR_VALIDATION_REQUIRED
        assert err.error_message == "Missing --space"
        assert err.retryable is False
        assert err.suggested_action == "fix_input"

    def test_override_retryable(self):
        err = ConfpubError(ERR_AUTH_REQUIRED, "Token expired", retryable=True)
        assert err.retryable is True

    def test_to_dict(self):
        err = ConfpubError(
            ERR_IO_CONNECTION,
            "Connection refused",
            details={"host": "example.com"},
        )
        d = err.to_dict()
        assert d["code"] == ERR_IO_CONNECTION
        assert d["message"] == "Connection refused"
        assert d["retryable"] is True
        assert d["suggested_action"] == "retry"
        assert d["details"]["host"] == "example.com"

    def test_to_dict_no_details(self):
        err = ConfpubError(ERR_VALIDATION_REQUIRED, "Missing field")
        d = err.to_dict()
        assert "details" not in d

    def test_is_exception(self):
        err = ConfpubError(ERR_VALIDATION_REQUIRED, "test")
        assert isinstance(err, Exception)
        assert str(err) == "test"


class TestBuilderHelpers:
    def test_validation_error(self):
        err = validation_error(message="Bad manifest")
        assert err.code == ERR_VALIDATION_REQUIRED
        assert err.error_message == "Bad manifest"

    def test_auth_error(self):
        err = auth_error(message="No token")
        assert err.code == ERR_AUTH_REQUIRED

    def test_conflict_error(self):
        err = conflict_error(page_id="123")
        assert err.code == ERR_CONFLICT_FINGERPRINT
        assert err.details["page_id"] == "123"

    def test_io_error(self):
        err = io_error(code=ERR_IO_CONNECTION, message="Timeout")
        assert err.code == ERR_IO_CONNECTION
        assert err.retryable is True

    def test_internal_error(self):
        err = internal_error()
        assert err.code == ERR_INTERNAL_CONVERTER
        assert err.suggested_action == "escalate"
