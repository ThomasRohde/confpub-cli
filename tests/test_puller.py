"""Tests for the pull workflow orchestration."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from confpub.errors import ERR_CONFLICT_FILE_EXISTS, ERR_VALIDATION_REQUIRED, ConfpubError
from confpub.puller import _slugify, pull_pages


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(
    page_id: str,
    title: str,
    body: str = "<p>Hello</p>",
    space_key: str = "TEST",
    version: int = 1,
) -> dict:
    return {
        "id": page_id,
        "title": title,
        "space": {"key": space_key},
        "version": {"number": version},
        "body": {"storage": {"value": body}},
    }


def _mock_client(pages: dict[str, dict], children: dict[str, list] | None = None):
    """Create a mock ConfluenceClient.

    pages: {page_id: page_dict}
    children: {page_id: [child_page_dict, ...]}
    """
    client = MagicMock()
    children = children or {}

    def get_page_by_id(pid):
        return pages.get(pid, {})

    def get_page(space, title):
        for p in pages.values():
            if p.get("space", {}).get("key") == space and p.get("title") == title:
                return p
        return None

    def get_page_children_deep(pid):
        return children.get(pid, [])

    def get_attachments(pid):
        return []

    def download_attachment(pid, filename, path):
        return False

    def get_page_ancestors(pid):
        return []

    client.get_page_by_id = get_page_by_id
    client.get_page = get_page
    client.get_page_children_deep = get_page_children_deep
    client.get_attachments = get_attachments
    client.download_attachment = download_attachment
    client.get_page_ancestors = get_page_ancestors
    return client


# ---------------------------------------------------------------------------
# Slugify tests
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self):
        assert _slugify("My Cool Page") == "my-cool-page"

    def test_special_chars(self):
        assert _slugify("Hello & World!") == "hello-world"

    def test_underscores(self):
        assert _slugify("some_page_name") == "some-page-name"

    def test_multiple_spaces(self):
        assert _slugify("  lots   of   spaces  ") == "lots-of-spaces"

    def test_already_slugified(self):
        assert _slugify("already-slugified") == "already-slugified"


# ---------------------------------------------------------------------------
# Single page pull
# ---------------------------------------------------------------------------


class TestSinglePagePull:
    def test_pull_single_page_by_id(self, tmp_path):
        page = _make_page("123", "Overview", "<p>Hello world</p>")
        client = _mock_client({"123": page})

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="123",
                output_dir=str(tmp_path),
            )

        assert result["summary"]["pages_pulled"] == 1
        assert len(result["files"]) == 1
        assert result["files"][0]["page_id"] == "123"
        assert result["files"][0]["title"] == "Overview"

        # File should exist
        md_file = tmp_path / "overview.md"
        assert md_file.exists()
        content = md_file.read_text()
        assert "Hello world" in content

    def test_pull_single_page_by_space_title(self, tmp_path):
        page = _make_page("456", "Getting Started", "<h1>Welcome</h1>")
        client = _mock_client({"456": page})

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                space="TEST",
                title="Getting Started",
                output_dir=str(tmp_path),
            )

        assert result["summary"]["pages_pulled"] == 1
        md_file = tmp_path / "getting-started.md"
        assert md_file.exists()

    def test_pull_requires_page_id_or_space_title(self, tmp_path):
        with pytest.raises(ConfpubError) as exc_info:
            pull_pages(output_dir=str(tmp_path))
        assert exc_info.value.code == ERR_VALIDATION_REQUIRED


# ---------------------------------------------------------------------------
# Recursive pull
# ---------------------------------------------------------------------------


class TestRecursivePull:
    def test_recursive_pulls_children(self, tmp_path):
        root = _make_page("1", "Root Page")
        child1 = _make_page("2", "Child One", "<p>Child 1 content</p>")
        child2 = _make_page("3", "Child Two", "<p>Child 2 content</p>")

        pages = {"1": root, "2": child1, "3": child2}
        children = {"1": [child1, child2]}
        client = _mock_client(pages, children)

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="1",
                output_dir=str(tmp_path),
                recursive=True,
            )

        assert result["summary"]["pages_pulled"] == 3
        assert (tmp_path / "root-page.md").exists()
        assert (tmp_path / "child-one.md").exists()
        assert (tmp_path / "child-two.md").exists()

    def test_recursive_generates_manifest(self, tmp_path):
        root = _make_page("1", "Root Page")
        child = _make_page("2", "Child Page")

        pages = {"1": root, "2": child}
        children = {"1": [child]}
        client = _mock_client(pages, children)

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="1",
                output_dir=str(tmp_path),
                recursive=True,
                generate_manifest=True,
            )

        assert result["summary"]["manifest_generated"] is True
        assert result["manifest_file"] is not None
        manifest_path = Path(result["manifest_file"])
        assert manifest_path.exists()
        content = manifest_path.read_text()
        assert "Root Page" in content
        assert "space:" in content


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


class TestConflictDetection:
    def test_fails_on_existing_files(self, tmp_path):
        page = _make_page("1", "Existing")
        client = _mock_client({"1": page})

        # Create the file that would conflict
        (tmp_path / "existing.md").write_text("old content")

        with patch("confpub.puller.build_client", return_value=client):
            with pytest.raises(ConfpubError) as exc_info:
                pull_pages(page_id="1", output_dir=str(tmp_path))
            assert exc_info.value.code == ERR_CONFLICT_FILE_EXISTS

    def test_force_overwrites_existing_files(self, tmp_path):
        page = _make_page("1", "Existing", "<p>New content</p>")
        client = _mock_client({"1": page})

        (tmp_path / "existing.md").write_text("old content")

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="1",
                output_dir=str(tmp_path),
                force=True,
            )

        assert result["summary"]["pages_pulled"] == 1
        content = (tmp_path / "existing.md").read_text()
        assert "New content" in content


# ---------------------------------------------------------------------------
# Layout modes
# ---------------------------------------------------------------------------


class TestLayoutModes:
    def test_flat_layout(self, tmp_path):
        root = _make_page("1", "Root")
        child = _make_page("2", "Child")
        pages = {"1": root, "2": child}
        children = {"1": [child]}
        client = _mock_client(pages, children)

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="1",
                output_dir=str(tmp_path),
                recursive=True,
                layout="flat",
            )

        assert result["layout"] == "flat"
        assert (tmp_path / "root.md").exists()
        assert (tmp_path / "child.md").exists()

    def test_nested_layout(self, tmp_path):
        root = _make_page("1", "Root")
        child = _make_page("2", "Child")
        pages = {"1": root, "2": child}
        children = {"1": [child]}
        client = _mock_client(pages, children)

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="1",
                output_dir=str(tmp_path),
                recursive=True,
                layout="nested",
            )

        assert result["layout"] == "nested"
        assert (tmp_path / "root" / "index.md").exists()
        assert (tmp_path / "root" / "child" / "index.md").exists()


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


class TestAttachments:
    def test_attachments_downloaded(self, tmp_path):
        page = _make_page(
            "1", "Page",
            '<p>See image:</p><ac:image><ri:attachment ri:filename="img.png" /></ac:image>',
        )
        client = _mock_client({"1": page})

        # Mock attachments
        client.get_attachments = lambda pid: [
            {"title": "img.png", "_links": {"download": "/download/img.png"}}
        ] if pid == "1" else []

        def fake_download(pid, filename, path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            Path(path).write_bytes(b"PNG_DATA")
            return True

        client.download_attachment = fake_download

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="1",
                output_dir=str(tmp_path),
            )

        assert result["summary"]["attachments_downloaded"] == 1
        assert result["files"][0]["attachments_downloaded"] == 1
        # Attachment file should exist
        assert (tmp_path / "assets" / "page" / "img.png").exists()

    def test_attachment_paths_use_forward_slashes(self, tmp_path):
        """Markdown image refs must use forward slashes regardless of OS."""
        page = _make_page(
            "1", "My Page",
            '<ac:image><ri:attachment ri:filename="diagram.png" /></ac:image>',
        )
        client = _mock_client({"1": page})
        client.get_attachments = lambda pid: [
            {"title": "diagram.png", "_links": {"download": "/dl/diagram.png"}}
        ] if pid == "1" else []

        def fake_download(pid, filename, path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            Path(path).write_bytes(b"PNG")
            return True

        client.download_attachment = fake_download

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(page_id="1", output_dir=str(tmp_path))

        md_content = (tmp_path / "my-page.md").read_text()
        # Must contain forward-slash path, never backslash
        assert "assets/my-page/diagram.png" in md_content
        assert "\\" not in md_content.split("assets")[1].split(")")[0]

    def test_failed_download_produces_warning(self, tmp_path):
        """A single failing attachment should not abort the pull."""
        page = _make_page("1", "Page")
        client = _mock_client({"1": page})
        client.get_attachments = lambda pid: [
            {"title": "good.png", "_links": {"download": "/dl/good.png"}},
            {"title": "bad.png", "_links": {"download": "/dl/bad.png"}},
        ] if pid == "1" else []

        def selective_download(pid, filename, path):
            if filename == "bad.png":
                return False  # simulate failure
            os.makedirs(os.path.dirname(path), exist_ok=True)
            Path(path).write_bytes(b"OK")
            return True

        client.download_attachment = selective_download

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(page_id="1", output_dir=str(tmp_path))

        assert result["summary"]["attachments_downloaded"] == 1
        assert len(result["warnings"]) == 1
        assert "bad.png" in result["warnings"][0]

    def test_no_attachments_flag(self, tmp_path):
        page = _make_page("1", "Page")
        client = _mock_client({"1": page})
        client.get_attachments = MagicMock(return_value=[])

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="1",
                output_dir=str(tmp_path),
                include_attachments=False,
            )

        assert result["summary"]["attachments_downloaded"] == 0
        # get_attachments should not have been called
        client.get_attachments.assert_not_called()


# ---------------------------------------------------------------------------
# Lockfile
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Data Center compatibility
# ---------------------------------------------------------------------------


class TestDataCenterCompat:
    """Ensure pull works for Confluence Data Center deployment patterns."""

    def test_pull_by_space_title_has_space_key(self, tmp_path):
        """get_page by space+title must produce the space key for manifest generation."""
        page = _make_page("1", "Root", space_key="PROJ")
        child = _make_page("2", "Child")
        pages = {"1": page, "2": child}
        children = {"1": [child]}
        client = _mock_client(pages, children)

        # get_page looks up by space+title, so wire it to return the page
        def get_page(space, title):
            if space == "PROJ" and title == "Root":
                return page
            return None

        client.get_page = get_page

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                space="PROJ", title="Root",
                output_dir=str(tmp_path), recursive=True,
                generate_manifest=True,
            )

        assert result["summary"]["pages_pulled"] == 2
        manifest_path = tmp_path / "confpub.yaml"
        assert manifest_path.exists()
        content = manifest_path.read_text()
        assert "space: PROJ" in content

    def test_pull_page_without_space_expansion_falls_back(self, tmp_path):
        """If the page response lacks space.key, the CLI --space arg is used."""
        page = {"id": "99", "title": "Legacy", "version": {"number": 1},
                "body": {"storage": {"value": "<p>hi</p>"}}}
        client = _mock_client({"99": page})

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="99", output_dir=str(tmp_path),
            )

        assert result["summary"]["pages_pulled"] == 1


# ---------------------------------------------------------------------------
# Lockfile
# ---------------------------------------------------------------------------


class TestLockfile:
    def test_lockfile_created(self, tmp_path):
        page = _make_page("1", "Test Page", version=3)
        client = _mock_client({"1": page})

        with patch("confpub.puller.build_client", return_value=client):
            pull_pages(page_id="1", output_dir=str(tmp_path))

        lockfile_path = tmp_path / "confpub.lock"
        assert lockfile_path.exists()
        data = json.loads(lockfile_path.read_text())
        assert "Test Page" in data["pages"]
        assert data["pages"]["Test Page"]["page_id"] == "1"
        assert data["pages"]["Test Page"]["version"] == 3


# ---------------------------------------------------------------------------
# Multi-level recursive pull (Bug 1 verification)
# ---------------------------------------------------------------------------


class TestMultiLevelRecursivePull:
    def test_three_level_tree(self, tmp_path):
        """Verify that recursive pull collects grandchildren (3-level tree)."""
        root = _make_page("1", "Root")
        child = _make_page("2", "Child")
        grandchild = _make_page("3", "Grandchild", "<p>Deep content</p>")

        pages = {"1": root, "2": child, "3": grandchild}
        children = {"1": [child], "2": [grandchild]}
        client = _mock_client(pages, children)

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="1",
                output_dir=str(tmp_path),
                recursive=True,
            )

        assert result["summary"]["pages_pulled"] == 3
        assert (tmp_path / "root.md").exists()
        assert (tmp_path / "child.md").exists()
        assert (tmp_path / "grandchild.md").exists()
        gc_content = (tmp_path / "grandchild.md").read_text()
        assert "Deep content" in gc_content

    def test_page_id_recursive_combination(self, tmp_path):
        """--page-id + --recursive should collect the full subtree."""
        root = _make_page("10", "Project")
        child1 = _make_page("20", "Sub A")
        child2 = _make_page("30", "Sub B")

        pages = {"10": root, "20": child1, "30": child2}
        children = {"10": [child1, child2]}
        client = _mock_client(pages, children)

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="10",
                output_dir=str(tmp_path),
                recursive=True,
            )

        assert result["summary"]["pages_pulled"] == 3
        titles = {f["title"] for f in result["files"]}
        assert titles == {"Project", "Sub A", "Sub B"}


# ---------------------------------------------------------------------------
# Manifest generation flag (Issue 9 verification)
# ---------------------------------------------------------------------------


class TestManifestPathSeparators:
    """Bug 1: Manifest file paths must use forward slashes on all platforms."""

    def test_manifest_paths_no_backslashes(self, tmp_path):
        root = _make_page("1", "Root")
        child = _make_page("2", "Child")
        pages = {"1": root, "2": child}
        children = {"1": [child]}
        client = _mock_client(pages, children)

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="1",
                output_dir=str(tmp_path),
                recursive=True,
                layout="nested",
                generate_manifest=True,
            )

        manifest_content = Path(result["manifest_file"]).read_text()
        # No backslashes should appear in any file paths in the manifest
        for line in manifest_content.split("\n"):
            if "file:" in line:
                assert "\\" not in line, f"Backslash found in manifest path: {line}"


class TestNestedLayoutNoAutoManifest:
    """Bug 4: --layout nested without --manifest should NOT create confpub.yaml."""

    def test_nested_without_manifest_flag(self, tmp_path):
        root = _make_page("1", "Root")
        child = _make_page("2", "Child")
        pages = {"1": root, "2": child}
        children = {"1": [child]}
        client = _mock_client(pages, children)

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="1",
                output_dir=str(tmp_path),
                recursive=True,
                layout="nested",
                generate_manifest=False,
            )

        assert result["summary"]["manifest_generated"] is False
        assert result["manifest_file"] is None
        assert not (tmp_path / "confpub.yaml").exists()


class TestManifestFlag:
    def test_single_page_with_manifest_flag(self, tmp_path):
        """--manifest generates confpub.yaml even for a single page."""
        page = _make_page("1", "Solo Page")
        client = _mock_client({"1": page})

        with patch("confpub.puller.build_client", return_value=client):
            result = pull_pages(
                page_id="1",
                output_dir=str(tmp_path),
                generate_manifest=True,
            )

        assert result["summary"]["manifest_generated"] is True
        assert result["manifest_file"] is not None
        manifest = Path(result["manifest_file"])
        assert manifest.exists()
        content = manifest.read_text()
        assert "Solo Page" in content
