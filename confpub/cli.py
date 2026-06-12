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


def _warm_trust_cache(client: Any, page_id: str) -> None:
    """Opportunistically score a page to keep the trust cache warm.

    Called as a side effect after commands that touch a page.
    Never raises — failures are silently ignored.
    """
    try:
        from confpub.trust.scoring import opportunistic_score
        opportunistic_score(client, page_id)
    except Exception:
        pass


def _collect_child_pages(client: Any, page_id: str) -> list[str]:
    """Recursively collect all child page IDs under a parent."""
    result: list[str] = []
    children = client.get_page_children(page_id)
    for child in children:
        cid = str(child.get("id", ""))
        if cid:
            result.append(cid)
            result.extend(_collect_child_pages(client, cid))
    return result


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
    quiet: Optional[bool] = typer.Option(None, "--quiet", help="Suppress progress output on stderr"),
    verbose: Optional[bool] = typer.Option(None, "--verbose", help="Include diagnostics in result"),
    compact: Optional[bool] = typer.Option(None, "--compact", help="Output single-line JSON (no indentation)"),
) -> None:
    """Allow --quiet/--verbose/--compact between the group name and the subcommand.

    Uses Optional[bool] with None default so that defaults don't overwrite
    flags already set by the root-level main_callback.
    """
    if quiet is not None:
        set_quiet(quiet)
    if verbose is not None:
        set_verbose(verbose)
    if compact is not None:
        set_compact(compact)


