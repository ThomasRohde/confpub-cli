"""Tests for confpub.front_matter module."""

import pytest

from confpub.errors import ConfpubError, ERR_VALIDATION_MARKDOWN
from confpub.front_matter import FrontMatterData, parse_front_matter


class TestParseFrontMatter:
    def test_all_fields_populated(self):
        md = (
            "---\n"
            "title: My Page\n"
            "space: DEV\n"
            "parent: Documentation\n"
            "labels:\n"
            "  - api\n"
            "  - public\n"
            "page_id: '123456'\n"
            "html_macro_name: macro-html\n"
            "html_macro_format: forge-adf-extension\n"
            "html_macro_forge_extension_key: app/static/macro-html\n"
            "html_macro_forge_extension_id: ari:cloud:ecosystem::extension/app/static/macro-html\n"
            "html_macro_forge_environment: PRODUCTION\n"
            "html_macro_forge_cloud_id: cloud-123\n"
            "html_macro_forge_context_ids: ari:cloud:confluence:site/cloud-123\n"
            "html_macro_forge_account_id: account-123\n"
            "---\n"
            "\n"
            "# Content\n"
        )
        fm = parse_front_matter(md)
        assert fm is not None
        assert fm.title == "My Page"
        assert fm.space == "DEV"
        assert fm.parent == "Documentation"
        assert fm.labels == ["api", "public"]
        assert fm.page_id == "123456"
        assert fm.html_macro_name == "macro-html"
        assert fm.html_macro_format == "forge-adf-extension"
        assert fm.html_macro_forge_extension_key == "app/static/macro-html"
        assert fm.html_macro_forge_extension_id == "ari:cloud:ecosystem::extension/app/static/macro-html"
        assert fm.html_macro_forge_environment == "PRODUCTION"
        assert fm.html_macro_forge_cloud_id == "cloud-123"
        assert fm.html_macro_forge_context_ids == "ari:cloud:confluence:site/cloud-123"
        assert fm.html_macro_forge_account_id == "account-123"

    def test_partial_fields(self):
        md = "---\ntitle: Just Title\n---\n\nContent"
        fm = parse_front_matter(md)
        assert fm is not None
        assert fm.title == "Just Title"
        assert fm.space is None
        assert fm.parent is None
        assert fm.labels == []
        assert fm.page_id is None

    def test_no_front_matter_returns_none(self):
        md = "# No front matter\n\nJust content."
        assert parse_front_matter(md) is None

    def test_single_string_labels_coercion(self):
        md = "---\nlabels: api\n---\n\nContent"
        fm = parse_front_matter(md)
        assert fm is not None
        assert fm.labels == ["api"]

    def test_int_page_id_coercion(self):
        md = "---\npage_id: 789\n---\n\nContent"
        fm = parse_front_matter(md)
        assert fm is not None
        assert fm.page_id == "789"

    def test_unknown_keys_ignored(self):
        md = "---\ntitle: Page\nauthor: Alice\ndraft: true\n---\n\nContent"
        fm = parse_front_matter(md)
        assert fm is not None
        assert fm.title == "Page"
        # No error from unknown keys

    def test_title_as_list_raises(self):
        md = "---\ntitle:\n  - one\n  - two\n---\n\nContent"
        with pytest.raises(ConfpubError) as exc_info:
            parse_front_matter(md)
        assert exc_info.value.code == ERR_VALIDATION_MARKDOWN
        assert "title" in exc_info.value.error_message

    def test_labels_as_int_raises(self):
        md = "---\nlabels: 42\n---\n\nContent"
        with pytest.raises(ConfpubError) as exc_info:
            parse_front_matter(md)
        assert exc_info.value.code == ERR_VALIDATION_MARKDOWN
        assert "labels" in exc_info.value.error_message

    def test_labels_with_non_string_item_raises(self):
        md = "---\nlabels:\n  - good\n  - 123\n---\n\nContent"
        with pytest.raises(ConfpubError) as exc_info:
            parse_front_matter(md)
        assert exc_info.value.code == ERR_VALIDATION_MARKDOWN
        assert "labels" in exc_info.value.error_message

    def test_page_id_as_list_raises(self):
        md = "---\npage_id:\n  - 1\n  - 2\n---\n\nContent"
        with pytest.raises(ConfpubError) as exc_info:
            parse_front_matter(md)
        assert exc_info.value.code == ERR_VALIDATION_MARKDOWN
        assert "page_id" in exc_info.value.error_message

    def test_space_as_int_raises(self):
        md = "---\nspace: 42\n---\n\nContent"
        with pytest.raises(ConfpubError) as exc_info:
            parse_front_matter(md)
        assert exc_info.value.code == ERR_VALIDATION_MARKDOWN
        assert "space" in exc_info.value.error_message

    def test_html_macro_format_as_bool_raises(self):
        md = "---\nhtml_macro_format: true\n---\n\nContent"
        with pytest.raises(ConfpubError) as exc_info:
            parse_front_matter(md)
        assert exc_info.value.code == ERR_VALIDATION_MARKDOWN
        assert "html_macro_format" in exc_info.value.error_message
