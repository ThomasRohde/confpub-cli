"""Tests for confpub.guide module."""

from confpub.guide import build_guide


class TestBuildGuide:
    def test_has_required_top_level_keys(self):
        guide = build_guide()
        for key in ("schema_version", "commands", "error_codes", "auth", "concurrency"):
            assert key in guide, f"Missing top-level key: {key}"

    def test_all_commands_present(self):
        guide = build_guide()
        expected_commands = [
            "guide", "search",
            "page.list", "page.inspect", "page.publish", "page.delete",
            "space.list",
            "attachment.list", "attachment.upload",
            "plan.create", "plan.validate", "plan.apply", "plan.verify",
            "auth.inspect",
            "config.set", "config.inspect",
        ]
        for cmd in expected_commands:
            assert cmd in guide["commands"], f"Missing command: {cmd}"

    def test_command_has_required_fields(self):
        guide = build_guide()
        for cmd_id, cmd in guide["commands"].items():
            assert "group" in cmd, f"{cmd_id} missing 'group'"
            assert "mutates" in cmd, f"{cmd_id} missing 'mutates'"
            assert "description" in cmd, f"{cmd_id} missing 'description'"
            assert isinstance(cmd["mutates"], bool), f"{cmd_id} 'mutates' must be bool"

    def test_write_commands_are_mutating(self):
        guide = build_guide()
        for cmd_id in ("page.publish", "page.delete", "plan.apply", "config.set"):
            assert guide["commands"][cmd_id]["mutates"] is True

    def test_read_commands_are_not_mutating(self):
        guide = build_guide()
        for cmd_id in ("search", "page.list", "page.inspect", "space.list", "plan.validate"):
            assert guide["commands"][cmd_id]["mutates"] is False

    def test_plan_apply_has_safety_flags(self):
        guide = build_guide()
        cmd = guide["commands"]["plan.apply"]
        assert "safety_flags" in cmd
        assert "--skip-fingerprint-check" in cmd["safety_flags"]
        assert "--cascade" in cmd["safety_flags"]

    def test_search_guide_entry(self):
        guide = build_guide()
        cmd = guide["commands"]["search"]
        assert cmd["group"] == "read"
        assert cmd["mutates"] is False
        assert "--cql" in cmd["flags"]
        assert "--space" in cmd["flags"]
        assert "--type" in cmd["flags"]
        assert "result_schema" in cmd
        assert "examples" in cmd
        assert len(cmd["examples"]) > 0

    def test_all_error_codes_present(self):
        guide = build_guide()
        expected_errors = [
            "ERR_VALIDATION_REQUIRED", "ERR_VALIDATION_MANIFEST",
            "ERR_VALIDATION_MARKDOWN", "ERR_VALIDATION_ASSET_MISSING",
            "ERR_AUTH_REQUIRED", "ERR_AUTH_EXPIRED", "ERR_AUTH_FORBIDDEN",
            "ERR_CONFLICT_FINGERPRINT", "ERR_CONFLICT_LOCK", "ERR_CONFLICT_PAGE_EXISTS",
            "ERR_IO_FILE_NOT_FOUND", "ERR_IO_CONNECTION", "ERR_IO_TIMEOUT",
            "ERR_INTERNAL_CONVERTER", "ERR_INTERNAL_SDK",
        ]
        for code in expected_errors:
            assert code in guide["error_codes"], f"Missing error code: {code}"

    def test_error_codes_have_required_fields(self):
        guide = build_guide()
        for code, entry in guide["error_codes"].items():
            assert "exit_code" in entry, f"{code} missing 'exit_code'"
            assert "retryable" in entry, f"{code} missing 'retryable'"
            assert "suggested_action" in entry, f"{code} missing 'suggested_action'"

    def test_exit_code_values(self):
        guide = build_guide()
        codes = guide["error_codes"]
        assert codes["ERR_VALIDATION_REQUIRED"]["exit_code"] == 10
        assert codes["ERR_AUTH_REQUIRED"]["exit_code"] == 20
        assert codes["ERR_CONFLICT_FINGERPRINT"]["exit_code"] == 40
        assert codes["ERR_IO_CONNECTION"]["exit_code"] == 50
        assert codes["ERR_INTERNAL_SDK"]["exit_code"] == 90

    def test_io_errors_are_retryable(self):
        guide = build_guide()
        assert guide["error_codes"]["ERR_IO_CONNECTION"]["retryable"] is True
        assert guide["error_codes"]["ERR_IO_TIMEOUT"]["retryable"] is True

    def test_io_errors_have_retry_after(self):
        guide = build_guide()
        assert guide["error_codes"]["ERR_IO_CONNECTION"]["retry_after_ms"] == 2000

    def test_auth_section(self):
        guide = build_guide()
        auth = guide["auth"]
        assert "precedence" in auth
        assert len(auth["precedence"]) == 4
        assert auth["inspect_command"] == "confpub auth inspect"

    def test_concurrency_section(self):
        guide = build_guide()
        concurrency = guide["concurrency"]
        assert "rule" in concurrency
        assert "safe_patterns" in concurrency
        assert len(concurrency["safe_patterns"]) > 0
