# `confpub` Trust Scoring Spec v1

### 1. Purpose

`confpub` trust scoring estimates how safe it is to rely on a Confluence page or space as current guidance.

It does not attempt to prove factual truth. It estimates operational trustworthiness based on governance, freshness, evidence, structure, and corroboration signals.

### 2. Non-goals

The scorer must not:

* pretend to detect objective truth
* require LLM inference for the base score
* mutate Confluence content during ordinary scoring
* make Cloud-only signals mandatory
* hide missing-signal uncertainty

### 3. Primary object model

There are two scored resource types:

* `page`
* `space`

A page score is primary. A space score is an aggregate over page scores plus space-level coverage metrics.

### 4. Score semantics

The score range is `0..100`.

Bands:

* `85..100` = `high`
* `70..84` = `good`
* `50..69` = `caution`
* `0..49` = `low`

The engine must also emit a `confidence` value `0..1` representing how complete the signal set was.

A low-confidence 78 must not be presented the same way as a high-confidence 78.

### 5. Profiles

The scorer must support named profiles. Start with three:

* `official-knowledge`
* `working-area`
* `historical-record`

The profile controls weights, half-lives, hard caps, and anti-signals.

The effective profile resolution order is:

1. explicit CLI flag (`--profile`)
2. `confpub.meta.v1` content property `profile` field
3. space-level default profile
4. global default = `official-knowledge`

### 6. Page classification

The scorer uses five orthogonal dimensions instead of a single flat class field:

```yaml
primary_class: one of the classes below
subtype: optional, more specific class
domain: architecture | engineering | operations_itsm | product | project_program | people_hr | finance_ops | marketing_sales | legal_compliance | security_risk | company | cross_functional | personal
lifecycle_state: draft | active | review_due | approved | proposed | accepted | deprecated | superseded | archived
generation_mode: human | imported | generated
```

Primary classes:

* `hub` — landing pages, indexes, space homepages, curated collections
* `governance` — policy, standard, guideline, principle, control
* `instruction` — how-to, procedure, SOP, runbook, troubleshooting, tutorial
* `reference` — FAQ, glossary, catalog entry, component reference
* `specification` — requirements, architecture, design spec, system spec
* `decision` — ADR, DACI, design decision, decision log entry
* `analysis` — root cause analysis, risk assessment, architecture review
* `plan` — project plan, roadmap, change plan, launch plan
* `report` — status report, weekly report, incident report, release notes
* `record` — meeting notes, minutes, action log, generated meeting recap
* `people_org` — employee handbook, org chart, roles, team profile
* `scaffold` — template, checklist, form, starter doc
* `unknown`

`primary_class` resolution order:

1. explicit CLI flag (`--doc-class`)
2. `confpub.meta.v1` content property `primary_class` field
3. `confpub.meta.v1` content property `doc_class` field (legacy, mapped)
4. label mapping
5. title-pattern mapping
6. `unknown`

`lifecycle_state` resolution order:

1. `confpub.meta.v1` content property `lifecycle_state` field
2. label mapping (e.g., label `draft` → lifecycle_state `draft`)
3. page status (`archived` / `trashed` → lifecycle_state `archived`)

Legacy `doc_class` values are mapped automatically: `policy`/`standard` → `governance`, `runbook` → `instruction`, `adr` → `decision`, `project` → `plan`, `meeting-notes` → `record`, `reference` → `reference`.

### 7. Inputs

The page scorer may consume these inputs:

Core inputs:

* page id
* space key / space id
* title
* status
* created timestamp
* last modified timestamp
* version number
* version message
* minor-edit flag
* author id
* owner id
* last owner id
* labels
* content properties (via `confpub property get`)
* page body or derived structural features

Optional inputs:

* content state
* analytics views
* analytics unique viewers
* inbound-link count
* outbound-link count
* watcher count
* link-check results
* `confpub` publish metadata (from lockfile or manifest)

### 8. `confpub` properties

