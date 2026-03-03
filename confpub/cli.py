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

import os

from confpub import __version__
from confpub.envelope import Envelope
from confpub.errors import ConfpubError, exit_code_for, ERR_INTERNAL_SDK
from confpub.output import emit_stderr, emit_stdout, is_compact, is_verbose, set_compact, set_quiet, set_verbose


def _resolve_space(cli_space: str | None, required: bool = False, fm_space: str | None = None) -> str | None:
    """Resolve space from CLI flag, front-matter, or CONFPUB_SPACE env var, with validation."""
    from confpub.config import ENV_SPACE
    from confpub.errors import validate_space_key

    space = cli_space or fm_space or os.environ.get(ENV_SPACE)
    if space is not None:
        validate_space_key(space)
        return space
    if required:
        raise ConfpubError(
            "ERR_VALIDATION_REQUIRED",
            "Space key is required. Use --space, front-matter, or set CONFPUB_SPACE.",
        )
    return None

# ---------------------------------------------------------------------------
# Subcommand group apps
# ---------------------------------------------------------------------------


def _group_callback(
    quiet: bool = typer.Option(False, "--quiet", help="Suppress progress output on stderr"),
    verbose: bool = typer.Option(False, "--verbose", help="Include diagnostics in result"),
    compact: bool = typer.Option(False, "--compact", help="Output single-line JSON (no indentation)"),
) -> None:
    """Allow --quiet/--verbose/--compact between the group name and the subcommand."""
    set_quiet(quiet)
    set_verbose(verbose)
    set_compact(compact)


page_app = typer.Typer(help="Page operations", callback=_group_callback)
plan_app = typer.Typer(help="Transactional plan workflow", callback=_group_callback)
auth_app = typer.Typer(help="Authentication", callback=_group_callback)
config_app = typer.Typer(help="Configuration", callback=_group_callback)
space_app = typer.Typer(help="Space operations", callback=_group_callback)
attachment_app = typer.Typer(help="Attachment operations", callback=_group_callback)
label_app = typer.Typer(help="Label operations", callback=_group_callback)
comment_app = typer.Typer(help="Comment operations", callback=_group_callback)

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
app.add_typer(label_app, name="label")
app.add_typer(comment_app, name="comment")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"confpub {__version__}")
        raise typer.Exit(0)


@app.callback()
def main_callback(
    quiet: bool = typer.Option(False, "--quiet", help="Suppress progress output on stderr"),
    verbose: bool = typer.Option(False, "--verbose", help="Include diagnostics in result"),
    compact: bool = typer.Option(False, "--compact", help="Output single-line JSON (no indentation)"),
    version: bool = typer.Option(
        False, "--version", help="Show version and exit",
        callback=_version_callback, is_eager=True,
    ),
) -> None:
    """confpub — publish Markdown to Confluence."""
    set_quiet(quiet)
    set_verbose(verbose)
    set_compact(compact)


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
        self.client: Any = None


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
            err_diag: dict[str, Any] = {"traceback": tb.format_exc()}
            if ctx.client and hasattr(ctx.client, "_call_count"):
                err_diag["api_call_count"] = ctx.client._call_count
            ctx.metrics["diagnostics"] = err_diag
        envelope = Envelope.failure(
            command_name,
            [e],
            target=ctx.target,
            warnings=ctx.warnings,
            metrics=ctx.metrics,
        )
        emit_stdout(envelope.to_json_bytes(indent=not is_compact()))
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
        emit_stdout(envelope.to_json_bytes(indent=not is_compact()))
        raise typer.Exit(code=90)
    else:
        duration_ms = int((time.monotonic() - start) * 1000)
        ctx.metrics["duration_ms"] = duration_ms
        if is_verbose():
            import sys
            from confpub.config import load_config as _load_verbose_config

            diag: dict[str, Any] = {
                "duration_ms": duration_ms,
                "command": command_name,
                "target": ctx.target,
                "warning_count": len(ctx.warnings),
                "python_version": sys.version,
                "confpub_version": __version__,
            }
            if ctx.client and hasattr(ctx.client, "_call_count"):
                diag["api_call_count"] = ctx.client._call_count
            try:
                _vcfg = _load_verbose_config()
                diag["config_source"] = _vcfg.token_source
                diag["confluence_url"] = _vcfg.base_url
                diag["is_cloud"] = _vcfg.is_cloud
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
        emit_stdout(envelope.to_json_bytes(indent=not is_compact()))