page_app = typer.Typer(help="Page operations", callback=_group_callback)
plan_app = typer.Typer(help="Transactional plan workflow", callback=_group_callback)
auth_app = typer.Typer(help="Authentication", callback=_group_callback)
config_app = typer.Typer(help="Configuration", callback=_group_callback)
space_app = typer.Typer(help="Space operations", callback=_group_callback)
attachment_app = typer.Typer(help="Attachment operations", callback=_group_callback)
label_app = typer.Typer(help="Label operations", callback=_group_callback)
comment_app = typer.Typer(help="Comment operations", callback=_group_callback)
property_app = typer.Typer(help="Page property operations", callback=_group_callback)
skill_app = typer.Typer(help="Skill management", callback=_group_callback)
trust_app = typer.Typer(help="Trust scoring administration", callback=_group_callback)
trust_cache_app = typer.Typer(help="Trust cache operations", callback=_group_callback)
trust_profile_app = typer.Typer(help="Trust profile operations", callback=_group_callback)
trust_anchor_app = typer.Typer(help="Trust anchor operations", callback=_group_callback)
trust_app.add_typer(trust_cache_app, name="cache")
trust_app.add_typer(trust_profile_app, name="profile")
trust_app.add_typer(trust_anchor_app, name="anchor")

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
app.add_typer(property_app, name="property")
app.add_typer(skill_app, name="skill")
app.add_typer(trust_app, name="trust")


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
    title: Optional[str] = typer.Option(None, "--title", help="Filter by title (substring match)"),
    label: Optional[str] = typer.Option(None, "--label", help="Filter by label"),
    limit: int = typer.Option(25, "--limit", help="Maximum number of pages to return"),
    start: int = typer.Option(0, "--start", help="Starting offset for pagination"),
) -> None:
    """List pages in a Confluence space."""
    with command_context("page.list") as ctx:
        if limit < 1:
            from confpub.errors import ERR_VALIDATION_REQUIRED
            raise ConfpubError(ERR_VALIDATION_REQUIRED, "limit must be a positive integer (>= 1)")
        space = _resolve_space(space, required=True)
        ctx.target = {"space": space}
        from confpub.confluence import build_client, _slim_page
        client = build_client()
        ctx.client = client

        if label:
            # Use CQL search for label filtering — the list_pages API doesn't support it
            cql = f'type = page AND space = "{space}" AND label = "{label}"'
            if title:
                cql += f' AND title ~ "{title}"'
            search_result = client.search(cql, start=start, limit=limit)
            pages = []
            for sr in search_result.get("results", []):
                page_id = sr.get("id")
                if page_id:
                    # Normalize to _slim_page schema for consistent field names
                    normalized = {"id": page_id, "title": sr.get("title")}
                    if sr.get("url"):
                        normalized["webui"] = sr["url"]
                    if sr.get("last_modified"):
                        normalized["version"] = {"when": sr["last_modified"]}
                    pages.append(normalized)
            ctx.result = {
                "pages": pages,
                "start": search_result.get("start", start),
                "limit": search_result.get("limit", limit),
                "size": len(pages),
                "has_more": search_result.get("has_more", False),
            }
        else:
            page_result = client.list_pages(space, start=start, limit=limit)
            pages = [_slim_page(p, base_url=client._config.base_url.rstrip("/"), is_cloud=client._config.is_cloud) for p in page_result["pages"]]
            if title:
                title_lower = title.lower()
                pages = [p for p in pages if title_lower in (p.get("title") or "").lower()]
            ctx.result = {
                "pages": pages,
                "start": page_result["start"],
                "limit": page_result["limit"],
                "size": len(pages),
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
        if not raw and format not in ("storage", "markdown"):
            raise ConfpubError("ERR_VALIDATION_REQUIRED", f"--format must be 'storage' or 'markdown', got '{format}'")
        if raw:
            ctx.result = page
        else:
            result = _slim_page(page, base_url=client._config.base_url.rstrip("/"), is_cloud=client._config.is_cloud)
            labels = client.get_labels(str(page["id"]))
            result["labels"] = labels
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
            _warm_trust_cache(client, str(page["id"]))


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
    html_macro_name: Optional[str] = typer.Option(None, "--html-macro-name", help="HTML macro name (html for DC; Cloud apps vary, default html-macro)"),
    html_macro_format: Optional[str] = typer.Option(None, "--html-macro-format", help="HTML macro storage format: classic or forge-adf-extension"),
    html_macro_forge_extension_key: Optional[str] = typer.Option(None, "--html-macro-forge-extension-key", help="Forge HTML macro extension-key copied from a working macro"),
    html_macro_forge_extension_id: Optional[str] = typer.Option(None, "--html-macro-forge-extension-id", help="Forge HTML macro extension-id copied from a working macro"),
    html_macro_forge_environment: Optional[str] = typer.Option(None, "--html-macro-forge-environment", help="Forge environment for the HTML macro (default PRODUCTION)"),
    html_macro_forge_cloud_id: Optional[str] = typer.Option(None, "--html-macro-forge-cloud-id", help="Optional Forge cloud-id copied from a working macro"),
    html_macro_forge_context_ids: Optional[str] = typer.Option(None, "--html-macro-forge-context-ids", help="Optional Forge context-ids copied from a working macro"),
    html_macro_forge_account_id: Optional[str] = typer.Option(None, "--html-macro-forge-account-id", help="Optional Forge account-id copied from a working macro"),
) -> None:
    """Publish a single Markdown file to Confluence."""
    from pathlib import Path as _Path
    from confpub.front_matter import parse_front_matter
    from confpub.publish import derive_title

    target = {"space": space, "file": file}
    with command_context("page.publish", target=target) as ctx:
        source = _Path(file)
        if not source.exists():
            from confpub.errors import ERR_IO_FILE_NOT_FOUND
            raise ConfpubError(
                ERR_IO_FILE_NOT_FOUND,
                f"Source file not found: {file}",
                details={"file": file},
                retryable=False,
                suggested_action="fix_input",
            )

        # Parse front-matter (inside command_context so errors get the JSON envelope)
        try:
            md_text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            from confpub.errors import ERR_VALIDATION_MARKDOWN
            raise ConfpubError(
                ERR_VALIDATION_MARKDOWN,
                f"File is not valid UTF-8 text: {file}",
                details={"file": file, "error": str(e)},
                suggested_action="fix_input",
            ) from e
        fm = parse_front_matter(md_text)

        fm_title = fm.title if fm else None
        fm_space = fm.space if fm else None
        fm_parent = fm.parent if fm else None
        fm_page_id = fm.page_id if fm else None
        fm_labels = fm.labels if fm else []

        resolved_title = derive_title(file, title, title_from_h1=title_from_h1, front_matter_title=fm_title)

        # Resolve page_id: CLI flag > front-matter
        effective_page_id = page_id or fm_page_id

        ctx.target["title"] = resolved_title
        if effective_page_id:
            ctx.target["page_id"] = effective_page_id

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

        # Resolve html_macro_name: CLI flag > front-matter > config/env/default in publish_page
        fm_html_macro = fm.html_macro_name if fm else None
        effective_html_macro = html_macro_name or fm_html_macro
        fm_html_macro_format = fm.html_macro_format if fm else None
        effective_html_macro_format = html_macro_format or fm_html_macro_format
        fm_html_macro_forge_extension_key = fm.html_macro_forge_extension_key if fm else None
        effective_html_macro_forge_extension_key = (
            html_macro_forge_extension_key or fm_html_macro_forge_extension_key
        )
        fm_html_macro_forge_extension_id = fm.html_macro_forge_extension_id if fm else None
        effective_html_macro_forge_extension_id = (
            html_macro_forge_extension_id or fm_html_macro_forge_extension_id
        )
        fm_html_macro_forge_environment = fm.html_macro_forge_environment if fm else None
        effective_html_macro_forge_environment = (
            html_macro_forge_environment or fm_html_macro_forge_environment
        )
        fm_html_macro_forge_cloud_id = fm.html_macro_forge_cloud_id if fm else None
        effective_html_macro_forge_cloud_id = (
            html_macro_forge_cloud_id or fm_html_macro_forge_cloud_id
        )
        fm_html_macro_forge_context_ids = fm.html_macro_forge_context_ids if fm else None
        effective_html_macro_forge_context_ids = (
            html_macro_forge_context_ids or fm_html_macro_forge_context_ids
        )
        fm_html_macro_forge_account_id = fm.html_macro_forge_account_id if fm else None
        effective_html_macro_forge_account_id = (
            html_macro_forge_account_id or fm_html_macro_forge_account_id
        )

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
            html_macro_name=effective_html_macro,
            html_macro_format=effective_html_macro_format,
            html_macro_forge_extension_key=effective_html_macro_forge_extension_key,
            html_macro_forge_extension_id=effective_html_macro_forge_extension_id,
            html_macro_forge_environment=effective_html_macro_forge_environment,
            html_macro_forge_cloud_id=effective_html_macro_forge_cloud_id,
            html_macro_forge_context_ids=effective_html_macro_forge_context_ids,
            html_macro_forge_account_id=effective_html_macro_forge_account_id,
        )
        ctx.warnings.extend(result.pop("warnings", []))
        ctx.result = result
        if not dry_run:
            # Extract page IDs from publish changes
            for change in result.get("changes", []):
                pid = change.get("confluence_page_id")
                if pid:
                    from confpub.confluence import build_client as _build
                    _warm_trust_cache(_build(), str(pid))
                    break  # single-page publish has one change


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
        from pathlib import Path as _Path
        from confpub.errors import ERR_IO_FILE_NOT_FOUND
        source = _Path(file).resolve()
        if not source.exists():
            raise ConfpubError(
                ERR_IO_FILE_NOT_FOUND,
                f"File not found: {file}",
                details={"file": file},
                retryable=False,
                suggested_action="fix_input",
            )
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        result = client.upload_attachment(page_id, str(source))
        ctx.result = result