Use two Confluence content-property keys, readable and writable via the existing `confpub property get/set` commands.

`confpub.meta.v1` is authoritative metadata written by publishing workflows.

Shape:

```json
{
  "schema_version": "1.0",
  "primary_class": "governance",
  "subtype": "standard",
  "domain": "engineering",
  "lifecycle_state": "approved",
  "generation_mode": "human",
  "profile": "official-knowledge",
  "owner_account_id": "abc123",
  "reviewed_at": "2026-03-20",
  "review_interval_days": 180,
  "expires_at": null,
  "approvers": ["acct:1", "acct:2"],
  "authoritative_sources": [
    {"type": "repo", "ref": "https://git/..."},
    {"type": "jira", "ref": "ARCH-123"},
    {"type": "page", "ref": "987654"}
  ],
  "supersedes": [],
  "superseded_by": null,
  "source_of_record": {
    "type": "git",
    "ref": "main",
    "commit": "abc123"
  }
}
```

`confpub.trust.v1` is optional computed output written only by explicit mutating commands (`trust stamp`).

Shape:

```json
{
  "schema_version": "1.0",
  "algorithm_version": "1.0",
  "scored_at": "2026-03-26T15:20:00Z",
  "profile": "official-knowledge",
  "primary_class": "governance",
  "subtype": "standard",
  "lifecycle_state": "approved",
  "score": 81,
  "band": "good",
  "confidence": 0.92,
  "hard_caps": [],
  "subscores": {
    "stewardship": 0.84,
    "freshness": 0.77,
    "evidence": 0.90,
    "structure": 0.73,
    "corroboration": 0.58
  },
  "signal_fingerprint": "sha256:...",
  "page_version": 19
}
```

Each property stays well within the 32 KB Confluence content-property limit. ([Atlassian Developer][2])

### 9. Scoring algorithm

Page score formula:

`page_score = round(100 * hard_cap_multiplier * weighted_sum)`

Where:

`weighted_sum =
0.30 * stewardship +
0.25 * freshness +
0.20 * evidence +
0.15 * structure +
0.10 * corroboration`

Each subscore is normalized `0..1`.

### 10. Hard caps

Hard caps prevent bad pages from looking acceptable.

Apply the minimum of all applicable caps:

* archived or trashed page: `0.10`
* explicit `superseded_by` present: `0.15`
* body contains strong anti-signals such as "do not use", "obsolete", "deprecated", "for reference only": `0.20`
* review date overdue by > 2x interval: `0.25`
* `lifecycle_state` is `deprecated`: `0.25`
* title matches `(?i)^(copy of|draft|tmp|test)\b`: `0.30`
* `primary_class` is `scaffold`: `0.35`
* `lifecycle_state` is `draft`: `0.40`
* no owner and age > 90 days: `0.45`

### 11. Subscores

#### 11.1 Stewardship (`0.30`)

Purpose: estimate whether the page is actively owned and governed.

Signals:

* explicit owner present
* review date present
* review interval present
* approvers present
* content state present and final
* meaningful version history
* last edit not exclusively minor-edit churn
* source-of-record present

Suggested points:

* owner present: `0.22`
* review metadata present: `0.22`
* approvers present: `0.12`
* final content state: `0.10`
* version history maturity: `0.12`
* non-trivial recent edit history: `0.10`
* source-of-record declared: `0.12`

#### 11.2 Freshness (`0.25`)

Purpose: estimate whether the page is current relative to its class.

Freshness uses a class-specific half-life.

Default half-lives by `primary_class`:

* `hub`: 180 days
* `governance`: 365 days
* `instruction`: 120 days
* `reference`: 365 days
* `specification`: 270 days
* `decision`: 9999 days
* `analysis`: 180 days
* `plan`: 60 days
* `report`: 45 days
* `record`: 30 days
* `people_org`: 180 days
* `scaffold`: 365 days
* `unknown`: 120 days

Freshness reference date order:

1. `reviewed_at`
2. page version modified timestamp
3. created timestamp