# ---------------------------------------------------------------------------
# Stub commands (replaced in later phases)
# ---------------------------------------------------------------------------


@page_app.command("list")
def page_list(
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key (or CONFPUB_SPACE env var)"),
    limit: int = typer.Option(25, "--limit", help="Maximum number of pages to return"),
    start: int = typer.Option(0, "--start", help="Starting offset for pagination"),
) -> None:
    """List pages in a Confluence space."""
    with command_context("page.list") as ctx:
        space = _resolve_space(space, required=True)
        ctx.target = {"space": space}
        from confpub.confluence import build_client, _slim_page
        client = build_client()
        ctx.client = client
        page_result = client.list_pages(space, start=start, limit=limit)
        ctx.result = {
            "pages": [_slim_page(p, base_url=client._config.base_url.rstrip("/"), is_cloud=client._config.is_cloud) for p in page_result["pages"]],
            "start": page_result["start"],
            "limit": page_result["limit"],
            "size": page_result["size"],
            "has_more": page_result["has_more"],
        }


@page_app.command("inspect")
def page_inspect(
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key (or CONFPUB_SPACE env var)"),
    title: str = typer.Option(None, "--title", help="Page title"),
    page_id: str = typer.Option(None, "--page-id", help="Confluence page ID"),
    raw: bool = typer.Option(False, "--raw", help="Return full raw API response"),
    format: str = typer.Option("storage", "--format", help="Output format: storage (raw HTML) or markdown"),
) -> None:
    """Inspect a Confluence page."""
    with command_context("page.inspect", target={"space": space, "title": title, "page_id": page_id}) as ctx:
        space = _resolve_space(space)
        from confpub.confluence import build_client, _slim_page
        client = build_client()
        ctx.client = client
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
            result = _slim_page(page, base_url=client._config.base_url.rstrip("/"), is_cloud=client._config.is_cloud)
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
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key (or CONFPUB_SPACE env var)"),
    parent: Optional[str] = typer.Option(None, "--parent", help="Parent page title"),
    title: Optional[str] = typer.Option(None, "--title", help="Page title (defaults to filename stem, hyphen/underscore→spaces, title-cased)"),
    title_from_h1: bool = typer.Option(False, "--title-from-h1", help="Derive title from first H1 heading in the Markdown file"),
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Confluence page ID (skip lookup, update directly)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing"),
    backup: bool = typer.Option(False, "--backup", help="Backup existing page before overwriting"),
    label: Optional[list[str]] = typer.Option(None, "--label", help="Label to apply (repeatable)"),
) -> None:
    """Publish a single Markdown file to Confluence."""
    from pathlib import Path as _Path
    from confpub.front_matter import parse_front_matter
    from confpub.publish import derive_title

    # Parse front-matter from the file (before command_context so title is resolved for target)
    fm = None
    source = _Path(file)
    if source.exists():
        md_text = source.read_text(encoding="utf-8")
        fm = parse_front_matter(md_text)

    fm_title = fm.title if fm else None
    fm_space = fm.space if fm else None
    fm_parent = fm.parent if fm else None
    fm_page_id = fm.page_id if fm else None
    fm_labels = fm.labels if fm else []

    resolved_title = derive_title(file, title, title_from_h1=title_from_h1, front_matter_title=fm_title)

    # Resolve page_id: CLI flag > front-matter
    effective_page_id = page_id or fm_page_id

    target = {"space": space, "title": resolved_title, "file": file}
    if effective_page_id:
        target["page_id"] = effective_page_id
    with command_context("page.publish", target=target) as ctx:
        space = _resolve_space(space, required=True, fm_space=fm_space)
        ctx.target["space"] = space

        # Resolve parent: CLI flag > front-matter
        effective_parent = parent or fm_parent

        if not effective_page_id and not effective_parent:
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                "Either --page-id or --parent is required (via flag or front-matter)",
            )

        # Merge labels: CLI + front-matter (deduplicated, order-preserving)
        cli_labels = label or []
        merged_labels = list(dict.fromkeys(cli_labels + fm_labels))

        from confpub.publish import publish_page
        result = publish_page(
            file=file,
            space=space,
            parent=effective_parent or "",
            title=resolved_title,
            page_id=effective_page_id,
            dry_run=dry_run,
            backup=backup,
            progress_callback=ctx,
            labels=merged_labels,
        )
        ctx.result = result


