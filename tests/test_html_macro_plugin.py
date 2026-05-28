"""Tests for the ::: html block → Confluence HTML macro feature."""

from __future__ import annotations

import pytest

from confpub.converter import convert_markdown
from confpub.reverse_converter import convert_storage_to_markdown


# ---------------------------------------------------------------------------
# Forward conversion tests
# ---------------------------------------------------------------------------


class TestHtmlMacroForward:
    """Test Markdown → Confluence Storage Format for ::: html blocks."""

    def test_dc_default(self):
        md = "::: html\n<b>bold</b>\n:::"
        result = convert_markdown(md)
        assert '<ac:structured-macro ac:name="html">' in result
        assert "<![CDATA[<b>bold</b>]]>" in result
        assert "</ac:structured-macro>" in result

    def test_cloud_macro_name(self):
        md = "::: html\n<b>bold</b>\n:::"
        result = convert_markdown(md, html_macro_name="html-macro")
        assert '<ac:structured-macro ac:name="html-macro">' in result

    def test_multiline_content(self):
        md = "::: html\n<div>\n  <p>Hello</p>\n</div>\n:::"
        result = convert_markdown(md)
        assert "<div>\n  <p>Hello</p>\n</div>" in result

    def test_empty_block(self):
        md = "::: html\n:::"
        result = convert_markdown(md)
        assert '<ac:structured-macro ac:name="html">' in result
        assert "<![CDATA[]]>" in result

    def test_multiple_blocks(self):
        md = "::: html\n<b>one</b>\n:::\n\n::: html\n<i>two</i>\n:::"
        result = convert_markdown(md)
        assert result.count('<ac:structured-macro ac:name="html">') == 2
        assert "<![CDATA[<b>one</b>]]>" in result
        assert "<![CDATA[<i>two</i>]]>" in result

    def test_mixed_with_markdown(self):
        md = "# Title\n\nSome text.\n\n::: html\n<b>bold</b>\n:::\n\nMore text."
        result = convert_markdown(md)
        assert "<h1>Title</h1>" in result
        assert "<p>Some text.</p>" in result
        assert '<ac:structured-macro ac:name="html">' in result
        assert "<p>More text.</p>" in result

    def test_custom_macro_name(self):
        md = "::: html\n<b>bold</b>\n:::"
        result = convert_markdown(md, html_macro_name="custom-html")
        assert '<ac:structured-macro ac:name="custom-html">' in result

    def test_unclosed_block_no_crash(self):
        md = "::: html\n<b>bold</b>\nno closing fence"
        result = convert_markdown(md)
        # Unclosed block should not produce a macro
        assert "ac:structured-macro" not in result

    def test_inline_colons_dont_close(self):
        md = "::: html\n<div>content ::: more</div>\n:::"
        result = convert_markdown(md)
        assert "<div>content ::: more</div>" in result
        assert '<ac:structured-macro ac:name="html">' in result

    def test_case_insensitive_html(self):
        md = "::: HTML\n<b>bold</b>\n:::"
        result = convert_markdown(md)
        assert '<ac:structured-macro ac:name="html">' in result

    def test_case_insensitive_mixed(self):
        md = "::: Html\n<b>bold</b>\n:::"
        result = convert_markdown(md)
        assert '<ac:structured-macro ac:name="html">' in result

    def test_style_tag_content(self):
        """Verify that <style> tags are preserved inside the HTML macro."""
        md = "::: html\n<style>body { color: red; }</style>\n:::"
        result = convert_markdown(md)
        assert "<style>body { color: red; }</style>" in result

    def test_script_tag_content(self):
        """Verify that <script> tags are preserved inside the HTML macro."""
        md = "::: html\n<script>alert('hi');</script>\n:::"
        result = convert_markdown(md)
        assert "<script>alert('hi');</script>" in result


# ---------------------------------------------------------------------------
# Reverse conversion tests
# ---------------------------------------------------------------------------


class TestHtmlMacroReverse:
    """Test Confluence Storage Format → Markdown for HTML macros."""

    def test_dc_html_macro(self):
        storage = (
            '<ac:structured-macro ac:name="html">'
            "<ac:plain-text-body><![CDATA[<b>bold</b>]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(storage)
        assert "::: html" in result.markdown
        assert "<b>bold</b>" in result.markdown
        assert ":::" in result.markdown

    def test_cloud_html_macro(self):
        storage = (
            '<ac:structured-macro ac:name="html-macro">'
            "<ac:plain-text-body><![CDATA[<b>bold</b>]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(storage)
        assert "::: html" in result.markdown
        assert "<b>bold</b>" in result.markdown

    def test_cloud_macro_html_macro(self):
        storage = (
            '<ac:structured-macro ac:name="macro-html">'
            "<ac:plain-text-body><![CDATA[<b>bold</b>]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(storage)
        assert "::: html" in result.markdown
        assert "<b>bold</b>" in result.markdown
        assert result.unknown_macros == []


# ---------------------------------------------------------------------------
# Roundtrip tests
# ---------------------------------------------------------------------------


class TestHtmlMacroRoundtrip:
    """Test forward → reverse roundtrip preservation."""

    def test_dc_roundtrip(self):
        original = "::: html\n<b>hello</b>\n:::"
        storage = convert_markdown(original)
        result = convert_storage_to_markdown(storage)
        assert "<b>hello</b>" in result.markdown
        assert "::: html" in result.markdown

    def test_cloud_roundtrip(self):
        original = "::: html\n<b>hello</b>\n:::"
        storage = convert_markdown(original, html_macro_name="html-macro")
        result = convert_storage_to_markdown(storage)
        assert "<b>hello</b>" in result.markdown
        assert "::: html" in result.markdown

    def test_multiline_roundtrip(self):
        original = "::: html\n<div>\n  <p>text</p>\n</div>\n:::"
        storage = convert_markdown(original)
        result = convert_storage_to_markdown(storage)
        assert "<div>" in result.markdown
        assert "<p>text</p>" in result.markdown
        assert "::: html" in result.markdown
