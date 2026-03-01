"""Tests for confpub.lockfile module."""

import json

import pytest

from confpub.lockfile import (
    LockPageEntry,
    Lockfile,
    load_lockfile,
    remove_from_lockfile,
    save_lockfile,
    update_lockfile,
)


class TestLockfileModel:
    def test_basic_model(self):
        lf = Lockfile(pages={
            "Overview": LockPageEntry(page_id="123", version=5),
        })
        assert lf.pages["Overview"].page_id == "123"
        assert lf.pages["Overview"].version == 5


class TestLoadLockfile:
    def test_load_existing(self, tmp_path):
        f = tmp_path / "confpub.lock"
        f.write_text(json.dumps({
            "schema_version": "1.0",
            "last_updated": "2026-02-28T14:35:00Z",
            "pages": {
                "Overview": {"page_id": "123", "version": 5},
                "Design": {"page_id": "456", "version": 1},
            },
        }))
        lf = load_lockfile(f)
        assert lf is not None
        assert lf.pages["Overview"].page_id == "123"
        assert lf.pages["Design"].version == 1

    def test_load_nonexistent(self, tmp_path):
        lf = load_lockfile(tmp_path / "missing.lock")
        assert lf is None

    def test_load_invalid_json(self, tmp_path):
        f = tmp_path / "bad.lock"
        f.write_text("not valid json{{{")
        lf = load_lockfile(f)
        assert lf is None


class TestSaveLockfile:
    def test_save_and_reload(self, tmp_path):
        path = tmp_path / "confpub.lock"
        lf = Lockfile(pages={
            "Test": LockPageEntry(page_id="789", version=3),
        })
        save_lockfile(path, lf)

        # Verify file exists and contains correct data
        data = json.loads(path.read_text())
        assert data["pages"]["Test"]["page_id"] == "789"
        assert data["pages"]["Test"]["version"] == 3
        assert "last_updated" in data

    def test_atomic_write(self, tmp_path):
        """Verify no temp files remain after successful write."""
        path = tmp_path / "confpub.lock"
        lf = Lockfile(pages={"A": LockPageEntry(page_id="1", version=1)})
        save_lockfile(path, lf)

        # Only the lock file should exist
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "confpub.lock"

    def test_overwrite_existing(self, tmp_path):
        path = tmp_path / "confpub.lock"
        lf1 = Lockfile(pages={"A": LockPageEntry(page_id="1", version=1)})
        save_lockfile(path, lf1)

        lf2 = Lockfile(pages={"B": LockPageEntry(page_id="2", version=2)})
        save_lockfile(path, lf2)

        loaded = load_lockfile(path)
        assert loaded is not None
        assert "B" in loaded.pages
        assert "A" not in loaded.pages


class TestUpdateLockfile:
    def test_add_new_page(self):
        lf = Lockfile()
        update_lockfile(lf, "New Page", "999", 1)
        assert lf.pages["New Page"].page_id == "999"
        assert lf.pages["New Page"].version == 1

    def test_update_existing_page(self):
        lf = Lockfile(pages={
            "Existing": LockPageEntry(page_id="100", version=1),
        })
        update_lockfile(lf, "Existing", "100", 2)
        assert lf.pages["Existing"].version == 2

    def test_preserves_other_pages(self):
        lf = Lockfile(pages={
            "A": LockPageEntry(page_id="1", version=1),
            "B": LockPageEntry(page_id="2", version=1),
        })
        update_lockfile(lf, "A", "1", 2)
        assert lf.pages["B"].page_id == "2"
        assert lf.pages["B"].version == 1


class TestRemoveFromLockfile:
    def test_remove_existing_entry(self):
        lf = Lockfile(pages={
            "A": LockPageEntry(page_id="1", version=1),
            "B": LockPageEntry(page_id="2", version=2),
        })
        result = remove_from_lockfile(lf, "A")
        assert result is True
        assert "A" not in lf.pages
        assert "B" in lf.pages

    def test_remove_nonexistent_entry(self):
        lf = Lockfile(pages={
            "A": LockPageEntry(page_id="1", version=1),
        })
        result = remove_from_lockfile(lf, "Missing")
        assert result is False
        assert "A" in lf.pages

    def test_remove_from_empty_lockfile(self):
        lf = Lockfile()
        result = remove_from_lockfile(lf, "Anything")
        assert result is False

    def test_remove_all_entries(self):
        lf = Lockfile(pages={
            "A": LockPageEntry(page_id="1", version=1),
        })
        remove_from_lockfile(lf, "A")
        assert len(lf.pages) == 0