Suggested function:

`freshness = exp(-ln(2) * age_days / half_life_days)`

Then apply class overrides:

* `decision` max freshness `0.80` unless referenced by a current authoritative page
* `record` max overall page score `65` (configurable per profile) unless explicitly promoted to another class

#### 11.3 Evidence (`0.20`)

Purpose: estimate whether claims are grounded.

Signals:

* authoritative source links present
* internal upstream page references
* repo link present
* Jira/change ticket references present
* approver references present
* no dead source links
* citations or references count above threshold

Suggested points:

* at least one authoritative source: `0.30`
* multiple source types: `0.20`
* repo or source-of-record link: `0.20`
* Jira/change refs: `0.10`
* no dead links: `0.10`
* reference density threshold met: `0.10`

#### 11.4 Structure (`0.15`)

Purpose: estimate readability and maintenance hygiene.

Signals:

* summary or excerpt exists
* headings exist
* labels exist
* body length within sane range
* attachments referenced correctly
* no placeholder or anti-signal text
* no empty sections

Suggested points:

* has summary/excerpt: `0.15`
* has headings: `0.15`
* has labels: `0.10`
* sane length: `0.15`
* no placeholder text: `0.20`
* no empty sections: `0.10`
* assets resolve: `0.15`

Strong anti-signals:

* `TBD`
* `TODO`
* `FIXME`
* `coming soon`
* `placeholder`
* empty tables
* one-line stub pages

#### 11.5 Corroboration (`0.10`)

Purpose: give a small boost to pages that appear used and connected.

Signals:

* unique viewers
* total views
* inbound links
* watcher count

This category must stay weak. Popularity is not truth.

Suggested formula:

* viewer percentile within space
* inbound-link percentile within space
* watch-count percentile within space

Then:
`corroboration = 0.5*viewer_pct + 0.3*inbound_link_pct + 0.2*watch_pct`

If analytics or watch data is unavailable, renormalize remaining terms.

### 12. Missing-signal handling

The scorer must never silently treat unavailable signals as zeros.

It must emit:

* `capabilities`
* `missing_signals`
* `weight_renormalization`
* `confidence`

Example:

```json
{
  "capabilities": {
    "content_state": true,
    "analytics": false,
    "watchers": false,
    "content_properties": true
  },
  "missing_signals": ["analytics.views", "analytics.unique_viewers", "watchers.count"],
  "weight_renormalization": {
    "stewardship": 0.3333,
    "freshness": 0.2778,
    "evidence": 0.2222,
    "structure": 0.1667,
    "corroboration": 0.0
  },
  "confidence": 0.81
}
```

### 13. Space scoring

Do not average raw page scores.

Compute:

* weighted median page score
* p10 page score
* percentage of pages below 50
* ownership coverage
* review coverage
* overdue-review burden
* superseded/archive burden

Recommended formula:

`space_score =
0.40 * weighted_median_page_score +
0.20 * ownership_coverage +
0.15 * review_coverage +
0.15 * (1 - overdue_burden) +
0.10 * (1 - low_score_burden)`

Where all terms are normalized `0..1`.

Weight pages by importance:

`importance = max(1, log1p(unique_viewers_90d))`

Fallback when analytics is unavailable:

`importance = 1`

### 14. Inference rules

The scorer may infer some signals, but must mark them as inferred.

Allowed inference:

* doc class from labels/title/space
* owner fallback to `lastOwnerId` or recent version author when explicit owner absent
* review interval from profile defaults
* source-of-record from `confpub` lockfile or manifest metadata if present locally

Disallowed inference:

* factual truth of page content
* approval status from social signals
* authority from popularity alone

### 15. Caching model

Use a local SQLite cache.

Default DB path:

`~/.confpub/trust-cache.sqlite3`

Override via `CONFPUB_CACHE_DIR` environment variable:

`$CONFPUB_CACHE_DIR/trust-cache.sqlite3`

Tables:

* `capability_cache`
* `page_snapshot_cache`
* `property_cache`
* `parsed_feature_cache`
* `analytics_cache`
* `link_check_cache`
* `page_score_cache`
* `space_score_cache`

Cache keys must include:

* site/base URL
* resource id
* resource type
* page version
* property version or property fingerprint
* algorithm version
* profile
* doc class
* requested time window

#### TTLs

* capabilities: 24h
* page metadata / labels / properties: 15m
* parsed body features: until page version changes, else 24h
* analytics: 6h
* link checks: 7d
* page scores: 15m or invalidate on page-version change
* space scores: 1h

#### Invalidation

Invalidate page score when any of these change:

* page version number
* `confpub.meta.v1` fingerprint
* algorithm version
* selected profile
* doc class
* analytics time window

Invalidate space score when:

* any constituent page score changed
* aggregation algorithm version changed
* selected profile changed

Use stale-while-revalidate:

* if TTL expired but entry exists, return stale result with `stale=true`
* refresh opportunistically

### 16. Timeouts and concurrency

Defaults:

* Confluence API connect timeout: 5s
* Confluence API read timeout: 15s
* analytics request timeout: 5s
* link check timeout: 5s total per link
* worker concurrency: 8

On timeout:

* record missing signal
* continue scoring
* lower confidence
* never fail the whole score unless core page metadata is unavailable

### 17. Output contract

All commands emit the standard `confpub` JSON envelope on stdout. The envelope structure matches `envelope.py`:

```json
{
  "schema_version": "1.0",
  "request_id": "req_YYYYMMDD_HHMMSS_xxxxxxxx",
  "ok": true,
  "command": "page.score",
  "target": {
    "page_id": "123456",
    "space": "EA",
    "title": "Target Architecture"
  },
  "result": {
    "algorithm_version": "1.0",
    "profile": "official-knowledge",
    "primary_class": "governance",
    "subtype": "standard",
    "lifecycle_state": "approved",
    "score": 81,
    "band": "good",
    "confidence": 0.92,
    "hard_caps": [],
    "subscores": {
      "stewardship": 0.84,
      "freshness": 0.77,
      "evidence": 0.90,
      "structure": 0.73,
      "corroboration": 0.58
    },
    "signals": [
      {
        "id": "owner.present",
        "status": "positive",
        "weight": 0.22,
        "value": true,
        "source": "page.ownerId"
      }
    ],
    "missing_signals": [],
    "capabilities": {
      "content_properties": true,
      "content_state": true,
      "analytics": true
    },
    "cache": {
      "hit": true,
      "stale": false,
      "age_seconds": 122
    }
  },
  "warnings": [],
  "errors": [],
  "metrics": {
    "duration_ms": 481
  }
}
```

The `signals` array is included when `--include-signals` is set. The `missing_signals` array is included when `--include-missing` is set. Both are omitted by default to keep output compact.

Global flags `--quiet`, `--verbose`, and `--compact` apply as with all other commands.

### 18. Error codes

Trust scoring errors use the existing `confpub` error-code prefix convention. Each prefix maps to a fixed exit code and default `suggested_action` / `retryable` via `errors.py`.

Validation errors (exit 10):

* `ERR_VALIDATION_TRUST_PROFILE` — requested profile not found
* `ERR_VALIDATION_TRUST_DOC_CLASS` — unknown document class
* `ERR_VALIDATION_TRUST_RESOURCE` — unsupported resource type for scoring
* `ERR_VALIDATION_TRUST_PROPERTY_SIZE` — computed property exceeds 32 KB limit
* `ERR_VALIDATION_TRUST_SCORE` — requested score not found in cache

I/O errors (exit 50):

* `ERR_IO_TRUST_METADATA` — core page metadata unavailable from Confluence API
* `ERR_IO_TRUST_TIMEOUT` — signal collection timed out
* `ERR_IO_TRUST_CAPABILITY` — required Confluence capability unavailable

Conflict errors (exit 40):