@plan_app.command("create")
def plan_create(
    manifest: str = typer.Option(..., "--manifest", help="Path to confpub.yaml manifest"),
    output: Optional[str] = typer.Option(None, "--output", help="Output path for plan artifact"),
    space: Optional[str] = typer.Option(None, "--space", help="Confluence space key (or CONFPUB_SPACE env var)"),
    parent: Optional[str] = typer.Option(None, "--parent", help="Override manifest parent"),
    html_macro_name: Optional[str] = typer.Option(None, "--html-macro-name", help="HTML macro name (html for DC; Cloud apps vary, default html-macro)"),
    html_macro_format: Optional[str] = typer.Option(None, "--html-macro-format", help="HTML macro storage format: classic or forge-adf-extension"),
    html_macro_forge_extension_key: Optional[str] = typer.Option(None, "--html-macro-forge-extension-key", help="Forge HTML macro extension-key copied from a working macro"),
    html_macro_forge_extension_id: Optional[str] = typer.Option(None, "--html-macro-forge-extension-id", help="Forge HTML macro extension-id copied from a working macro"),
    html_macro_forge_environment: Optional[str] = typer.Option(None, "--html-macro-forge-environment", help="Forge environment for the HTML macro (default PRODUCTION)"),
    html_macro_forge_cloud_id: Optional[str] = typer.Option(None, "--html-macro-forge-cloud-id", help="Optional Forge cloud-id copied from a working macro"),
    html_macro_forge_context_ids: Optional[str] = typer.Option(None, "--html-macro-forge-context-ids", help="Optional Forge context-ids copied from a working macro"),
    html_macro_forge_account_id: Optional[str] = typer.Option(None, "--html-macro-forge-account-id", help="Optional Forge account-id copied from a working macro"),
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
            html_macro_name=html_macro_name,
            html_macro_format=html_macro_format,
            html_macro_forge_extension_key=html_macro_forge_extension_key,
            html_macro_forge_extension_id=html_macro_forge_extension_id,
            html_macro_forge_environment=html_macro_forge_environment,
            html_macro_forge_cloud_id=html_macro_forge_cloud_id,
            html_macro_forge_context_ids=html_macro_forge_context_ids,
            html_macro_forge_account_id=html_macro_forge_account_id,
        )
        ctx.warnings.extend(result.pop("warnings", []))
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
    html_macro_name: Optional[str] = typer.Option(None, "--html-macro-name", help="HTML macro name (html for DC; Cloud apps vary, default html-macro)"),
    html_macro_format: Optional[str] = typer.Option(None, "--html-macro-format", help="HTML macro storage format: classic or forge-adf-extension"),
    html_macro_forge_extension_key: Optional[str] = typer.Option(None, "--html-macro-forge-extension-key", help="Forge HTML macro extension-key copied from a working macro"),
    html_macro_forge_extension_id: Optional[str] = typer.Option(None, "--html-macro-forge-extension-id", help="Forge HTML macro extension-id copied from a working macro"),
    html_macro_forge_environment: Optional[str] = typer.Option(None, "--html-macro-forge-environment", help="Forge environment for the HTML macro (default PRODUCTION)"),
    html_macro_forge_cloud_id: Optional[str] = typer.Option(None, "--html-macro-forge-cloud-id", help="Optional Forge cloud-id copied from a working macro"),
    html_macro_forge_context_ids: Optional[str] = typer.Option(None, "--html-macro-forge-context-ids", help="Optional Forge context-ids copied from a working macro"),
    html_macro_forge_account_id: Optional[str] = typer.Option(None, "--html-macro-forge-account-id", help="Optional Forge account-id copied from a working macro"),
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
            html_macro_name=html_macro_name,
            html_macro_format=html_macro_format,
            html_macro_forge_extension_key=html_macro_forge_extension_key,
            html_macro_forge_extension_id=html_macro_forge_extension_id,
            html_macro_forge_environment=html_macro_forge_environment,
            html_macro_forge_cloud_id=html_macro_forge_cloud_id,
            html_macro_forge_context_ids=html_macro_forge_context_ids,
            html_macro_forge_account_id=html_macro_forge_account_id,
        )
        ctx.warnings.extend(result.pop("warnings", []))
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
    key: str = typer.Argument(..., help="Configuration key (base_url, user, token, ssl_verify, html_macro_name, html_macro_format, html_macro_forge_extension_key, html_macro_forge_extension_id, html_macro_forge_environment, html_macro_forge_cloud_id, html_macro_forge_context_ids, html_macro_forge_account_id)"),
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
        _warm_trust_cache(client, page_id)


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
        _warm_trust_cache(client, page_id)


