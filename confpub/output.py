"""TOON / LLM=true / isatty output routing.

Rules:
- stdout is EXCLUSIVELY for the structured JSON envelope (one object per invocation)
- stderr gets progress events, diagnostics, and debug logs
- LLM=true suppresses interactive behaviour and progress noise
"""

from __future__ import annotations

import os
import sys

import orjson

# Module-level overrides set by the CLI layer
_quiet: bool | None = None
_verbose: bool | None = None
_compact: bool = False


def set_quiet(value: bool) -> None:
    global _quiet
    _quiet = value


def set_verbose(value: bool) -> None:
    global _verbose
    _verbose = value


def set_compact(value: bool) -> None:
    global _compact
    _compact = value


def is_compact() -> bool:
    """True when JSON output should be single-line (no indentation)."""
    return _compact


def is_llm_mode() -> bool:
    """True when LLM=true is set in the environment."""
    return os.environ.get("LLM", "").lower() == "true"


def is_ci() -> bool:
    """True when CI=true is set in the environment."""
    return os.environ.get("CI", "").lower() == "true"


def is_interactive() -> bool:
    """True when stdout is a TTY and LLM mode is off."""
    return sys.stdout.isatty() and not is_llm_mode()


def is_quiet() -> bool:
    """True when progress/diagnostics should be suppressed."""
    if _quiet is not None:
        return _quiet
    return is_llm_mode() or not sys.stdout.isatty()


def is_verbose() -> bool:
    """True when extra diagnostics should be included."""
    if _verbose is not None:
        return _verbose
    return False


def emit_stdout(data: bytes) -> None:
    """Write envelope JSON bytes to stdout. This is the ONLY stdout writer."""
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()


def emit_progress(step: int, total: int, message: str) -> None:
    """Emit an NDJSON progress event to stderr. Suppressed in quiet mode."""
    if is_quiet():
        return
    event = {"event": "progress", "step": step, "total": total, "message": message}
    line = orjson.dumps(event).decode("utf-8")
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def emit_stderr(message: str) -> None:
    """Write a diagnostic message to stderr. Suppressed in quiet mode."""
    if is_quiet():
        return
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