* `ERR_CONFLICT_TRUST_WRITEBACK` — page version changed between score and stamp

Internal errors (exit 90):

* `ERR_INTERNAL_TRUST_CACHE` — trust cache corrupted or unreadable

### 19. CLI surface

Score read commands extend the existing `page` and `space` nouns. Trust administration uses a new `trust` top-level noun.

#### Read commands

`confpub page score`
Scores one page. Envelope command name: `page.score`.

Examples:

```bash
confpub page score --page-id 123456
confpub page score --space EA --title "Target Architecture"
confpub page score --page-id 123456 --profile official-knowledge
confpub page score --page-id 123456 --explain full
confpub page score --page-id 123456 --refresh
```

Flags:

* `--page-id` — Confluence page ID
* `--space` — space key (alternative to `--page-id`)
* `--title` — page title (used with `--space`)
* `--profile` — scoring profile override
* `--doc-class` — document class override
* `--explain {none|summary|full}` — explanation verbosity in result
* `--refresh` — bypass cache, recompute from live data
* `--include-signals` — include full signal breakdown in result
* `--include-missing` — include missing-signal details in result
* `--window 90d` — analytics time window

`confpub space score`
Scores one space. Envelope command name: `space.score`.

Examples:

```bash
confpub space score --space EA
confpub space score --space EA --profile official-knowledge
confpub space score --space EA --top 20 --include-low-pages
```

Flags:

* `--space` — space key (required)
* `--profile` — scoring profile override
* `--window 90d` — analytics time window
* `--top N` — include top N pages by score in result
* `--include-pages` — include all page scores in result
* `--include-low-pages` — include pages scoring below `caution` band
* `--page-limit` — max pages to score (default: all)
* `--refresh` — bypass cache, recompute from live data

#### Trust administration commands

`confpub trust profile inspect`
Shows built-in or custom scoring profiles. Envelope command name: `trust.profile.inspect`.

`confpub trust profile validate --file trust-profile.yaml`
Validates a custom profile file. Envelope command name: `trust.profile.validate`.

`confpub trust cache inspect`
Shows cache stats, TTLs, hit rate. Envelope command name: `trust.cache.inspect`.

`confpub trust cache purge`
Mutating. Clears some or all trust cache entries. Envelope command name: `trust.cache.purge`.

`confpub trust cache warm`
Precomputes scores for a space or CQL result set. Envelope command name: `trust.cache.warm`.

Examples:

```bash
confpub trust cache warm --space EA
confpub trust cache warm --cql 'label = "official-knowledge"'
confpub trust cache purge --space EA
```

#### Explicit write-back commands

Ordinary score commands must not mutate Confluence.

`confpub trust stamp page`
Writes `confpub.trust.v1` content property to a page. Envelope command name: `trust.stamp.page`.

Examples:

```bash
confpub trust stamp page --page-id 123456
confpub trust stamp page --space EA --title "Target Architecture" --if-fresh
```

Flags:

* `--page-id` — Confluence page ID
* `--space` — space key (alternative to `--page-id`)
* `--title` — page title (used with `--space`)
* `--profile` — scoring profile override
* `--if-fresh` — only stamp if the cached score is still fresh
* `--force` — overwrite existing `confpub.trust.v1` without version check
* `--dry-run` — compute and display the property value without writing

`confpub trust stamp space`
Optional. Writes an aggregate summary to a space-level local artifact or export.

### 20. Implementation order

Phase 1: `page score` with local cache, profile support, and only core signals.
Phase 2: `space score` and aggregate metrics.
Phase 3: optional Cloud-only signals such as content state and analytics.
Phase 4: `trust stamp`, custom profiles, and cache warming.

The key design decision: **`confpub.meta.v1` is authoritative** and **`confpub.trust.v1` is disposable**. Metadata is part of governance. Computed score is just a view.

[2]: https://developer.atlassian.com/cloud/confluence/confluence-entity-properties/ "Confluence entity properties"
