"""Tests for HTML macro detection/adoption helpers."""

from confpub.config import HtmlMacroSettings
from confpub.html_macro_detection import (
    extract_html_macro_candidates,
    has_html_macro_blocks,
    html_macro_fallback_warnings,
)


class TestHtmlMacroBlockDetection:
    def test_detects_closed_html_block(self):
        assert has_html_macro_blocks("Text\n\n::: html\n<div>ok</div>\n:::")

    def test_ignores_unclosed_html_block(self):
        assert not has_html_macro_blocks("::: html\n<div>missing close</div>")


class TestStorageExtraction:
    def test_extracts_classic_candidate(self):
        storage = (
            '<ac:structured-macro ac:name="macro-html">'
            "<ac:plain-text-body><![CDATA[<b>ok</b>]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )

        candidates = extract_html_macro_candidates(storage, page_id="123", title="Working")

        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.format == "classic"
        assert candidate.html_macro_name == "macro-html"
        assert candidate.config_values() == {
            "html_macro_format": "classic",
            "html_macro_name": "macro-html",
        }

    def test_extracts_forge_candidate(self):
        storage = (
            "<ac:adf-extension>"
            '<ac:adf-node type="extension">'
            '<ac:adf-attribute key="extension-key">ari/app/env/static/macro-html</ac:adf-attribute>'
            '<ac:adf-attribute key="parameters">'
            '<ac:adf-parameter key="extension-id">ari:cloud:ecosystem::extension/app/env/static/macro-html</ac:adf-parameter>'
            '<ac:adf-parameter key="forge-environment">PRODUCTION</ac:adf-parameter>'
            '<ac:adf-parameter key="cloud-id">cloud-123</ac:adf-parameter>'
            '<ac:adf-parameter key="context-ids">ari:cloud:confluence:site/cloud-123</ac:adf-parameter>'
            '<ac:adf-parameter key="account-id">account-123</ac:adf-parameter>'
            '<ac:adf-parameter key="guest-params">'
            '<ac:adf-parameter key="__body-content">&lt;div&gt;ok&lt;/div&gt;</ac:adf-parameter>'
            "</ac:adf-parameter>"
            "</ac:adf-attribute>"
            "</ac:adf-node>"
            "</ac:adf-extension>"
        )

        candidates = extract_html_macro_candidates(storage, page_id="123", title="Working")

        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.format == "forge-adf-extension"
        assert candidate.html_macro_name == "macro-html"
        assert candidate.html_macro_forge_extension_key == "ari/app/env/static/macro-html"
        assert candidate.html_macro_forge_extension_id == "ari:cloud:ecosystem::extension/app/env/static/macro-html"
        assert candidate.html_macro_forge_cloud_id == "cloud-123"
        assert candidate.html_macro_forge_context_ids == "ari:cloud:confluence:site/cloud-123"
        assert candidate.html_macro_forge_account_id == "account-123"
        assert "html_macro_forge_extension_key" in candidate.config_values()


class TestFallbackWarnings:
    def test_warns_only_for_cloud_default_classic_with_html_block(self):
        settings = HtmlMacroSettings(name="html-macro", format="classic")

        warnings = html_macro_fallback_warnings(
            "::: html\n<div>ok</div>\n:::",
            is_cloud=True,
            settings=settings,
        )

        assert warnings
        assert "default classic" in warnings[0]

    def test_no_warning_for_explicit_classic(self):
        settings = HtmlMacroSettings(
            name="html-macro",
            format="classic",
            format_source="override",
        )

        warnings = html_macro_fallback_warnings(
            "::: html\n<div>ok</div>\n:::",
            is_cloud=True,
            settings=settings,
        )

        assert warnings == []
