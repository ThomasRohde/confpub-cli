"""Tests for trust scoring models and constants."""

import pytest

from confpub.trust.models import (
    ALGORITHM_VERSION,
    BANDS,
    DEFAULT_HALF_LIVES,
    DEFAULT_WEIGHTS,
    PRIMARY_CLASSES,
    LIFECYCLE_STATES,
    Capabilities,
    ConfpubMeta,
    HardCapConfig,
    PageScoreResult,
    ProfileConfig,
    RawPageData,
    ResolvedClassification,
    Signal,
    band_for_score,
)


class TestBandForScore:
    def test_high_band(self):
        assert band_for_score(85) == "high"
        assert band_for_score(100) == "high"

    def test_good_band(self):
        assert band_for_score(70) == "good"
        assert band_for_score(84) == "good"

    def test_caution_band(self):
        assert band_for_score(50) == "caution"
        assert band_for_score(69) == "caution"

    def test_low_band(self):
        assert band_for_score(0) == "low"
        assert band_for_score(49) == "low"

    def test_boundary_values(self):
        assert band_for_score(84) == "good"
        assert band_for_score(85) == "high"
        assert band_for_score(69) == "caution"
        assert band_for_score(70) == "good"
        assert band_for_score(49) == "low"
        assert band_for_score(50) == "caution"


class TestConstants:
    def test_primary_classes_complete(self):
        expected = {
            "hub", "governance", "instruction", "reference", "specification",
            "decision", "analysis", "plan", "report", "record",
            "people_org", "scaffold", "unknown",
        }
        assert set(PRIMARY_CLASSES) == expected

    def test_half_lives_cover_all_primary_classes(self):
        for cls in PRIMARY_CLASSES:
            assert cls in DEFAULT_HALF_LIVES, f"Missing half-life for {cls}"

    def test_weights_sum_to_one(self):
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9

    def test_algorithm_version(self):
        assert ALGORITHM_VERSION == "1.0"

    def test_lifecycle_states(self):
        assert "draft" in LIFECYCLE_STATES
        assert "active" in LIFECYCLE_STATES
        assert "deprecated" in LIFECYCLE_STATES
        assert "archived" in LIFECYCLE_STATES


class TestConfpubMeta:
    def test_minimal(self):
        meta = ConfpubMeta()
        assert meta.primary_class is None
        assert meta.lifecycle_state is None
        assert meta.approvers == []

    def test_full(self):
        meta = ConfpubMeta(
            primary_class="governance",
            subtype="standard",
            domain="engineering",
            lifecycle_state="approved",
            generation_mode="human",
            profile="official-knowledge",
            owner_account_id="abc123",
            reviewed_at="2026-03-20",
            review_interval_days=180,
            approvers=["acct:1"],
            authoritative_sources=[{"type": "repo", "ref": "https://git/..."}],
            source_of_record={"type": "git", "ref": "main"},
        )
        assert meta.primary_class == "governance"
        assert meta.subtype == "standard"
        assert meta.lifecycle_state == "approved"

    def test_legacy_doc_class_accepted(self):
        meta = ConfpubMeta(doc_class="runbook")
        assert meta.doc_class == "runbook"
        assert meta.primary_class is None  # not auto-mapped in the model

    def test_from_dict(self):
        data = {"schema_version": "1.0", "primary_class": "instruction", "owner_account_id": "x"}
        meta = ConfpubMeta(**data)
        assert meta.primary_class == "instruction"


class TestPageScoreResult:
    def test_serialization(self):
        result = PageScoreResult(
            profile="official-knowledge",
            primary_class="governance",
            score=81,
            band="good",
            confidence=0.85,
            subscores={"stewardship": 0.8, "freshness": 0.7, "evidence": 0.9, "structure": 0.6, "corroboration": 0.0},
            page_version=5,
            scored_at="2026-03-26T12:00:00Z",
        )
        d = result.model_dump(mode="json", exclude_none=True)
        assert d["score"] == 81
        assert d["primary_class"] == "governance"
        assert "signals" not in d

    def test_with_lifecycle_state(self):
        result = PageScoreResult(
            profile="official-knowledge",
            primary_class="instruction",
            lifecycle_state="draft",
            score=30,
            band="low",
            confidence=0.70,
            subscores={"stewardship": 0.5, "freshness": 0.5, "evidence": 0.5, "structure": 0.5, "corroboration": 0.0},
            page_version=1,
            scored_at="2026-03-26T12:00:00Z",
        )
        d = result.model_dump(mode="json", exclude_none=True)
        assert d["lifecycle_state"] == "draft"


class TestResolvedClassification:
    def test_defaults(self):
        c = ResolvedClassification()
        assert c.primary_class == "unknown"
        assert c.lifecycle_state is None

    def test_full(self):
        c = ResolvedClassification(
            primary_class="governance",
            subtype="policy",
            domain="security_risk",
            lifecycle_state="approved",
            generation_mode="human",
        )
        assert c.primary_class == "governance"
        assert c.subtype == "policy"


class TestSignal:
    def test_signal_creation(self):
        s = Signal(
            id="owner.present",
            status="positive",
            weight=0.22,
            value=True,
            source="confpub.meta.v1",
        )
        assert s.inferred is False
        d = s.model_dump()
        assert d["id"] == "owner.present"
