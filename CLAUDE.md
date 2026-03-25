# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
uv pip install -e ".[dev]"              # Install with dev deps
pytest tests/ -v                        # Run all tests
pytest tests/test_converter.py -v       # Run one test module
pytest tests/test_converter.py::TestHeadings::test_h1 -v  # Run single test
pytest tests/ -k "fingerprint" -v       # Run tests matching name pattern
pytest tests/ -v --cov=confpub          # Run with coverage
uvx hatch version minor                 # Bump version (patch/minor/major)
python -m confpub <args>                # Run dev version of CLI (not the global install)
```

No linter is configured. Python 3.10+ required.

### Dev vs global CLI

- **`confpub`** (in PATH) — global install via `uv tool install confpub-cli`. This is the production version from PyPI.
- **`python -m confpub`** — runs from the local editable source. Use this for dev testing to ensure you're testing your local changes, not the globally installed version.

## Architecture

Agent-first CLI for publishing Markdown to Confluence. Every command returns structured JSON on stdout; stderr is reserved for progress/diagnostics.

### Command flow

All commands follow the same pattern through `cli.py`:

1. Typer handler receives flags
2. `command_context()` context manager wraps execution — catches `ConfpubError` and unexpected exceptions, records timing, emits the JSON envelope via `Envelope` (envelope.py)
3. Handler delegates to a domain module (publish.py, applier.py, puller.py, etc.)
4. Domain module calls `ConfluenceClient` (confluence.py) which wraps atlassian-python-api and translates its exceptions into `ConfpubError`

### Key design rules

- **stdout is JSON-only** — one envelope object per invocation, never mixed with text
- **Error codes are stable** — prefixed by category (`ERR_VALIDATION_*`, `ERR_AUTH_*`, `ERR_CONFLICT_*`, `ERR_IO_*`, `ERR_INTERNAL_*`), each maps to a fixed exit code via prefix (10/20/40/50/90). Never rename or remove error codes without a major version bump.
- **`ConfpubError`** carries code, message, retryable flag, suggested_action, and details dict — all fields flow into the envelope's `errors` array
- **Lockfile** (`confpub.lock`) maps page titles to Confluence page IDs for idempotent re-publishing. Updated by publish, pull, apply, and delete. Uses atomic writes (tempfile + rename).

### Transactional workflow

`plan create` → `plan validate` → `plan apply` → `plan verify` — each step is a separate command with no side effects except apply. Fingerprinting (SHA-256 of storage-format body) detects external edits between plan creation and apply.

### Markdown conversion

`converter.py` uses markdown-it-py with a custom `ConfluenceRenderer` to produce Confluence Storage Format XHTML. `reverse_converter.py` does the inverse using BeautifulSoup4 + markdownify. Both are pure functions (no I/O, no network).

### Test conventions

- Tests use `typer.testing.CliRunner` via `run_cli` fixture (conftest.py)
- Confluence API calls are mocked with `unittest.mock` — no live integration tests
- Test classes group related cases (e.g., `TestHeadings`, `TestApplyPlanReal`)
- New domain functions get unit tests; CLI-level behavior gets integration tests in `test_integration.py`

## Version

Defined in `confpub/__init__.py`, read by hatch from `pyproject.toml` config. Bump with `uvx hatch version`. Push to `main` triggers GitHub Actions publish to PyPI.
