"""Tests for Confluence Storage Format → Markdown reverse converter."""

import pytest

from confpub.reverse_converter import convert_storage_to_markdown


class TestBasicElements:
    def test_headings(self):
        html = "<h1>Title</h1><h2>Subtitle</h2><h3>Section</h3>"
        result = convert_storage_to_markdown(html)
        assert "# Title" in result.markdown
        assert "## Subtitle" in result.markdown
        assert "### Section" in result.markdown

    def test_paragraphs(self):
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        result = convert_storage_to_markdown(html)
        assert "First paragraph." in result.markdown
        assert "Second paragraph." in result.markdown

    def test_bold(self):
        html = "<p><strong>bold text</strong></p>"
        result = convert_storage_to_markdown(html)
        assert "**bold text**" in result.markdown

    def test_italic(self):
        html = "<p><em>italic text</em></p>"
        result = convert_storage_to_markdown(html)
        assert "*italic text*" in result.markdown

    def test_inline_code(self):
        html = "<p><code>some_code</code></p>"
        result = convert_storage_to_markdown(html)
        assert "`some_code`" in result.markdown

    def test_strikethrough(self):
        html = "<p><del>deleted</del></p>"
        result = convert_storage_to_markdown(html)
        assert "~~deleted~~" in result.markdown

    def test_empty_input(self):
        result = convert_storage_to_markdown("")
        assert result.markdown == ""

    def test_whitespace_only(self):
        result = convert_storage_to_markdown("   \n  ")
        assert result.markdown == ""


class TestLinks:
    def test_standard_link(self):
        html = '<p><a href="https://example.com">Example</a></p>'
        result = convert_storage_to_markdown(html)
        assert "[Example](https://example.com)" in result.markdown

    def test_confluence_page_link(self):
        html = '<ac:link><ri:page ri:content-title="Getting Started" /><ac:plain-text-link-body>Start Here</ac:plain-text-link-body></ac:link>'
        result = convert_storage_to_markdown(html)
        assert "[Start Here](Getting Started)" in result.markdown

    def test_confluence_page_link_no_body(self):
        html = '<ac:link><ri:page ri:content-title="Overview" /></ac:link>'
        result = convert_storage_to_markdown(html)
        assert "[Overview](Overview)" in result.markdown


class TestImages:
    def test_ri_url_image(self):
        html = '<ac:image><ri:url ri:value="https://example.com/img.png" /></ac:image>'
        result = convert_storage_to_markdown(html)
        assert "![](https://example.com/img.png)" in result.markdown

    def test_ri_attachment_image_with_map(self):
        html = '<ac:image><ri:attachment ri:filename="diagram.png" /></ac:image>'
        result = convert_storage_to_markdown(
            html, attachment_map={"diagram.png": "assets/overview/diagram.png"},
        )
        assert "![diagram.png](assets/overview/diagram.png)" in result.markdown

    def test_ri_attachment_image_without_map(self):
        html = '<ac:image><ri:attachment ri:filename="photo.jpg" /></ac:image>'
        result = convert_storage_to_markdown(html)
        assert "![photo.jpg](photo.jpg)" in result.markdown


