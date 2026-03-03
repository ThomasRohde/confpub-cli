"""Tests for confpub.converter module."""

from confpub.converter import convert_markdown, extract_front_matter, extract_h1_title, fingerprint_content


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


class TestTaskLists:
    def test_unchecked_task(self):
        result = convert_markdown("- [ ] Buy milk")
        assert "<ac:task-list>" in result
        assert "<ac:task>" in result
        assert "<ac:task-status>incomplete</ac:task-status>" in result
        assert "Buy milk" in result
        assert "</ac:task-body></ac:task>" in result
        assert "</ac:task-list>" in result

    def test_checked_task(self):
        result = convert_markdown("- [x] Buy milk")
        assert "<ac:task-status>complete</ac:task-status>" in result

    def test_mixed_task_list(self):
        md = "- [ ] First\n- [x] Second\n- [ ] Third"
        result = convert_markdown(md)
        assert result.count("<ac:task>") == 3
        assert "<ac:task-status>incomplete</ac:task-status>" in result
        assert "<ac:task-status>complete</ac:task-status>" in result

    def test_task_ids_increment(self):
        md = "- [ ] A\n- [ ] B\n- [ ] C"
        result = convert_markdown(md)
        assert "<ac:task-id>1</ac:task-id>" in result
        assert "<ac:task-id>2</ac:task-id>" in result
        assert "<ac:task-id>3</ac:task-id>" in result

    def test_regular_list_unchanged(self):
        result = convert_markdown("- Normal item\n- Another item")
        assert "<ul>" in result
        assert "<li>" in result
        assert "<ac:task" not in result

    def test_no_input_checkbox_in_output(self):
        result = convert_markdown("- [ ] Task")
        assert "<input" not in result


class TestMath:
    def test_inline_math(self):
        result = convert_markdown("The equation $E=mc^2$ is famous.")
        assert '<ac:structured-macro ac:name="mathinline">' in result
        assert "<![CDATA[E=mc^2]]>" in result
        assert "</ac:structured-macro>" in result

    def test_block_math(self):
        result = convert_markdown("$$\nx^2 + y^2 = z^2\n$$")
        assert '<ac:structured-macro ac:name="mathblock">' in result
        assert "x^2 + y^2 = z^2" in result

    def test_inline_math_in_paragraph(self):
        result = convert_markdown("Given $a$ and $b$, compute $a+b$.")
        assert result.count('ac:name="mathinline"') == 3


class TestDefinitionLists:
    def test_basic_deflist(self):
        md = "Term\n:   Definition here"
        result = convert_markdown(md)
        assert "<dl>" in result
        assert "<dt>" in result
        assert "Term" in result
        assert "<dd>" in result
        assert "Definition here" in result
        assert "</dl>" in result

    def test_multiple_terms(self):
        md = "Apple\n:   A fruit\n\nBanana\n:   Another fruit"
        result = convert_markdown(md)
        assert result.count("<dt>") == 2
        assert result.count("<dd>") == 2

    def test_multiple_definitions(self):
        md = "Term\n:   First def\n:   Second def"
        result = convert_markdown(md)
        assert result.count("<dd>") == 2


class TestFootnotes:
    def test_footnote_ref_link(self):
        md = "Text with a footnote[^1].\n\n[^1]: Footnote content."
        result = convert_markdown(md)
        assert '<sup><a id="footnote-ref-1" href="#footnote-1">[1]</a></sup>' in result

    def test_footnote_body(self):
        md = "Text[^1].\n\n[^1]: Footnote content."
        result = convert_markdown(md)
        assert '<li id="footnote-1">' in result
        assert "Footnote content." in result

    def test_footnote_back_link(self):
        md = "Text[^1].\n\n[^1]: Footnote content."
        result = convert_markdown(md)
        assert 'href="#footnote-ref-1"' in result
        assert "\u21a9" in result

    def test_multiple_footnotes(self):
        md = "First[^1] and second[^2].\n\n[^1]: Note one.\n[^2]: Note two."
        result = convert_markdown(md)
        assert "footnote-1" in result
        assert "footnote-2" in result
        assert result.count("<ac:task") == 0  # no task contamination


