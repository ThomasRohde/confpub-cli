# Copilot Instructions

Agent-first CLI for publishing Markdown to Confluence. Python 3.10+, no linter configured.

## Commands

```bash
uv pip install -e ".[dev]"                                               # Install with dev deps
pytest tests/ -v                                                         # Run all tests
pytest tests/test_converter.py -v                                        # Run one module
pytest tests/test_converter.py::TestHeadings::test_h1 -v                # Run single test
pytest tests/ -k "fingerprint" -v                                        # Run by name pattern
pytest tests/ -v --cov=confpub                                           # Run with coverage
uvx hatch version minor                                                  # Bump version (patch/minor/major)
```

## Architecture

### Command flow

Every command follows this path through `cli.py`:

1. Typer handler receives flags and calls `command_context(command_name)` — a context manager that records timing, catches errors, and emits the final JSON envelope on stdout.
2. Handler populates a `CommandResult` (result, target, warnings, metrics) then delegates to a domain module (`publish.py`, `applier.py`, `puller.py`, `planner.py`, etc.).
3. Domain module calls `ConfluenceClient` (`confluence.py`), which wraps `atlassian-python-api` and translates its exceptions into `ConfpubError`.
4. `command_context` serializes an `Envelope` and writes it to stdout; any exception that escapes domain code is caught here too.

### Subcommand groups

`page`, `plan`, `auth`, `config`, `space`, `attachment`, `label`, `comment` — each is a `typer.Typer` added to the root `app` in `cli.py`.

### Transactional plan workflow

`plan create` → `plan validate` → `plan apply` → `plan verify`

Only `plan apply` has side effects. `plan create` fingerprints existing pages (SHA-256 of storage-format body) so that `plan apply` can detect external edits (`ERR_CONFLICT_FINGERPRINT`) before writing.

### Markdown conversion

- `converter.py` — `markdown-it-py` + custom `ConfluenceRenderer` → Confluence Storage Format XHTML. Pure function, no I/O.
- `reverse_converter.py` — BeautifulSoup4 + markdownify → Markdown. Pure function, no I/O.

### Lockfile

`confpub.lock` maps page titles → `{page_id, version, content_fingerprint}`. Updated atomically (tempfile + `os.replace`) by publish, pull, apply, and delete.

## Key Conventions

### stdout is JSON-only

Every invocation emits exactly one `Envelope` object on stdout. Never write anything else there. Progress events and diagnostics go to stderr via `output.py` helpers (`emit_progress`, `emit_stderr`), and are suppressed when `--quiet`, `LLM=true`, or stdout is not a TTY.

### Error codes are stable public API

Error codes use the pattern `ERR_{CATEGORY}_{SPECIFIC}`. Category prefixes map to fixed exit codes:

| Prefix | Exit code |
|---|---|
| `ERR_VALIDATION` | 10 |
| `ERR_AUTH` | 20 |
| `ERR_CONFLICT` | 40 |
| `ERR_IO` | 50 |
| `ERR_INTERNAL` | 90 |

Never rename or remove an error code constant without a major version bump. Use the builder helpers (`validation_error(...)`, `auth_error(...)`, etc.) in `errors.py` rather than constructing `ConfpubError` directly.

### ConfpubError

All domain errors must be `ConfpubError` instances. Fields: `code`, `message`, `retryable`, `suggested_action`, `details`. These flow directly into `Envelope.errors`.

### Pydantic models everywhere

`Envelope`, `Lockfile`, `Manifest`, `ConfigModel`, and plan artifacts are all Pydantic v2 `BaseModel`. Use `model_dump(mode="json")` for serialization.

### Credential precedence

CLI flags → env vars (`CONFPUB_URL`, `CONFPUB_TOKEN`, `CONFPUB_USER`, `CONFPUB_SPACE`, `CONFPUB_SSL_VERIFY`) → config file (`~/.config/confpub/config.json`) → OS keychain.

### Test conventions

- Use the `run_cli` fixture from `conftest.py` (wraps `typer.testing.CliRunner`) for all CLI-level tests.
- Mock all Confluence API calls with `unittest.mock` — no live integration tests.
- Group related test cases in classes (e.g. `class TestHeadings`, `class TestApplyPlanReal`).
- Unit tests for new domain functions go in the matching `test_<module>.py`; CLI-level behavior goes in `test_integration.py`.

## Version

Defined in `confpub/__init__.py`. Hatch reads it from `pyproject.toml`. Pushing to `main` triggers the GitHub Actions publish workflow.
