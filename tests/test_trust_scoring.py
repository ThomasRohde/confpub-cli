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
