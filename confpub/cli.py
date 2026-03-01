"""Typer CLI application — commands, envelope output, exit codes.

This module defines the top-level app with subcommand groups for each noun.
Command handlers are thin wrappers that delegate to domain modules.
"""

from __future__ import annotations

import time
import traceback
from contextlib import contextmanager
from typing import Any, Iterator, Optional

import typer

from confpub import __version__
from confpub.envelope import Envelope
from confpub.errors import ConfpubError, exit_code_for, ERR_INTERNAL_SDK
from confpub.output import emit_stderr, emit_stdout, is_verbose, set_quiet, set_verbose

# ---------------------------------------------------------------------------
# Subcommand group apps
# ---------------------------------------------------------------------------

page_app = typer.Typer(help="Page operations")
plan_app = typer.Typer(help="Transactional plan workflow")
auth_app = typer.Typer(help="Authentication")
config_app = typer.Typer(help="Configuration")
space_app = typer.Typer(help="Space operations")
attachment_app = typer.Typer(help="Attachment operations")

# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="confpub",
    help="Agent-first CLI to publish Markdown to Confluence.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(page_app, name="page")
app.add_typer(plan_app, name="plan")
app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")
app.add_typer(space_app, name="space")
app.add_typer(attachment_app, name="attachment")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"confpub {__version__}")
        raise typer.Exit(0)


@app.callback()
def main_callback(
    quiet: bool = typer.Option(False, "--quiet", help="Suppress progress output on stderr"),
    verbose: bool = typer.Option(False, "--verbose", help="Include diagnostics in result"),
    version: bool = typer.Option(
        False, "--version", help="Show version and exit",
        callback=_version_callback, is_eager=True,
    ),
) -> None:
    """confpub — publish Markdown to Confluence."""
    set_quiet(quiet)
    set_verbose(verbose)


# ---------------------------------------------------------------------------
# command_context — envelope wrapping for every command
# ---------------------------------------------------------------------------


class CommandResult:
    """Mutable container yielded by command_context for the handler to fill."""

    def __init__(self) -> None:
        self.result: Any = None
        self.target: dict[str, Any] | None = None
        self.warnings: list[str] = []
        self.metrics: dict[str, Any] = {}


@contextmanager
def command_context(command_name: str, target: dict[str, Any] | None = None) -> Iterator[CommandResult]:
    """Context manager that wraps every CLI command.

    - Records start time for metrics.duration_ms
    - Yields a CommandResult for the handler to populate
    - On success: emits a success envelope on stdout
    - On ConfpubError: emits an error envelope + raises typer.Exit
    - On unexpected exception: emits ERR_INTERNAL + raises typer.Exit(90)
    """
    start = time.monotonic()
    ctx = CommandResult()
    ctx.target = target

    try:
        yield ctx
    except ConfpubError as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        ctx.metrics["duration_ms"] = duration_ms
        if is_verbose():
            import traceback as tb
            ctx.metrics["diagnostics"] = {"traceback": tb.format_exc()}
        envelope = Envelope.failure(
            command_name,
            [e],
            target=ctx.target,
            warnings=ctx.warnings,
            metrics=ctx.metrics,
        )
        emit_stdout(envelope.to_json_bytes())
        raise typer.Exit(code=exit_code_for(e.code))
    except typer.Exit:
        raise
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        ctx.metrics["duration_ms"] = duration_ms
        emit_stderr(f"Internal error: {exc}")
        emit_stderr(traceback.format_exc())
        err = ConfpubError(
            ERR_INTERNAL_SDK,
            f"Unexpected error: {exc}",
        )
        envelope = Envelope.failure(
            command_name,
            [err],
            target=ctx.target,
            warnings=ctx.warnings,
            metrics=ctx.metrics,
        )
        emit_stdout(envelope.to_json_bytes())
        raise typer.Exit(code=90)
    else:
        duration_ms = int((time.monotonic() - start) * 1000)
        ctx.metrics["duration_ms"] = duration_ms
        if is_verbose():
            ctx.metrics["diagnostics"] = {
                "command": command_name,
                "target": ctx.target,
                "warning_count": len(ctx.warnings),
            }
        envelope = Envelope.success(
            command_name,
            ctx.result,
            target=ctx.target,
            warnings=ctx.warnings,
            metrics=ctx.metrics,
        )
        emit_stdout(envelope.to_json_bytes())


