# Trust Scoring — Improvement Roadmap

Phase 1 (shipped) implemented page scoring, SQLite cache, profiles, trust anchors, auto-warming, search enrichment, advisory verdicts, the classification taxonomy, and the Textual TUI browser.

This document tracks planned improvements.

## Phase 2: Space Scoring

`confpub space score` — aggregate trust metrics across a space.

Formula: `0.40 * weighted_median_page_score + 0.20 * ownership_coverage + 0.15 * review_coverage + 0.15 * (1 - overdue_burden) + 0.10 * (1 - low_score_burden)`, all terms `0..1`.

Weight pages by importance: `max(1, log1p(unique_viewers_90d))`. Fallback `1` when analytics unavailable.

Emit: weighted median, p10, percentage below 50, ownership coverage, review coverage, overdue-review burden, superseded/archive burden.

## Phase 3: Cloud-Only Signals

Add optional signal collection for Confluence Cloud features:

- **Content state** (draft/published) — stewardship subscore signal, hard cap for draft state
- **Analytics** (views, unique viewers over configurable window) — corroboration subscore
- **Watchers** — corroboration subscore
- **Inbound links** via CQL reverse search — corroboration subscore

These unlock the corroboration subscore (currently always 0) and add content state to stewardship. Missing signals continue to be handled via weight renormalization.

Add `--window` flag to `page score` and `space score` to control the analytics time window.

## Phase 4: Trust Stamp and Cache Warming

`confpub trust stamp page` — write `confpub.trust.v1` content property to a Confluence page. Mutating. Supports `--if-fresh`, `--force`, `--dry-run`.

`confpub trust cache warm` — precompute scores for a space or CQL result set. Supports `--space`, `--cql`.

`confpub trust profile validate --file trust-profile.yaml` — validate custom scoring profiles.

## Phase 5: Export, Merge, and Reporting

`confpub trust export` — dump all cached scores as JSON or CSV for external analysis.

`confpub trust merge` — combine score exports from multiple instances or time periods.

Trust reports: trend over time, governance coverage, top/bottom pages.

## Phase 6: Textual TUI Enhancements

- Live Confluence browsing (list spaces/pages from API, score on demand)
- Space-level score view
- Filter and search within the TUI
- Anchor management from the TUI
- Score trend sparklines

## Scoring Algorithm Improvements

- **Link check** (dead link detection) — currently missing from evidence subscore
- **Asset resolution** — verify attachments referenced in body exist — currently missing from structure subscore
- **Hub scoring** — score partly from child link freshness, not just own body
- **Concurrent scoring** — parallel API calls for space-wide scoring (currently sequential)
- **Inbound link counting** via CQL search — evidence/corroboration signal without analytics API

## Design Principles

- **`confpub.meta.v1` is authoritative**, `confpub.trust.v1` is disposable. Metadata is governance. Computed score is just a view.
- **Scoring must work fully automatically** from native Confluence signals. No metadata setup required.
- **Missing signals are never treated as zeros.** Weights are renormalized, confidence is lowered.
- **Hard caps override anchor floors** at the space level. Page-level anchors always apply.
- **Works on both Cloud and Data Center** — no Cloud-only feature is mandatory.
