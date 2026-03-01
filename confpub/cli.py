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
            import sys
            from confpub.config import load_config as _load_verbose_config

            diag: dict[str, Any] = {
                "command": command_name,
                "target": ctx.target,
                "warning_count": len(ctx.warnings),
                "python_version": sys.version,
                "confpub_version": __version__,
            }
            try:
                _vcfg = _load_verbose_config()
                diag["confluence_url"] = _vcfg.base_url
            except Exception:
                pass
            ctx.metrics["diagnostics"] = diag
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
        ctx.result = {"pages": [_slim_page(p, base_url=client._config.base_url.rstrip("/")) for p in pages]}


@page_app.command("inspect")
def page_inspect(
    space: str = typer.Option(None, "--space", help="Confluence space key"),
    title: str = typer.Option(None, "--title", help="Page title"),
    page_id: str = typer.Option(None, "--page-id", help="Confluence page ID"),
    raw: bool = typer.Option(False, "--raw", help="Return full raw API response"),
    format: str = typer.Option("storage", "--format", help="Output format: storage (raw HTML) or markdown"),
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
        if not page:
            from confpub.errors import ERR_VALIDATION_NOT_FOUND
            raise ConfpubError(ERR_VALIDATION_NOT_FOUND, f"Page not found")
        if raw:
            ctx.result = page
        else:
            result = _slim_page(page, base_url=client._config.base_url.rstrip("/"))
            if format == "markdown" and "body_storage" in result:
                from confpub.reverse_converter import convert_storage_to_markdown
                conversion = convert_storage_to_markdown(result["body_storage"])
                result["body_markdown"] = conversion.markdown
                del result["body_storage"]
                if conversion.warnings:
                    result["conversion_warnings"] = conversion.warnings
                if conversion.unknown_macros:
                    result["unknown_macros"] = conversion.unknown_macros
            ctx.result = result


@page_app.command("publish")
def page_publish(
    file: str = typer.Argument(..., help="Markdown file to publish"),
    space: str = typer.Option(..., "--space", help="Confluence space key"),
    parent: Optional[str] = typer.Option(None, "--parent", help="Parent page title"),
    title: Optional[str] = typer.Option(None, "--title", help="Page title (defaults to filename stem, hyphen/underscore→spaces, title-cased)"),
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Confluence page ID (skip lookup, update directly)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing"),
    backup: bool = typer.Option(False, "--backup", help="Backup existing page before overwriting"),
) -> None:
    """Publish a single Markdown file to Confluence."""
    from confpub.publish import derive_title
    resolved_title = derive_title(file, title)
    if not page_id and not parent:
        raise ConfpubError(
            "ERR_VALIDATION_REQUIRED",
            "Either --page-id or --parent is required",
        )
    target = {"space": space, "title": resolved_title, "file": file}
    if page_id:
        target["page_id"] = page_id
    with command_context("page.publish", target=target) as ctx:
        from confpub.publish import publish_page
        result = publish_page(
            file=file,
            space=space,
            parent=parent or "",
            title=title,
            page_id=page_id,
            dry_run=dry_run,
            backup=backup,
            progress_callback=ctx,
        )
        ctx.result = result


@page_app.command("pull")
def page_pull(
    space: str = typer.Option(None, "--space", help="Confluence space key"),
    title: str = typer.Option(None, "--title", help="Page title"),
    page_id: str = typer.Option(None, "--page-id", help="Confluence page ID"),
    output: str = typer.Option(".", "--output", "-o", help="Output directory"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Pull child pages recursively"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
    layout: str = typer.Option("flat", "--layout", help="Output layout: flat or nested"),
    no_attachments: bool = typer.Option(False, "--no-attachments", help="Skip downloading attachments"),
    manifest: bool = typer.Option(False, "--manifest", help="Generate confpub.yaml manifest"),
) -> None:
    """Pull Confluence pages to local Markdown files."""
    target = {"space": space, "title": title, "page_id": page_id}
    with command_context("page.pull", target=target) as ctx:
        from confpub.errors import ERR_VALIDATION_REQUIRED
        if not page_id and not (space and title):
            raise ConfpubError(
                ERR_VALIDATION_REQUIRED,
                "Either --page-id or both --space and --title are required",
            )
        from confpub.puller import pull_pages
        result = pull_pages(
            space=space,
            title=title,
            page_id=page_id,
            output_dir=output,
            recursive=recursive,
            force=force,
            layout=layout,
            include_attachments=not no_attachments,
            generate_manifest=manifest,
        )
        ctx.warnings.extend(result.pop("warnings", []))
        ctx.result = result


@page_app.command("delete")
def page_delete(
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key"),
    title: Optional[str] = typer.Option(None, "--title", help="Page title"),
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Confluence page ID"),
    cascade: bool = typer.Option(False, "--cascade", help="Also delete child pages"),
) -> None:
    """Delete a Confluence page."""
    with command_context("page.delete", target={"space": space, "title": title, "page_id": page_id}) as ctx:
        if not page_id and not (space and title):
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                "Either --page-id or both --space and --title are required",
            )
        from confpub.confluence import build_client
        client = build_client()
        if page_id:
            if cascade:
                client._delete_descendants(page_id)
            result = client.delete_page(page_id)
        else:
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
        from confpub.confluence import build_client, _slim_attachment
        client = build_client()
        attachments = client.get_attachments(page_id)
        ctx.result = {"attachments": [_slim_attachment(a) for a in attachments]}


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
        if not result.get("results"):
            ctx.warnings.append("No assertions were verified — result is vacuously true")
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
# search command (top-level, not in a subgroup)
# ---------------------------------------------------------------------------


@app.command("search")
def search(
    cql: Optional[str] = typer.Option(None, "--cql", help="Raw CQL query"),
    space: Optional[str] = typer.Option(None, "--space", help="Filter by space key"),
    title: Optional[str] = typer.Option(None, "--title", help="Search by page title (fuzzy match)"),
    content_type: Optional[str] = typer.Option(None, "--type", help="Filter by content type (page, blogpost, etc.)"),
    limit: int = typer.Option(25, "--limit", help="Maximum results to return"),
    start: int = typer.Option(0, "--start", help="Starting offset for pagination"),
    include_archived: bool = typer.Option(False, "--include-archived", help="Include results from archived spaces"),
    excerpt_length: int = typer.Option(200, "--excerpt-length", help="Max excerpt chars (0 = unlimited)"),
) -> None:
    """Search Confluence content using CQL."""
    target = {"cql": cql, "space": space, "title": title, "type": content_type}
    with command_context("search", target=target) as ctx:
        # Build effective CQL from flags
        fragments: list[str] = []
        if space:
            fragments.append(f'space = "{space}"')
        if title:
            fragments.append(f'title ~ "{title}"')
        if content_type:
            fragments.append(f'type = "{content_type}"')
        if cql:
            fragments.append(f"({cql})")

        if not fragments:
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                "At least one of --cql, --space, --title, or --type is required",
            )

        effective_cql = " AND ".join(fragments)

        from confpub.confluence import build_client
        client = build_client()
        result = client.search(
            effective_cql,
            start=start,
            limit=limit,
            include_archived_spaces=include_archived,
            excerpt_length=excerpt_length,
        )
        result["cql_query"] = effective_cql
        ctx.result = result


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
                        valid_sections=list(full_guide.keys()),
                    )
            ctx.result = result
        else:
            ctx.result = full_guide


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> None:
    """Entry point called by the `confpub` console script."""
    import sys
    import click
    from confpub.errors import ERR_VALIDATION_REQUIRED
    try:
        exit_code = app(standalone_mode=False)
        sys.exit(exit_code or 0)
    except click.UsageError as e:
        err = ConfpubError(ERR_VALIDATION_REQUIRED, e.format_message())
        envelope = Envelope.failure("cli", [err])
        emit_stdout(envelope.to_json_bytes())
        sys.exit(10)
