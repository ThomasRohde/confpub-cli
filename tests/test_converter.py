"""Tests for confpub.converter module."""

from confpub.converter import convert_markdown, extract_h1_title, fingerprint_content


class TestHeadings:
    def test_h1(self):
        result = convert_markdown("# Hello")
        assert "<h1>" in result
        assert "Hello" in result
        assert "</h1>" in result

    def test_h2(self):
        result = convert_markdown("## Sub")
        assert "<h2>" in result
        assert "</h2>" in result

    def test_h3(self):
        result = convert_markdown("### Deep")
        assert "<h3>" in result

    def test_h6(self):
        result = convert_markdown("###### Deepest")
        assert "<h6>" in result


class TestParagraphs:
    def test_basic_paragraph(self):
        result = convert_markdown("Hello world")
        assert "<p>Hello world</p>" in result

    def test_two_paragraphs(self):
        result = convert_markdown("First\n\nSecond")
        assert "<p>First</p>" in result
        assert "<p>Second</p>" in result


class TestInlineFormatting:
    def test_bold(self):
        result = convert_markdown("**bold**")
        assert "<strong>bold</strong>" in result

    def test_italic(self):
        result = convert_markdown("*italic*")
        assert "<em>italic</em>" in result

    def test_strikethrough(self):
        result = convert_markdown("~~deleted~~")
        assert "<del>deleted</del>" in result

    def test_inline_code(self):
        result = convert_markdown("`code`")
        assert "<code>code</code>" in result

    def test_mixed_formatting(self):
        result = convert_markdown("**bold** and *italic* and `code`")
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result
        assert "<code>code</code>" in result


class TestLinks:
    def test_link(self):
        result = convert_markdown("[Example](https://example.com)")
        assert '<a href="https://example.com">' in result
        assert "Example" in result
        assert "</a>" in result


class TestImages:
    def test_image(self):
        result = convert_markdown("![alt](image.png)")
        assert "<ac:image>" in result
        assert "image.png" in result
        assert "</ac:image>" in result


class TestCodeBlocks:
    def test_fenced_code_no_language(self):
        result = convert_markdown("```\nprint('hello')\n```")
        assert '<ac:structured-macro ac:name="code">' in result
        assert "print(&#x27;hello&#x27;)" in result or "print('hello')" in result
        assert "</ac:structured-macro>" in result

    def test_fenced_code_with_language(self):
        result = convert_markdown("```python\nprint('hello')\n```")
        assert '<ac:parameter ac:name="language">python</ac:parameter>' in result

    def test_fenced_code_with_javascript(self):
        result = convert_markdown("```javascript\nconsole.log('hi');\n```")
        assert '<ac:parameter ac:name="language">javascript</ac:parameter>' in result


class TestBlockquotes:
    def test_basic_blockquote(self):
        result = convert_markdown("> This is a quote")
        assert "<blockquote>" in result
        assert "This is a quote" in result
        assert "</blockquote>" in result


class TestAdmonitions:
    def test_note_admonition(self):
        result = convert_markdown("> [!NOTE]\n> This is a note")
        assert '<ac:structured-macro ac:name="info">' in result
        assert "This is a note" in result
        assert "</ac:structured-macro>" in result

    def test_warning_admonition(self):
        result = convert_markdown("> [!WARNING]\n> Be careful")
        assert '<ac:structured-macro ac:name="warning">' in result
        assert "Be careful" in result

    def test_tip_admonition(self):
        result = convert_markdown("> [!TIP]\n> Pro tip here")
        assert '<ac:structured-macro ac:name="tip">' in result

    def test_caution_admonition(self):
        result = convert_markdown("> [!CAUTION]\n> Watch out")
        assert '<ac:structured-macro ac:name="note">' in result


class TestLists:
    def test_unordered_list(self):
        result = convert_markdown("- Item 1\n- Item 2\n- Item 3")
        assert "<ul>" in result
        assert "<li>" in result
        assert "Item 1" in result
        assert "Item 3" in result
        assert "</ul>" in result

    def test_ordered_list(self):
        result = convert_markdown("1. First\n2. Second\n3. Third")
        assert "<ol>" in result
        assert "<li>" in result
        assert "First" in result
        assert "</ol>" in result

    def test_nested_list(self):
        result = convert_markdown("- Outer\n  - Inner")
        assert "<ul>" in result
        assert "Outer" in result
        assert "Inner" in result


class TestTables:
    def test_basic_table(self):
        md = "| Header 1 | Header 2 |\n| --- | --- |\n| Cell 1 | Cell 2 |"
        result = convert_markdown(md)
        assert "<table>" in result
        assert "<thead>" in result
        assert "<th>" in result
        assert "Header 1" in result
        assert "<tbody>" in result
        assert "<td>" in result
        assert "Cell 1" in result
        assert "</table>" in result


class TestHorizontalRule:
    def test_hr(self):
        result = convert_markdown("---")
        assert "<hr />" in result


class TestHTMLEscaping:
    def test_special_chars_escaped(self):
        result = convert_markdown("Use `<div>` and `&` in code")
        assert "&lt;div&gt;" in result
        assert "&amp;" in result


class TestFingerprint:
    def test_fingerprint_deterministic(self):
        content = "<p>hello</p>"
        fp1 = fingerprint_content(content)
        fp2 = fingerprint_content(content)
        assert fp1 == fp2
        assert len(fp1) == 64

    def test_fingerprint_changes_with_content(self):
        assert fingerprint_content("<p>a</p>") != fingerprint_content("<p>b</p>")


class TestFullDocument:
    def test_mixed_document(self):
        md = """# Title

Some **bold** and *italic* text.

## Code Example

```python
def hello():
    print("Hello, world!")
```

| Name | Value |
| --- | --- |
| foo | bar |

- Item 1
- Item 2

> A wise quote

---

[Link](https://example.com)
"""
        result = convert_markdown(md)
        assert "<h1>" in result
        assert "<h2>" in result
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result
        assert '<ac:structured-macro ac:name="code">' in result
        assert '<ac:parameter ac:name="language">python</ac:parameter>' in result
        assert "<table>" in result
        assert "<ul>" in result
        assert "<blockquote>" in result
        assert "<hr />" in result
        assert '<a href="https://example.com">' in result


class TestExtractH1Title:
    """Suggestion 2: extract_h1_title should extract text from first H1 heading."""

    def test_simple_h1(self):
        assert extract_h1_title("# My Page Title") == "My Page Title"

    def test_h1_with_body(self):
        md = "# Getting Started\n\nSome content here."
        assert extract_h1_title(md) == "Getting Started"

    def test_no_h1_returns_none(self):
        assert extract_h1_title("## Only H2\n\nNo H1 here.") is None

    def test_empty_returns_none(self):
        assert extract_h1_title("") is None

    def test_h1_with_inline_code(self):
        assert extract_h1_title("# Using `confpub` CLI") == "Using confpub CLI"

    def test_first_h1_wins(self):
        md = "# First Title\n\n## Sub\n\n# Second Title"
        assert extract_h1_title(md) == "First Title"

    def test_h2_before_h1(self):
        md = "## Intro\n\n# Main Title"
        assert extract_h1_title(md) == "Main Title"
