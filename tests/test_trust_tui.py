"""Tests for trust browser TUI helpers."""

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable

from confpub.trust.tui import _score_entry_row_key


def _entry(**overrides):
    defaults = {
        "cache_key": "",
        "page_id": "111",
        "page_version": 1,
        "profile": "official-knowledge",
        "doc_class": "standard",
        "primary_class": "standard",
    }
    defaults.update(overrides)
    return defaults


class TestScoreEntryRowKey:
    def test_uses_cache_key_when_present(self):
        assert _score_entry_row_key(_entry(cache_key="cache-1"), 0) == "cache-1"

    def test_fallback_disambiguates_duplicate_page_ids(self):
        first = _score_entry_row_key(_entry(page_version=1), 0)
        second = _score_entry_row_key(_entry(page_version=2), 1)

        assert first != second

    @pytest.mark.asyncio
    async def test_textual_datatable_accepts_duplicate_page_ids_with_row_keys(self):
        class TableApp(App):
            def compose(self) -> ComposeResult:
                yield DataTable(id="table")

        app = TableApp()
        entries = [
            _entry(cache_key="cache-1", page_version=1),
            _entry(cache_key="cache-2", page_version=2),
        ]

        async with app.run_test():
            table = app.query_one("#table", DataTable)
            table.add_columns("Page ID")
            for idx, entry in enumerate(entries):
                table.add_row(entry["page_id"], key=_score_entry_row_key(entry, idx))

            assert table.row_count == 2
