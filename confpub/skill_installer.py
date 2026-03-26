"""Skill installer — detect coding agents in a repo and install the confpub publishing skill."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from confpub import __version__
from confpub.errors import ConfpubError, ERR_CONFLICT_FILE_EXISTS, ERR_VALIDATION_REQUIRED

SKILL_NAME = "confpub-publishing"
MARKER_START = "<!-- confpub-skill:v"
MARKER_END = "<!-- /confpub-skill -->"

VALID_AGENTS = ("claude", "copilot", "cursor", "windsurf", "agents-md")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AgentInfo:
    name: str
    detected_by: str
    skill_dir: str  # relative to repo root
    entry_file: str | None = None  # file to append to, if any


@dataclass
class InstallAgentResult:
    name: str
    detected_by: str
    skill_dir: str
    files_written: int = 0
    entry_file: str | None = None
    action: str = "installed"  # installed | skipped | updated


# ---------------------------------------------------------------------------
# Agent detection
# ---------------------------------------------------------------------------

_DETECTION_RULES: list[tuple[str, list[str], str, str | None]] = [
    # (agent_name, detection_paths, skill_dir, entry_file)
    ("claude", [".claude", "CLAUDE.md"], f".claude/skills/{SKILL_NAME}", None),
    ("copilot", [".github/copilot-instructions.md"], f".github/skills/{SKILL_NAME}", ".github/copilot-instructions.md"),
    ("cursor", [".cursor/rules", ".cursorrules"], f".cursor/skills/{SKILL_NAME}", f".cursor/rules/{SKILL_NAME}.mdc"),
    ("windsurf", [".windsurfrules", ".windsurf"], f".windsurf/skills/{SKILL_NAME}", ".windsurfrules"),
    ("agents-md", ["AGENTS.md"], f".agents/skills/{SKILL_NAME}", "AGENTS.md"),
]


def detect_agents(root: Path) -> list[AgentInfo]:
    """Scan a directory for coding agent customizations."""
    found: list[AgentInfo] = []
    for agent_name, paths, skill_dir, entry_file in _DETECTION_RULES:
        for p in paths:
            if (root / p).exists():
                found.append(AgentInfo(
                    name=agent_name,
                    detected_by=p,
                    skill_dir=skill_dir,
                    entry_file=entry_file,
                ))
                break
    return found


def _agent_info_for(name: str) -> AgentInfo:
    """Build AgentInfo for a named agent (when using --agent override)."""
    for agent_name, paths, skill_dir, entry_file in _DETECTION_RULES:
        if agent_name == name:
            return AgentInfo(
                name=agent_name,
                detected_by="--agent flag",
                skill_dir=skill_dir,
                entry_file=entry_file,
            )
    raise ConfpubError(
        ERR_VALIDATION_REQUIRED,
        f"Unknown agent: {name!r}. Valid agents: {', '.join(VALID_AGENTS)}",
    )


# ---------------------------------------------------------------------------
# Skill data location
# ---------------------------------------------------------------------------


def get_skill_data_path() -> Path:
    """Return the path to the bundled skill_data directory."""
    return Path(__file__).parent / "skill_data"


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def install_skill(
    root: Path,
    agents: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install the confpub skill for detected (or specified) agents."""
    source = get_skill_data_path()
    if not source.is_dir():
        raise ConfpubError(ERR_VALIDATION_REQUIRED, f"Skill data not found at {source}")

    # Resolve agents
    if agents:
        agent_list = [_agent_info_for(a) for a in agents]
    else:
        agent_list = detect_agents(root)

    if not agent_list:
        # Default to Claude Code format
        agent_list = [AgentInfo(
            name="claude",
            detected_by="default (no agents detected)",
            skill_dir=f".claude/skills/{SKILL_NAME}",
            entry_file=None,
        )]

    results: list[dict[str, Any]] = []
    total_files = 0

    for agent in agent_list:
        dest = root / agent.skill_dir

        # Conflict check
        if dest.is_dir() and (dest / "SKILL.md").exists() and not force:
            raise ConfpubError(
                ERR_CONFLICT_FILE_EXISTS,
                f"Skill already installed at {agent.skill_dir}. Use --force to overwrite.",
                details={"agent": agent.name, "skill_dir": agent.skill_dir},
            )

        # Copy skill tree
        file_count = _copy_skill_tree(source, dest, dry_run)

        # Generate README
        if not dry_run:
            _generate_readme(dest, agent.name)

        file_count += 1  # README

        # Agent-specific entry point
        entry_written = None
        if agent.entry_file:
            entry_path = root / agent.entry_file
            if agent.name == "cursor":
                entry_written = _write_cursor_mdc(source, entry_path, force, dry_run)
            else:
                entry_written = _append_pointer_block(entry_path, agent.name, force, dry_run)

        results.append({
            "name": agent.name,
            "detected_by": agent.detected_by,
            "skill_dir": agent.skill_dir,
            "files_written": file_count,
            "entry_file": agent.entry_file if entry_written else None,
        })
        total_files += file_count

    return {
        "dry_run": dry_run,
        "agents": results,
        "total_files_written": total_files,
        "version": __version__,
    }


