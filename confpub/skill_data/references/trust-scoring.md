# Trust Scoring: Page and Space Trustworthiness Assessment

confpub trust scoring estimates how safe it is to rely on a Confluence page or space as current guidance. It does not detect factual truth — it estimates operational trustworthiness based on governance, freshness, evidence, structure, and corroboration signals.

Scoring works fully automatically from native Confluence signals (version history, body structure, links, labels). No metadata setup is required. Optional `confpub.meta.v1` metadata and trust anchors improve accuracy further.

## Core Concepts

**Score range:** `0..100` with four bands:
- `85..100` = `high` — actively governed, current, well-evidenced
- `70..84` = `good` — solid but may have minor gaps
- `50..69` = `caution` — usable but warrants review
- `0..49` = `low` — stale, ungoverned, or flagged

**Advisory:** Every score includes a machine-readable verdict and guidance:
- `"trustworthy"` — safe to rely on
- `"usable"` — reasonable, check freshness and ownership
- `"verify before using"` — governance gaps, verify independently
- `"do not trust"` — potentially outdated or abandoned

**Confidence:** `0..1` representing how complete the signal set was. A low-confidence score with a high band is downgraded (e.g., "probably trustworthy" instead of "trustworthy").

**Profiles** control scoring weights, half-lives, and hard caps:
- `official-knowledge` — strictest, for authoritative documentation (default)
- `working-area` — relaxed, for team working spaces
- `historical-record` — lenient on freshness, for archives

**Page classification** uses five orthogonal dimensions:
- `primary_class`: hub, governance, instruction, reference, specification, decision, analysis, plan, report, record, people_org, scaffold, unknown
- `subtype`: optional refinement (e.g., `policy`, `runbook`, `adr`, `status_report`)
- `lifecycle_state`: draft, active, approved, deprecated, superseded, archived
- `domain`: engineering, operations_itsm, product, security_risk, etc.
- `generation_mode`: human, imported, generated

Legacy `doc_class` values (policy, runbook, adr, etc.) are accepted and auto-mapped.

## Using Trust Scores as an Agent

When searching Confluence for information, trust scores are included in search results automatically. Use them to:

1. **Prefer high-trust sources** — cite pages with verdict "trustworthy" or "usable" over lower-scored alternatives
2. **Warn on low-trust content** — if only low-trust sources are available, tell the user: "The available Confluence sources score low on trust. Verify before acting on this information."
3. **Cite trust levels** — when presenting information from Confluence, include the trust verdict so the user knows the source quality

Example search workflow:
```bash
# Search with trust scores inline
confpub search --space EA --type page --title "deployment"
```

Each result includes:
```json
{
  "title": "Deployment Guide",
  "trust": {
    "score": 88,
    "band": "high",
    "advisory": {"verdict": "trustworthy", "guidance": "Safe to rely on as current guidance."},
    "primary_class": "instruction"
  }
}
```

Pages without cached scores omit the `trust` field. Use `confpub page inspect` to trigger scoring, or `confpub page score` for explicit scoring with full detail.

## Scoring a Page

```bash
# Score by page ID
confpub page score --page-id 123456

# Score by space + title
confpub page score --space EA --title "Target Architecture"

# Override the scoring profile
confpub page score --page-id 123456 --profile working-area

# Full explanation with signal breakdown
confpub page score --page-id 123456 --explain full

# Bypass cache and recompute from live data
confpub page score --page-id 123456 --refresh
```

### Subscores

The score is a weighted sum of five subscores, each `0..1`:

| Subscore | Weight | What it measures |
|----------|--------|-----------------|
| Stewardship | 0.30 | Owner present, multi-editor history, version maturity, edit quality, review metadata |
| Freshness | 0.25 | Currency relative to primary class half-life |
| Evidence | 0.20 | Outbound links, internal links, Jira macros, external references, tables/images |
| Structure | 0.15 | Headings, summary, labels, body length, no placeholder text |
| Corroboration | 0.10 | Viewers, inbound links, watchers (Phase 2) |

