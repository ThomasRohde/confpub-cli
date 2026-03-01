"""Tests for confpub.manifest module."""

import pytest
from pathlib import Path

from confpub.errors import ConfpubError, ERR_VALIDATION_MANIFEST, ERR_IO_FILE_NOT_FOUND
from confpub.manifest import (
    FlatPage,
    Manifest,
    ManifestPage,
    PlanArtifact,
    PlanPage,
    PlanSummary,
    load_manifest,
    resolve_page_tree,
)


SAMPLE_MANIFEST_YAML = """\
schema_version: "1.0"
space: DEV
parent: "Architecture Notes"
conflict_strategy: fail
on_removal: leave
labels:
  - architecture
  - auto-published
pages:
  - title: "Overview"
    file: overview.md
  - title: "Component Design"
    file: components/design.md
    assets:
      - components/diagrams/*.png
    children:
      - title: "API Reference"
        file: components/api.md
"""


class TestManifestModel:
    def test_parse_basic(self):
        import yaml
        data = yaml.safe_load(SAMPLE_MANIFEST_YAML)
        m = Manifest(**data)
        assert m.space == "DEV"
        assert m.parent == "Architecture Notes"
        assert len(m.pages) == 2
        assert m.conflict_strategy == "fail"
        assert m.labels == ["architecture", "auto-published"]

    def test_nested_pages(self):
        import yaml
        data = yaml.safe_load(SAMPLE_MANIFEST_YAML)
        m = Manifest(**data)
        design_page = m.pages[1]
        assert design_page.title == "Component Design"
        assert len(design_page.children) == 1
        assert design_page.children[0].title == "API Reference"

    def test_defaults(self):
        m = Manifest(space="X", parent="Y")
        assert m.schema_version == "1.0"
        assert m.conflict_strategy == "fail"
        assert m.on_removal == "leave"
        assert m.pages == []
        assert m.labels == []