class TestCodeMacro:
    def test_code_block_with_language(self):
        html = (
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">python</ac:parameter>'
            '<ac:plain-text-body><![CDATA[def hello():\n    print("hi")\n]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )
        result = convert_storage_to_markdown(html)
        assert "```python" in result.markdown
        assert 'def hello():' in result.markdown
        assert '    print("hi")' in result.markdown
        assert "```" in result.markdown

    def test_code_block_without_language(self):
        html = (
            '<ac:structured-macro ac:name="code">'
            '<ac:plain-text-body><![CDATA[echo hello\n]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )
        result = convert_storage_to_markdown(html)
        assert "```\n" in result.markdown
        assert "echo hello" in result.markdown

    def test_code_block_preserves_content(self):
        code = "function add(a, b) {\n  return a + b;\n}\n"
        html = (
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">javascript</ac:parameter>'
            f'<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )
        result = convert_storage_to_markdown(html)
        assert "```javascript" in result.markdown
        assert "function add(a, b) {" in result.markdown
        assert "  return a + b;" in result.markdown


class TestAdmonitionMacros:
    def test_info_to_note(self):
        html = (
            '<ac:structured-macro ac:name="info">'
            '<ac:rich-text-body><p>This is informational.</p></ac:rich-text-body>'
            '</ac:structured-macro>'
        )
        result = convert_storage_to_markdown(html)
        assert "> [!NOTE]" in result.markdown
        assert "This is informational." in result.markdown

    def test_tip_to_tip(self):
        html = (
            '<ac:structured-macro ac:name="tip">'
            '<ac:rich-text-body><p>Pro tip here.</p></ac:rich-text-body>'
            '</ac:structured-macro>'
        )
        result = convert_storage_to_markdown(html)
        assert "> [!TIP]" in result.markdown
        assert "Pro tip here." in result.markdown

    def test_warning_to_warning(self):
        html = (
            '<ac:structured-macro ac:name="warning">'
            '<ac:rich-text-body><p>Be careful!</p></ac:rich-text-body>'
            '</ac:structured-macro>'
        )
        result = convert_storage_to_markdown(html)
        assert "> [!WARNING]" in result.markdown
        assert "Be careful!" in result.markdown

    def test_note_to_caution(self):
        html = (
            '<ac:structured-macro ac:name="note">'
            '<ac:rich-text-body><p>Caution needed.</p></ac:rich-text-body>'
            '</ac:structured-macro>'
        )
        result = convert_storage_to_markdown(html)
        assert "> [!CAUTION]" in result.markdown
        assert "Caution needed." in result.markdown


class TestTables:
    def test_simple_table(self):
        html = (
            "<table>"
            "<thead><tr><th>Name</th><th>Value</th></tr></thead>"
            "<tbody><tr><td>a</td><td>1</td></tr></tbody>"
            "</table>"
        )
        result = convert_storage_to_markdown(html)
        assert "Name" in result.markdown
        assert "Value" in result.markdown
        assert "a" in result.markdown
        assert "1" in result.markdown
        assert "|" in result.markdown


class TestLists:
    def test_unordered_list(self):
        html = "<ul><li>item one</li><li>item two</li></ul>"
        result = convert_storage_to_markdown(html)
        assert "item one" in result.markdown
        assert "item two" in result.markdown

    def test_ordered_list(self):
        html = "<ol><li>first</li><li>second</li></ol>"
        result = convert_storage_to_markdown(html)
        assert "first" in result.markdown
        assert "second" in result.markdown


class TestUnknownMacros:
    def test_unknown_macro_becomes_comment(self):
        html = (
            '<ac:structured-macro ac:name="jira">'
            '<ac:parameter ac:name="key">PROJ-123</ac:parameter>'
            '</ac:structured-macro>'
        )
        result = convert_storage_to_markdown(html)
        assert "<!-- confluence-macro: jira" in result.markdown
        assert "jira" in result.unknown_macros
        assert len(result.warnings) > 0

    def test_multiple_unknown_macros(self):
        html = (
            '<ac:structured-macro ac:name="custom1"></ac:structured-macro>'
            '<ac:structured-macro ac:name="custom2"></ac:structured-macro>'
        )
        result = convert_storage_to_markdown(html)
        assert "custom1" in result.unknown_macros
        assert "custom2" in result.unknown_macros


class TestMixedContent:
    def test_page_with_multiple_elements(self):
        html = (
            "<h1>Overview</h1>"
            "<p>This is the <strong>overview</strong> page.</p>"
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">python</ac:parameter>'
            '<ac:plain-text-body><![CDATA[print("hello")\n]]></ac:plain-text-body>'
            '</ac:structured-macro>'
            '<ac:structured-macro ac:name="info">'
            '<ac:rich-text-body><p>Remember to check docs.</p></ac:rich-text-body>'
            '</ac:structured-macro>'
            "<ul><li>Item A</li><li>Item B</li></ul>"
        )
        result = convert_storage_to_markdown(html)
        assert "# Overview" in result.markdown
        assert "**overview**" in result.markdown
        assert "```python" in result.markdown
        assert "> [!NOTE]" in result.markdown
        assert "Item A" in result.markdown

    def test_no_warnings_for_known_macros(self):
        html = (
            '<ac:structured-macro ac:name="code">'
            '<ac:plain-text-body><![CDATA[x = 1\n]]></ac:plain-text-body>'
            '</ac:structured-macro>'
        )
        result = convert_storage_to_markdown(html)
        assert len(result.warnings) == 0
        assert len(result.unknown_macros) == 0


class TestRoundTrip:
    """Test that content survives a round-trip through conversion."""

    def test_headings_round_trip(self):
        from confpub.converter import convert_markdown
        md = "# My Title\n\n## Subtitle\n\nSome content here.\n"
        storage = convert_markdown(md)
        result = convert_storage_to_markdown(storage)
        assert "My Title" in result.markdown
        assert "Subtitle" in result.markdown
        assert "Some content here." in result.markdown

    def test_bold_italic_round_trip(self):
        from confpub.converter import convert_markdown
        md = "This is **bold** and *italic* text.\n"
        storage = convert_markdown(md)
        result = convert_storage_to_markdown(storage)
        assert "**bold**" in result.markdown
        assert "*italic*" in result.markdown

    def test_code_block_round_trip(self):
        from confpub.converter import convert_markdown
        md = "```python\ndef hello():\n    pass\n```\n"
        storage = convert_markdown(md)
        result = convert_storage_to_markdown(storage)
        assert "```python" in result.markdown
        assert "def hello():" in result.markdown

    def test_list_round_trip(self):
        from confpub.converter import convert_markdown
        md = "- item one\n- item two\n- item three\n"
        storage = convert_markdown(md)
        result = convert_storage_to_markdown(storage)
        assert "item one" in result.markdown
        assert "item two" in result.markdown
        assert "item three" in result.markdown