# ---------------------------------------------------------------------------
# Comment commands
# ---------------------------------------------------------------------------


@comment_app.command("list")
def comment_list(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    limit: int = typer.Option(25, "--limit", help="Maximum comments to return"),
) -> None:
    """List comments on a Confluence page."""
    with command_context("comment.list", target={"page_id": page_id}) as ctx:
        if limit < 1:
            from confpub.errors import ERR_VALIDATION_REQUIRED
            raise ConfpubError(ERR_VALIDATION_REQUIRED, "limit must be a positive integer (>= 1)")
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        comments = client.get_comments(page_id, limit=limit)
        ctx.result = {"comments": comments, "count": len(comments)}


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

        from confpub.config import load_config as _load_comment_config
        from confpub.config import resolve_html_macro_settings as _resolve_comment_html_macro_settings
        from confpub.converter import convert_markdown
        _comment_config = _load_comment_config()
        _comment_html_macro = _resolve_comment_html_macro_settings(_comment_config)
        storage_body = convert_markdown(
            md_text,
            html_macro_name=_comment_html_macro.name,
            html_macro_format=_comment_html_macro.format,
            html_macro_forge_extension_key=_comment_html_macro.forge_extension_key,
            html_macro_forge_extension_id=_comment_html_macro.forge_extension_id,
            html_macro_forge_environment=_comment_html_macro.forge_environment,
            html_macro_forge_cloud_id=_comment_html_macro.forge_cloud_id,
            html_macro_forge_context_ids=_comment_html_macro.forge_context_ids,
            html_macro_forge_account_id=_comment_html_macro.forge_account_id,
        )

        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        result = client.add_comment(page_id, storage_body)
        ctx.result = result


# ---------------------------------------------------------------------------
# Property commands
# ---------------------------------------------------------------------------


