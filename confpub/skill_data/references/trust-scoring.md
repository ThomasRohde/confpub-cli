# Trust Scoring: Page and Space Trustworthiness Assessment

confpub trust scoring estimates how safe it is to rely on a Confluence page or space as current guidance. It does not detect factual truth — it estimates operational trustworthiness based on governance, freshness, evidence, structure, and corroboration signals.

## Core Concepts

**Score range:** `0..100` with four bands:
- `85..100` = `high` — actively governed, current, well-evidenced
- `70..84` = `good` — solid but may have minor gaps
- `50..69` = `caution` — usable but warrants review
- `0..49` = `low` — stale, ungoverned, or flagged

**Confidence:** `0..1` representing how complete the signal set was. A low-confidence 78 should not be treated the same as a high-confidence 78.

**Profiles** control scoring weights, half-lives, and hard caps:
- `official-knowledge` — strictest, for authoritative documentation (default)
- `working-area` — relaxed, for team working spaces
- `historical-record` — lenient on freshness, for archives

**Page classification** uses five orthogonal dimensions instead of one flat class:
- `primary_class`: hub, governance, instruction, reference, specification, decision, analysis, plan, report, record, people_org, scaffold, unknown
- `subtype`: optional refinement (e.g., `policy`, `runbook`, `adr`, `status_report`)
- `lifecycle_state`: draft, active, approved, deprecated, superseded, archived
- `domain`: engineering, operations_itsm, product, security_risk, etc.
- `generation_mode`: human, imported, generated

Legacy `doc_class` values (policy, runbook, adr, etc.) are accepted and auto-mapped.

## Scoring a Page

```bash
# Score by page ID
confpub page score --page-id 123456

# Score by space + title
confpub page score --space EA --title "Target Architecture"

# Override the scoring profile
confpub page score --page-id 123456 --profile working-area

# Full explanation with signal breakdown
confpub page score --page-id 123456 --explain full --include-signals

# Bypass cache and recompute from live data
confpub page score --page-id 123456 --refresh
```

The result includes score, band, confidence, subscores, and optionally the full signal breakdown:

```json
{
  "algorithm_version": "1.0",
  "profile": "official-knowledge",
  "primary_class": "governance",
  "subtype": "standard",
  "lifecycle_state": "approved",
  "score": 81,
  "band": "good",
  "confidence": 0.92,
  "subscores": {
    "stewardship": 0.84,
    "freshness": 0.77,
    "evidence": 0.90,
    "structure": 0.73,
    "corroboration": 0.58
  }
}
```

### Subscores

The score is a weighted sum of five subscores, each `0..1`:

| Subscore | Weight | What it measures |
|----------|--------|-----------------|
| Stewardship | 0.30 | Active ownership, review metadata, approvers, source-of-record |
| Freshness | 0.25 | Currency relative to primary class half-life |
| Evidence | 0.20 | Authoritative sources, repo links, Jira references, no dead links |
| Structure | 0.15 | Headings, summary, labels, no placeholder text, sane length |
| Corroboration | 0.10 | Viewers, inbound links, watchers (weak signal — popularity is not truth) |

### Hard Caps

Hard caps prevent bad pages from scoring well regardless of subscores:

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

## Scoring a Space

Space scores aggregate page scores with coverage metrics. They do not average raw scores.

```bash
# Score an entire space
confpub space score --space EA

# Include the worst-scoring pages
confpub space score --space EA --include-low-pages

# Top 20 pages by score
confpub space score --space EA --top 20
```

The space score formula weighs median page score (0.40), ownership coverage (0.20), review coverage (0.15), overdue burden (0.15), and low-score burden (0.10).

## Governance Metadata (`confpub.meta.v1`)

Trust scoring reads governance metadata from the `confpub.meta.v1` content property. This is the authoritative source for ownership, review dates, approvers, and document classification.

```bash
# Read the governance metadata
confpub property get --page-id 123456 --key "confpub.meta.v1"

# Set governance metadata
confpub property set --page-id 123456 --key "confpub.meta.v1" --value '{
  "schema_version": "1.0",
  "primary_class": "governance",
  "subtype": "standard",
  "domain": "engineering",
  "lifecycle_state": "approved",
  "profile": "official-knowledge",
  "owner_account_id": "abc123",
  "reviewed_at": "2026-03-20",
  "review_interval_days": 180,
  "approvers": ["acct:1", "acct:2"],
  "authoritative_sources": [
    {"type": "repo", "ref": "https://github.com/org/repo"},
    {"type": "jira", "ref": "ARCH-123"}
  ]
}'
```