@page_app.command("pull")
def page_pull(
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key (or CONFPUB_SPACE env var)"),
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
    with command_context("page.pull", target={"space": space, "title": title, "page_id": page_id}) as ctx:
        space = _resolve_space(space)
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
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key (or CONFPUB_SPACE env var)"),
    title: Optional[str] = typer.Option(None, "--title", help="Page title"),
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Confluence page ID"),
    cascade: bool = typer.Option(False, "--cascade", help="Also delete child pages"),
) -> None:
    """Delete a Confluence page."""
    with command_context("page.delete", target={"space": space, "title": title, "page_id": page_id}) as ctx:
        space = _resolve_space(space)
        if not page_id and not (space and title):
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                "Either --page-id or both --space and --title are required",
            )
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client

        # Collect descendant IDs before deleting (for lockfile cleanup)
        deleted_ids: set[str] = set()
        if page_id:
            if cascade:
                deleted_ids.update(client.get_descendant_ids(page_id))
                client._delete_descendants(page_id)
            deleted_ids.add(page_id)
            result = client.delete_page(page_id)
        else:
            if cascade:
                page = client.get_page(space, title)
                if page:
                    pid = str(page["id"])
                    deleted_ids.update(client.get_descendant_ids(pid))
                    deleted_ids.add(pid)
            result = client.delete_page_by_title(space, title, cascade=cascade)

        # Clean up lockfile entries for deleted pages
        from pathlib import Path
        from confpub.lockfile import load_lockfile, save_lockfile, remove_by_page_ids
        lockfile_path = Path.cwd() / "confpub.lock"
        lockfile = load_lockfile(lockfile_path)
        if lockfile and remove_by_page_ids(lockfile, deleted_ids, title=title if not page_id else None):
            save_lockfile(lockfile_path, lockfile)

        # Enrich result with deleted ID summary
        result["deleted_ids"] = sorted(deleted_ids)
        result["deleted_count"] = len(deleted_ids)
        ctx.result = result


@page_app.command("move")
def page_move(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID to move"),
    target_parent: Optional[str] = typer.Option(None, "--target-parent", help="Title of the new parent page"),
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key (or CONFPUB_SPACE env var)"),
    target_parent_id: Optional[str] = typer.Option(None, "--target-parent-id", help="Page ID of the new parent"),
) -> None:
    """Move a page under a new parent."""
    target = {"page_id": page_id}
    with command_context("page.move", target=target) as ctx:
        space = _resolve_space(space)
        if not target_parent and not target_parent_id:
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                "Either --target-parent or --target-parent-id is required",
            )
        if target_parent and not space:
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                "--space is required when using --target-parent",
            )
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client

        if target_parent_id:
            # Use target_id directly — more reliable, no title resolution needed
            parent_page = client.get_page_by_id(target_parent_id)
            if not parent_page or not parent_page.get("id"):
                from confpub.errors import ERR_VALIDATION_NOT_FOUND
                raise ConfpubError(ERR_VALIDATION_NOT_FOUND, f"Target parent page not found: {target_parent_id}")
            resolved_space = parent_page.get("space", {}).get("key", space or "")
            result = client.move_page(resolved_space, page_id, target_id=target_parent_id)
        else:
            result = client.move_page(space, page_id, target_title=target_parent)

        ctx.result = result


@space_app.command("list")
def space_list() -> None:
    """List accessible Confluence spaces."""
    with command_context("space.list") as ctx:
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
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
        ctx.client = client
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
        ctx.client = client
        result = client.upload_attachment(page_id, file)
        ctx.result = result


@plan_app.command("create")
def plan_create(
    manifest: str = typer.Option(..., "--manifest", help="Path to confpub.yaml manifest"),
    output: Optional[str] = typer.Option(None, "--output", help="Output path for plan artifact"),
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key (or CONFPUB_SPACE env var)"),
    parent: Optional[str] = typer.Option(None, "--parent", help="Override manifest parent"),
) -> None:
    """Generate a plan artifact from a manifest."""
    with command_context("plan.create", target={"manifest": manifest}) as ctx:
        space = _resolve_space(space)
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
# Label commands
# ---------------------------------------------------------------------------


