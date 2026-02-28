"""confpub.lock — page ID persistence for idempotent re-publishing.

The lockfile maps page titles to Confluence page IDs and versions.
It uses atomic writes (tempfile + os.rename) to prevent corruption.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class LockPageEntry(BaseModel):
    """A single page entry in the lockfile."""

    page_id: str
    version: int = 1


class Lockfile(BaseModel):
    """The confpub.lock model."""

    schema_version: str = "1.0"
    last_updated: str = ""
    pages: dict[str, LockPageEntry] = Field(default_factory=dict)


def load_lockfile(path: str | Path) -> Lockfile | None:
    """Load the lockfile if it exists. Returns None if not found."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        # Convert raw page dicts to LockPageEntry
        pages = {}
        for title, entry in data.get("pages", {}).items():
            if isinstance(entry, dict):
                pages[title] = LockPageEntry(**entry)
        return Lockfile(
            schema_version=data.get("schema_version", "1.0"),
            last_updated=data.get("last_updated", ""),
            pages=pages,
        )
    except Exception:
        return None


def save_lockfile(path: str | Path, lockfile: Lockfile) -> None:
    """Atomically write the lockfile using tempfile + os.rename."""
    p = Path(path)
    lockfile.last_updated = datetime.now(timezone.utc).isoformat()

    data = {
        "schema_version": lockfile.schema_version,
        "last_updated": lockfile.last_updated,
        "pages": {
            title: entry.model_dump() for title, entry in lockfile.pages.items()
        },
    }
    content = json.dumps(data, indent=2)

    # Atomic write: write to temp file in same dir, then rename
    dir_path = p.parent
    dir_path.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmp_path, str(p))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def update_lockfile(
    lockfile: Lockfile, title: str, page_id: str, version: int,
) -> Lockfile:
    """Update a page entry in the lockfile."""
    lockfile.pages[title] = LockPageEntry(page_id=page_id, version=version)
    return lockfile