# ---------------------------------------------------------------------------
# Stub commands (replaced in later phases)
# ---------------------------------------------------------------------------


@page_app.command("list")
def page_list(
    space: str = typer.Option(..., "--space", help="Confluence space key"),
) -> None:
    """List pages in a Confluence space."""
    with command_context("page.list", target={"space": space}) as ctx:
        from confpub.confluence import build_client, _slim_page
        client = build_client()
        pages = client.list_pages(space)
        ctx.result = {"pages": [_slim_page(p) for p in pages]}


@page_app.command("inspect")
def page_inspect(
    space: str = typer.Option(None, "--space", help="Confluence space key"),
    title: str = typer.Option(None, "--title", help="Page title"),
    page_id: str = typer.Option(None, "--page-id", help="Confluence page ID"),
    raw: bool = typer.Option(False, "--raw", help="Return full raw API response"),
) -> None:
    """Inspect a Confluence page."""
    with command_context("page.inspect", target={"space": space, "title": title, "page_id": page_id}) as ctx:
        from confpub.confluence import build_client, _slim_page
        client = build_client()
        if page_id:
            page = client.get_page_by_id(page_id)
        else:
            from confpub.errors import validation_error, ERR_VALIDATION_REQUIRED
            if not space or not title:
                raise validation_error(ERR_VALIDATION_REQUIRED, "Either --page-id or both --space and --title are required")
            page = client.get_page(space, title)
        ctx.result = page if raw else _slim_page(page) if page else page


@page_app.command("publish")
def page_publish(
    file: str = typer.Argument(..., help="Markdown file to publish"),
    space: str = typer.Option(..., "--space", help="Confluence space key"),
    parent: str = typer.Option(..., "--parent", help="Parent page title"),
    title: Optional[str] = typer.Option(None, "--title", help="Page title (defaults to filename stem, hyphen/underscore→spaces, title-cased)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing"),
    backup: bool = typer.Option(False, "--backup", help="Backup existing page before overwriting"),
) -> None:
    """Publish a single Markdown file to Confluence."""
    from confpub.publish import derive_title
    resolved_title = derive_title(file, title)
    target = {"space": space, "title": resolved_title, "file": file}
    with command_context("page.publish", target=target) as ctx:
        from confpub.publish import publish_page
        result = publish_page(
            file=file,
            space=space,
            parent=parent,
            title=title,
            dry_run=dry_run,
            backup=backup,
            progress_callback=ctx,
        )
        ctx.result = result


@page_app.command("delete")
def page_delete(
    space: str = typer.Option(..., "--space", help="Confluence space key"),
    title: str = typer.Option(..., "--title", help="Page title"),
    cascade: bool = typer.Option(False, "--cascade", help="Also delete child pages"),
) -> None:
    """Delete a Confluence page."""
    with command_context("page.delete", target={"space": space, "title": title}) as ctx:
        from confpub.confluence import build_client
        client = build_client()
        result = client.delete_page_by_title(space, title, cascade=cascade)
        ctx.result = result


@space_app.command("list")
def space_list() -> None:
    """List accessible Confluence spaces."""
    with command_context("space.list") as ctx:
        from confpub.confluence import build_client
        client = build_client()
        spaces = client.list_spaces()
        ctx.result = {"spaces": spaces}


@attachment_app.command("list")
def attachment_list(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
) -> None:
    """List attachments on a Confluence page."""
    with command_context("attachment.list", target={"page_id": page_id}) as ctx:
        from confpub.confluence import build_client
        client = build_client()
        attachments = client.get_attachments(page_id)
        ctx.result = {"attachments": attachments}


@attachment_app.command("upload")
def attachment_upload(
    file: str = typer.Argument(..., help="File to upload"),
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
) -> None:
    """Upload an attachment to a Confluence page."""
    with command_context("attachment.upload", target={"page_id": page_id, "file": file}) as ctx:
        from confpub.confluence import build_client
        client = build_client()
        result = client.upload_attachment(page_id, file)
        ctx.result = result


