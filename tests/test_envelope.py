"""Tests for confpub.envelope module."""

import json
import re

from confpub.envelope import Envelope, ErrorDetail, generate_request_id
from confpub.errors import ConfpubError, ERR_IO_CONNECTION, ERR_VALIDATION_REQUIRED


class TestRequestId:
    def test_format(self):
        rid = generate_request_id()
        assert re.match(r"^req_\d{8}_\d{6}_[0-9a-f]{4}$", rid)

    def test_uniqueness(self):
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100


class TestEnvelopeSuccess:
    def test_basic_success(self):
        env = Envelope.success("page.list", result={"pages": []})
        assert env.ok is True
        assert env.command == "page.list"
        assert env.result == {"pages": []}
        assert env.errors == []
        assert env.warnings == []
        assert env.schema_version == "1.0"
        assert env.request_id.startswith("req_")

    def test_with_target_and_warnings(self):
        env = Envelope.success(
            "page.publish",
            result={"page_id": "123"},
            target={"space": "DEV", "title": "Test"},
            warnings=["Large file detected"],
            metrics={"duration_ms": 500},
        )
        assert env.target == {"space": "DEV", "title": "Test"}
        assert env.warnings == ["Large file detected"]
        assert env.metrics["duration_ms"] == 500


class TestEnvelopeFailure:
    def test_from_confpub_error(self):
        err = ConfpubError(ERR_IO_CONNECTION, "Connection refused")
        env = Envelope.failure("page.list", [err])
        assert env.ok is False
        assert env.result is None
        assert len(env.errors) == 1
        assert env.errors[0].code == ERR_IO_CONNECTION
        assert env.errors[0].retryable is True

    def test_from_error_detail(self):
        detail = ErrorDetail(
            code=ERR_VALIDATION_REQUIRED,
            message="Missing --space",
            retryable=False,
            suggested_action="fix_input",
        )
        env = Envelope.failure("page.publish", [detail])
        assert env.errors[0].code == ERR_VALIDATION_REQUIRED

    def test_from_dict(self):
        env = Envelope.failure("page.publish", [
            {"code": "ERR_TEST", "message": "test error"}
        ])
        assert env.errors[0].code == "ERR_TEST"

    def test_multiple_errors(self):
        errors = [
            ConfpubError(ERR_VALIDATION_REQUIRED, "Missing --space"),
            ConfpubError(ERR_IO_CONNECTION, "Timeout"),
        ]
        env = Envelope.failure("page.publish", errors)
        assert len(env.errors) == 2


class TestEnvelopeSerialization:
    def test_to_json_bytes(self):
        env = Envelope.success("page.list", result={"pages": []})
        data = env.to_json_bytes()
        assert isinstance(data, bytes)
        parsed = json.loads(data)
        assert parsed["ok"] is True
        assert parsed["command"] == "page.list"

    def test_to_json_str(self):
        env = Envelope.success("page.list", result=None)
        s = env.to_json_str()
        assert isinstance(s, str)
        parsed = json.loads(s)
        assert parsed["result"] is None

    def test_envelope_invariants(self):
        """All required fields are always present per PRD."""
        env = Envelope.success("test.cmd", result={})
        parsed = json.loads(env.to_json_bytes())
        for key in ("schema_version", "request_id", "ok", "command", "result", "errors", "warnings", "metrics"):
            assert key in parsed, f"Missing required field: {key}"

    def test_failure_result_is_null(self):
        env = Envelope.failure("test.cmd", [
            ConfpubError(ERR_VALIDATION_REQUIRED, "error"),
        ])
        parsed = json.loads(env.to_json_bytes())
        assert parsed["result"] is None
        assert parsed["ok"] is False

    def test_errors_always_array(self):
        success = json.loads(Envelope.success("x", result={}).to_json_bytes())
        failure = json.loads(
            Envelope.failure("x", [ConfpubError(ERR_VALIDATION_REQUIRED, "e")]).to_json_bytes()
        )
        assert isinstance(success["errors"], list)
        assert isinstance(failure["errors"], list)
        assert isinstance(success["warnings"], list)