@property_app.command("list")
def property_list(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
) -> None:
    """List all properties on a Confluence page."""
    with command_context("property.list", target={"page_id": page_id}) as ctx:
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        props = client.get_page_properties(page_id)
        ctx.result = {"properties": props, "count": len(props)}


@property_app.command("get")
def property_get(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    key: str = typer.Option(..., "--key", help="Property key"),
) -> None:
    """Get a single property from a Confluence page."""
    with command_context("property.get", target={"page_id": page_id, "key": key}) as ctx:
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        ctx.result = client.get_page_property(page_id, key)


@property_app.command("set")
def property_set(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    key: str = typer.Option(..., "--key", help="Property key"),
    value: str = typer.Option(..., "--value", help="Property value (JSON string or plain text)"),
) -> None:
    """Set a property on a Confluence page (create or update)."""
    with command_context("property.set", target={"page_id": page_id, "key": key}) as ctx:
        import json as _json
        try:
            parsed_value = _json.loads(value)
        except (ValueError, TypeError):
            parsed_value = value

        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        ctx.result = client.set_page_property(page_id, key, parsed_value)
        _warm_trust_cache(client, page_id)


@property_app.command("delete")
def property_delete(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    key: str = typer.Option(..., "--key", help="Property key to delete"),
) -> None:
    """Delete a property from a Confluence page."""
    with command_context("property.delete", target={"page_id": page_id, "key": key}) as ctx:
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        ctx.result = client.delete_page_property(page_id, key)


# ---------------------------------------------------------------------------
# Page history / version commands (added to page_app)
# ---------------------------------------------------------------------------


@page_app.command("history")
def page_history(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    limit: int = typer.Option(25, "--limit", help="Maximum versions to return"),
) -> None:
    """Show version history of a Confluence page."""
    with command_context("page.history", target={"page_id": page_id}) as ctx:
        if limit < 1:
            from confpub.errors import ERR_VALIDATION_REQUIRED
            raise ConfpubError(ERR_VALIDATION_REQUIRED, "limit must be a positive integer (>= 1)")
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        versions = client.get_page_history(page_id, limit=limit)
        ctx.result = {"versions": versions, "count": len(versions)}
        _warm_trust_cache(client, page_id)


@page_app.command("version")
def page_version(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    version_number: int = typer.Option(..., "--version-number", help="Version number to retrieve"),
) -> None:
    """Get a specific version of a Confluence page."""
    with command_context("page.version", target={"page_id": page_id, "version": version_number}) as ctx:
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        ctx.result = client.get_page_version(page_id, version_number)


# ---------------------------------------------------------------------------
# Page export command (added to page_app)
# ---------------------------------------------------------------------------


@page_app.command("export")
def page_export(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    fmt: str = typer.Option(..., "--format", help="Export format: pdf or word"),
    output: str = typer.Option(..., "--output", help="Output file path"),
) -> None:
    """Export a Confluence page as PDF or Word."""
    with command_context("page.export", target={"page_id": page_id, "format": fmt}) as ctx:
        if fmt not in ("pdf", "word"):
            raise ConfpubError("ERR_VALIDATION_REQUIRED", f"--format must be 'pdf' or 'word', got '{fmt}'")
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        ctx.result = client.export_page(page_id, fmt, output)


# ---------------------------------------------------------------------------
# Attachment download / delete commands (added to attachment_app)
# ---------------------------------------------------------------------------


@attachment_app.command("download")
def attachment_download(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    filename: str = typer.Option(..., "--filename", help="Attachment filename"),
    output: str = typer.Option(..., "--output", help="Output file path"),
) -> None:
    """Download an attachment from a Confluence page."""
    with command_context("attachment.download", target={"page_id": page_id, "filename": filename}) as ctx:
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        success = client.download_attachment(page_id, filename, output, raise_on_error=True)
        if not success:
            from confpub.errors import ERR_VALIDATION_NOT_FOUND
            raise ConfpubError(ERR_VALIDATION_NOT_FOUND, f"Attachment '{filename}' not found on page {page_id}")
        import os
        file_size = os.path.getsize(output) if os.path.exists(output) else 0
        ctx.result = {
            "downloaded": True,
            "page_id": page_id,
            "filename": filename,
            "output_path": os.path.abspath(output),
            "file_size": file_size,
        }


@attachment_app.command("delete")
def attachment_delete_cmd(
    page_id: str = typer.Option(..., "--page-id", help="Confluence page ID"),
    filename: str = typer.Option(..., "--filename", help="Attachment filename to delete"),
) -> None:
    """Delete an attachment from a Confluence page."""
    with command_context("attachment.delete", target={"page_id": page_id, "filename": filename}) as ctx:
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        ctx.result = client.delete_attachment(page_id, filename)


