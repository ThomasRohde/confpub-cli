"""SQLite trust score cache.

Default path: ``~/.confpub/trust-cache.sqlite3``
Override via ``CONFPUB_CACHE_DIR`` environment variable.

Cache failures in the scoring path emit warnings but never block scoring.
Only explicit cache commands (``trust cache inspect/purge``) raise errors.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import orjson

from confpub.errors import ERR_INTERNAL_TRUST_CACHE, ConfpubError
from confpub.trust.models import ALGORITHM_VERSION, PageScoreResult

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

ENV_CACHE_DIR = "CONFPUB_CACHE_DIR"
ENV_CACHE_TTL = "CONFPUB_CACHE_TTL"
_DEFAULT_CACHE_DIR = Path.home() / ".confpub"
_DB_FILENAME = "trust-cache.sqlite3"

_SCHEMA_VERSION = 2

# TTLs in seconds — default page score TTL is 7 days
_DEFAULT_TTL_PAGE_SCORE = 604800  # 7 days
TTL_CAPABILITY = 86400  # 24 hours


def _page_score_ttl() -> int:
    """Return the page score TTL in seconds, respecting CONFPUB_CACHE_TTL."""
    env = os.environ.get(ENV_CACHE_TTL)
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    return _DEFAULT_TTL_PAGE_SCORE


TTL_PAGE_SCORE = _page_score_ttl()


def _cache_dir() -> Path:
    env = os.environ.get(ENV_CACHE_DIR)
    if env:
        return Path(env)
    return _DEFAULT_CACHE_DIR


def cache_path() -> Path:
    """Return the resolved cache database path."""
    return _cache_dir() / _DB_FILENAME


# ---------------------------------------------------------------------------
# SQL schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS page_score_cache (
    cache_key     TEXT PRIMARY KEY,
    site_url      TEXT NOT NULL,
    page_id       TEXT NOT NULL,
    title         TEXT NOT NULL DEFAULT '',
    space_key     TEXT NOT NULL DEFAULT '',
    page_version  INTEGER NOT NULL,
    algorithm_ver TEXT NOT NULL,
    profile       TEXT NOT NULL,
    doc_class     TEXT NOT NULL,
    score_json    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capability_cache (
    site_url     TEXT PRIMARY KEY,
    capabilities TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""


# ---------------------------------------------------------------------------
# TrustCache
# ---------------------------------------------------------------------------


class TrustCache:
    """Local SQLite cache for trust scores."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or cache_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()

    # -- schema ----------------------------------------------------------

    def _ensure_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(_SCHEMA_SQL)

        # Migrate from v1 → v2: add title and space_key columns
        try:
            cur.execute("SELECT title FROM page_score_cache LIMIT 0")
        except sqlite3.OperationalError:
            cur.execute("ALTER TABLE page_score_cache ADD COLUMN title TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE page_score_cache ADD COLUMN space_key TEXT NOT NULL DEFAULT ''")

        cur.execute("DELETE FROM schema_version")
        cur.execute("INSERT INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,))
        self._conn.commit()

    # -- cache key -------------------------------------------------------

    @staticmethod
    def make_cache_key(
        site_url: str,
        page_id: str,
        page_version: int,
        profile: str,
        doc_class: str,
    ) -> str:
        """Deterministic SHA-256 key from composite components."""
        raw = f"{site_url}|{page_id}|{page_version}|{ALGORITHM_VERSION}|{profile}|{doc_class}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # -- read/write ------------------------------------------------------

    def get_page_score(self, cache_key: str) -> tuple[PageScoreResult | None, bool]:
        """Look up a cached page score.

        Returns:
            ``(result, is_stale)`` — ``result`` is ``None`` on cache miss.
            ``is_stale`` is ``True`` when the entry exists but TTL has expired.
        """
        cur = self._conn.execute(
            "SELECT score_json, expires_at FROM page_score_cache WHERE cache_key = ?",
            (cache_key,),
        )
        row = cur.fetchone()
        if row is None:
            return None, False

        score_json, expires_at_str = row
        result = PageScoreResult(**orjson.loads(score_json))
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromisoformat(expires_at_str)
        is_stale = now > expires_at
        return result, is_stale

    def put_page_score(
        self,
        cache_key: str,
        result: PageScoreResult,
        *,
        site_url: str,
        page_id: str,
        title: str = "",
        space_key: str = "",
        page_version: int,
        profile: str,
        doc_class: str,
        ttl_seconds: int = TTL_PAGE_SCORE,
    ) -> None:
        """Write a page score to cache."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)
        score_json = orjson.dumps(
            result.model_dump(mode="json", exclude_none=True)
        ).decode()

        self._conn.execute(
            """INSERT OR REPLACE INTO page_score_cache
               (cache_key, site_url, page_id, title, space_key, page_version,
                algorithm_ver, profile, doc_class,
                score_json, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cache_key,
                site_url,
                page_id,
                title,
                space_key,
                page_version,
                ALGORITHM_VERSION,
                profile,
                doc_class,
                score_json,
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )
        self._conn.commit()

    # -- bulk lookup by page ID ------------------------------------------

    def get_scores_by_page_ids(
        self, page_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Look up the most recent cached score for each page ID.

        Returns a dict mapping page_id to a slim score summary:
        ``{score, band, confidence, primary_class, stale}``.
        Pages without cached scores are omitted.
        """
        if not page_ids:
            return {}

        placeholders = ",".join("?" for _ in page_ids)
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            f"""SELECT page_id, score_json, expires_at
                FROM page_score_cache
                WHERE page_id IN ({placeholders})
                ORDER BY created_at DESC""",
            page_ids,
        )
        result: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            pid, score_json, expires_at_str = row
            if pid in result:
                continue  # keep the most recent (first due to ORDER BY)
            try:
                data = orjson.loads(score_json)
                is_stale = now > expires_at_str
                advisory = data.get("advisory")
                if not advisory:
                    from confpub.trust.models import advisory_for
                    advisory = advisory_for(data.get("band", "low"), data.get("confidence", 0.0))
                result[pid] = {
                    "score": data.get("score"),
                    "band": data.get("band"),
                    "confidence": data.get("confidence"),
                    "primary_class": data.get("primary_class"),
                    "advisory": advisory,
                    "stale": is_stale,
                }
            except Exception:
                continue
        return result

    # -- full listing ----------------------------------------------------

    def get_all_scores(self) -> list[dict[str, Any]]:
        """Return all cached page scores as flat dicts for table display."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "SELECT page_id, title, space_key, page_version, profile, doc_class, "
            "score_json, created_at, expires_at "
            "FROM page_score_cache ORDER BY created_at DESC"
        )
        results: list[dict[str, Any]] = []
        for row in cur.fetchall():
            pid, title, space_key, version, profile, doc_class, score_json, created_at, expires_at = row
            try:
                data = orjson.loads(score_json)
                results.append({
                    "page_id": pid,
                    "title": title,
                    "space_key": space_key,
                    "page_version": version,
                    "profile": profile,
                    "primary_class": data.get("primary_class", doc_class),
                    "subtype": data.get("subtype"),
                    "lifecycle_state": data.get("lifecycle_state"),
                    "score": data.get("score", 0),
                    "band": data.get("band", "?"),
                    "confidence": data.get("confidence", 0.0),
                    "subscores": data.get("subscores", {}),
                    "hard_caps": data.get("hard_caps", []),
                    "signals": data.get("signals"),
                    "scored_at": data.get("scored_at", created_at),
                    "stale": now > expires_at,
                })
            except Exception:
                continue
        return results

    # -- inspect ---------------------------------------------------------

    def inspect(self) -> dict[str, Any]:
        """Return cache statistics."""
        cur = self._conn.execute("SELECT COUNT(*) FROM page_score_cache")
        entry_count = cur.fetchone()[0]

        cur = self._conn.execute(
            "SELECT MIN(created_at), MAX(created_at) FROM page_score_cache"
        )
        oldest, newest = cur.fetchone()

        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM page_score_cache WHERE expires_at < ?",
            (now,),
        )
        stale_count = cur.fetchone()[0]

        db_size = self._path.stat().st_size if self._path.exists() else 0

        return {
            "db_path": str(self._path),
            "db_size_bytes": db_size,
            "entry_count": entry_count,
            "stale_count": stale_count,
            "oldest_entry": oldest,
            "newest_entry": newest,
            "algorithm_version": ALGORITHM_VERSION,
        }

    # -- purge -----------------------------------------------------------

    def purge(
        self,
        *,
        space: str | None = None,
        page_id: str | None = None,
        older_than_hours: int | None = None,
        purge_all: bool = False,
    ) -> dict[str, Any]:
        """Delete cache entries matching the given criteria.

        Returns:
            ``{deleted_count, remaining_count}``.
        """
        if purge_all:
            cur = self._conn.execute("DELETE FROM page_score_cache")
        elif page_id:
            cur = self._conn.execute(
                "DELETE FROM page_score_cache WHERE page_id = ?", (page_id,)
            )
        elif space:
            cur = self._conn.execute(
                "DELETE FROM page_score_cache WHERE space_key = ?", (space,)
            )
        elif older_than_hours is not None:
            if older_than_hours < 0:
                older_than_hours = 0
            cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
            ).isoformat()
            cur = self._conn.execute(
                "DELETE FROM page_score_cache WHERE created_at < ?", (cutoff,)
            )
        else:
            cur = self._conn.execute("SELECT COUNT(*) FROM page_score_cache")
            return {"deleted_count": 0, "remaining_count": cur.fetchone()[0]}

        deleted = cur.rowcount
        self._conn.commit()

        cur = self._conn.execute("SELECT COUNT(*) FROM page_score_cache")
        remaining = cur.fetchone()[0]
        return {"deleted_count": deleted, "remaining_count": remaining}

    # -- lifecycle -------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


def open_cache(db_path: Path | None = None) -> TrustCache:
    """Open the trust cache, raising ``ERR_INTERNAL_TRUST_CACHE`` on failure.

    Use this for explicit cache commands where failure should be reported.
    For scoring, construct ``TrustCache`` directly and catch exceptions.
    """
    try:
        return TrustCache(db_path)
    except (sqlite3.DatabaseError, OSError) as exc:
        raise ConfpubError(
            ERR_INTERNAL_TRUST_CACHE,
            f"Failed to open trust cache: {exc}",
            details={"path": str(db_path or cache_path())},
        ) from exc
