"""Pydantic models and constants for trust scoring."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALGORITHM_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Page classification taxonomy (5 orthogonal dimensions)
# ---------------------------------------------------------------------------

PRIMARY_CLASSES: list[str] = [
    "hub",
    "governance",
    "instruction",
    "reference",
    "specification",
    "decision",
    "analysis",
    "plan",
    "report",
    "record",
    "people_org",
    "scaffold",
    "unknown",
]

LIFECYCLE_STATES: list[str] = [
    "draft",
    "active",
    "review_due",
    "approved",
    "proposed",
    "accepted",
    "deprecated",
    "superseded",
    "archived",
]

GENERATION_MODES: list[str] = [
    "human",
    "imported",
    "generated",
]

# Default freshness half-lives by primary class (days)
DEFAULT_HALF_LIVES: dict[str, int] = {
    "hub": 180,
    "governance": 365,
    "instruction": 120,
    "reference": 365,
    "specification": 270,
    "decision": 9999,
    "analysis": 180,
    "plan": 60,
    "report": 45,
    "record": 30,
    "people_org": 180,
    "scaffold": 365,
    "unknown": 120,
}

BANDS: list[tuple[str, int, int]] = [
    ("high", 85, 100),
    ("good", 70, 84),
    ("caution", 50, 69),
    ("low", 0, 49),
]

# Agent-facing trust advisories keyed by (band, low_confidence)
ADVISORIES: dict[str, dict[str, str]] = {
    "high": {
        "verdict": "trustworthy",
        "guidance": "Safe to rely on as current guidance. Content is governed, current, and well-evidenced.",
    },
    "high_low_conf": {
        "verdict": "probably trustworthy",
        "guidance": "Likely reliable but some signals are missing. Verify critical claims independently.",
    },
    "good": {
        "verdict": "usable",
        "guidance": "Reasonable to use but may have minor governance gaps. Check freshness and ownership before acting on it.",
    },
    "good_low_conf": {
        "verdict": "usable with caution",
        "guidance": "Appears usable but confidence is low — key signals are missing. Cross-reference with other sources.",
    },
    "caution": {
        "verdict": "verify before using",
        "guidance": "Governance gaps detected. Do not treat as authoritative without independent verification. Check when it was last reviewed and by whom.",
    },
    "low": {
        "verdict": "do not trust",
        "guidance": "Significant governance, freshness, or evidence problems. Treat as potentially outdated or abandoned. Look for a more authoritative source.",
    },
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "stewardship": 0.30,
    "freshness": 0.25,
    "evidence": 0.20,
    "structure": 0.15,
    "corroboration": 0.10,
}


def band_for_score(score: int) -> str:
    """Return the band name for a given score (0..100)."""
    for name, lo, hi in BANDS:
        if lo <= score <= hi:
            return name
    return "low"


def advisory_for(band: str, confidence: float) -> dict[str, str]:
    """Return agent-facing trust advisory for a band + confidence level."""
    low_conf = confidence < 0.70
    if low_conf and band in ("high", "good"):
        key = f"{band}_low_conf"
    else:
        key = band
    return dict(ADVISORIES.get(key, ADVISORIES["low"]))


# ---------------------------------------------------------------------------
# Profile configuration
# ---------------------------------------------------------------------------


class HardCapConfig(BaseModel):
    """A single hard-cap rule within a profile."""

    name: str
    cap: float
    enabled: bool = True


class ProfileConfig(BaseModel):
    """Scoring profile controlling weights, half-lives, and hard caps."""

    name: str
    weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    half_lives: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_HALF_LIVES))
    hard_caps: list[HardCapConfig] = Field(default_factory=list)
    anti_signal_patterns: list[str] = Field(default_factory=list)
    title_cap_pattern: str = r"(?i)^(copy of|draft|tmp|test)\b"
    record_score_cap: int = 65


# ---------------------------------------------------------------------------
# confpub.meta.v1 content property
# ---------------------------------------------------------------------------


class ConfpubMeta(BaseModel):
    """Parsed shape of the ``confpub.meta.v1`` content property."""

    schema_version: str = "1.0"
    primary_class: str | None = None
    subtype: str | None = None
    domain: str | None = None
    lifecycle_state: str | None = None
    generation_mode: str | None = None
    # Legacy field — still accepted, mapped to primary_class
    doc_class: str | None = None
    profile: str | None = None
    owner_account_id: str | None = None
    reviewed_at: str | None = None
    review_interval_days: int | None = None
    expires_at: str | None = None
    approvers: list[str] = Field(default_factory=list)
    authoritative_sources: list[dict[str, str]] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    source_of_record: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Signal model
# ---------------------------------------------------------------------------


class Signal(BaseModel):
    """A single scoring signal with its contribution."""

    id: str
    status: str  # positive, negative, neutral, missing
    weight: float
    value: Any = None
    source: str = ""
    inferred: bool = False


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class Capabilities(BaseModel):
    """Which Confluence API capabilities are available for scoring."""

    content_properties: bool = True
    content_state: bool = False
    analytics: bool = False
    watchers: bool = False
    labels: bool = True
    page_history: bool = True


# ---------------------------------------------------------------------------
# Raw page data (internal, not exposed in envelope)
# ---------------------------------------------------------------------------


class RawPageData(BaseModel):
    """All raw data collected from Confluence for a single page."""

    page_id: str
    space_key: str
    title: str
    status: str
    body_storage: str = ""
    version_number: int = 1
    version_when: str = ""
    version_by: str = ""
    created: str | None = None
    labels: list[dict[str, Any]] = Field(default_factory=list)
    meta_property: ConfpubMeta | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    parent_id: str | None = None


# ---------------------------------------------------------------------------
# Resolved classification (internal)
# ---------------------------------------------------------------------------


class ClassificationReasoning(BaseModel):
    """Explains how and why a page was classified."""

    source: str = "unknown"  # cli_override | meta_primary | meta_legacy | label | title_pattern | default
    matched_value: str | None = None  # the value that matched (e.g. label name, pattern text)
    evaluated_title_patterns: list[dict[str, Any]] = Field(default_factory=list)  # [{pattern, class, matched}]


class ResolvedClassification(BaseModel):
    """Fully resolved page classification from all sources."""

    primary_class: str = "unknown"
    subtype: str | None = None
    domain: str | None = None
    lifecycle_state: str | None = None
    generation_mode: str | None = None
    reasoning: ClassificationReasoning | None = None


# ---------------------------------------------------------------------------
# Score result (the ``result`` field in the envelope)
# ---------------------------------------------------------------------------


class PageScoreResult(BaseModel):
    """Trust score result returned in the envelope."""

    algorithm_version: str = ALGORITHM_VERSION
    profile: str
    primary_class: str
    subtype: str | None = None
    lifecycle_state: str | None = None
    score: int
    band: str
    confidence: float
    advisory: dict[str, str] | None = None
    anchor: dict[str, Any] | None = None
    hard_caps: list[dict[str, Any]] = Field(default_factory=list)
    subscores: dict[str, float]
    signals: list[dict[str, Any]] | None = None
    missing_signals: list[str] | None = None
    classification: dict[str, Any] | None = None
    capabilities: dict[str, bool] | None = None
    weight_renormalization: dict[str, float] | None = None
    cache: dict[str, Any] | None = None
    page_version: int
    scored_at: str
