"""Built-in scoring profiles and profile resolution."""

from __future__ import annotations

from confpub.errors import ERR_VALIDATION_TRUST_PROFILE, ConfpubError
from confpub.trust.models import (
    ConfpubMeta,
    DEFAULT_HALF_LIVES,
    DEFAULT_WEIGHTS,
    HardCapConfig,
    ProfileConfig,
)

# ---------------------------------------------------------------------------
# Default anti-signal patterns (body text, case-insensitive)
# ---------------------------------------------------------------------------

_DEFAULT_ANTI_SIGNALS: list[str] = [
    r"(?i)\bdo not use\b",
    r"(?i)\bobsolete\b",
    r"(?i)\bdeprecated\b",
    r"(?i)\bfor reference only\b",
]

# ---------------------------------------------------------------------------
# Hard cap definitions
# ---------------------------------------------------------------------------

_ALL_HARD_CAPS: list[HardCapConfig] = [
    HardCapConfig(name="archived", cap=0.10),
    HardCapConfig(name="superseded_by", cap=0.15),
    HardCapConfig(name="anti_signal_body", cap=0.20),
    HardCapConfig(name="overdue_review", cap=0.25),
    HardCapConfig(name="title_pattern", cap=0.30),
    HardCapConfig(name="lifecycle_draft", cap=0.40),
    HardCapConfig(name="lifecycle_deprecated", cap=0.25),
    HardCapConfig(name="scaffold_class", cap=0.35),
    HardCapConfig(name="no_owner_90d", cap=0.45),
]

# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------

_OFFICIAL_KNOWLEDGE = ProfileConfig(
    name="official-knowledge",
    weights=dict(DEFAULT_WEIGHTS),
    half_lives=dict(DEFAULT_HALF_LIVES),
    hard_caps=list(_ALL_HARD_CAPS),
    anti_signal_patterns=list(_DEFAULT_ANTI_SIGNALS),
    title_cap_pattern=r"(?i)^(copy of|draft|tmp|test)\b",
    record_score_cap=65,
)

_WORKING_AREA = ProfileConfig(
    name="working-area",
    weights={
        "stewardship": 0.30,
        "freshness": 0.20,
        "evidence": 0.20,
        "structure": 0.20,
        "corroboration": 0.10,
    },
    half_lives={
        **DEFAULT_HALF_LIVES,
        "plan": 120,
        "report": 90,
        "record": 60,
        "instruction": 180,
        "unknown": 180,
    },
    hard_caps=[
        HardCapConfig(name="archived", cap=0.10),
        HardCapConfig(name="superseded_by", cap=0.15),
        HardCapConfig(name="anti_signal_body", cap=0.20),
        HardCapConfig(name="overdue_review", cap=0.30),
        HardCapConfig(name="title_pattern", cap=0.50),
        HardCapConfig(name="lifecycle_draft", cap=0.60),
        HardCapConfig(name="lifecycle_deprecated", cap=0.35),
        HardCapConfig(name="scaffold_class", cap=0.50),
        HardCapConfig(name="no_owner_90d", cap=0.55),
    ],
    anti_signal_patterns=list(_DEFAULT_ANTI_SIGNALS),
    title_cap_pattern=r"(?i)^(copy of|draft|tmp|test)\b",
    record_score_cap=75,
)

_HISTORICAL_RECORD = ProfileConfig(
    name="historical-record",
    weights={
        "stewardship": 0.35,
        "freshness": 0.10,
        "evidence": 0.25,
        "structure": 0.20,
        "corroboration": 0.10,
    },
    half_lives={
        "hub": 365,
        "governance": 730,
        "instruction": 365,
        "reference": 730,
        "specification": 730,
        "decision": 9999,
        "analysis": 365,
        "plan": 365,
        "report": 365,
        "record": 365,
        "people_org": 365,
        "scaffold": 730,
        "unknown": 365,
    },
    hard_caps=[
        HardCapConfig(name="archived", cap=0.10),
        HardCapConfig(name="superseded_by", cap=0.15),
        HardCapConfig(name="anti_signal_body", cap=0.20),
        HardCapConfig(name="overdue_review", cap=0.35),
        # title_pattern and lifecycle_draft intentionally omitted
        HardCapConfig(name="lifecycle_deprecated", cap=0.35),
        HardCapConfig(name="scaffold_class", cap=0.40),
        HardCapConfig(name="no_owner_90d", cap=0.55),
    ],
    anti_signal_patterns=list(_DEFAULT_ANTI_SIGNALS),
    title_cap_pattern=r"(?i)^(copy of|draft|tmp|test)\b",
    record_score_cap=80,
)

_PROFILES: dict[str, ProfileConfig] = {
    "official-knowledge": _OFFICIAL_KNOWLEDGE,
    "working-area": _WORKING_AREA,
    "historical-record": _HISTORICAL_RECORD,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_profile(name: str) -> ProfileConfig:
    """Return a profile by name, or raise ``ERR_VALIDATION_TRUST_PROFILE``."""
    profile = _PROFILES.get(name)
    if profile is None:
        raise ConfpubError(
            ERR_VALIDATION_TRUST_PROFILE,
            f"Scoring profile '{name}' not found. "
            f"Available profiles: {', '.join(sorted(_PROFILES))}",
            details={"requested": name, "available": sorted(_PROFILES)},
        )
    return profile


def list_profiles() -> dict[str, ProfileConfig]:
    """Return all built-in profiles."""
    return dict(_PROFILES)


def resolve_profile(
    cli_override: str | None = None,
    meta: ConfpubMeta | None = None,
) -> ProfileConfig:
    """Resolve the effective profile.

    Precedence: CLI flag > confpub.meta.v1.profile > default (official-knowledge).
    """
    name = cli_override or (meta.profile if meta else None) or "official-knowledge"
    return get_profile(name)