@plan_app.command("create")
def plan_create(
    manifest: str = typer.Option(..., "--manifest", help="Path to confpub.yaml manifest"),
    output: Optional[str] = typer.Option(None, "--output", help="Output path for plan artifact"),
    space: Optional[str] = typer.Option(None, "--space", help="Override manifest space"),
    parent: Optional[str] = typer.Option(None, "--parent", help="Override manifest parent"),
) -> None:
    """Generate a plan artifact from a manifest."""
    with command_context("plan.create", target={"manifest": manifest}) as ctx:
        from confpub.planner import create_plan
        result = create_plan(
            manifest_path=manifest,
            output_path=output,
            space_override=space,
            parent_override=parent,
        )
        ctx.result = result


@plan_app.command("validate")
def plan_validate(
    plan: str = typer.Option(..., "--plan", help="Path to plan artifact JSON"),
) -> None:
    """Validate a plan artifact against current state."""
    with command_context("plan.validate", target={"plan": plan}) as ctx:
        from confpub.validator import validate_plan
        result = validate_plan(plan_path=plan)
        ctx.result = result


@plan_app.command("apply")
def plan_apply(
    plan: str = typer.Option(..., "--plan", help="Path to plan artifact JSON"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing"),
    backup: bool = typer.Option(False, "--backup", help="Backup pages before overwriting"),
    skip_fingerprint_check: bool = typer.Option(False, "--skip-fingerprint-check", help="Skip stale-state detection"),
    cascade: bool = typer.Option(False, "--cascade", help="Allow cascading deletes"),
) -> None:
    """Apply a plan to Confluence."""
    with command_context("plan.apply", target={"plan": plan}) as ctx:
        from confpub.applier import apply_plan
        result = apply_plan(
            plan_path=plan,
            dry_run=dry_run,
            backup=backup,
            skip_fingerprint_check=skip_fingerprint_check,
            cascade=cascade,
        )
        ctx.result = result


@plan_app.command("verify")
def plan_verify(
    assertions: Optional[str] = typer.Option(None, "--assertions", help="Path to assertions JSON"),
    plan: Optional[str] = typer.Option(None, "--plan", help="Path to plan artifact"),
) -> None:
    """Verify post-conditions after apply."""
    with command_context("plan.verify", target={"assertions": assertions}) as ctx:
        from confpub.verifier import verify_assertions
        result = verify_assertions(assertions_path=assertions, plan_path=plan)
        ctx.result = result


@auth_app.command("inspect")
def auth_inspect() -> None:
    """Show current credential status."""
    with command_context("auth.inspect") as ctx:
        from confpub.config import load_config
        config = load_config()
        ctx.result = config.auth_status()


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Configuration key (base_url, user, token)"),
    value: str = typer.Argument(..., help="Configuration value"),
) -> None:
    """Set a configuration value."""
    with command_context("config.set", target={"key": key}) as ctx:
        from confpub.config import set_config_value
        set_config_value(key, value)
        ctx.result = {"key": key, "value": value}


@config_app.command("inspect")
def config_inspect() -> None:
    """Show current configuration."""
    with command_context("config.inspect") as ctx:
        from confpub.config import load_config
        config = load_config()
        ctx.result = config.to_display_dict()


# ---------------------------------------------------------------------------
# guide command (top-level, not in a subgroup)
# ---------------------------------------------------------------------------


@app.command("guide")
def guide(
    section: Optional[str] = typer.Option(None, "--section", help="Return a specific section of the guide"),
) -> None:
    """Machine-readable CLI schema for agent consumption."""
    with command_context("guide") as ctx:
        from confpub.guide import build_guide
        full_guide = build_guide()
        if section:
            parts = section.split(".")
            result = full_guide
            for part in parts:
                if isinstance(result, dict) and part in result:
                    result = result[part]
                else:
                    from confpub.errors import validation_error, ERR_VALIDATION_REQUIRED
                    raise validation_error(
                        ERR_VALIDATION_REQUIRED,
                        f"Unknown guide section: {section}",
                    )
            ctx.result = result
        else:
            ctx.result = full_guide


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> None:
    """Entry point called by the `confpub` console script."""
    app()