class TestFrontMatter:
    def test_front_matter_stripped(self):
        md = "---\ntitle: My Page\ntags: [a, b]\n---\n\n# Hello"
        result = convert_markdown(md)
        assert "title:" not in result
        assert "tags:" not in result
        assert "<h1>" in result
        assert "Hello" in result

    def test_no_regression_without_front_matter(self):
        result = convert_markdown("# Hello\n\nWorld")
        assert "<h1>" in result
        assert "Hello" in result
        assert "World" in result


class TestContainerPanel:
    def test_panel_with_title(self):
        md = "::: panel Important Note\nThis is panel content.\n:::"
        result = convert_markdown(md)
        assert '<ac:structured-macro ac:name="panel">' in result
        assert '<ac:parameter ac:name="title">Important Note</ac:parameter>' in result
        assert "<ac:rich-text-body>" in result
        assert "This is panel content." in result
        assert "</ac:rich-text-body></ac:structured-macro>" in result

    def test_panel_without_title(self):
        md = "::: panel\nJust content.\n:::"
        result = convert_markdown(md)
        assert '<ac:structured-macro ac:name="panel">' in result
        assert 'ac:name="title"' not in result
        assert "Just content." in result


class TestContainerExpand:
    def test_expand_with_title(self):
        md = "::: expand Click to expand\nHidden content here.\n:::"
        result = convert_markdown(md)
        assert '<ac:structured-macro ac:name="expand">' in result
        assert '<ac:parameter ac:name="title">Click to expand</ac:parameter>' in result
        assert "Hidden content here." in result


class TestContainerLayout:
    def test_two_equal_layout(self):
        md = ":::: layout two-equal\n::: cell\nLeft column\n:::\n::: cell\nRight column\n:::\n::::"
        result = convert_markdown(md)
        assert '<ac:layout><ac:layout-section ac:type="two_equal">' in result
        assert "<ac:layout-cell>" in result
        assert "Left column" in result
        assert "Right column" in result
        assert "</ac:layout-cell>" in result
        assert "</ac:layout-section></ac:layout>" in result

    def test_single_column_layout(self):
        md = ":::: layout single\n::: cell\nOnly column\n:::\n::::"
        result = convert_markdown(md)
        assert 'ac:type="single"' in result

    def test_three_column_layout(self):
        md = ":::: layout three-equal\n::: cell\nA\n:::\n::: cell\nB\n:::\n::: cell\nC\n:::\n::::"
        result = convert_markdown(md)
        assert 'ac:type="three_equal"' in result
        assert result.count("<ac:layout-cell>") == 3


class TestExtractFrontMatter:
    def test_basic_extraction(self):
        md = "---\ntitle: Hello\nspace: DEV\n---\n\n# Content"
        result = extract_front_matter(md)
        assert result is not None
        assert result["title"] == "Hello"
        assert result["space"] == "DEV"

    def test_no_front_matter_returns_none(self):
        md = "# Just a heading\n\nParagraph."
        assert extract_front_matter(md) is None

    def test_invalid_yaml_returns_none(self):
        md = "---\n: invalid: yaml: {{{\n---\n\nContent"
        assert extract_front_matter(md) is None

    def test_non_mapping_returns_none(self):
        md = "---\n- just\n- a\n- list\n---\n\nContent"
        assert extract_front_matter(md) is None

    def test_preserves_unknown_keys(self):
        md = "---\ntitle: Page\nauthor: Alice\ndraft: true\n---\n\nContent"
        result = extract_front_matter(md)
        assert result is not None
        assert result["title"] == "Page"
        assert result["author"] == "Alice"
        assert result["draft"] is True
