"""Tests for the trust scoring engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from confpub.errors import ConfpubError
from confpub.trust.body_parser import BodyFeatures, analyze_body
from confpub.trust.models import ConfpubMeta, RawPageData, ResolvedClassification
from confpub.trust.profiles import get_profile, resolve_profile
from confpub.trust.scoring import (
    _compute_corroboration,
    _compute_evidence,
    _compute_freshness,
    _compute_stewardship,
    _compute_structure,
    _evaluate_hard_caps,
    _renormalize_weights,
    _resolve_classification,
    score_page,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw(
    *,
    title: str = "Architecture Overview",
    status: str = "current",
    body: str = "<p>Some content with enough length to pass the threshold easily.</p><h2>Section</h2><p>More content here.</p>",
    version: int = 5,
    version_when: str = "",
    labels: list | None = None,
    meta: ConfpubMeta | None = None,
    history: list | None = None,
) -> RawPageData:
    if not version_when:
        version_when = datetime.now(timezone.utc).isoformat()
    return RawPageData(
        page_id="12345",
        space_key="EA",
        title=title,
        status=status,
        body_storage=body,
        version_number=version,
        version_when=version_when,
        version_by="testuser",
        created=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        labels=labels or [],
        meta_property=meta,
        history=history or [],
    )


def _full_meta(**overrides) -> ConfpubMeta:
    defaults = {
        "primary_class": "governance",
        "subtype": "standard",
        "lifecycle_state": "approved",
        "owner_account_id": "abc123",
        "reviewed_at": datetime.now(timezone.utc).date().isoformat(),
        "review_interval_days": 180,
        "approvers": ["acct:1"],
        "authoritative_sources": [
            {"type": "repo", "ref": "https://github.com/org/repo"},
            {"type": "jira", "ref": "ARCH-123"},
        ],
        "source_of_record": {"type": "git", "ref": "main"},
    }
    defaults.update(overrides)
    return ConfpubMeta(**defaults)


# ---------------------------------------------------------------------------
# Classification resolution
# ---------------------------------------------------------------------------


class TestClassificationResolution:
    def test_cli_override_wins(self):
        c = _resolve_classification("instruction", _full_meta(primary_class="governance"), [], "Test", "current")
        assert c.primary_class == "instruction"

    def test_meta_primary_class_used(self):
        c = _resolve_classification(None, _full_meta(primary_class="specification"), [], "Test", "current")
        assert c.primary_class == "specification"

    def test_legacy_doc_class_mapped(self):
        meta = ConfpubMeta(doc_class="runbook")
        c = _resolve_classification(None, meta, [], "Test", "current")
        assert c.primary_class == "instruction"

    def test_legacy_doc_class_adr_maps_to_decision(self):
        meta = ConfpubMeta(doc_class="adr")
        c = _resolve_classification(None, meta, [], "Test", "current")
        assert c.primary_class == "decision"

    def test_legacy_doc_class_policy_maps_to_governance(self):
        meta = ConfpubMeta(doc_class="policy")
        c = _resolve_classification(None, meta, [], "Test", "current")
        assert c.primary_class == "governance"

    def test_legacy_cli_override_mapped(self):
        c = _resolve_classification("runbook", None, [], "Test", "current")
        assert c.primary_class == "instruction"

    def test_label_inference_governance(self):
        labels = [{"name": "policy"}]
        c = _resolve_classification(None, None, labels, "Test", "current")
        assert c.primary_class == "governance"

    def test_label_inference_instruction(self):
        labels = [{"name": "runbook"}]
        c = _resolve_classification(None, None, labels, "Test", "current")
        assert c.primary_class == "instruction"

    def test_label_inference_decision(self):
        labels = [{"name": "adr"}]
        c = _resolve_classification(None, None, labels, "Test", "current")
        assert c.primary_class == "decision"

    def test_title_inference_adr(self):
        c = _resolve_classification(None, None, [], "ADR-001 Use PostgreSQL", "current")
        assert c.primary_class == "decision"

    def test_title_inference_meeting_notes(self):
        c = _resolve_classification(None, None, [], "Weekly Meeting Notes", "current")
        assert c.primary_class == "record"

    def test_title_inference_runbook(self):
        c = _resolve_classification(None, None, [], "Database Runbook", "current")
        assert c.primary_class == "instruction"

    def test_fallback_unknown(self):
        c = _resolve_classification(None, None, [], "Some Page", "current")
        assert c.primary_class == "unknown"

    def test_invalid_override_raises(self):
        with pytest.raises(ConfpubError) as exc_info:
            _resolve_classification("nonexistent", None, [], "Test", "current")
        assert exc_info.value.code == "ERR_VALIDATION_TRUST_DOC_CLASS"

    def test_lifecycle_from_meta(self):
        meta = ConfpubMeta(lifecycle_state="draft")
        c = _resolve_classification(None, meta, [], "Test", "current")
        assert c.lifecycle_state == "draft"

    def test_lifecycle_from_label(self):
        labels = [{"name": "deprecated"}]
        c = _resolve_classification(None, None, labels, "Test", "current")
        assert c.lifecycle_state == "deprecated"

    def test_lifecycle_from_page_status(self):
        c = _resolve_classification(None, None, [], "Test", "archived")
        assert c.lifecycle_state == "archived"

    def test_subtype_from_meta(self):
        meta = ConfpubMeta(primary_class="governance", subtype="policy")
        c = _resolve_classification(None, meta, [], "Test", "current")
        assert c.subtype == "policy"


# ---------------------------------------------------------------------------
# Profile resolution
# ---------------------------------------------------------------------------


class TestProfileResolution:
    def test_cli_override_wins(self):
        p = resolve_profile("working-area", _full_meta(profile="official-knowledge"))
        assert p.name == "working-area"

    def test_meta_profile(self):
        p = resolve_profile(None, _full_meta(profile="historical-record"))
        assert p.name == "historical-record"

    def test_default_profile(self):
        p = resolve_profile(None, None)
        assert p.name == "official-knowledge"

    def test_invalid_profile_raises(self):
        with pytest.raises(ConfpubError) as exc_info:
            get_profile("nonexistent")
        assert exc_info.value.code == "ERR_VALIDATION_TRUST_PROFILE"


# ---------------------------------------------------------------------------
# Stewardship subscore
# ---------------------------------------------------------------------------


class TestStewardshipSubscore:
    def test_full_signals(self):
        meta = _full_meta()
        raw = _make_raw(
            meta=meta,
            version=5,
            history=[
                {"number": 5, "when": "2026-03-26", "by": "user1", "message": "Updated docs"},
                {"number": 4, "when": "2026-03-20", "by": "user1", "message": "Fixed typo"},
                {"number": 3, "when": "2026-03-15", "by": "user2", "message": ""},
            ],
        )
        score, signals = _compute_stewardship(raw, meta)
        assert score > 0.8
        assert any(s.id == "owner.present" and s.status == "positive" for s in signals)
        assert any(s.id == "content_state.final" and s.status == "missing" for s in signals)

    def test_empty_meta_low_score(self):
        raw = _make_raw(version=1)
        score, signals = _compute_stewardship(raw, None)
        assert score < 0.3

    def test_owner_inference(self):
        raw = _make_raw(
            version=2,
            history=[
                {"number": 2, "when": "2026-03-26", "by": "user1", "message": ""},
                {"number": 1, "when": "2026-01-01", "by": "original_author", "message": ""},
            ],
        )
        score, signals = _compute_stewardship(raw, None)
        owner_signal = next(s for s in signals if s.id == "owner.present")
        assert owner_signal.status == "positive"
        assert owner_signal.inferred is True


# ---------------------------------------------------------------------------
# Freshness subscore
# ---------------------------------------------------------------------------


class TestFreshnessSubscore:
    def test_fresh_page(self):
        raw = _make_raw(version_when=datetime.now(timezone.utc).isoformat())
        profile = get_profile("official-knowledge")
        score, _ = _compute_freshness(raw, None, profile, "governance")
        assert score > 0.95

    def test_half_life_decay(self):
        ref = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        raw = _make_raw(version_when=ref)
        profile = get_profile("official-knowledge")
        score, _ = _compute_freshness(raw, None, profile, "instruction")
        assert 0.45 < score < 0.55  # instruction half-life = 120 days

    def test_very_old_page(self):
        ref = (datetime.now(timezone.utc) - timedelta(days=1000)).isoformat()
        raw = _make_raw(version_when=ref)
        profile = get_profile("official-knowledge")
        score, _ = _compute_freshness(raw, None, profile, "governance")
        assert score < 0.15

    def test_reviewed_at_preferred(self):
        old = (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()
        recent = datetime.now(timezone.utc).date().isoformat()
        meta = _full_meta(reviewed_at=recent)
        raw = _make_raw(version_when=old, meta=meta)
        profile = get_profile("official-knowledge")
        score, signals = _compute_freshness(raw, meta, profile, "governance")
        assert score > 0.9
        assert signals[0].source == "confpub.meta.v1.reviewed_at"

    def test_decision_class_capped_at_080(self):
        raw = _make_raw(version_when=datetime.now(timezone.utc).isoformat())
        profile = get_profile("official-knowledge")
        score, _ = _compute_freshness(raw, None, profile, "decision")
        assert score <= 0.80

    def test_different_class_half_lives(self):
        ref = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        raw = _make_raw(version_when=ref)
        profile = get_profile("official-knowledge")
        # Report half-life = 45 days (fast decay)
        report_score, _ = _compute_freshness(raw, None, profile, "report")
        # Governance half-life = 365 days (slow decay)
        gov_score, _ = _compute_freshness(raw, None, profile, "governance")
        assert report_score < gov_score


# ---------------------------------------------------------------------------
# Evidence subscore
# ---------------------------------------------------------------------------


class TestEvidenceSubscore:
    def test_full_evidence(self):
        meta = _full_meta()
        raw = _make_raw(meta=meta, body='<p><a href="https://x.com">link</a></p>' * 5)
        features = analyze_body(raw.body_storage)
        score, signals = _compute_evidence(raw, meta, features)
        assert score > 0.5

    def test_no_meta_no_links(self):
        raw = _make_raw(body="<p>Plain text</p>")
        features = analyze_body(raw.body_storage)
        score, signals = _compute_evidence(raw, None, features)
        assert score < 0.2

    def test_body_links_improve_score(self):
        raw0 = _make_raw(body="<p>No links</p>")
        raw3 = _make_raw(body='<p><a href="https://a.com">A</a> <a href="https://b.com">B</a> <a href="https://c.com">C</a></p>')
        f0 = analyze_body(raw0.body_storage)
        f3 = analyze_body(raw3.body_storage)
        score_low, _ = _compute_evidence(raw0, None, f0)
        score_high, _ = _compute_evidence(raw3, None, f3)
        assert score_high > score_low

    def test_jira_macros_in_body(self):
        raw = _make_raw(body='<ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">PROJ-123</ac:parameter></ac:structured-macro>')
        features = analyze_body(raw.body_storage)
        score, signals = _compute_evidence(raw, None, features)
        jira_signal = next(s for s in signals if s.id == "jira_refs")
        assert jira_signal.status == "positive"


# ---------------------------------------------------------------------------
# Structure subscore
# ---------------------------------------------------------------------------


class TestStructureSubscore:
    def test_well_structured(self):
        html = (
            '<ac:structured-macro ac:name="excerpt"><ac:rich-text-body><p>Summary</p></ac:rich-text-body></ac:structured-macro>'
            "<h2>Overview</h2><p>" + "x " * 200 + "</p>"
            "<h2>Details</h2><p>" + "y " * 200 + "</p>"
        )
        raw = _make_raw(body=html, labels=[{"name": "governance"}])
        profile = get_profile("official-knowledge")
        score, _ = _compute_structure(raw, profile)
        assert score > 0.7

    def test_stub_page(self):
        raw = _make_raw(body="<p>Short</p>")
        profile = get_profile("official-knowledge")
        score, _ = _compute_structure(raw, profile)
        assert score < 0.5

    def test_placeholder_penalty(self):
        raw = _make_raw(body="<p>TODO: fill this in. Coming soon.</p>" + "x " * 200)
        profile = get_profile("official-knowledge")
        score, signals = _compute_structure(raw, profile)
        placeholder_signal = next(s for s in signals if s.id == "no_placeholder")
        assert placeholder_signal.status == "negative"

    def test_empty_sections(self):
        html = "<h2>Section A</h2><h2>Section B</h2><p>Content</p>"
        raw = _make_raw(body=html)
        profile = get_profile("official-knowledge")
        score, signals = _compute_structure(raw, profile)
        empty_signal = next(s for s in signals if s.id == "no_empty_sections")
        assert empty_signal.status == "negative"


# ---------------------------------------------------------------------------
# Corroboration subscore
# ---------------------------------------------------------------------------


class TestCorroborationSubscore:
    def test_always_zero_in_phase1(self):
        score, signals = _compute_corroboration()
        assert score == 0.0
        assert all(s.status == "missing" for s in signals)


# ---------------------------------------------------------------------------
# Hard caps
# ---------------------------------------------------------------------------


class TestHardCaps:
    def test_archived(self):
        raw = _make_raw(status="archived")
        profile = get_profile("official-knowledge")
        cls = ResolvedClassification(primary_class="unknown")
        caps = _evaluate_hard_caps(raw, None, profile, cls, [])
        assert any(c["name"] == "archived" and c["cap"] == 0.10 for c in caps)

    def test_superseded_by(self):
        meta = _full_meta(superseded_by="page:999")
        raw = _make_raw(meta=meta)
        profile = get_profile("official-knowledge")
        cls = ResolvedClassification(primary_class="governance")
        caps = _evaluate_hard_caps(raw, meta, profile, cls, [])
        assert any(c["name"] == "superseded_by" for c in caps)

    def test_anti_signal_body(self):
        raw = _make_raw()
        profile = get_profile("official-knowledge")
        cls = ResolvedClassification(primary_class="unknown")
        caps = _evaluate_hard_caps(raw, None, profile, cls, ["deprecated"])
        assert any(c["name"] == "anti_signal_body" for c in caps)

    def test_title_pattern(self):
        raw = _make_raw(title="Copy of Old Page")
        profile = get_profile("official-knowledge")
        cls = ResolvedClassification(primary_class="unknown")
        caps = _evaluate_hard_caps(raw, None, profile, cls, [])
        assert any(c["name"] == "title_pattern" for c in caps)

    def test_lifecycle_draft_cap(self):
        raw = _make_raw()
        profile = get_profile("official-knowledge")
        cls = ResolvedClassification(primary_class="instruction", lifecycle_state="draft")
        caps = _evaluate_hard_caps(raw, None, profile, cls, [])
        assert any(c["name"] == "lifecycle_draft" for c in caps)

    def test_lifecycle_deprecated_cap(self):
        raw = _make_raw()
        profile = get_profile("official-knowledge")
        cls = ResolvedClassification(primary_class="governance", lifecycle_state="deprecated")
        caps = _evaluate_hard_caps(raw, None, profile, cls, [])
        assert any(c["name"] == "lifecycle_deprecated" for c in caps)

    def test_scaffold_class_cap(self):
        raw = _make_raw()
        profile = get_profile("official-knowledge")
        cls = ResolvedClassification(primary_class="scaffold")
        caps = _evaluate_hard_caps(raw, None, profile, cls, [])
        assert any(c["name"] == "scaffold_class" for c in caps)

    def test_no_caps_returns_empty(self):
        raw = _make_raw(title="Architecture Overview")
        profile = get_profile("official-knowledge")
        cls = ResolvedClassification(primary_class="governance", lifecycle_state="approved")
        caps = _evaluate_hard_caps(raw, _full_meta(), profile, cls, [])
        assert len(caps) == 0

    def test_multiple_caps_all_returned(self):
        raw = _make_raw(status="archived", title="Copy of Something")
        profile = get_profile("official-knowledge")
        cls = ResolvedClassification(primary_class="scaffold", lifecycle_state="deprecated")
        caps = _evaluate_hard_caps(raw, None, profile, cls, ["obsolete"])
        assert len(caps) >= 4  # archived + title + scaffold + deprecated + anti_signal


# ---------------------------------------------------------------------------
# Weight renormalization
# ---------------------------------------------------------------------------


class TestWeightRenormalization:
    def test_no_missing(self):
        weights = {"a": 0.5, "b": 0.3, "c": 0.2}
        result = _renormalize_weights(weights, set())
        assert abs(sum(result.values()) - 1.0) < 1e-9

    def test_one_missing(self):
        weights = {"a": 0.5, "b": 0.3, "c": 0.2}
        result = _renormalize_weights(weights, {"c"})
        assert result["c"] == 0.0
        assert abs(result["a"] + result["b"] - 1.0) < 1e-9

    def test_corroboration_missing(self):
        from confpub.trust.models import DEFAULT_WEIGHTS
        result = _renormalize_weights(DEFAULT_WEIGHTS, {"corroboration"})
        assert result["corroboration"] == 0.0
        assert abs(sum(result.values()) - 1.0) < 1e-9
        assert abs(result["stewardship"] - 0.3333) < 0.01


# ---------------------------------------------------------------------------
# Body parser
# ---------------------------------------------------------------------------


class TestBodyParser:
    def test_headings(self):
        f = analyze_body("<h1>Title</h1><h2>Sub</h2><p>Text</p>")
        assert f.heading_count == 2

    def test_outbound_links(self):
        f = analyze_body('<p><a href="https://example.com">Link</a></p>')
        assert f.outbound_link_count >= 1

    def test_placeholder_detection(self):
        f = analyze_body("<p>TODO: implement this. Also TBD and FIXME</p>")
        assert len(f.placeholder_texts) == 3

    def test_empty_sections(self):
        f = analyze_body("<h2>A</h2><h2>B</h2><p>Content</p>")
        assert f.empty_section_count == 1

    def test_anti_signal_detection(self):
        f = analyze_body(
            "<p>This page is deprecated and should not be used.</p>",
            anti_signal_patterns=[r"(?i)\bdeprecated\b"],
        )
        assert len(f.anti_signal_matches) > 0

    def test_excerpt_detection(self):
        f = analyze_body('<ac:structured-macro ac:name="excerpt"><p>Summary</p></ac:structured-macro>')
        assert f.has_excerpt is True


# ---------------------------------------------------------------------------
# End-to-end scoring (mocked client)
# ---------------------------------------------------------------------------


def _mock_client(
    page: dict | None = None,
    labels: list | None = None,
    meta: dict | None = None,
    history: list | None = None,
):
    client = MagicMock()
    client.get_page_by_id.return_value = page or {
        "id": "12345",
        "title": "Architecture Overview",
        "status": "current",
        "version": {"number": 5, "when": datetime.now(timezone.utc).isoformat(), "by": {"displayName": "testuser"}},
        "body": {"storage": {"value": "<h2>Overview</h2><p>" + "x " * 200 + "</p>"}},
        "space": {"key": "EA"},
        "ancestors": [{"id": "99"}],
    }
    client.get_labels.return_value = labels or [{"name": "governance"}]

    if meta is not None:
        client.get_page_property.return_value = {"key": "confpub.meta.v1", "value": meta, "version": 1}
    else:
        client.get_page_property.side_effect = ConfpubError("ERR_VALIDATION_NOT_FOUND", "Not found")

    client.get_page_history.return_value = history or [
        {"number": 5, "when": datetime.now(timezone.utc).isoformat(), "by": "testuser", "message": "Updated"},
        {"number": 4, "when": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(), "by": "testuser", "message": "Refactored"},
        {"number": 3, "when": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(), "by": "otheruser", "message": ""},
    ]
    client._call_count = 0
    return client


class TestEndToEndScoring:
    @patch("confpub.trust.scoring.TrustCache")
    @patch("confpub.config.load_config")
    def test_high_quality_page(self, mock_config, MockCache):
        mock_config.return_value = MagicMock(base_url="https://x.atlassian.net")
        MockCache.return_value = MagicMock()
        MockCache.return_value.get_page_score.return_value = (None, False)
        MockCache.make_cache_key = TrustCache_make_cache_key_stub

        meta = _full_meta()
        client = _mock_client(meta=meta.model_dump())
        result = score_page(client, page_id="12345", refresh=True)

        assert result.score >= 50
        assert result.band in ("good", "high", "caution")
        assert result.confidence > 0.5
        assert result.primary_class == "governance"

    @patch("confpub.trust.scoring.TrustCache")
    @patch("confpub.config.load_config")
    def test_orphan_page(self, mock_config, MockCache):
        mock_config.return_value = MagicMock(base_url="https://x.atlassian.net")
        MockCache.return_value = MagicMock()
        MockCache.return_value.get_page_score.return_value = (None, False)
        MockCache.make_cache_key = TrustCache_make_cache_key_stub

        old_date = (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()
        client = _mock_client(
            page={
                "id": "99999",
                "title": "Old Orphan",
                "status": "current",
                "version": {"number": 1, "when": old_date, "by": {"displayName": "someone"}},
                "body": {"storage": {"value": "<p>Stub</p>"}},
                "space": {"key": "EA"},
                "ancestors": [],
            },
            labels=[],
            history=[{"number": 1, "when": old_date, "by": "someone", "message": ""}],
        )
        result = score_page(client, page_id="99999", refresh=True)
        assert result.score < 50
        assert result.band == "low"

    @patch("confpub.trust.scoring.TrustCache")
    @patch("confpub.config.load_config")
    def test_include_signals(self, mock_config, MockCache):
        mock_config.return_value = MagicMock(base_url="https://x.atlassian.net")
        MockCache.return_value = MagicMock()
        MockCache.return_value.get_page_score.return_value = (None, False)
        MockCache.make_cache_key = TrustCache_make_cache_key_stub

        client = _mock_client()
        result = score_page(client, page_id="12345", include_signals=True, refresh=True)
        assert result.signals is not None
        assert len(result.signals) > 0

    @patch("confpub.trust.scoring.TrustCache")
    @patch("confpub.config.load_config")
    def test_include_missing(self, mock_config, MockCache):
        mock_config.return_value = MagicMock(base_url="https://x.atlassian.net")
        MockCache.return_value = MagicMock()
        MockCache.return_value.get_page_score.return_value = (None, False)
        MockCache.make_cache_key = TrustCache_make_cache_key_stub

        client = _mock_client()
        result = score_page(client, page_id="12345", include_missing=True, refresh=True)
        assert result.missing_signals is not None
        assert "analytics.views" in result.missing_signals
        assert result.capabilities is not None

    @patch("confpub.trust.scoring.TrustCache")
    @patch("confpub.config.load_config")
    def test_record_class_cap(self, mock_config, MockCache):
        mock_config.return_value = MagicMock(base_url="https://x.atlassian.net")
        MockCache.return_value = MagicMock()
        MockCache.return_value.get_page_score.return_value = (None, False)
        MockCache.make_cache_key = TrustCache_make_cache_key_stub

        meta = _full_meta(primary_class="record")
        client = _mock_client(
            meta=meta.model_dump(),
            labels=[{"name": "meeting-notes"}],
        )
        result = score_page(
            client, page_id="12345",
            doc_class_override="record",
            refresh=True,
        )
        assert result.score <= 65
        assert result.primary_class == "record"

    @patch("confpub.trust.scoring.TrustCache")
    @patch("confpub.config.load_config")
    def test_legacy_doc_class_override(self, mock_config, MockCache):
        mock_config.return_value = MagicMock(base_url="https://x.atlassian.net")
        MockCache.return_value = MagicMock()
        MockCache.return_value.get_page_score.return_value = (None, False)
        MockCache.make_cache_key = TrustCache_make_cache_key_stub

        client = _mock_client()
        result = score_page(client, page_id="12345", doc_class_override="runbook", refresh=True)
        assert result.primary_class == "instruction"

    @patch("confpub.trust.scoring.TrustCache")
    @patch("confpub.config.load_config")
    def test_lifecycle_state_in_result(self, mock_config, MockCache):
        mock_config.return_value = MagicMock(base_url="https://x.atlassian.net")
        MockCache.return_value = MagicMock()
        MockCache.return_value.get_page_score.return_value = (None, False)
        MockCache.make_cache_key = TrustCache_make_cache_key_stub

        meta = _full_meta(lifecycle_state="approved")
        client = _mock_client(meta=meta.model_dump())
        result = score_page(client, page_id="12345", refresh=True)
        assert result.lifecycle_state == "approved"


def TrustCache_make_cache_key_stub(site_url, page_id, page_version, profile, doc_class):
    return f"{site_url}|{page_id}|{page_version}|{profile}|{doc_class}"


# ---------------------------------------------------------------------------
# New title pattern tests (expanded heuristics)
# ---------------------------------------------------------------------------


class TestExpandedTitlePatterns:
    """Tests for the expanded title-based classification heuristics."""

    # instruction patterns
    def test_step_n_instruction(self):
        c = _resolve_classification(None, None, [], "STEP 3: Configure Networking", "current")
        assert c.primary_class == "instruction"

    def test_getting_started_instruction(self):
        c = _resolve_classification(None, None, [], "Getting started with Kubernetes", "current")
        assert c.primary_class == "instruction"

    def test_onboarding_instruction(self):
        c = _resolve_classification(None, None, [], "Developer Onboarding Guide", "current")
        assert c.primary_class == "instruction"

    def test_decommission_instruction(self):
        c = _resolve_classification(None, None, [], "Service Decommission Checklist", "current")
        assert c.primary_class == "instruction"

    def test_preparation_guide_instruction(self):
        c = _resolve_classification(None, None, [], "DR Preparation Guide", "current")
        assert c.primary_class == "instruction"

    def test_setup_guide_instruction(self):
        c = _resolve_classification(None, None, [], "Development Setup Guide", "current")
        assert c.primary_class == "instruction"

    def test_quick_start_instruction(self):
        c = _resolve_classification(None, None, [], "Quick Start for New Developers", "current")
        assert c.primary_class == "instruction"

    def test_tutorial_instruction(self):
        c = _resolve_classification(None, None, [], "Git Tutorial for Beginners", "current")
        assert c.primary_class == "instruction"

    def test_troubleshooting_instruction(self):
        c = _resolve_classification(None, None, [], "Network Troubleshooting", "current")
        assert c.primary_class == "instruction"

    # reference patterns
    def test_terminology_reference(self):
        c = _resolve_classification(None, None, [], "CLD2 Terminology", "current")
        assert c.primary_class == "reference"

    def test_api_example_reference(self):
        c = _resolve_classification(None, None, [], "REST API Example", "current")
        assert c.primary_class == "reference"

    def test_terraform_example_reference(self):
        c = _resolve_classification(None, None, [], "Terraform Example for VPCs", "current")
        assert c.primary_class == "reference"

    def test_tldr_reference(self):
        c = _resolve_classification(None, None, [], "TL;DR Cloud Migration", "current")
        assert c.primary_class == "reference"

    def test_best_practices_reference(self):
        c = _resolve_classification(None, None, [], "Best Practices for Logging", "current")
        assert c.primary_class == "reference"

    def test_resource_catalog_reference(self):
        c = _resolve_classification(None, None, [], "Service Resource Catalog", "current")
        assert c.primary_class == "reference"

    def test_cheat_sheet_reference(self):
        c = _resolve_classification(None, None, [], "Kubernetes Cheat Sheet", "current")
        assert c.primary_class == "reference"

    # hub patterns
    def test_all_caps_title_hub(self):
        c = _resolve_classification(None, None, [], "CLOUD PLATFORM", "current")
        assert c.primary_class == "hub"

    def test_all_caps_with_ampersand_hub(self):
        c = _resolve_classification(None, None, [], "SECURITY & COMPLIANCE", "current")
        assert c.primary_class == "hub"

    def test_overview_suffix_hub(self):
        c = _resolve_classification(None, None, [], "Platform Overview", "current")
        assert c.primary_class == "hub"

    def test_table_of_contents_hub(self):
        c = _resolve_classification(None, None, [], "Table of Contents", "current")
        assert c.primary_class == "hub"

    # governance patterns (EAGOV)
    def test_mandate_governance(self):
        c = _resolve_classification(None, None, [], "Data Retention Mandate", "current")
        assert c.primary_class == "governance"

    def test_principles_governance(self):
        c = _resolve_classification(None, None, [], "Architecture Principles", "current")
        assert c.primary_class == "governance"

    def test_guidelines_governance(self):
        c = _resolve_classification(None, None, [], "API Guidelines", "current")
        assert c.primary_class == "governance"

    def test_eagov_numbered_governance(self):
        c = _resolve_classification(None, None, [], "EAGOV-012 Data Classification", "current")
        assert c.primary_class == "governance"

    def test_governance_scope_governance(self):
        c = _resolve_classification(None, None, [], "Enterprise Governance Scope", "current")
        assert c.primary_class == "governance"

    # specification patterns
    def test_submission_template_specification(self):
        c = _resolve_classification(None, None, [], "EAGOV Submission Template v2", "current")
        assert c.primary_class == "specification"

    # record patterns
    def test_action_log_record(self):
        c = _resolve_classification(None, None, [], "Q4 Action Log", "current")
        assert c.primary_class == "record"

    def test_survey_record(self):
        c = _resolve_classification(None, None, [], "Developer Survey Results", "current")
        assert c.primary_class == "record"

    def test_feedback_record(self):
        c = _resolve_classification(None, None, [], "Sprint Feedback Collection", "current")
        assert c.primary_class == "record"

    def test_issue_history_record(self):
        c = _resolve_classification(None, None, [], "Platform Issue History", "current")
        assert c.primary_class == "record"


# ---------------------------------------------------------------------------
# Classification explainability tests
# ---------------------------------------------------------------------------


class TestClassificationExplainability:
    """Tests that classification reasoning is populated correctly."""

    def test_cli_override_reasoning(self):
        c = _resolve_classification("instruction", None, [], "Test Page", "current")
        assert c.reasoning is not None
        assert c.reasoning.source == "cli_override"
        assert c.reasoning.matched_value == "instruction"

    def test_meta_primary_reasoning(self):
        meta = _full_meta(primary_class="governance")
        c = _resolve_classification(None, meta, [], "Test Page", "current")
        assert c.reasoning is not None
        assert c.reasoning.source == "meta_primary"
        assert c.reasoning.matched_value == "governance"

    def test_meta_legacy_reasoning(self):
        meta = ConfpubMeta(doc_class="runbook")
        c = _resolve_classification(None, meta, [], "Test Page", "current")
        assert c.reasoning is not None
        assert c.reasoning.source == "meta_legacy"
        assert c.reasoning.matched_value == "runbook"

    def test_label_reasoning(self):
        labels = [{"name": "policy"}]
        c = _resolve_classification(None, None, labels, "Test Page", "current")
        assert c.reasoning is not None
        assert c.reasoning.source == "label"
        assert c.reasoning.matched_value == "policy"

    def test_title_pattern_reasoning(self):
        c = _resolve_classification(None, None, [], "Getting started with Docker", "current")
        assert c.reasoning is not None
        assert c.reasoning.source == "title_pattern"
        assert c.reasoning.matched_value is not None
        assert len(c.reasoning.evaluated_title_patterns) > 0

    def test_default_reasoning_with_evaluated_patterns(self):
        c = _resolve_classification(None, None, [], "Something Completely Unique", "current")
        assert c.reasoning is not None
        assert c.reasoning.source == "default"
        assert c.primary_class == "unknown"
        # All title patterns should have been evaluated
        assert len(c.reasoning.evaluated_title_patterns) > 0
        assert all(not p["matched"] for p in c.reasoning.evaluated_title_patterns)

    def test_title_pattern_shows_which_matched(self):
        c = _resolve_classification(None, None, [], "STEP 1: Deploy the Service", "current")
        assert c.reasoning is not None
        assert c.reasoning.source == "title_pattern"
        # At least one pattern should show matched=True
        matched = [p for p in c.reasoning.evaluated_title_patterns if p["matched"]]
        assert len(matched) >= 1
        assert matched[0]["class"] == "instruction"


# ---------------------------------------------------------------------------
# Skill description validation tests
# ---------------------------------------------------------------------------


class TestSkillDescriptionValidation:
    """Tests for the 1024-char skill description limit."""

    def test_current_skill_description_under_limit(self):
        from confpub.skill_installer import SKILL_DESCRIPTION_MAX_LENGTH, _validate_skill_description, get_skill_data_path
        source = get_skill_data_path()
        result = _validate_skill_description(source)
        assert result is None, f"SKILL.md description exceeds {SKILL_DESCRIPTION_MAX_LENGTH} chars"

    def test_validates_over_limit(self, tmp_path):
        from confpub.skill_installer import _validate_skill_description
        skill = tmp_path / "SKILL.md"
        long_desc = "x" * 1100
        skill.write_text(f"---\nname: test\ndescription: {long_desc}\n---\n# Test\n")
        result = _validate_skill_description(tmp_path)
        assert result is not None
        assert result["length"] == 1100
        assert result["max_length"] == 1024
        assert result["excess"] == 76

    def test_validates_under_limit(self, tmp_path):
        from confpub.skill_installer import _validate_skill_description
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: test\ndescription: Short description\n---\n# Test\n")
        result = _validate_skill_description(tmp_path)
        assert result is None

    def test_install_raises_on_over_limit(self, tmp_path):
        from confpub.skill_installer import _validate_skill_description, SKILL_DESCRIPTION_MAX_LENGTH
        skill = tmp_path / "SKILL.md"
        long_desc = "x" * 1100
        skill.write_text(f"---\nname: test\ndescription: {long_desc}\n---\n# Test\n")
        result = _validate_skill_description(tmp_path)
        assert result is not None
        assert result["field"] == "description"


# ---------------------------------------------------------------------------
# Cache TTL configuration tests
# ---------------------------------------------------------------------------


class TestCacheTTLConfiguration:
    """Tests for the configurable cache TTL."""

    def test_default_ttl_is_seven_days(self):
        from confpub.trust.cache import _DEFAULT_TTL_PAGE_SCORE
        assert _DEFAULT_TTL_PAGE_SCORE == 604800

    def test_env_override_ttl(self, monkeypatch):
        monkeypatch.setenv("CONFPUB_CACHE_TTL", "3600")
        from confpub.trust.cache import _page_score_ttl
        assert _page_score_ttl() == 3600

    def test_invalid_env_ttl_uses_default(self, monkeypatch):
        monkeypatch.setenv("CONFPUB_CACHE_TTL", "not-a-number")
        from confpub.trust.cache import _page_score_ttl, _DEFAULT_TTL_PAGE_SCORE
        assert _page_score_ttl() == _DEFAULT_TTL_PAGE_SCORE
