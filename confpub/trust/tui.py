"""Textual TUI for browsing cached trust scores."""

from __future__ import annotations

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static
from rich.text import Text


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

BAND_COLORS = {
    "high": "green",
    "good": "cyan",
    "caution": "yellow",
    "low": "red",
}


def _colored_score(score: int, band: str) -> Text:
    color = BAND_COLORS.get(band, "white")
    return Text(str(score), style=f"bold {color}")


def _colored_band(band: str) -> Text:
    color = BAND_COLORS.get(band, "white")
    return Text(band, style=color)


def _format_signal_value(signal: dict) -> str:
    """Render a signal value as human-readable text."""
    val = signal.get("value")
    sid = signal.get("id", "")

    if val is None:
        return ""

    # Freshness decay: {age_days, half_life, freshness}
    if sid == "freshness.decay" and isinstance(val, dict):
        age = val.get("age_days", 0)
        hl = val.get("half_life", 0)
        f = val.get("freshness", 0)
        return f"{age:.0f} days old, half-life {hl}d, freshness {f:.2f}"

    # Review metadata: {reviewed_at, interval}
    if sid == "review.metadata" and isinstance(val, dict):
        parts = []
        if val.get("reviewed_at"):
            parts.append("review date set")
        else:
            parts.append("no review date")
        if val.get("interval"):
            parts.append("interval set")
        else:
            parts.append("no interval")
        return ", ".join(parts)

    # Tables/images: {tables, images}
    if sid == "tables_or_images" and isinstance(val, dict):
        parts = []
        if val.get("tables"):
            parts.append(f"{val['tables']} table{'s' if val['tables'] != 1 else ''}")
        if val.get("images"):
            parts.append(f"{val['images']} image{'s' if val['images'] != 1 else ''}")
        return ", ".join(parts) if parts else "none"

    # Repo/SOR: {source_of_record, repo_source}
    if sid == "repo_or_sor" and isinstance(val, dict):
        parts = []
        if val.get("source_of_record"):
            parts.append("source-of-record")
        if val.get("repo_source"):
            parts.append("repo link")
        return ", ".join(parts) if parts else "none"

    # Lists (e.g. multiple_source_types)
    if isinstance(val, list):
        return ", ".join(str(v) for v in val) if val else "none"

    # Booleans
    if isinstance(val, bool):
        return "yes" if val else "no"

    # Numbers
    if isinstance(val, (int, float)):
        return str(val)

    return str(val)


def _bar(value: float, width: int = 20) -> Text:
    """Render a 0..1 value as a colored bar."""
    filled = int(value * width)
    if value >= 0.7:
        color = "green"
    elif value >= 0.4:
        color = "yellow"
    else:
        color = "red"
    bar = "█" * filled + "░" * (width - filled)
    return Text(f"{bar} {value:.2f}", style=color)


# ---------------------------------------------------------------------------
# Detail screen
# ---------------------------------------------------------------------------