Key fields the scorer reads from `confpub.meta.v1`:

| Field | Effect on score |
|-------|----------------|
| `primary_class` | Determines freshness half-life and class-specific caps |
| `subtype` | Informational, included in result |
| `lifecycle_state` | Hard caps: `draft` (0.40), `deprecated` (0.25) |
| `profile` | Overrides scoring profile |
| `owner_account_id` | Stewardship: owner present |
| `reviewed_at` | Freshness reference date (preferred over last-modified) |
| `review_interval_days` | Overdue detection threshold |
| `approvers` | Stewardship + evidence boost |
| `authoritative_sources` | Evidence: grounded claims |
| `source_of_record` | Stewardship + evidence boost |
| `superseded_by` | Hard cap at 0.15 |

## Automatic Cache Warming

Trust scores are automatically computed and cached whenever confpub interacts with a page. This happens as a silent side effect — it never delays or disrupts the primary command.

Commands that warm the cache:
- `page inspect` — inspecting a page scores it
- `page publish` — publishing scores the result (not on dry-run)
- `property set` — especially useful after setting `confpub.meta.v1`
- `label add` / `label remove` — labels affect classification
- `page history` — checking history scores the page

If a fresh cache entry already exists (TTL 15 min), scoring is skipped at zero cost. This means that normal usage of confpub naturally builds up a trust score cache — agents don't need to explicitly run `page score` on every page.

## Search Enrichment

Search results include cached trust scores by default:

```bash
confpub search --space EA --type page --limit 10
```

Each page-type result includes a `trust` field when a cached score exists:

```json
{
  "id": "327859",
  "title": "Target Architecture",
  "trust": {
    "score": 81,
    "band": "good",
    "confidence": 0.92,
    "primary_class": "governance",
    "stale": false
  }
}
```

Pages without cached scores omit the `trust` field. Use `--no-score` to disable enrichment.

## Trust Administration

### Cache Management

Trust scores are cached locally in `~/.confpub/trust-cache.sqlite3`. Cache entries have TTLs (page scores: 15 min, space scores: 1 hour) and are invalidated when page versions change.

```bash
# View cache statistics
confpub trust cache inspect

# Precompute scores for a space
confpub trust cache warm --space EA

# Precompute scores for labeled pages
confpub trust cache warm --cql 'label = "official-knowledge"'

# Clear cache entries
confpub trust cache purge --space EA
```

### Profiles

```bash
# Inspect built-in profiles
confpub trust profile inspect

# Validate a custom profile file
confpub trust profile validate --file trust-profile.yaml
```

### Stamping Scores to Confluence

Ordinary score commands never mutate Confluence. Use `trust stamp` to explicitly write the computed score as a `confpub.trust.v1` content property.

```bash
# Write the score property to a page
confpub trust stamp page --page-id 123456

# Only stamp if the cached score is fresh
confpub trust stamp page --space EA --title "Target Architecture" --if-fresh

# Preview without writing
confpub trust stamp page --page-id 123456 --dry-run
```

The stamped property is disposable — it can be deleted and recomputed at any time. The authoritative data lives in `confpub.meta.v1`.

## Agent Workflow: Auditing a Space

A typical trust audit workflow. Note: steps 2 and 4 can use `page inspect` instead of `page score` — the trust cache is warmed automatically either way.

```bash
# 1. Score the space to get an overview
confpub space score --space EA --include-low-pages

# 2. Investigate low-scoring pages (page inspect also warms the cache)
confpub page score --page-id 123456 --explain full --include-signals --include-missing

# 3. Fix governance gaps — set ownership and review metadata
confpub property set --page-id 123456 --key "confpub.meta.v1" --value '{
  "schema_version": "1.0",
  "primary_class": "instruction",
  "subtype": "runbook",
  "lifecycle_state": "active",
  "owner_account_id": "abc123",
  "reviewed_at": "2026-03-26",
  "review_interval_days": 90
}'

# 4. Re-score to verify improvement
confpub page score --page-id 123456 --refresh

# 5. Stamp the score for visibility
confpub trust stamp page --page-id 123456
```

## Missing Signals

The scorer never silently treats unavailable signals as zeros. When signals are missing (e.g., analytics unavailable on Confluence Server), the scorer:

1. Records the missing signals
2. Renormalizes weights across available subscores
3. Lowers the confidence value
4. Continues scoring — never fails unless core page metadata is unavailable

Use `--include-missing` to see exactly which signals were unavailable and how weights were renormalized.
