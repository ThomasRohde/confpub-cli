"""Tests for confpub.output module."""

import json
import os

from confpub.output import (
    emit_progress,
    emit_stderr,
    emit_stdout,
    is_ci,
    is_llm_mode,
    is_quiet,
    is_verbose,
    set_quiet,
    set_verbose,
)


class TestLLMMode:
    def test_llm_true(self, monkeypatch):
        monkeypatch.setenv("LLM", "true")
        assert is_llm_mode() is True

    def test_llm_false(self, monkeypatch):
        monkeypatch.delenv("LLM", raising=False)
        assert is_llm_mode() is False

    def test_llm_other(self, monkeypatch):
        monkeypatch.setenv("LLM", "yes")
        assert is_llm_mode() is False


class TestCIMode:
    def test_ci_true(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        assert is_ci() is True

    def test_ci_false(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        assert is_ci() is False


class TestQuietVerbose:
    def test_set_quiet_override(self):
        set_quiet(True)
        assert is_quiet() is True
        set_quiet(False)
        assert is_quiet() is False
        set_quiet(None)  # type: ignore[arg-type]  — reset

    def test_set_verbose_override(self):
        set_verbose(True)
        assert is_verbose() is True
        set_verbose(False)
        assert is_verbose() is False
        set_verbose(None)  # type: ignore[arg-type]  — reset


class TestEmitStdout:
    def test_writes_to_stdout(self, capsys):
        emit_stdout(b'{"ok": true}')
        captured = capsys.readouterr()
        assert captured.out == '{"ok": true}\n'


class TestEmitProgress:
    def test_emits_ndjson_to_stderr_when_not_quiet(self, capsys):
        set_quiet(False)
        emit_progress(1, 3, "Step one")
        captured = capsys.readouterr()
        line = json.loads(captured.err.strip())
        assert line["event"] == "progress"
        assert line["step"] == 1
        assert line["total"] == 3
        assert line["message"] == "Step one"
        set_quiet(None)  # type: ignore[arg-type]

    def test_suppressed_in_quiet_mode(self, capsys):
        set_quiet(True)
        emit_progress(1, 3, "Step one")
        captured = capsys.readouterr()
        assert captured.err == ""
        set_quiet(None)  # type: ignore[arg-type]


class TestEmitStderr:
    def test_writes_to_stderr(self, capsys):
        set_quiet(False)
        emit_stderr("debug info")
        captured = capsys.readouterr()
        assert "debug info" in captured.err
        set_quiet(None)  # type: ignore[arg-type]

    def test_suppressed_in_quiet_mode(self, capsys):
        set_quiet(True)
        emit_stderr("should not appear")
        captured = capsys.readouterr()
        assert captured.err == ""
        set_quiet(None)  # type: ignore[arg-type]