class ScoreDetailScreen(Screen):
    """Shows full score breakdown for a single cached entry."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
        Binding("q", "pop_screen", "Back"),
    ]

    def __init__(self, entry: dict) -> None:
        super().__init__()
        self._entry = entry

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            Static(self._build_detail(), id="detail-content"),
        )
        yield Footer()

    def _build_detail(self) -> Text:
        e = self._entry
        score = e["score"]
        band = e["band"]
        color = BAND_COLORS.get(band, "white")

        t = Text()
        title = e.get("title") or "(untitled)"
        space = e.get("space_key") or ""
        t.append("\n  Title:   ", style="bold")
        t.append(title)
        if space:
            t.append(f"  [{space}]", style="dim")
        t.append("\n  Page ID: ", style="bold")
        t.append(str(e["page_id"]))
        t.append("  v" + str(e["page_version"]))
        t.append("\n  Score:   ", style="bold")
        t.append(f"{score}", style=f"bold {color}")
        t.append(f"  ({band})", style=color)
        t.append(f"  confidence {e['confidence']:.2f}")
        t.append("\n  Class:   ", style="bold")
        t.append(e["primary_class"])
        if e.get("subtype"):
            t.append(f" / {e['subtype']}")
        if e.get("lifecycle_state"):
            t.append(f"  [{e['lifecycle_state']}]", style="dim")
        t.append("\n  Profile: ", style="bold")
        t.append(e["profile"])
        t.append("\n  Scored:  ", style="bold")
        t.append(e.get("scored_at", "?")[:19])
        if e.get("stale"):
            t.append("  (stale)", style="dim yellow")
        t.append("\n")

        # Subscores
        subscores = e.get("subscores", {})
        if subscores:
            t.append("\n  ── Subscores ──\n", style="bold")
            for name in ("stewardship", "freshness", "evidence", "structure", "corroboration"):
                val = subscores.get(name, 0.0)
                t.append(f"  {name:<15} ", style="bold")
                t.append_text(_bar(val))
                t.append("\n")

        # Hard caps
        caps = e.get("hard_caps", [])
        if caps:
            t.append("\n  ── Hard Caps ──\n", style="bold red")
            for cap in caps:
                t.append(f"  • {cap['name']}", style="red")
                t.append(f" (cap={cap['cap']}) — {cap.get('reason', '')}\n")

        # Signals
        signals = e.get("signals")
        if signals:
            t.append("\n  ── Signals ──\n", style="bold")
            for s in signals:
                status = s.get("status", "?")
                if status == "positive":
                    icon, sty = "+", "green"
                elif status == "negative":
                    icon, sty = "−", "red"
                elif status == "missing":
                    icon, sty = "?", "dim"
                else:
                    icon, sty = "~", "yellow"
                t.append(f"  {icon} ", style=sty)
                t.append(f"{s['id']:<30}", style=sty)
                t.append(f" {_format_signal_value(s)}")
                if s.get("inferred"):
                    t.append(" (inferred)", style="dim")
                t.append("\n")

        if not signals:
            t.append("\n  (No signal detail in cache.)\n", style="dim")

        return t

    def action_pop_screen(self) -> None:
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Main table screen
# ---------------------------------------------------------------------------


class ScoreTableScreen(Screen):
    """Main screen showing all cached trust scores in a sortable table."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "rescore", "Re-score"),
        Binding("d", "delete_entry", "Delete"),
        Binding("s", "cycle_sort", "Sort"),
    ]

    _sort_columns = ["score", "band", "title", "primary_class", "space_key", "confidence"]
    _sort_index = 0
    _sort_reverse = True
    _entries: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="score-table")
        yield Footer()

    def on_mount(self) -> None:
        self._load_data()

    def _load_data(self) -> None:
        from confpub.trust.cache import TrustCache

        table = self.query_one("#score-table", DataTable)
        table.clear(columns=True)
        table.cursor_type = "row"

        table.add_columns(
            "Score", "Band", "Space", "Title",
            "Class", "Lifecycle", "Conf",
            "Page ID", "Ver", "Scored At",
        )

        try:
            cache = TrustCache()
            self._entries = cache.get_all_scores()
            cache.close()
        except Exception:
            self._entries = []

        self._sort_and_populate()

    def _sort_and_populate(self) -> None:
        table = self.query_one("#score-table", DataTable)
        table.clear()

        col = self._sort_columns[self._sort_index % len(self._sort_columns)]
        self._entries.sort(key=lambda e: e.get(col, ""), reverse=self._sort_reverse)

        for e in self._entries:
            band = e["band"]
            title = e.get("title") or ""
            if len(title) > 45:
                title = title[:42] + "..."
            table.add_row(
                _colored_score(e["score"], band),
                _colored_band(band),
                e.get("space_key") or "",
                title,
                e["primary_class"],
                e.get("lifecycle_state") or "",
                f"{e['confidence']:.2f}",
                e["page_id"],
                str(e["page_version"]),
                e.get("scored_at", "")[:16],
                key=e["page_id"],
            )

        sort_col = self._sort_columns[self._sort_index % len(self._sort_columns)]
        direction = "↓" if self._sort_reverse else "↑"
        self.sub_title = f"Sorted by {sort_col} {direction}  |  {len(self._entries)} entries"

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        entry = self._selected_entry()
        if entry:
            self.app.push_screen(ScoreDetailScreen(entry))

    def _selected_entry(self) -> dict | None:
        table = self.query_one("#score-table", DataTable)
        if table.row_count == 0:
            return None
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        idx = table.get_row_index(row_key)
        if 0 <= idx < len(self._entries):
            return self._entries[idx]
        return None

    def action_rescore(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        self.sub_title = f"Scoring page {entry['page_id']}..."
        self.call_after_refresh(self._do_rescore, entry["page_id"])

    def _do_rescore(self, page_id: str) -> None:
        try:
            from confpub.confluence import build_client
            from confpub.trust.scoring import score_page
            client = build_client()
            score_page(client, page_id=page_id, include_signals=True, refresh=True)
        except Exception as exc:
            self.sub_title = f"Score failed: {exc}"
            return
        self._load_data()

    def action_delete_entry(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        try:
            from confpub.trust.cache import TrustCache
            cache = TrustCache()
            cache.purge(page_id=entry["page_id"])
            cache.close()
        except Exception:
            pass
        self._load_data()

    def action_cycle_sort(self) -> None:
        self._sort_index += 1
        if self._sort_index % len(self._sort_columns) == 0:
            self._sort_reverse = not self._sort_reverse
        self._sort_and_populate()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class TrustBrowserApp(App):
    """Browse cached confpub trust scores."""

    TITLE = "confpub trust browser"
    CSS = """
    Screen {
        background: $surface;
    }
    #score-table {
        height: 1fr;
    }
    #detail-content {
        padding: 1 2;
    }
    """

    def on_mount(self) -> None:
        self.push_screen(ScoreTableScreen())
