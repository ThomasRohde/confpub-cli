"""Tests for the SQLite trust cache."""

import time

import pytest

from confpub.trust.cache import TrustCache
from confpub.trust.models import PageScoreResult


def _sample_result(**overrides) -> PageScoreResult:
    defaults = {
        "profile": "official-knowledge",
        "primary_class": "governance",
        "score": 75,
        "band": "good",
        "confidence": 0.85,
        "subscores": {
            "stewardship": 0.8,
            "freshness": 0.7,
            "evidence": 0.6,
            "structure": 0.5,
            "corroboration": 0.0,
        },
        "page_version": 3,
        "scored_at": "2026-03-26T12:00:00Z",
    }
    defaults.update(overrides)
    return PageScoreResult(**defaults)


class TestCacheMiss:
    def test_empty_cache_returns_none(self, tmp_path):
        cache = TrustCache(tmp_path / "test.db")
        result, stale = cache.get_page_score("nonexistent")
        assert result is None
        assert stale is False
        cache.close()


class TestCacheRoundTrip:
    def test_put_and_get(self, tmp_path):
        cache = TrustCache(tmp_path / "test.db")
        key = TrustCache.make_cache_key("https://x.atlassian.net", "123", 5, "official-knowledge", "standard")
        result = _sample_result(score=81)

        cache.put_page_score(
            key, result,
            site_url="https://x.atlassian.net",
            page_id="123", page_version=5,
            profile="official-knowledge", doc_class="standard",
        )

        cached, stale = cache.get_page_score(key)
        assert cached is not None
        assert cached.score == 81
        assert cached.band == "good"
        assert stale is False
        cache.close()

    def test_stale_entry(self, tmp_path):
        cache = TrustCache(tmp_path / "test.db")
        key = "stale-key"
        result = _sample_result()

        cache.put_page_score(
            key, result,
            site_url="https://x.atlassian.net",
            page_id="456", page_version=1,
            profile="official-knowledge", doc_class="standard",
            ttl_seconds=0,  # immediately stale
        )

        cached, stale = cache.get_page_score(key)
        assert cached is not None
        assert stale is True
        cache.close()


class TestCacheKey:
    def test_deterministic(self):
        k1 = TrustCache.make_cache_key("https://x.net", "123", 5, "official-knowledge", "standard")
        k2 = TrustCache.make_cache_key("https://x.net", "123", 5, "official-knowledge", "standard")
        assert k1 == k2

    def test_varies_with_version(self):
        k1 = TrustCache.make_cache_key("https://x.net", "123", 5, "official-knowledge", "standard")
        k2 = TrustCache.make_cache_key("https://x.net", "123", 6, "official-knowledge", "standard")
        assert k1 != k2

    def test_varies_with_profile(self):
        k1 = TrustCache.make_cache_key("https://x.net", "123", 5, "official-knowledge", "standard")
        k2 = TrustCache.make_cache_key("https://x.net", "123", 5, "working-area", "standard")
        assert k1 != k2

    def test_varies_with_doc_class(self):
        k1 = TrustCache.make_cache_key("https://x.net", "123", 5, "official-knowledge", "standard")
        k2 = TrustCache.make_cache_key("https://x.net", "123", 5, "official-knowledge", "runbook")
        assert k1 != k2


class TestInspect:
    def test_empty_cache_stats(self, tmp_path):
        cache = TrustCache(tmp_path / "test.db")
        stats = cache.inspect()
        assert stats["entry_count"] == 0
        assert stats["stale_count"] == 0
        cache.close()

    def test_stats_after_insert(self, tmp_path):
        cache = TrustCache(tmp_path / "test.db")
        for i in range(3):
            cache.put_page_score(
                f"key-{i}", _sample_result(score=50 + i),
                site_url="https://x.net", page_id=str(i),
                page_version=1, profile="official-knowledge", doc_class="standard",
            )
        stats = cache.inspect()
        assert stats["entry_count"] == 3
        cache.close()


class TestPurge:
    def test_purge_all(self, tmp_path):
        cache = TrustCache(tmp_path / "test.db")
        for i in range(5):
            cache.put_page_score(
                f"key-{i}", _sample_result(),
                site_url="https://x.net", page_id=str(i),
                page_version=1, profile="official-knowledge", doc_class="standard",
            )
        result = cache.purge(purge_all=True)
        assert result["deleted_count"] == 5
        assert result["remaining_count"] == 0
        cache.close()

    def test_purge_by_page_id(self, tmp_path):
        cache = TrustCache(tmp_path / "test.db")
        cache.put_page_score(
            "key-a", _sample_result(),
            site_url="https://x.net", page_id="111",
            page_version=1, profile="official-knowledge", doc_class="standard",
        )
        cache.put_page_score(
            "key-b", _sample_result(),
            site_url="https://x.net", page_id="222",
            page_version=1, profile="official-knowledge", doc_class="standard",
        )
        result = cache.purge(page_id="111")
        assert result["deleted_count"] == 1
        assert result["remaining_count"] == 1
        cache.close()

    def test_purge_no_criteria(self, tmp_path):
        cache = TrustCache(tmp_path / "test.db")
        cache.put_page_score(
            "key-a", _sample_result(),
            site_url="https://x.net", page_id="111",
            page_version=1, profile="official-knowledge", doc_class="standard",
        )
        result = cache.purge()
        assert result["deleted_count"] == 0
        assert result["remaining_count"] == 1
        cache.close()


class TestSchemaCreation:
    def test_fresh_db_has_tables(self, tmp_path):
        cache = TrustCache(tmp_path / "test.db")
        # Verify tables exist by running queries
        cache._conn.execute("SELECT COUNT(*) FROM page_score_cache")
        cache._conn.execute("SELECT COUNT(*) FROM capability_cache")
        cache._conn.execute("SELECT version FROM schema_version")
        cache.close()
