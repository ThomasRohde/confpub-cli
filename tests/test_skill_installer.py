"""Tests for confpub.skill_installer module."""

import pytest

from confpub.skill_installer import (
    SKILL_NAME,
    detect_agents,
    install_skill,
    inspect_skill,
    _copy_skill_tree,
    _strip_marker_block,
    _read_installed_version,
    get_skill_data_path,
)
from confpub.errors import ConfpubError


@pytest.fixture
def repo(tmp_path):
    """Create a temporary repo directory."""
    return tmp_path


class TestDetectAgents:
    def test_detects_claude_from_claude_md(self, repo):
        (repo / "CLAUDE.md").write_text("# CLAUDE.md")
        agents = detect_agents(repo)
        assert len(agents) == 1
        assert agents[0].name == "claude"
        assert agents[0].detected_by == "CLAUDE.md"

    def test_detects_claude_from_dot_claude_dir(self, repo):
        (repo / ".claude").mkdir()
        agents = detect_agents(repo)
        assert len(agents) == 1
        assert agents[0].name == "claude"
        assert agents[0].detected_by == ".claude"

    def test_detects_copilot(self, repo):
        (repo / ".github").mkdir()
        (repo / ".github" / "copilot-instructions.md").write_text("# Copilot")
        agents = detect_agents(repo)
        assert len(agents) == 1
        assert agents[0].name == "copilot"

    def test_detects_cursor(self, repo):
        (repo / ".cursor" / "rules").mkdir(parents=True)
        agents = detect_agents(repo)
        assert len(agents) == 1
        assert agents[0].name == "cursor"

    def test_detects_windsurf(self, repo):
        (repo / ".windsurfrules").write_text("# Windsurf")
        agents = detect_agents(repo)
        assert len(agents) == 1
        assert agents[0].name == "windsurf"

    def test_detects_agents_md(self, repo):
        (repo / "AGENTS.md").write_text("# AGENTS")
        agents = detect_agents(repo)
        assert len(agents) == 1
        assert agents[0].name == "agents-md"

    def test_detects_multiple_agents(self, repo):
        (repo / "CLAUDE.md").write_text("# CLAUDE")
        (repo / ".github").mkdir()
        (repo / ".github" / "copilot-instructions.md").write_text("# Copilot")
        (repo / ".cursor" / "rules").mkdir(parents=True)
        agents = detect_agents(repo)
        names = {a.name for a in agents}
        assert names == {"claude", "copilot", "cursor"}

    def test_detects_nothing_in_empty_dir(self, repo):
        agents = detect_agents(repo)
        assert len(agents) == 0


