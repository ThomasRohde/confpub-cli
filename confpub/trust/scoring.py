"""Trust scoring engine.

Orchestrates signal collection, subscore computation, hard caps,
weight renormalization, and final score calculation.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from confpub.errors import (
    ERR_IO_TRUST_METADATA,
    ERR_VALIDATION_NOT_FOUND,
    ERR_VALIDATION_TRUST_DOC_CLASS,
    ConfpubError,
)
from confpub.output import emit_stderr
from confpub.trust.body_parser import analyze_body
from confpub.trust.cache import TrustCache
from confpub.trust.models import (
    ALGORITHM_VERSION,
    PRIMARY_CLASSES,
    LIFECYCLE_STATES,
    Capabilities,
    ClassificationReasoning,
    ConfpubMeta,
    PageScoreResult,
    ProfileConfig,
    RawPageData,
    ResolvedClassification,
    Signal,
    advisory_for,
    band_for_score,
)
from confpub.trust.profiles import resolve_profile

# ---------------------------------------------------------------------------
# Classification inference
# ---------------------------------------------------------------------------

# Legacy doc_class values mapped to the new primary_class
_LEGACY_CLASS_MAP: dict[str, str] = {
    "policy": "governance",
    "standard": "governance",
    "runbook": "instruction",
    "reference": "reference",
    "adr": "decision",
    "project": "plan",
    "meeting-notes": "record",
    "draft": "unknown",  # draft is now lifecycle_state, not a class
    "unknown": "unknown",
}

_LABEL_TO_CLASS: dict[str, str] = {
    # governance
    "policy": "governance",
    "standard": "governance",
    "guideline": "governance",
    "principle": "governance",
    # instruction
    "runbook": "instruction",
    "playbook": "instruction",
    "how-to": "instruction",
    "procedure": "instruction",
    "sop": "instruction",
    "tutorial": "instruction",
    "troubleshooting": "instruction",
    # reference
    "reference": "reference",
    "faq": "reference",
    "glossary": "reference",
    "catalog": "reference",
    # specification
    "specification": "specification",
    "requirements": "specification",
    "architecture": "specification",
    "design-spec": "specification",
    # decision
    "adr": "decision",
    "decision": "decision",
    "daci": "decision",
    # analysis
    "analysis": "analysis",
    "rca": "analysis",
    "risk-assessment": "analysis",
    "review": "analysis",
    # plan
    "plan": "plan",
    "roadmap": "plan",
    "project-plan": "plan",
    # report
    "report": "report",
    "status-report": "report",
    "release-notes": "report",
    # record
    "meeting-notes": "record",
    "meeting-note": "record",
    "minutes": "record",
    "record": "record",
    # hub
    "hub": "hub",
    "index": "hub",
    "homepage": "hub",
    # people_org
    "handbook": "people_org",
    "org-chart": "people_org",
    "team-profile": "people_org",
    # scaffold
    "template": "scaffold",
    "scaffold": "scaffold",
    # primary class names accepted directly as labels
    "hub": "hub",
    "governance": "governance",
    "instruction": "instruction",
    "specification": "specification",
    "decision": "decision",
    "analysis": "analysis",
    "plan": "plan",
    "report": "report",
    "record": "record",
    "people_org": "people_org",
    "people-org": "people_org",
}

_LABEL_TO_LIFECYCLE: dict[str, str] = {
    "draft": "draft",
    "approved": "approved",
    "deprecated": "deprecated",
    "archived": "archived",
    "proposed": "proposed",
    "accepted": "accepted",
}

_TITLE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # decision
    (re.compile(r"(?i)^ADR[\s\-]?\d+"), "decision"),
    # record
    (re.compile(r"(?i)\bmeeting[\s\-]?notes?\b"), "record"),
    (re.compile(r"(?i)\bminutes\b"), "record"),
    (re.compile(r"(?i)\baction[\s\-]?log\b"), "record"),
    (re.compile(r"(?i)\bsurvey\b"), "record"),
    (re.compile(r"(?i)\bfeedback\b"), "record"),
    (re.compile(r"(?i)\bissue[\s\-]?history\b"), "record"),
    # instruction — procedural patterns
    (re.compile(r"(?i)^STEP\s+\d+"), "instruction"),
    (re.compile(r"(?i)\brunbook\b"), "instruction"),
    (re.compile(r"(?i)\bplaybook\b"), "instruction"),
    (re.compile(r"(?i)\bhow[\s\-]?to\b"), "instruction"),
    (re.compile(r"(?i)^getting[\s\-]?started\b"), "instruction"),
    (re.compile(r"(?i)\bonboarding\b"), "instruction"),
    (re.compile(r"(?i)\baccess[\s\-]?guide\b"), "instruction"),
    (re.compile(r"(?i)\bdecommission"), "instruction"),
    (re.compile(r"(?i)\bpreparation[\s\-]?guide\b"), "instruction"),
    (re.compile(r"(?i)\bsetup[\s\-]?guide\b"), "instruction"),
    (re.compile(r"(?i)\binstallation[\s\-]?guide\b"), "instruction"),
    (re.compile(r"(?i)\bquick[\s\-]?start\b"), "instruction"),
    (re.compile(r"(?i)\btutorial\b"), "instruction"),
    (re.compile(r"(?i)\bprocedure\b"), "instruction"),
    (re.compile(r"(?i)\btroubleshooting\b"), "instruction"),
    (re.compile(r"(?i)\bsop\b"), "instruction"),
    # report
    (re.compile(r"(?i)\bstatus[\s\-]?report\b"), "report"),
    (re.compile(r"(?i)\brelease[\s\-]?notes?\b"), "report"),
    # governance — including EAGOV patterns
    (re.compile(r"(?i)\bpolicy\b"), "governance"),
    (re.compile(r"(?i)\bmandate\b"), "governance"),
    (re.compile(r"(?i)\bprinciples?\b"), "governance"),
    (re.compile(r"(?i)\bguidelines?\b"), "governance"),
    (re.compile(r"(?i)\brules?\b(?:\s+for\b|\s+of\b)"), "governance"),
    (re.compile(r"(?i)\bstandard\b"), "governance"),
    (re.compile(r"(?i)^(?:EAGOV|EA[\s\-]?GOV)[\s\-]?\d+"), "governance"),
    (re.compile(r"(?i)\bgovernance[\s\-]?scope\b"), "governance"),
    # specification — including EAGOV submission templates
    (re.compile(r"(?i)\barchitecture\b"), "specification"),
    (re.compile(r"(?i)\bdesign[\s\-]?spec\b"), "specification"),
    (re.compile(r"(?i)\bsubmission[\s\-]?template\b"), "specification"),
    # plan
    (re.compile(r"(?i)\broadmap\b"), "plan"),
    # people_org
    (re.compile(r"(?i)\bhandbook\b"), "people_org"),
    (re.compile(r"(?i)\borg[\s\-]?chart\b"), "people_org"),
    # reference — expanded patterns
    (re.compile(r"(?i)\bglossary\b"), "reference"),
    (re.compile(r"(?i)\bFAQ\b"), "reference"),
    (re.compile(r"(?i)\bterminology\b"), "reference"),
    (re.compile(r"(?i)\bAPI[\s\-]?example\b"), "reference"),
    (re.compile(r"(?i)\bterraform[\s\-]?example\b"), "reference"),
    (re.compile(r"(?i)\bTL\s*;?\s*DR\b"), "reference"),
    (re.compile(r"(?i)\bbest[\s\-]?practices?\b"), "reference"),
    (re.compile(r"(?i)\bresource[\s\-]?catalog\b"), "reference"),
    (re.compile(r"(?i)\breference[\s\-]?guide\b"), "reference"),
    (re.compile(r"(?i)\bcheat[\s\-]?sheet\b"), "reference"),
    # hub — section headers and index pages
    (re.compile(r"^[A-Z][A-Z\s\-&]{4,}$"), "hub"),
    (re.compile(r"(?i)\bindex\b"), "hub"),
    (re.compile(r"(?i)\bhomepage\b"), "hub"),
    (re.compile(r"(?i)\boverview\b$"), "hub"),
    (re.compile(r"(?i)\btable[\s\-]?of[\s\-]?contents\b"), "hub"),
    # scaffold
    (re.compile(r"(?i)\btemplate\b"), "scaffold"),
    # analysis
    (re.compile(r"(?i)\breview\b"), "analysis"),
    (re.compile(r"(?i)\bassessment\b"), "analysis"),
    (re.compile(r"(?i)\broot[\s\-]?cause\b"), "analysis"),
]


def _resolve_classification(
    class_override: str | None,
    meta: ConfpubMeta | None,
    labels: list[dict[str, Any]],
    title: str,
    page_status: str,
) -> ResolvedClassification:
    """Resolve the full page classification from all sources.

    For primary_class, precedence: CLI > meta.primary_class > meta.doc_class (legacy) > labels > title > unknown.
    For lifecycle_state: meta.lifecycle_state > labels > page status > None.
    """
    result = ResolvedClassification()
    reasoning = ClassificationReasoning()

    # --- primary_class ---
    if class_override:
        if class_override not in PRIMARY_CLASSES:
            # Check if it's a legacy doc_class value
            if class_override in _LEGACY_CLASS_MAP:
                result.primary_class = _LEGACY_CLASS_MAP[class_override]
                reasoning.source = "cli_override"
                reasoning.matched_value = class_override
            else:
                raise ConfpubError(
                    ERR_VALIDATION_TRUST_DOC_CLASS,
                    f"Unknown primary class '{class_override}'. "
                    f"Valid classes: {', '.join(PRIMARY_CLASSES)}",
                    details={"requested": class_override, "valid": PRIMARY_CLASSES},
                )
        else:
            result.primary_class = class_override
            reasoning.source = "cli_override"
            reasoning.matched_value = class_override
    elif meta and meta.primary_class and meta.primary_class in PRIMARY_CLASSES:
        result.primary_class = meta.primary_class
        reasoning.source = "meta_primary"
        reasoning.matched_value = meta.primary_class
    elif meta and meta.doc_class:
        # Legacy fallback
        result.primary_class = _LEGACY_CLASS_MAP.get(meta.doc_class, "unknown")
        reasoning.source = "meta_legacy"
        reasoning.matched_value = meta.doc_class
    else:
        # Infer from labels
        for lbl in labels:
            name = lbl.get("name", "").lower()
            if name in _LABEL_TO_CLASS:
                result.primary_class = _LABEL_TO_CLASS[name]
                reasoning.source = "label"
                reasoning.matched_value = name
                break

        # Infer from title
        if result.primary_class == "unknown":
            for pattern, cls in _TITLE_PATTERNS:
                matched = bool(pattern.search(title))
                reasoning.evaluated_title_patterns.append({
                    "pattern": pattern.pattern,
                    "class": cls,
                    "matched": matched,
                })
                if matched and result.primary_class == "unknown":
                    result.primary_class = cls
                    reasoning.source = "title_pattern"
                    reasoning.matched_value = pattern.pattern

            if result.primary_class == "unknown":
                reasoning.source = "default"

    # --- subtype (from meta only) ---
    if meta and meta.subtype:
        result.subtype = meta.subtype

    # --- domain (from meta only) ---
    if meta and meta.domain:
        result.domain = meta.domain

    # --- lifecycle_state ---
    if meta and meta.lifecycle_state and meta.lifecycle_state in LIFECYCLE_STATES:
        result.lifecycle_state = meta.lifecycle_state
    else:
        # Infer from labels
        for lbl in labels:
            name = lbl.get("name", "").lower()
            if name in _LABEL_TO_LIFECYCLE:
                result.lifecycle_state = _LABEL_TO_LIFECYCLE[name]
                break
        # Infer from page status
        if result.lifecycle_state is None and page_status in ("archived", "trashed"):
            result.lifecycle_state = "archived"

    # --- generation_mode ---
    if meta and meta.generation_mode:
        result.generation_mode = meta.generation_mode

    result.reasoning = reasoning
    return result


# ---------------------------------------------------------------------------
# Signal collection from Confluence
# ---------------------------------------------------------------------------


def _collect_raw_data(
    client: Any,
    *,
    page_id: str | None = None,
    space: str | None = None,
    title: str | None = None,
) -> RawPageData:
    """Fetch all raw data needed for scoring from Confluence."""
    # Resolve the page
    page: dict[str, Any] = {}
    try:
        if page_id:
            page = client.get_page_by_id(page_id)
        elif space and title:
            page = client.get_page(space, title)
    except ConfpubError:
        raise
    except Exception as exc:
        raise ConfpubError(
            ERR_IO_TRUST_METADATA,
            f"Failed to fetch page metadata: {exc}",
        ) from exc

    if not page or not page.get("id"):
        raise ConfpubError(
            ERR_IO_TRUST_METADATA,
            "Core page metadata unavailable — cannot score.",
            details={"page_id": page_id, "space": space, "title": title},
        )

    pid = str(page["id"])
    version = page.get("version", {})
    version_number = version.get("number", 1) if isinstance(version, dict) else 1
    version_when = version.get("when", "") if isinstance(version, dict) else ""
    version_by = ""
    if isinstance(version, dict):
        by = version.get("by", {})
        version_by = (
            by.get("displayName", by.get("username", ""))
            if isinstance(by, dict)
            else str(by)
        )

    page_space = page.get("space", {})
    space_key = (
        page_space.get("key", space or "")
        if isinstance(page_space, dict)
        else (space or "")
    )

    body = page.get("body", {})
    body_storage = ""
    if isinstance(body, dict):
        storage = body.get("storage", {})
        body_storage = storage.get("value", "") if isinstance(storage, dict) else ""

    status = page.get("status", "current")
    page_title = page.get("title", title or "")

    ancestors = page.get("ancestors", [])
    parent_id = str(ancestors[-1]["id"]) if ancestors else None

    # Labels
    labels: list[dict[str, Any]] = []
    try:
        labels = client.get_labels(pid)
    except Exception:
        pass

    # confpub.meta.v1 content property
    meta_property: ConfpubMeta | None = None
    try:
        prop = client.get_page_property(pid, "confpub.meta.v1")
        if prop and "value" in prop:
            val = prop["value"]
            if isinstance(val, dict):
                meta_property = ConfpubMeta(**val)
    except ConfpubError as e:
        if e.code not in (ERR_VALIDATION_NOT_FOUND, "ERR_AUTH_FORBIDDEN"):
            raise
    except Exception:
        pass

    # Version history (limit 5 to avoid N+1 explosion)
    history: list[dict[str, Any]] = []
    try:
        history = client.get_page_history(pid, limit=5)
    except Exception:
        pass

    # Infer created timestamp from earliest history entry
    created = None
    if history:
        created = history[-1].get("when", version_when)

    return RawPageData(
        page_id=pid,
        space_key=space_key,
        title=page_title,
        status=status,
        body_storage=body_storage,
        version_number=version_number,
        version_when=version_when,
        version_by=version_by,
        created=created,
        labels=labels,
        meta_property=meta_property,
        history=history,
        parent_id=parent_id,
    )


# ---------------------------------------------------------------------------
# Subscore: Stewardship (0.30)
# ---------------------------------------------------------------------------

_STEWARDSHIP_SIGNALS = {
    "owner.present": 0.18,
    "multi_editor": 0.16,
    "version.maturity": 0.16,
    "edit.quality": 0.12,
    "review.metadata": 0.14,
    "approvers.present": 0.08,
    "source_of_record.present": 0.08,
    "content_state.final": 0.08,  # missing in Phase 1
}


def _compute_stewardship(
    raw: RawPageData,
    meta: ConfpubMeta | None,
) -> tuple[float, list[Signal]]:
    signals: list[Signal] = []

    # Owner present — infer from history if no explicit owner
    owner_id = meta.owner_account_id if meta else None
    inferred = False
    if not owner_id and raw.history:
        earliest = raw.history[-1] if raw.history else None
        if earliest:
            owner_id = earliest.get("by", "")
            inferred = bool(owner_id)

    signals.append(Signal(
        id="owner.present",
        status="positive" if owner_id else "negative",
        weight=_STEWARDSHIP_SIGNALS["owner.present"],
        value=bool(owner_id),
        source="confpub.meta.v1.owner_account_id" if not inferred else "history.earliest.by",
        inferred=inferred,
    ))

    # Multi-editor: distinct editors in history (native Confluence signal)
    editors = {h.get("by", "") for h in raw.history if h.get("by")}
    editor_count = len(editors)
    multi_score = 1.0 if editor_count >= 3 else (0.5 if editor_count == 2 else 0.0)
    signals.append(Signal(
        id="multi_editor",
        status="positive" if editor_count >= 3 else ("neutral" if editor_count == 2 else "negative"),
        weight=_STEWARDSHIP_SIGNALS["multi_editor"],
        value=editor_count,
        source="page.history.distinct_editors",
    ))

    # Version maturity
    vn = raw.version_number
    maturity_score = 1.0 if vn >= 5 else (0.75 if vn >= 3 else (0.5 if vn == 2 else 0.25))
    signals.append(Signal(
        id="version.maturity",
        status="positive" if vn >= 3 else "neutral",
        weight=_STEWARDSHIP_SIGNALS["version.maturity"],
        value=vn,
        source="page.version.number",
    ))

    # Non-trivial edit history (version messages)
    substantive = sum(1 for h in raw.history if h.get("message", ""))
    edit_score = 1.0 if substantive >= 2 else (0.5 if substantive == 1 else 0.0)
    signals.append(Signal(
        id="edit.quality",
        status="positive" if substantive >= 2 else ("neutral" if substantive == 1 else "negative"),
        weight=_STEWARDSHIP_SIGNALS["edit.quality"],
        value=substantive,
        source="page.history.messages",
    ))

    # Review metadata (meta-dependent, lower weight)
    has_reviewed_at = bool(meta and meta.reviewed_at)
    has_interval = bool(meta and meta.review_interval_days)
    review_score = 1.0 if (has_reviewed_at and has_interval) else (0.5 if (has_reviewed_at or has_interval) else 0.0)
    signals.append(Signal(
        id="review.metadata",
        status="positive" if review_score == 1.0 else ("neutral" if review_score > 0 else "negative"),
        weight=_STEWARDSHIP_SIGNALS["review.metadata"],
        value={"reviewed_at": has_reviewed_at, "interval": has_interval},
        source="confpub.meta.v1",
    ))

    # Approvers (meta-dependent)
    has_approvers = bool(meta and meta.approvers)
    signals.append(Signal(
        id="approvers.present",
        status="positive" if has_approvers else "negative",
        weight=_STEWARDSHIP_SIGNALS["approvers.present"],
        value=len(meta.approvers) if meta else 0,
        source="confpub.meta.v1.approvers",
    ))

    # Source of record (meta-dependent)
    has_sor = bool(meta and meta.source_of_record)
    signals.append(Signal(
        id="source_of_record.present",
        status="positive" if has_sor else "negative",
        weight=_STEWARDSHIP_SIGNALS["source_of_record.present"],
        value=has_sor,
        source="confpub.meta.v1.source_of_record",
    ))

    # Content state — always missing in Phase 1
    signals.append(Signal(
        id="content_state.final",
        status="missing",
        weight=_STEWARDSHIP_SIGNALS["content_state.final"],
        value=None,
        source="content_state_api",
    ))

    # Compute subscore, redistributing missing content_state weight
    available = [s for s in signals if s.status != "missing"]
    total_available_weight = sum(s.weight for s in available)

    score = 0.0
    for s in available:
        ew = s.weight / total_available_weight if total_available_weight > 0 else 0.0
        if s.id == "review.metadata":
            score += ew * review_score
        elif s.id == "version.maturity":
            score += ew * maturity_score
        elif s.id == "edit.quality":
            score += ew * edit_score
        elif s.id == "multi_editor":
            score += ew * multi_score
        elif s.status == "positive":
            score += ew * 1.0

    return score, signals


# ---------------------------------------------------------------------------
# Subscore: Freshness (0.25)
# ---------------------------------------------------------------------------


def _compute_freshness(
    raw: RawPageData,
    meta: ConfpubMeta | None,
    profile: ProfileConfig,
    primary_class: str,
) -> tuple[float, list[Signal]]:
    # Reference date: reviewed_at > version_when > created
    ref_date: datetime | None = None
    ref_source = ""

    if meta and meta.reviewed_at:
        try:
            ref_date = datetime.fromisoformat(meta.reviewed_at)
            if ref_date.tzinfo is None:
                ref_date = ref_date.replace(tzinfo=timezone.utc)
            ref_source = "confpub.meta.v1.reviewed_at"
        except (ValueError, TypeError):
            pass

    if ref_date is None and raw.version_when:
        try:
            ref_date = datetime.fromisoformat(raw.version_when)
            if ref_date.tzinfo is None:
                ref_date = ref_date.replace(tzinfo=timezone.utc)
            ref_source = "page.version.when"
        except (ValueError, TypeError):
            pass

    if ref_date is None and raw.created:
        try:
            ref_date = datetime.fromisoformat(raw.created)
            if ref_date.tzinfo is None:
                ref_date = ref_date.replace(tzinfo=timezone.utc)
            ref_source = "page.created"
        except (ValueError, TypeError):
            pass

    if ref_date is None:
        # No date at all — worst case
        return 0.0, [Signal(
            id="freshness.decay",
            status="negative",
            weight=1.0,
            value=None,
            source="none",
        )]

    now = datetime.now(timezone.utc)
    age_days = max(0.0, (now - ref_date).total_seconds() / 86400)
    half_life = profile.half_lives.get(primary_class, 120)

    freshness = math.exp(-math.log(2) * age_days / half_life)

    # Decision class: cap freshness (decisions age gracefully)
    if primary_class == "decision":
        freshness = min(freshness, 0.80)

    signal = Signal(
        id="freshness.decay",
        status="positive" if freshness >= 0.5 else ("neutral" if freshness >= 0.25 else "negative"),
        weight=1.0,
        value={"age_days": round(age_days, 1), "half_life": half_life, "freshness": round(freshness, 4)},
        source=ref_source,
    )

    return freshness, [signal]


# ---------------------------------------------------------------------------
# Subscore: Evidence (0.20)
# ---------------------------------------------------------------------------

_EVIDENCE_SIGNALS = {
    "outbound_links": 0.20,
    "internal_links": 0.15,
    "jira_refs": 0.15,
    "external_links": 0.10,
    "authoritative_source": 0.15,
    "repo_or_sor": 0.10,
    "tables_or_images": 0.10,
    "no_dead_links": 0.05,  # missing in Phase 1
}


def _compute_evidence(
    raw: RawPageData,
    meta: ConfpubMeta | None,
    body_features: "BodyFeatures",
) -> tuple[float, list[Signal]]:
    from confpub.trust.body_parser import BodyFeatures

    signals: list[Signal] = []
    sources = meta.authoritative_sources if meta else []

    # Outbound links (from body — works on any Confluence)
    link_count = body_features.outbound_link_count
    link_score = 1.0 if link_count >= 5 else (0.75 if link_count >= 3 else (0.4 if link_count >= 1 else 0.0))
    signals.append(Signal(
        id="outbound_links",
        status="positive" if link_count >= 3 else ("neutral" if link_count >= 1 else "negative"),
        weight=_EVIDENCE_SIGNALS["outbound_links"],
        value=link_count,
        source="body.links",
    ))

    # Internal page links (from body)
    int_links = body_features.internal_link_count
    int_score = 1.0 if int_links >= 3 else (0.5 if int_links >= 1 else 0.0)
    signals.append(Signal(
        id="internal_links",
        status="positive" if int_links >= 3 else ("neutral" if int_links >= 1 else "negative"),
        weight=_EVIDENCE_SIGNALS["internal_links"],
        value=int_links,
        source="body.internal_links",
    ))

    # Jira macros (from body — native Confluence macro, no metadata needed)
    jira_count = body_features.jira_macro_count
    # Also check meta sources for jira refs
    meta_jira = any(s.get("type") == "jira" for s in sources)
    has_jira = jira_count > 0 or meta_jira
    signals.append(Signal(
        id="jira_refs",
        status="positive" if has_jira else "negative",
        weight=_EVIDENCE_SIGNALS["jira_refs"],
        value=jira_count,
        source="body.jira_macros" if jira_count > 0 else "confpub.meta.v1",
    ))

    # External links (from body)
    ext_links = body_features.external_link_count
    ext_score = 1.0 if ext_links >= 2 else (0.5 if ext_links >= 1 else 0.0)
    signals.append(Signal(
        id="external_links",
        status="positive" if ext_links >= 2 else ("neutral" if ext_links >= 1 else "negative"),
        weight=_EVIDENCE_SIGNALS["external_links"],
        value=ext_links,
        source="body.external_links",
    ))

    # Authoritative sources (meta-dependent, lower weight now)
    has_source = len(sources) >= 1
    signals.append(Signal(
        id="authoritative_source",
        status="positive" if has_source else "negative",
        weight=_EVIDENCE_SIGNALS["authoritative_source"],
        value=len(sources),
        source="confpub.meta.v1.authoritative_sources",
    ))

    # Repo or source-of-record (meta-dependent)
    has_sor = bool(meta and meta.source_of_record)
    has_repo = any(s.get("type") == "repo" for s in sources)
    signals.append(Signal(
        id="repo_or_sor",
        status="positive" if (has_sor or has_repo) else "negative",
        weight=_EVIDENCE_SIGNALS["repo_or_sor"],
        value={"source_of_record": has_sor, "repo_source": has_repo},
        source="confpub.meta.v1",
    ))

    # Tables or images (from body — indicates structured evidence)
    has_visual = body_features.table_count > 0 or body_features.image_count > 0
    signals.append(Signal(
        id="tables_or_images",
        status="positive" if has_visual else "negative",
        weight=_EVIDENCE_SIGNALS["tables_or_images"],
        value={"tables": body_features.table_count, "images": body_features.image_count},
        source="body.visual_content",
    ))

    # No dead links — missing in Phase 1
    signals.append(Signal(
        id="no_dead_links",
        status="missing",
        weight=_EVIDENCE_SIGNALS["no_dead_links"],
        value=None,
        source="link_check",
    ))

    # Compute subscore
    available = [s for s in signals if s.status != "missing"]
    total_w = sum(s.weight for s in available)
    score = 0.0
    if total_w > 0:
        for s in available:
            ew = s.weight / total_w
            if s.id == "outbound_links":
                score += ew * link_score
            elif s.id == "internal_links":
                score += ew * int_score
            elif s.id == "external_links":
                score += ew * ext_score
            elif s.status == "positive":
                score += ew * 1.0

    return score, signals


# ---------------------------------------------------------------------------
# Subscore: Structure (0.15)
# ---------------------------------------------------------------------------

_STRUCTURE_SIGNALS = {
    "has_excerpt": 0.15,
    "has_headings": 0.15,
    "has_labels": 0.10,
    "sane_length": 0.15,
    "no_placeholder": 0.20,
    "no_empty_sections": 0.10,
    "assets_resolve": 0.15,  # missing in Phase 1
}


def _compute_structure(
    raw: RawPageData,
    profile: ProfileConfig,
) -> tuple[float, list[Signal]]:
    features = analyze_body(raw.body_storage, profile.anti_signal_patterns)
    signals: list[Signal] = []

    # Excerpt
    signals.append(Signal(
        id="has_excerpt",
        status="positive" if features.has_excerpt else "negative",
        weight=_STRUCTURE_SIGNALS["has_excerpt"],
        value=features.has_excerpt,
        source="body.excerpt",
    ))

    # Headings
    signals.append(Signal(
        id="has_headings",
        status="positive" if features.heading_count > 0 else "negative",
        weight=_STRUCTURE_SIGNALS["has_headings"],
        value=features.heading_count,
        source="body.headings",
    ))

    # Labels
    has_labels = len(raw.labels) > 0
    signals.append(Signal(
        id="has_labels",
        status="positive" if has_labels else "negative",
        weight=_STRUCTURE_SIGNALS["has_labels"],
        value=len(raw.labels),
        source="page.labels",
    ))

    # Sane length
    tl = features.text_length
    if tl < 200:
        length_score = 0.0
        length_status = "negative"
    elif tl > 50000:
        length_score = 0.5
        length_status = "neutral"
    else:
        length_score = 1.0
        length_status = "positive"
    signals.append(Signal(
        id="sane_length",
        status=length_status,
        weight=_STRUCTURE_SIGNALS["sane_length"],
        value=tl,
        source="body.text_length",
    ))

    # No placeholder text
    has_placeholders = len(features.placeholder_texts) > 0
    signals.append(Signal(
        id="no_placeholder",
        status="negative" if has_placeholders else "positive",
        weight=_STRUCTURE_SIGNALS["no_placeholder"],
        value=features.placeholder_texts if has_placeholders else [],
        source="body.placeholder_scan",
    ))

    # No empty sections
    signals.append(Signal(
        id="no_empty_sections",
        status="negative" if features.empty_section_count > 0 else "positive",
        weight=_STRUCTURE_SIGNALS["no_empty_sections"],
        value=features.empty_section_count,
        source="body.empty_sections",
    ))

    # Assets resolve — missing in Phase 1
    signals.append(Signal(
        id="assets_resolve",
        status="missing",
        weight=_STRUCTURE_SIGNALS["assets_resolve"],
        value=None,
        source="asset_check",
    ))

    # Compute subscore
    available = [s for s in signals if s.status != "missing"]
    total_w = sum(s.weight for s in available)
    score = 0.0
    if total_w > 0:
        for s in available:
            ew = s.weight / total_w
            if s.id == "sane_length":
                score += ew * length_score
            elif s.status == "positive":
                score += ew * 1.0

    return score, signals


# ---------------------------------------------------------------------------
# Subscore: Corroboration (0.10)
# ---------------------------------------------------------------------------


def _compute_corroboration() -> tuple[float, list[Signal]]:
    """Corroboration is entirely missing in Phase 1 (no analytics/watchers)."""
    return 0.0, [
        Signal(id="viewers", status="missing", weight=0.50, source="analytics"),
        Signal(id="inbound_links", status="missing", weight=0.30, source="search"),
        Signal(id="watchers", status="missing", weight=0.20, source="watchers_api"),
    ]


# ---------------------------------------------------------------------------
# Hard caps
# ---------------------------------------------------------------------------


def _evaluate_hard_caps(
    raw: RawPageData,
    meta: ConfpubMeta | None,
    profile: ProfileConfig,
    classification: ResolvedClassification,
    body_anti_signals: list[str],
) -> list[dict[str, Any]]:
    """Evaluate all hard caps and return those that triggered."""
    triggered: list[dict[str, Any]] = []
    caps_by_name = {c.name: c for c in profile.hard_caps if c.enabled}

    # Archived / trashed
    if "archived" in caps_by_name and raw.status in ("archived", "trashed"):
        triggered.append({
            "name": "archived",
            "cap": caps_by_name["archived"].cap,
            "reason": f"Page status is '{raw.status}'",
        })

    # Superseded by
    if "superseded_by" in caps_by_name and meta and meta.superseded_by:
        triggered.append({
            "name": "superseded_by",
            "cap": caps_by_name["superseded_by"].cap,
            "reason": f"Superseded by '{meta.superseded_by}'",
        })

    # Anti-signal body
    if "anti_signal_body" in caps_by_name and body_anti_signals:
        triggered.append({
            "name": "anti_signal_body",
            "cap": caps_by_name["anti_signal_body"].cap,
            "reason": f"Body contains: {', '.join(body_anti_signals[:3])}",
        })

    # Overdue review
    if "overdue_review" in caps_by_name and meta and meta.reviewed_at and meta.review_interval_days:
        try:
            reviewed = datetime.fromisoformat(meta.reviewed_at)
            if reviewed.tzinfo is None:
                reviewed = reviewed.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            overdue_days = (now - reviewed).days - meta.review_interval_days
            if overdue_days > meta.review_interval_days:
                triggered.append({
                    "name": "overdue_review",
                    "cap": caps_by_name["overdue_review"].cap,
                    "reason": f"Review overdue by {overdue_days} days (interval: {meta.review_interval_days}d)",
                })
        except (ValueError, TypeError):
            pass

    # Title pattern
    if "title_pattern" in caps_by_name:
        if re.match(profile.title_cap_pattern, raw.title):
            triggered.append({
                "name": "title_pattern",
                "cap": caps_by_name["title_pattern"].cap,
                "reason": f"Title '{raw.title}' matches exclusion pattern",
            })

    # Lifecycle: draft
    if "lifecycle_draft" in caps_by_name and classification.lifecycle_state == "draft":
        triggered.append({
            "name": "lifecycle_draft",
            "cap": caps_by_name["lifecycle_draft"].cap,
            "reason": "Lifecycle state is 'draft'",
        })

    # Lifecycle: deprecated
    if "lifecycle_deprecated" in caps_by_name and classification.lifecycle_state == "deprecated":
        triggered.append({
            "name": "lifecycle_deprecated",
            "cap": caps_by_name["lifecycle_deprecated"].cap,
            "reason": "Lifecycle state is 'deprecated'",
        })

    # Scaffold class
    if "scaffold_class" in caps_by_name and classification.primary_class == "scaffold":
        triggered.append({
            "name": "scaffold_class",
            "cap": caps_by_name["scaffold_class"].cap,
            "reason": "Page is classified as scaffold (template/checklist/starter doc)",
        })

    # Personal space (key starts with ~)
    if "personal_space" in caps_by_name and raw.space_key.startswith("~"):
        triggered.append({
            "name": "personal_space",
            "cap": caps_by_name["personal_space"].cap,
            "reason": f"Page is in personal space '{raw.space_key}'",
        })

    # No owner and age > 90 days
    if "no_owner_90d" in caps_by_name:
        has_owner = bool(meta and meta.owner_account_id)
        if not has_owner:
            ref = raw.created or raw.version_when
            if ref:
                try:
                    created_dt = datetime.fromisoformat(ref)
                    if created_dt.tzinfo is None:
                        created_dt = created_dt.replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - created_dt).days
                    if age_days > 90:
                        triggered.append({
                            "name": "no_owner_90d",
                            "cap": caps_by_name["no_owner_90d"].cap,
                            "reason": f"No owner and page is {age_days} days old",
                        })
                except (ValueError, TypeError):
                    pass

    return triggered


# ---------------------------------------------------------------------------
# Weight renormalization
# ---------------------------------------------------------------------------


def _renormalize_weights(
    weights: dict[str, float],
    missing_subscores: set[str],
) -> dict[str, float]:
    """Redistribute weight from missing subscores proportionally."""
    available = {k: v for k, v in weights.items() if k not in missing_subscores}
    total = sum(available.values())
    if total <= 0:
        return {k: 0.0 for k in weights}
    return {k: (v / total if k in available else 0.0) for k, v in weights.items()}


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


def _compute_confidence(
    all_signals: list[Signal],
    weights: dict[str, float],
    missing_subscores: set[str],
) -> float:
    """Compute confidence based on signal completeness."""
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return 0.0

    missing_subscore_weight = sum(weights.get(s, 0.0) for s in missing_subscores)
    total_signal_weight = sum(s.weight for s in all_signals)
    missing_signal_weight = sum(s.weight for s in all_signals if s.status == "missing")
    partial_penalty = 0.0
    if total_signal_weight > 0:
        partial_penalty = (missing_signal_weight / total_signal_weight) * (total_weight - missing_subscore_weight) * 0.5

    confidence = 1.0 - (missing_subscore_weight + partial_penalty) / total_weight
    return round(max(0.0, min(1.0, confidence)), 2)


# ---------------------------------------------------------------------------
# Missing signals list
# ---------------------------------------------------------------------------

_ALWAYS_MISSING_SIGNALS: list[str] = [
    "content_state",
    "analytics.views",
    "analytics.unique_viewers",
    "watchers.count",
]


# ---------------------------------------------------------------------------
# Opportunistic scoring (cache warming)
# ---------------------------------------------------------------------------


def opportunistic_score(client: Any, page_id: str) -> None:
    """Score a page if not already cached. Never raises.

    Call this after any command that touches a page to keep the
    trust cache warm. Skips silently if the cache already has a
    fresh entry or if anything goes wrong.
    """
    try:
        cache = TrustCache()
        # Quick check: is there any fresh entry for this page?
        cur = cache._conn.execute(
            "SELECT expires_at FROM page_score_cache WHERE page_id = ? ORDER BY created_at DESC LIMIT 1",
            (page_id,),
        )
        row = cur.fetchone()
        if row:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            if now <= row[0]:
                cache.close()
                return  # fresh cache entry exists, skip

        cache.close()
        # Score the page (this handles its own caching)
        score_page(client, page_id=page_id, refresh=True)
    except Exception:
        pass  # never disrupt the primary command


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------


def score_page(
    client: Any,
    *,
    page_id: str | None = None,
    space: str | None = None,
    title: str | None = None,
    profile_name: str | None = None,
    doc_class_override: str | None = None,
    include_signals: bool = False,
    include_missing: bool = False,
    refresh: bool = False,
) -> PageScoreResult:
    """Score a single page for operational trustworthiness."""
    # 1. Collect raw data
    raw = _collect_raw_data(client, page_id=page_id, space=space, title=title)

    # 2. Resolve classification and profile
    classification = _resolve_classification(
        doc_class_override, raw.meta_property, raw.labels, raw.title, raw.status,
    )
    primary_class = classification.primary_class
    profile = resolve_profile(profile_name, raw.meta_property)

    # 3. Check cache (unless refresh)
    cache: TrustCache | None = None
    cache_key = ""
    site_url = ""
    try:
        from confpub.config import load_config
        cfg = load_config()
        site_url = cfg.base_url or ""
    except Exception:
        pass

    if not refresh:
        try:
            cache = TrustCache()
            cache_key = TrustCache.make_cache_key(
                site_url, raw.page_id, raw.version_number, profile.name, primary_class,
            )
            cached_result, is_stale = cache.get_page_score(cache_key)
            if cached_result is not None and not is_stale:
                cached_result.cache = {"hit": True, "stale": False, "age_seconds": 0}
                if not include_signals:
                    cached_result.signals = None
                if not include_missing:
                    cached_result.missing_signals = None
                    cached_result.capabilities = None
                    cached_result.weight_renormalization = None
                return cached_result
        except Exception as exc:
            emit_stderr(f"Trust cache read failed (non-fatal): {exc}")
            cache = None

    # 4. Analyze body
    body_features = analyze_body(raw.body_storage, profile.anti_signal_patterns)

    # 5. Compute subscores
    stew_score, stew_signals = _compute_stewardship(raw, raw.meta_property)
    fresh_score, fresh_signals = _compute_freshness(raw, raw.meta_property, profile, primary_class)
    ev_score, ev_signals = _compute_evidence(raw, raw.meta_property, body_features)
    struct_score, struct_signals = _compute_structure(raw, profile)
    corr_score, corr_signals = _compute_corroboration()

    subscores = {
        "stewardship": round(stew_score, 4),
        "freshness": round(fresh_score, 4),
        "evidence": round(ev_score, 4),
        "structure": round(struct_score, 4),
        "corroboration": round(corr_score, 4),
    }

    all_signals = stew_signals + fresh_signals + ev_signals + struct_signals + corr_signals

    # 6. Weight renormalization (corroboration entirely missing)
    missing_subscores = {"corroboration"}
    renormalized = _renormalize_weights(profile.weights, missing_subscores)

    # 7. Weighted sum
    weighted_sum = sum(renormalized[k] * subscores[k] for k in renormalized)

    # 8. Hard caps
    triggered_caps = _evaluate_hard_caps(
        raw, raw.meta_property, profile, classification, body_features.anti_signal_matches,
    )
    cap_multiplier = min((c["cap"] for c in triggered_caps), default=1.0)

    # 9. Final score
    raw_score = round(100 * cap_multiplier * weighted_sum)
    if primary_class == "record":
        raw_score = min(raw_score, profile.record_score_cap)
    final_score = max(0, min(100, raw_score))

    # 10. Trust anchors (user-declared overrides)
    anchor_info = None
    try:
        from confpub.trust.anchors import apply_anchor
        final_score, anchor_info = apply_anchor(
            final_score, raw.space_key, raw.page_id,
            has_hard_caps=bool(triggered_caps),
        )
    except Exception:
        pass

    # 11. Band (after anchor adjustment)
    band = band_for_score(final_score)

    # 12. Confidence
    confidence = _compute_confidence(all_signals, profile.weights, missing_subscores)

    # 13. Capabilities
    capabilities = Capabilities()

    # 14. Build result
    now_iso = datetime.now(timezone.utc).isoformat()
    advisory = advisory_for(band, confidence)
    result = PageScoreResult(
        algorithm_version=ALGORITHM_VERSION,
        profile=profile.name,
        primary_class=primary_class,
        subtype=classification.subtype,
        lifecycle_state=classification.lifecycle_state,
        score=final_score,
        band=band,
        confidence=confidence,
        advisory=advisory,
        anchor=anchor_info,
        hard_caps=triggered_caps,
        subscores=subscores,
        page_version=raw.version_number,
        scored_at=now_iso,
    )

    # Always populate full detail for the cache
    result.signals = [s.model_dump(mode="json") for s in all_signals]
    result.missing_signals = list(_ALWAYS_MISSING_SIGNALS)
    result.capabilities = capabilities.model_dump(mode="json")
    result.weight_renormalization = {k: round(v, 4) for k, v in renormalized.items()}
    if classification.reasoning:
        result.classification = classification.reasoning.model_dump(mode="json")

    # 14. Write to cache (with full detail)
    try:
        if cache is None:
            cache = TrustCache()
        if not cache_key:
            cache_key = TrustCache.make_cache_key(
                site_url, raw.page_id, raw.version_number, profile.name, primary_class,
            )
        result.cache = {"hit": False, "stale": False, "age_seconds": 0}
        cache.put_page_score(
            cache_key,
            result,
            site_url=site_url,
            page_id=raw.page_id,
            title=raw.title,
            space_key=raw.space_key,
            page_version=raw.version_number,
            profile=profile.name,
            doc_class=primary_class,
        )
    except Exception as exc:
        emit_stderr(f"Trust cache write failed (non-fatal): {exc}")
        result.cache = None

    # Strip verbose fields from the returned result if not requested
    if not include_signals:
        result.signals = None
    if not include_missing:
        result.missing_signals = None
        result.capabilities = None
        result.weight_renormalization = None
        result.classification = None

    return result