# ---------------------------------------------------------------------------
# Space inspect command (added to space_app)
# ---------------------------------------------------------------------------


@space_app.command("inspect")
def space_inspect(
    space: str = typer.Option(..., "--space", help="Confluence space key"),
) -> None:
    """Get detailed information about a Confluence space."""
    with command_context("space.inspect", target={"space": space}) as ctx:
        from confpub.errors import validate_space_key
        validate_space_key(space)
        from confpub.confluence import build_client
        client = build_client()
        ctx.client = client
        ctx.result = client.get_space(space)


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
    no_score: bool = typer.Option(False, "--no-score", help="Omit cached trust scores from results"),
) -> None:
    """Search Confluence content using CQL."""
    with command_context("search", target={"cql": cql, "space": space, "title": title, "type": content_type}) as ctx:
        if limit < 1:
            from confpub.errors import ERR_VALIDATION_REQUIRED
            raise ConfpubError(ERR_VALIDATION_REQUIRED, "limit must be a positive integer (>= 1)")
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

        # Enrich results with cached trust scores (default on)
        if not no_score:
            try:
                from confpub.trust.cache import TrustCache
                cache = TrustCache()
                page_ids = [
                    r["id"] for r in result.get("results", [])
                    if r.get("id") and r.get("type") == "page"
                ]
                if page_ids:
                    scores = cache.get_scores_by_page_ids(page_ids)
                    for r in result.get("results", []):
                        pid = r.get("id")
                        if pid and pid in scores:
                            r["trust"] = scores[pid]
                cache.close()
            except Exception:
                pass  # cache unavailable — skip silently

        if space and result.get("total", 0) == 0:
            try:
                spaces = client.list_spaces()
                known_keys = {s["key"] for s in spaces}
                if space not in known_keys:
                    ctx.warnings.append(f"Space '{space}' not found. Use 'space list' to see accessible spaces.")
                else:
                    ctx.warnings.append(f"No results found in space '{space}'.")
            except Exception:
                ctx.warnings.append(f"No results found. Verify space '{space}' exists (use 'space list' to check).")
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
# skill group
# ---------------------------------------------------------------------------


@skill_app.command("install")
def skill_install(
    agent: Optional[list[str]] = typer.Option(None, "--agent", help="Target agent(s): claude, copilot, cursor, windsurf, agents-md"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing skill files"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview installation without writing"),
) -> None:
    """Install the confpub publishing skill into the current repo."""
    with command_context("skill.install") as ctx:
        from confpub.skill_installer import install_skill
        from pathlib import Path

        root = Path.cwd()
        result = install_skill(root, agents=agent, force=force, dry_run=dry_run)
        ctx.result = result


@skill_app.command("inspect")
def skill_inspect_cmd() -> None:
    """Detect coding agents and show skill installation status."""
    with command_context("skill.inspect") as ctx:
        from confpub.skill_installer import inspect_skill
        from pathlib import Path

        root = Path.cwd()
        ctx.result = inspect_skill(root)


# ---------------------------------------------------------------------------
# Trust scoring commands
# ---------------------------------------------------------------------------


@page_app.command("score")
def page_score(
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Confluence page ID"),
    space: Optional[str] = typer.Option(None, "--space", help="Space key (or CONFPUB_SPACE)"),
    title: Optional[str] = typer.Option(None, "--title", help="Page title (with --space)"),
    profile: Optional[str] = typer.Option(None, "--profile", help="Scoring profile override"),
    doc_class: Optional[str] = typer.Option(None, "--doc-class", help="Primary class or legacy alias (governance, instruction, decision, reference, ...)"),
    explain: str = typer.Option("none", "--explain", help="Explanation verbosity: none|summary|full"),
    refresh: bool = typer.Option(False, "--refresh", help="Bypass cache, recompute from live data"),
    include_signals: bool = typer.Option(False, "--include-signals", help="Include signal breakdown"),
    include_missing: bool = typer.Option(False, "--include-missing", help="Include missing signal details"),
) -> None:
    """Score a page for operational trustworthiness."""
    space = _resolve_space(space)
    target = {"page_id": page_id, "space": space, "title": title}
    with command_context("page.score", target=target) as ctx:
        if not page_id and not (space and title):
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                "Either --page-id or both --space and --title are required",
            )
        # Validate --explain
        valid_explain = ("none", "summary", "full")
        if explain not in valid_explain:
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                f"--explain must be one of: {', '.join(valid_explain)} (got '{explain}')",
            )
        if explain == "full":
            include_signals = True
            include_missing = True
        elif explain == "summary":
            include_missing = True

        from confpub.confluence import build_client
        from confpub.trust.scoring import score_page as _score_page

        client = build_client()
        ctx.client = client
        result = _score_page(
            client,
            page_id=page_id,
            space=space,
            title=title,
            profile_name=profile,
            doc_class_override=doc_class,
            include_signals=include_signals,
            include_missing=include_missing,
            refresh=refresh,
        )
        ctx.result = result.model_dump(mode="json", exclude_none=True)


