"""Trust anchors — user-declared trust levels for spaces and pages.

Anchors encode insider knowledge that the scoring engine cannot infer:
"I know this space is authoritative" or "this page was approved by leadership."

Stored in ``~/.confpub/trust-anchors.json``. Managed via ``confpub trust anchor`` commands.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Path
# ---------------------------------------------------------------------------

_ANCHORS_FILE = "trust-anchors.json"


def _anchors_path() -> Path:
    cache_dir = os.environ.get("CONFPUB_CACHE_DIR")
    base = Path(cache_dir) if cache_dir else Path.home() / ".confpub"
    return base / _ANCHORS_FILE


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

# Trust levels and their score effects
TRUST_LEVELS: dict[str, dict[str, Any]] = {
    "high": {"floor": 85, "description": "Authoritative — treat as current, governed truth"},
    "good": {"floor": 70, "description": "Reliable — generally trustworthy, minor gaps possible"},
    "caution": {"ceiling": 65, "description": "Questionable — verify before relying on"},
    "low": {"ceiling": 50, "description": "Untrustworthy — do not use as authoritative source"},
    "exclude": {"ceiling": 0, "description": "Excluded — ignore entirely when searching for guidance"},
}


class TrustAnchor(BaseModel):
    """A single trust anchor declaration."""

    level: str  # high, good, caution, low, exclude
    reason: str = ""


class TrustAnchors(BaseModel):
    """All declared trust anchors."""

    spaces: dict[str, TrustAnchor] = Field(default_factory=dict)
    pages: dict[str, TrustAnchor] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------


def load_anchors() -> TrustAnchors:
    """Load trust anchors from disk. Returns empty anchors if file doesn't exist."""
    path = _anchors_path()
    if not path.exists():
        return TrustAnchors()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return TrustAnchors(**data)
    except Exception:
        return TrustAnchors()


def save_anchors(anchors: TrustAnchors) -> Path:
    """Save trust anchors to disk. Returns the file path."""
    path = _anchors_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(anchors.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Score adjustment
# ---------------------------------------------------------------------------


def apply_anchor(
    score: int,
    space_key: str,
    page_id: str,
    has_hard_caps: bool = False,
    anchors: TrustAnchors | None = None,
) -> tuple[int, dict[str, Any] | None]:
    """Apply trust anchors to a computed score.

    Page-level anchors take precedence over space-level anchors.
    Space-level floor boosts are suppressed when hard caps fired —
    the page has a specific problem that the space reputation shouldn't mask.
    Page-level anchors always apply (explicit user override for that page).

    Returns:
        ``(adjusted_score, anchor_info)`` where ``anchor_info`` is None
        if no anchor matched, or a dict with ``{level, reason, source, effect}``.
    """
    if anchors is None:
        anchors = load_anchors()

    # Check page-level anchor first
    anchor = anchors.pages.get(page_id)
    source = f"page:{page_id}"
    is_page_level = True

    # Fall back to space-level anchor
    if anchor is None:
        anchor = anchors.spaces.get(space_key)
        source = f"space:{space_key}"
        is_page_level = False

    if anchor is None:
        return score, None

    level_config = TRUST_LEVELS.get(anchor.level)
    if level_config is None:
        return score, None

    original = score

    # Space-level floor boost: skip if hard caps fired (the page has problems)
    if "floor" in level_config:
        if is_page_level or not has_hard_caps:
            score = max(score, level_config["floor"])

    if "ceiling" in level_config:
        score = min(score, level_config["ceiling"])

    effect = "unchanged"
    if score > original:
        effect = f"boosted from {original} to {score}"
    elif score < original:
        effect = f"capped from {original} to {score}"
    if has_hard_caps and not is_page_level and "floor" in level_config and score == original:
        effect = f"boost suppressed (hard caps active on this page)"

    return score, {
        "level": anchor.level,
        "reason": anchor.reason,
        "source": source,
        "effect": effect,
    }