class TestInstallSkill:
    def test_install_creates_skill_directory(self, repo):
        (repo / "CLAUDE.md").write_text("# CLAUDE")
        result = install_skill(repo)
        skill_dir = repo / ".claude" / "skills" / SKILL_NAME
        assert skill_dir.is_dir()
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "README.md").exists()
        assert (skill_dir / "references" / "patterns" / "adr.md").exists()
        assert result["total_files_written"] == 26  # 24 md + README

    def test_install_defaults_to_claude_when_no_agents(self, repo):
        result = install_skill(repo)
        assert result["agents"][0]["name"] == "claude"
        assert result["agents"][0]["detected_by"] == "default (no agents detected)"

    def test_install_with_agent_override(self, repo):
        result = install_skill(repo, agents=["cursor"])
        assert result["agents"][0]["name"] == "cursor"
        skill_dir = repo / ".cursor" / "skills" / SKILL_NAME
        assert skill_dir.is_dir()
        mdc = repo / ".cursor" / "rules" / f"{SKILL_NAME}.mdc"
        assert mdc.exists()

    def test_install_dry_run_writes_nothing(self, repo):
        (repo / "CLAUDE.md").write_text("# CLAUDE")
        result = install_skill(repo, dry_run=True)
        assert result["dry_run"] is True
        assert result["total_files_written"] == 26
        skill_dir = repo / ".claude" / "skills" / SKILL_NAME
        assert not skill_dir.exists()

    def test_install_conflict_raises_error(self, repo):
        (repo / "CLAUDE.md").write_text("# CLAUDE")
        install_skill(repo)
        with pytest.raises(ConfpubError) as exc_info:
            install_skill(repo)
        assert exc_info.value.code == "ERR_CONFLICT_FILE_EXISTS"

    def test_install_force_overwrites(self, repo):
        (repo / "CLAUDE.md").write_text("# CLAUDE")
        install_skill(repo)
        result = install_skill(repo, force=True)
        assert result["total_files_written"] == 26

    def test_install_appends_copilot_pointer(self, repo):
        (repo / ".github").mkdir()
        instructions = repo / ".github" / "copilot-instructions.md"
        instructions.write_text("# Existing instructions\n\nSome content.\n")
        install_skill(repo)
        content = instructions.read_text()
        assert "confpub-skill:v" in content
        assert "Confluence Publishing" in content
        assert "# Existing instructions" in content

    def test_install_copilot_force_replaces_marker(self, repo):
        (repo / ".github").mkdir()
        instructions = repo / ".github" / "copilot-instructions.md"
        instructions.write_text("# Existing\n")
        install_skill(repo)
        install_skill(repo, force=True)
        content = instructions.read_text()
        assert content.count("confpub-skill:v") == 1  # Only one marker block

    def test_install_generates_cursor_mdc(self, repo):
        (repo / ".cursor" / "rules").mkdir(parents=True)
        install_skill(repo)
        mdc = repo / ".cursor" / "rules" / f"{SKILL_NAME}.mdc"
        content = mdc.read_text()
        assert content.startswith("---\n")
        assert "description:" in content
        assert "alwaysApply: false" in content

    def test_install_invalid_agent_raises(self, repo):
        with pytest.raises(ConfpubError) as exc_info:
            install_skill(repo, agents=["unknown-agent"])
        assert "Unknown agent" in str(exc_info.value)


class TestInspectSkill:
    def test_inspect_empty_repo(self, repo):
        result = inspect_skill(repo)
        assert result["detected_agents"] == []
        assert result["skill_version"]
        assert result["skill_files"] == 25

    def test_inspect_with_agents(self, repo):
        (repo / "CLAUDE.md").write_text("# CLAUDE")
        result = inspect_skill(repo)
        assert len(result["detected_agents"]) == 1
        assert result["detected_agents"][0]["name"] == "claude"
        assert result["detected_agents"][0]["installed"] is False

    def test_inspect_after_install(self, repo):
        (repo / "CLAUDE.md").write_text("# CLAUDE")
        install_skill(repo)
        result = inspect_skill(repo)
        agent = result["detected_agents"][0]
        assert agent["installed"] is True
        assert agent["installed_version"] is not None


class TestHelpers:
    def test_skill_data_path_exists(self):
        path = get_skill_data_path()
        assert path.is_dir()
        assert (path / "SKILL.md").exists()

    def test_strip_marker_block(self):
        content = """# Header

Some content.

<!-- confpub-skill:v1.0.0 -->
## Confluence Publishing
Pointer text.
<!-- /confpub-skill -->

More content.
"""
        result = _strip_marker_block(content)
        assert "confpub-skill" not in result
        assert "# Header" in result
        assert "More content." in result

    def test_copy_skill_tree_dry_run(self, repo):
        source = get_skill_data_path()
        dest = repo / "skills"
        count = _copy_skill_tree(source, dest, dry_run=True)
        assert count > 0
        assert not dest.exists()

    def test_read_installed_version(self, repo):
        (repo / "skill").mkdir()
        (repo / "skill" / "README.md").write_text("Version: 1.11.0\n")
        assert _read_installed_version(repo / "skill") == "1.11.0"

    def test_read_installed_version_missing(self, repo):
        assert _read_installed_version(repo / "nonexistent") is None