@trust_app.command("browse")
def trust_browse() -> None:
    """Browse cached trust scores interactively."""
    from confpub.trust.tui import TrustBrowserApp
    app = TrustBrowserApp()
    app.run()


@trust_cache_app.command("inspect")
def trust_cache_inspect() -> None:
    """Show trust cache statistics."""
    with command_context("trust.cache.inspect") as ctx:
        from confpub.trust.cache import open_cache

        cache = open_cache()
        try:
            ctx.result = cache.inspect()
        finally:
            cache.close()


@trust_cache_app.command("purge")
def trust_cache_purge(
    space: Optional[str] = typer.Option(None, "--space", help="Purge entries for this space"),
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Purge entries for this page"),
    older_than: Optional[int] = typer.Option(None, "--older-than", help="Purge entries older than N hours"),
    all_entries: bool = typer.Option(False, "--all", help="Purge all entries"),
) -> None:
    """Clear trust cache entries."""
    with command_context("trust.cache.purge") as ctx:
        if not any([space, page_id, older_than is not None, all_entries]):
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                "At least one filter is required: --all, --space, --page-id, or --older-than",
            )
        if older_than is not None and older_than < 0:
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                f"--older-than must be non-negative (got {older_than})",
            )
        from confpub.trust.cache import open_cache

        cache = open_cache()
        try:
            ctx.result = cache.purge(
                space=space,
                page_id=page_id,
                older_than_hours=older_than,
                purge_all=all_entries,
            )
        finally:
            cache.close()


@trust_cache_app.command("warm")
def trust_cache_warm(
    space: Optional[str] = typer.Option(None, "--space", help="Space key to warm"),
    cql: Optional[str] = typer.Option(None, "--cql", help="CQL query to select pages"),
    profile: Optional[str] = typer.Option(None, "--profile", help="Scoring profile override"),
) -> None:
    """Precompute trust scores for a space or CQL result set."""
    with command_context("trust.cache.warm", target={"space": space, "cql": cql}) as ctx:
        if not space and not cql:
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                "Either --space or --cql is required",
            )
        from confpub.confluence import build_client
        from confpub.trust.scoring import score_page as _score_page

        client = build_client()
        ctx.client = client

        # Collect page IDs
        page_ids: list[tuple[str, str]] = []  # (page_id, title)
        if space:
            space = _resolve_space(space) or space
            start = 0
            while True:
                batch = client.list_pages(space, start=start, limit=100)
                for p in batch.get("pages", []):
                    pid = str(p.get("id", ""))
                    ptitle = p.get("title", "")
                    if pid:
                        page_ids.append((pid, ptitle))
                if not batch.get("has_more"):
                    break
                start += batch.get("limit", 100)
        elif cql:
            start = 0
            while True:
                batch = client.search(cql, start=start, limit=100)
                for r in batch.get("results", []):
                    pid = str(r.get("id", ""))
                    ptitle = r.get("title", "")
                    if pid:
                        page_ids.append((pid, ptitle))
                if not batch.get("has_more"):
                    break
                start += batch.get("limit", 100)

        total = len(page_ids)
        scored = 0
        failed = 0
        emit_stderr(f"Warming {total} pages...")

        for i, (pid, ptitle) in enumerate(page_ids, 1):
            try:
                _score_page(
                    client,
                    page_id=pid,
                    profile_name=profile,
                    refresh=True,
                )
                scored += 1
            except Exception:
                failed += 1
            if i % 10 == 0 or i == total:
                emit_stderr(f"  [{i}/{total}] scored={scored} failed={failed}")

        ctx.result = {
            "total_pages": total,
            "scored": scored,
            "failed": failed,
        }