Stewardship and evidence work primarily from **native Confluence signals** — version history, body content, and labels. Explicit metadata (`confpub.meta.v1`) provides additional boost but is not required.

### Hard Caps

| Condition | Max multiplier |
|-----------|---------------|
| Archived or trashed | 0.10 |
| `superseded_by` present | 0.15 |
| Body contains "do not use", "obsolete", "deprecated" | 0.20 |
| Review overdue by >2x interval | 0.25 |
| `lifecycle_state` = deprecated | 0.25 |
| Title starts with "Copy of", "Draft", "TMP", "Test" | 0.30 |
| `primary_class` = scaffold | 0.35 |
| `lifecycle_state` = draft | 0.40 |
| No owner and age >90 days | 0.45 |
| Personal space (`~username`) | 0.50 |

## Trust Anchors

Trust anchors let users declare insider knowledge about which spaces and pages are trustworthy. Set them once — they apply to every score automatically.

```bash
# Declare space trust levels
confpub trust anchor set --space EA --level high --reason "Architecture team authoritative space"
confpub trust anchor set --space DOCS --level good --reason "Official documentation"
confpub trust anchor set --space '~thomas' --level low --reason "Personal working space"

# Declare page-level trust
confpub trust anchor set --page-id 123456 --level high --reason "Approved by leadership"

# List all anchors
confpub trust anchor list

# Remove an anchor
confpub trust anchor remove --space EA
```

Trust levels and their effect on scores:

| Level | Effect | Meaning |
|-------|--------|---------|
| `high` | Score floor 85 | Authoritative — treat as governed truth |
| `good` | Score floor 70 | Reliable — generally trustworthy |
| `caution` | Score ceiling 65 | Questionable — verify before relying on |
| `low` | Score ceiling 50 | Untrustworthy — do not use as authoritative |
| `exclude` | Score ceiling 0 | Excluded — ignore entirely |

Page-level anchors take precedence over space-level anchors. Anchors are stored in `~/.confpub/trust-anchors.json`.

## Automatic Cache Warming

Trust scores are automatically computed and cached whenever confpub interacts with a page:
- `page inspect` — inspecting a page scores it
- `page publish` — publishing scores the result (not on dry-run)
- `property set` — especially useful after setting `confpub.meta.v1`
- `label add` / `label remove` — labels affect classification
- `page history` — checking history scores the page

Cache TTL is 7 days by default. Override with the `CONFPUB_CACHE_TTL` environment variable (value in seconds). If a fresh entry exists, scoring is skipped at zero cost.

### Bulk Cache Warming

Pre-populate the cache for an entire space or CQL result set:

```bash
confpub trust cache warm --space EA
confpub trust cache warm --cql 'label = "official-knowledge"'
confpub trust cache warm --space EA --profile working-area
```

## Search Enrichment

Search results include cached trust scores and advisories by default:

```bash
confpub search --space EA --type page --limit 10
```

Use `--no-score` to disable enrichment.

## Trust Administration

### Cache Management

```bash
confpub trust cache inspect         # View cache statistics
confpub trust cache purge --all     # Clear all entries
confpub trust cache purge --page-id 123456  # Clear one page
```

### Profiles

```bash
confpub trust profile inspect                      # List all profiles
confpub trust profile inspect --name working-area  # Show one profile
```

### Interactive Browser

```bash
confpub trust browse    # TUI browser for cached scores
```

Navigate with arrow keys, press Enter for detail view, `r` to re-score, `d` to delete, `s` to sort, `/` to search, `Escape` to clear search, `q` to quit. Search filters by title, class, space, band, and page ID.

## Governance Metadata (`confpub.meta.v1`)

Optional but recommended for teams with governance workflows. Trust scoring reads this content property for explicit ownership, review dates, and authoritative sources.