def inspect_skill(root: Path) -> dict[str, Any]:
    """Inspect a directory for agent customizations and existing skill installations."""
    agents = detect_agents(root)
    source = get_skill_data_path()
    skill_files = sum(1 for _ in source.rglob("*.md")) if source.is_dir() else 0

    detected: list[dict[str, Any]] = []
    for agent in agents:
        dest = root / agent.skill_dir
        installed = (dest / "SKILL.md").exists()
        installed_version = None
        if installed:
            installed_version = _read_installed_version(dest)
        detected.append({
            "name": agent.name,
            "detected_by": agent.detected_by,
            "installed": installed,
            "installed_version": installed_version,
        })

    return {
        "detected_agents": detected,
        "skill_version": __version__,
        "skill_files": skill_files,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _copy_skill_tree(source: Path, dest: Path, dry_run: bool) -> int:
    """Copy skill files from source to dest. Returns file count."""
    files: list[Path] = [f for f in source.rglob("*") if f.is_file() and f.name != "__init__.py"]
    if dry_run:
        return len(files)

    if dest.exists():
        shutil.rmtree(dest)
    for f in files:
        rel = f.relative_to(source)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
    return len(files)


def _generate_readme(dest: Path, agent_name: str) -> None:
    """Write a README.md in the installed skill directory."""
    content = f"""# confpub Publishing Skill

Installed by [confpub-cli](https://github.com/ThomasRohde/confpub-cli) v{__version__}.

## What This Is

Templates, syntax guides, and design patterns for creating professional
Confluence pages using the confpub CLI. Covers 14 enterprise document types
(ADR, RFC, runbook, sprint status, post-mortem, etc.), Confluence-specific
Markdown extensions, visual design with layouts and HTML macros, and
publishing workflows.

## Contents

- `SKILL.md` — Core skill definition (start here)
- `references/` — Syntax, design, and workflow guides
- `references/patterns/` — 14 document templates

## Usage

Your coding agent ({agent_name}) uses this skill when you ask about
Confluence publishing, documentation, or confpub.

## Updating

```bash
confpub skill install --force
```

---
Installed: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
Agent: {agent_name}
Version: {__version__}
"""
    (dest / "README.md").write_text(content, encoding="utf-8")


def _append_pointer_block(file: Path, agent_name: str, force: bool, dry_run: bool) -> bool:
    """Append a pointer block to an agent's entry file."""
    marker_start = f"{MARKER_START}{__version__} -->"
    block = f"""
{marker_start}
## Confluence Publishing (confpub)

When working with Confluence publishing, documentation templates, or the confpub CLI,
read the skill at `./{_skill_dir_for(agent_name)}/SKILL.md` for complete guidance
including templates, syntax reference, and design patterns.
{MARKER_END}
"""

    if not file.exists():
        if dry_run:
            return True
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(block.lstrip(), encoding="utf-8")
        return True

    content = file.read_text(encoding="utf-8")
    if MARKER_START in content:
        if not force:
            return False  # already installed, don't error — just skip
        content = _strip_marker_block(content)

    if dry_run:
        return True

    with open(file, "w", encoding="utf-8") as f:
        f.write(content.rstrip() + "\n" + block)
    return True


def _write_cursor_mdc(source: Path, mdc_path: Path, force: bool, dry_run: bool) -> bool:
    """Generate a Cursor .mdc rule file."""
    skill_md = (source / "SKILL.md").read_text(encoding="utf-8")

    # Extract description from YAML frontmatter
    description = "Create and publish professional Confluence pages using confpub CLI"
    if "description:" in skill_md:
        for line in skill_md.split("\n"):
            if line.strip().startswith("description:"):
                description = line.split(":", 1)[1].strip()
                break

    # Strip the original YAML frontmatter
    body = skill_md
    if body.startswith("---"):
        end = body.find("---", 3)
        if end != -1:
            body = body[end + 3:].lstrip()

    # Cursor frontmatter
    mdc_content = f"""---
description: "{description[:200]}"
globs: ["**/*.md", "**/confpub.yaml", "**/confpub.lock"]
alwaysApply: false
---

{body}"""

    if mdc_path.exists() and not force:
        return False

    if dry_run:
        return True

    mdc_path.parent.mkdir(parents=True, exist_ok=True)
    mdc_path.write_text(mdc_content, encoding="utf-8")
    return True


def _strip_marker_block(content: str) -> str:
    """Remove the confpub-skill marker block from file content."""
    lines = content.split("\n")
    result: list[str] = []
    inside = False
    for line in lines:
        if MARKER_START in line:
            inside = True
            continue
        if inside and MARKER_END in line:
            inside = False
            continue
        if not inside:
            result.append(line)
    return "\n".join(result)


def _skill_dir_for(agent_name: str) -> str:
    """Return the skill directory path for a given agent."""
    for name, _, skill_dir, _ in _DETECTION_RULES:
        if name == agent_name:
            return skill_dir
    return f".claude/skills/{SKILL_NAME}"


def _read_installed_version(dest: Path) -> str | None:
    """Try to read the version from an installed skill's README."""
    readme = dest / "README.md"
    if not readme.exists():
        return None
    content = readme.read_text(encoding="utf-8")
    for line in content.split("\n"):
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return None