@trust_profile_app.command("inspect")
def trust_profile_inspect(
    name: Optional[str] = typer.Option(None, "--name", help="Profile name (omit for all)"),
) -> None:
    """Show scoring profile details."""
    with command_context("trust.profile.inspect") as ctx:
        from confpub.trust.profiles import get_profile, list_profiles

        if name:
            p = get_profile(name)
            ctx.result = p.model_dump(mode="json")
        else:
            profiles = list_profiles()
            ctx.result = {
                "profiles": {k: v.model_dump(mode="json") for k, v in profiles.items()},
                "default": "official-knowledge",
            }


@trust_anchor_app.command("set")
def trust_anchor_set(
    space: Optional[str] = typer.Option(None, "--space", help="Space key to anchor"),
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Page ID to anchor"),
    level: str = typer.Option(..., "--level", help="Trust level: high, good, caution, low, exclude"),
    reason: str = typer.Option("", "--reason", help="Why this anchor exists"),
    recursive: bool = typer.Option(False, "--recursive", help="Include child pages (with --page-id)"),
) -> None:
    """Declare a trust level for a space or page."""
    with command_context("trust.anchor.set", target={"space": space, "page_id": page_id}) as ctx:
        if not space and not page_id:
            raise ConfpubError("ERR_VALIDATION_REQUIRED", "Either --space or --page-id is required")
        from confpub.trust.anchors import TRUST_LEVELS, TrustAnchor, load_anchors, save_anchors
        if level not in TRUST_LEVELS:
            raise ConfpubError(
                "ERR_VALIDATION_REQUIRED",
                f"Invalid trust level '{level}'. Valid: {', '.join(TRUST_LEVELS)}",
            )
        anchors = load_anchors()
        anchor = TrustAnchor(level=level, reason=reason)
        if space:
            anchors.spaces[space] = anchor
        if page_id:
            anchors.pages[page_id] = anchor
            if recursive:
                from confpub.confluence import build_client
                client = build_client()
                ctx.client = client
                child_ids = _collect_child_pages(client, page_id)
                for cid in child_ids:
                    anchors.pages[cid] = anchor
        path = save_anchors(anchors)
        # Invalidate affected cache entries so stale anchor data doesn't persist
        try:
            from confpub.trust.cache import TrustCache
            cache = TrustCache()
            if page_id:
                cache.purge(page_id=page_id)
            elif space:
                cache.purge(space=space)
            cache.close()
        except Exception:
            pass
        ctx.result = {
            "anchor": anchor.model_dump(),
            "target": {"space": space, "page_id": page_id},
            "file": str(path),
            "level_description": TRUST_LEVELS[level]["description"],
        }


@trust_anchor_app.command("list")
def trust_anchor_list() -> None:
    """List all declared trust anchors."""
    with command_context("trust.anchor.list") as ctx:
        from confpub.trust.anchors import TRUST_LEVELS, load_anchors
        anchors = load_anchors()
        spaces = {k: {**v.model_dump(), "description": TRUST_LEVELS.get(v.level, {}).get("description", "")}
                  for k, v in anchors.spaces.items()}
        pages = {k: {**v.model_dump(), "description": TRUST_LEVELS.get(v.level, {}).get("description", "")}
                 for k, v in anchors.pages.items()}
        ctx.result = {
            "spaces": spaces,
            "pages": pages,
            "total": len(anchors.spaces) + len(anchors.pages),
        }


@trust_anchor_app.command("remove")
def trust_anchor_remove(
    space: Optional[str] = typer.Option(None, "--space", help="Space key to remove"),
    page_id: Optional[str] = typer.Option(None, "--page-id", help="Page ID to remove"),
) -> None:
    """Remove a trust anchor."""
    with command_context("trust.anchor.remove", target={"space": space, "page_id": page_id}) as ctx:
        if not space and not page_id:
            raise ConfpubError("ERR_VALIDATION_REQUIRED", "Either --space or --page-id is required")
        from confpub.trust.anchors import load_anchors, save_anchors
        anchors = load_anchors()
        removed = False
        if space and space in anchors.spaces:
            del anchors.spaces[space]
            removed = True
        if page_id and page_id in anchors.pages:
            del anchors.pages[page_id]
            removed = True
        if removed:
            save_anchors(anchors)
            # Invalidate affected cache entries
            try:
                from confpub.trust.cache import TrustCache
                cache = TrustCache()
                if page_id:
                    cache.purge(page_id=page_id)
                elif space:
                    cache.purge(space=space)
                cache.close()
            except Exception:
                pass
        ctx.result = {"removed": removed}


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
