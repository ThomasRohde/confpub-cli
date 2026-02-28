"""Shared test fixtures."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from confpub.cli import app


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def run_cli(cli_runner: CliRunner):
    """Invoke the CLI and return the Result."""
    def _run(*args: str, env: dict[str, str] | None = None):
        return cli_runner.invoke(app, list(args), env=env)
    return _run