class TestLoadManifest:
    def test_load_valid(self, tmp_path):
        f = tmp_path / "confpub.yaml"
        f.write_text(SAMPLE_MANIFEST_YAML)
        m = load_manifest(str(f))
        assert m.space == "DEV"
        assert len(m.pages) == 2

    def test_load_missing_file(self):
        with pytest.raises(ConfpubError) as exc_info:
            load_manifest("/nonexistent/confpub.yaml")
        assert exc_info.value.code == ERR_IO_FILE_NOT_FOUND

    def test_load_invalid_yaml(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("not: [valid: yaml: {")
        with pytest.raises(ConfpubError) as exc_info:
            load_manifest(str(f))
        assert exc_info.value.code == ERR_VALIDATION_MANIFEST

    def test_load_non_mapping(self, tmp_path):
        f = tmp_path / "list.yaml"
        f.write_text("- item1\n- item2")
        with pytest.raises(ConfpubError) as exc_info:
            load_manifest(str(f))
        assert exc_info.value.code == ERR_VALIDATION_MANIFEST


class TestResolvePageTree:
    def test_flat_pages(self):
        m = Manifest(
            space="DEV",
            parent="Root",
            pages=[
                ManifestPage(title="A", file="a.md"),
                ManifestPage(title="B", file="b.md"),
            ],
        )
        flat = resolve_page_tree(m)
        assert len(flat) == 2
        assert flat[0].title == "A"
        assert flat[0].parent_title == "Root"
        assert flat[1].title == "B"
        assert flat[1].parent_title == "Root"

    def test_nested_pages(self):
        m = Manifest(
            space="DEV",
            parent="Root",
            pages=[
                ManifestPage(
                    title="Parent",
                    file="parent.md",
                    children=[
                        ManifestPage(title="Child", file="child.md"),
                    ],
                ),
            ],
        )
        flat = resolve_page_tree(m)
        assert len(flat) == 2
        assert flat[0].title == "Parent"
        assert flat[0].parent_title == "Root"
        assert flat[1].title == "Child"
        assert flat[1].parent_title == "Parent"

    def test_deep_nesting(self):
        m = Manifest(
            space="DEV",
            parent="Root",
            pages=[
                ManifestPage(
                    title="L1",
                    file="l1.md",
                    children=[
                        ManifestPage(
                            title="L2",
                            file="l2.md",
                            children=[
                                ManifestPage(title="L3", file="l3.md"),
                            ],
                        ),
                    ],
                ),
            ],
        )
        flat = resolve_page_tree(m)
        assert len(flat) == 3
        assert flat[2].title == "L3"
        assert flat[2].parent_title == "L2"

    def test_preserves_assets(self):
        m = Manifest(
            space="DEV",
            parent="Root",
            pages=[
                ManifestPage(title="A", file="a.md", assets=["img/*.png"]),
            ],
        )
        flat = resolve_page_tree(m)
        assert flat[0].assets == ["img/*.png"]


class TestManifestValidationErrors:
    def test_pydantic_errors_are_clean(self, tmp_path):
        """Pydantic ValidationError should produce clean details, not raw internals."""
        f = tmp_path / "bad_manifest.yaml"
        # conflict_strategy only allows "fail", "overwrite", "skip"
        f.write_text("space: DEV\nparent: Root\nconflict_strategy: invalid_value\n")
        with pytest.raises(ConfpubError) as exc_info:
            load_manifest(str(f))
        err = exc_info.value
        assert err.code == ERR_VALIDATION_MANIFEST
        assert "validation error" in err.error_message
        assert "validation_errors" in err.details
        for entry in err.details["validation_errors"]:
            assert "field" in entry
            assert "message" in entry
            # Should not contain raw Pydantic internals
            assert "input_value" not in str(entry)
            assert "pydantic" not in str(entry).lower()

    def test_missing_required_fields(self, tmp_path):
        """Missing required fields produce clean validation errors."""
        f = tmp_path / "minimal.yaml"
        f.write_text("labels: []\n")  # missing space and parent
        with pytest.raises(ConfpubError) as exc_info:
            load_manifest(str(f))
        err = exc_info.value
        assert err.code == ERR_VALIDATION_MANIFEST
        assert "validation_errors" in err.details
        fields = [e["field"] for e in err.details["validation_errors"]]
        assert "space" in fields
        assert "parent" in fields


class TestPersonalSpaceKey:
    """Confluence personal spaces use ~username (e.g. ~thro).

    The tilde must survive YAML parsing (bare ~ is YAML null) and must
    not be subject to OS path expansion.
    """

    def test_tilde_space_in_model(self):
        m = Manifest(space="~thro", parent="Home")
        assert m.space == "~thro"

    def test_tilde_space_in_yaml(self, tmp_path):
        f = tmp_path / "confpub.yaml"
        f.write_text('space: "~thro"\nparent: Home\n')
        m = load_manifest(str(f))
        assert m.space == "~thro"

    def test_tilde_space_unquoted_yaml(self, tmp_path):
        """~thro without quotes is a valid YAML string (only bare ~ is null)."""
        f = tmp_path / "confpub.yaml"
        f.write_text("space: ~thro\nparent: Home\n")
        m = load_manifest(str(f))
        assert m.space == "~thro"

    def test_bare_tilde_rejected(self, tmp_path):
        """Bare ~ is YAML null, so Pydantic should reject it."""
        f = tmp_path / "confpub.yaml"
        f.write_text("space: ~\nparent: Home\n")
        with pytest.raises(ConfpubError) as exc_info:
            load_manifest(str(f))
        assert exc_info.value.code == ERR_VALIDATION_MANIFEST

    def test_tilde_space_in_plan_artifact(self):
        plan = PlanArtifact(space="~thro", parent="Home")
        assert plan.space == "~thro"

    def test_resolve_tree_preserves_tilde_space(self):
        m = Manifest(
            space="~thro",
            parent="Home",
            pages=[ManifestPage(title="Notes", file="notes.md")],
        )
        flat = resolve_page_tree(m)
        assert len(flat) == 1
        # space is not in FlatPage, but parent_title should be preserved
        assert flat[0].parent_title == "Home"


class TestPlanArtifact:
    def test_create_plan(self):
        plan = PlanArtifact(
            space="DEV",
            parent="Root",
            pages=[
                PlanPage(
                    id="plan_1",
                    title="Overview",
                    source_file="overview.md",
                    operation="create",
                ),
            ],
            summary=PlanSummary(create=1),
        )
        assert plan.pages[0].operation == "create"
        assert plan.summary.create == 1
