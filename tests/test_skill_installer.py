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


class TestInstalledSkillContent:
    def _installed_skill_dir(self, repo):
        (repo / "CLAUDE.md").write_text("# CLAUDE")
        install_skill(repo)
        return repo / ".claude" / "skills" / SKILL_NAME

    def test_cloud_html_macro_guidance_installed(self, repo):
        skill_dir = self._installed_skill_dir(repo)

        skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        html_ref = (skill_dir / "references" / "syntax-html-macro.md").read_text(encoding="utf-8")

        assert "Marketplace app" in skill_md
        assert "html-macro" in skill_md
        assert "macro-html" in skill_md
        assert "CONFPUB_HTML_MACRO_NAME" in skill_md
        assert "forge-adf-extension" in skill_md
        assert "ac:adf-extension" in skill_md

        assert "Cloud vs. Server/DC Macro Names" in html_ref
        assert "html-macro` or `macro-html" in html_ref
        assert "Cloud Forge app" in html_ref
        assert "confpub page publish page.md --html-macro-name macro-html" in html_ref
        assert "--html-macro-format forge-adf-extension" in html_ref
        assert "confpub page inspect --page-id PAGE_ID --raw" in html_ref
        assert '<ac:structured-macro ac:name="...">' in html_ref
        assert '<ac:adf-extension>' in html_ref
        assert "guest-params" in html_ref
        assert "__body-content" in html_ref
        assert "confpub config set html_macro_name macro-html" in html_ref
        assert "confpub config set html_macro_format forge-adf-extension" in html_ref
        assert "html_macro_forge_extension_key" in html_ref
        assert "html_macro_forge_extension_id" in html_ref
        assert "html_macro_forge_cloud_id" in html_ref
        assert "html_macro_forge_context_ids" in html_ref
        assert "html_macro_forge_account_id" in html_ref
        assert "CONFPUB_HTML_MACRO_NAME=macro-html" in html_ref
        assert "body.view" in html_ref
        assert "browser rendered view" in html_ref

    def test_cloud_sandbox_and_widget_guidance_installed(self, repo):
        skill_dir = self._installed_skill_dir(repo)

        html_ref = (skill_dir / "references" / "syntax-html-macro.md").read_text(encoding="utf-8")
        styling_ref = (skill_dir / "references" / "design-styling.md").read_text(encoding="utf-8")

        assert "sandboxed iframe" in html_ref
        assert "fetch()" in html_ref
        assert "CORS" in html_ref
        assert "Data as JavaScript callback" in html_ref

        assert "Attachment-Backed Interactive Widget for Cloud" in styling_ref
        assert "window.__widgetDataReady" in styling_ref
        assert "data-confpub-data" in styling_ref
        assert "dataLink ? dataLink.href" in styling_ref
        assert "script.src = dataLink" in styling_ref
        assert "Data source:" in styling_ref
        assert "Last action:" in styling_ref
        assert "delegated" in styling_ref

    def test_layout_links_and_power_shell_guidance_installed(self, repo):
        skill_dir = self._installed_skill_dir(repo)

        layouts_ref = (skill_dir / "references" / "layouts.md").read_text(encoding="utf-8")
        macros_ref = (skill_dir / "references" / "syntax-macros.md").read_text(encoding="utf-8")
        workflow_ref = (skill_dir / "references" / "workflow.md").read_text(encoding="utf-8")

        assert "Avoid placing `::: panel` directly inside `::: cell`" in layouts_ref
        assert "leak literal `:::` markers" in layouts_ref
        assert "### Quick links" in layouts_ref

        assert "Cloud Page Link Caveats" in macros_ref
        assert "apostrophes" in macros_ref
        assert "literal Markdown" in macros_ref
        assert "https://example.atlassian.net/wiki/spaces/~username/overview" in macros_ref

        assert "Personal Spaces and PowerShell" in workflow_ref
        assert '$env:CONFPUB_SPACE = "~username"' in workflow_ref
        assert "Cloud Rendering Verification" in workflow_ref
        assert "unknown-macro?name=..." in workflow_ref
        assert "literal `:::` markers" in workflow_ref
        assert "Storage being valid is not enough" in workflow_ref


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