```bash
confpub property set --page-id 123456 --key "confpub.meta.v1" --value '{
  "schema_version": "1.0",
  "primary_class": "governance",
  "subtype": "standard",
  "lifecycle_state": "approved",
  "owner_account_id": "abc123",
  "reviewed_at": "2026-03-26",
  "review_interval_days": 180,
  "approvers": ["acct:1"],
  "authoritative_sources": [
    {"type": "repo", "ref": "https://github.com/org/repo"}
  ]
}'
```

## Agent Workflow: Trust-Aware Research

```bash
# 1. Search with trust scores inline
confpub search --space EA --type page --title "deployment"

# 2. Inspect high-trust results (auto-warms cache)
confpub page inspect --page-id 123456 --format markdown

# 3. If only low-trust sources found, tell the user
# 4. Cite trust levels when presenting answers
```

## Agent Workflow: Optimizing a Page for Trust

When the user says "optimize this page for trust" or "improve the score", follow this workflow:

```bash
# 1. Score the page with full signal breakdown
confpub page score --page-id 123456 --explain full
```

Read every negative signal and fix what you can:

| Negative Signal | How to Fix |
|-----------------|------------|
| `owner.present` = no | Set `confpub.meta.v1` with `owner_account_id` |
| `multi_editor` = 1 | Cannot fix directly — note as a recommendation to the user |
| `version.maturity` = 1 | The page needs more edits over time — not fixable in one pass |
| `edit.quality` = 0 | Use meaningful version messages when publishing |
| `review.metadata` = no | Set `reviewed_at` and `review_interval_days` in `confpub.meta.v1` |
| `approvers.present` = 0 | Set `approvers` list in `confpub.meta.v1` |
| `source_of_record.present` = no | Set `source_of_record` in `confpub.meta.v1` |
| `freshness.decay` low | The page is old — update content or set a recent `reviewed_at` |
| `outbound_links` = 0 | Add links to related pages, external docs, or source code |
| `internal_links` = 0 | Add Confluence page links with `[text](Page Title)` |
| `jira_refs` = 0 | Add Jira references with `{jira:PROJ-123}` macros |
| `external_links` = 0 | Add links to external documentation, repos, or standards |
| `authoritative_source` = 0 | Set `authoritative_sources` in `confpub.meta.v1` |
| `tables_or_images` = none | Add tables for structured data, diagrams for architecture |
| `has_excerpt` = no | Add an excerpt block or ensure the first paragraph is substantial |
| `has_headings` = 0 | Add section headings (`## Overview`, `## Details`, etc.) |
| `has_labels` = 0 | Add labels: `confpub label add --page-id 123456 --label governance --label engineering` |
| `sane_length` low | Expand thin content — stubs score poorly |
| `no_placeholder` negative | Remove TODO, TBD, FIXME, "coming soon" text |
| `no_empty_sections` negative | Fill in empty sections or remove the heading |

After fixing, re-score:

```bash
# 2. Re-score to verify improvement
confpub page score --page-id 123456 --refresh --explain full
```

The most impactful fixes are usually: add headings + labels + links (structure/evidence), remove placeholders (structure), and set `confpub.meta.v1` with owner and review date (stewardship).

## Classification Explainability

When scoring with `--explain summary` or `--explain full`, the result includes a `classification` field showing exactly how the primary class was resolved:

```bash
confpub page score --page-id 123456 --explain summary
```

The `classification` field contains:
- `source` — how the class was determined: `cli_override`, `meta_primary`, `meta_legacy`, `label`, `title_pattern`, or `default`
- `matched_value` — the specific value that triggered the match (label name, regex pattern, etc.)
- `evaluated_title_patterns` — full list of title patterns evaluated and whether each matched (only when classification fell through to title inference)

This makes it straightforward to understand why a page is classified as `unknown` and which patterns could be added or tuned.

## Recursive Anchors

Use `--recursive` with `--page-id` to anchor a page and all its descendants:

```bash
confpub trust anchor set --page-id 123456 --level high --reason "Approved tree" --recursive
```

## Missing Signals

The scorer never silently treats unavailable signals as zeros. When signals are missing (e.g., analytics unavailable), the scorer renormalizes weights, lowers confidence, and continues. Use `--include-missing` to see details.