@label_app.command("list")
def label_list(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
) -> None:
    """List labels on a Confluence page."""
    with command_context("label.list", target={"page_id": page_id}) as ctx:
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        labels = client.get_labels(page_id)
        ctx.result = {"labels": labels, "count": len(labels)}


@label_app.command("add")
def label_add(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    label: list[str] = typer.Option(..., "--label", help="Label name (repeatable)"),
) -> None:
    """Add labels to a Confluence page."""
    with command_context("label.add", target={"page_id": page_id}) as ctx:
        from confpub.errors import ERR_VALIDATION_LABEL
        # Validate labels
        for lbl in label:
            if " " in lbl:
                raise ConfpubError(
                    ERR_VALIDATION_LABEL,
                    f"Label must not contain spaces: '{lbl}'",
                    details={"label": lbl},
                )
            if len(lbl) > 255:
                raise ConfpubError(
                    ERR_VALIDATION_LABEL,
                    f"Label exceeds 255 characters: '{lbl[:50]}...'",
                    details={"label": lbl, "length": len(lbl)},
                )

        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        results = client.set_labels(page_id, label)
        ctx.result = {"labels_added": label, "results": results}


@label_app.command("remove")
def label_remove(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    label: list[str] = typer.Option(..., "--label", help="Label name to remove (repeatable)"),
) -> None:
    """Remove labels from a Confluence page."""
    with command_context("label.remove", target={"page_id": page_id}) as ctx:
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        results = []
        for lbl in label:
            result = client.remove_label(page_id, lbl)
            results.append(result)
        ctx.result = {"labels_removed": label, "results": results}


# ---------------------------------------------------------------------------
# Comment commands
# ---------------------------------------------------------------------------


@comment_app.command("add")
def comment_add(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    text: Optional[str] = typer.Option(None, "--text", help="Comment text (Markdown)"),
    file: Optional[str] = typer.Option(None, "--file", help="Path to Markdown file for comment body"),
) -> None:
    """Add a comment to a Confluence page."""
    with command_context("comment.add", target={"page_id": page_id}) as ctx:
        if not text and not file:
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                "Either --text or --file is required",
            )
        if text and file:
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                "--text and --file are mutually exclusive",
            )

        if file:
            from pathlib import Path
            p = Path(file)
            if not p.exists():
                from confpub.errors import ERR_IO_FILE_NOT_FOUND
                raise ConfpubError(ERR_IO_FILE_NOT_FOUND, f"File not found: {file}")
            md_text = p.read_text(encoding="utf-8")
        else:
            md_text = text

        from confpub.converter import convert_markdown
        storage_body = convert_markdown(md_text)

        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        result = client.add_comment(page_id, storage_body)
        ctx.result = result


# ---------------------------------------------------------------------------
# search command (top-level, not in a subgroup)
# ---------------------------------------------------------------------------


@app.command("search")
def search(
    cql: Optional[str] = typer.Option(None, "--cql", help="Raw CQL query"),
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key (or CONFPUB_SPACE env var)"),
    title: Optional[str] = typer.Option(None, "--title", help="Search by page title (fuzzy match)"),
    content_type: Optional[str] = typer.Option(None, "--type", help="Filter by content type (page, blogpost, etc.)"),
    limit: int = typer.Option(25, "--limit", help="Maximum results to return"),
    start: int = typer.Option(0, "--start", help="Starting offset for pagination"),
    include_archived: bool = typer.Option(False, "--include-archived", help="Include results from archived spaces"),
    excerpt_length: int = typer.Option(200, "--excerpt-length", help="Max excerpt chars (0 = unlimited)"),
) -> None:
    """Search Confluence content using CQL."""
    with command_context("search", target={"cql": cql, "space": space, "title": title, "type": content_type}) as ctx:
        space = _resolve_space(space)
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
        ctx.client = client
        result = client.search(
            effective_cql,
            start=start,
            limit=limit,
            include_archived_spaces=include_archived,
            excerpt_length=excerpt_length,
        )
        result["cql_query"] = effective_cql
        if space and result.get("total", 0) == 0:
            ctx.warnings.append(
                f"No results found. Verify space '{space}' exists (use 'space list' to check)."
            )
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
    except ConfpubError as e:
        envelope = Envelope.failure("cli", [e])
        emit_stdout(envelope.to_json_bytes())
        sys.exit(exit_code_for(e.code))
