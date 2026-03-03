"""Tests for Confluence macro syntax: forward conversion, reverse conversion, and round-trips."""

from confpub.converter import convert_markdown
from confpub.reverse_converter import convert_storage_to_markdown


# ---------------------------------------------------------------------------
# Forward conversion
# ---------------------------------------------------------------------------


class TestMacroForwardConversion:
    def test_toc_simple(self):
        result = convert_markdown("{toc}")
        assert '<ac:structured-macro ac:name="toc">' in result
        assert "</ac:structured-macro>" in result
        # Block-level: should NOT be wrapped in <p>
        assert "<p>" not in result

    def test_toc_with_params(self):
        result = convert_markdown("{toc:maxLevel=3}")
        assert '<ac:structured-macro ac:name="toc">' in result
        assert '<ac:parameter ac:name="maxLevel">3</ac:parameter>' in result

    def test_status_inline(self):
        result = convert_markdown("Status: {status:Done|colour=Green} here")
        assert '<ac:structured-macro ac:name="status">' in result
        assert '<ac:parameter ac:name="title">Done</ac:parameter>' in result
        assert '<ac:parameter ac:name="colour">Green</ac:parameter>' in result
        # Should be inline, so wrapped in a <p>
        assert "<p>" in result

    def test_status_in_paragraph(self):
        result = convert_markdown("The task is {status:In Progress|colour=Blue}.")
        assert '<ac:parameter ac:name="title">In Progress</ac:parameter>' in result
        assert '<ac:parameter ac:name="colour">Blue</ac:parameter>' in result

    def test_anchor_inline(self):
        result = convert_markdown("See {anchor:my-section} below.")
        assert '<ac:structured-macro ac:name="anchor">' in result
        assert '<ac:parameter ac:name="">my-section</ac:parameter>' in result

    def test_children_block(self):
        result = convert_markdown("{children}")
        assert '<ac:structured-macro ac:name="children">' in result
        assert "<p>" not in result

    def test_children_with_params(self):
        result = convert_markdown("{children:depth=3|sort=title}")
        assert '<ac:parameter ac:name="depth">3</ac:parameter>' in result
        assert '<ac:parameter ac:name="sort">title</ac:parameter>' in result

    def test_jira_key(self):
        result = convert_markdown("{jira:PROJECT-123}")
        assert '<ac:structured-macro ac:name="jira">' in result
        assert '<ac:parameter ac:name="key">PROJECT-123</ac:parameter>' in result

    def test_jira_jql(self):
        result = convert_markdown("{jira:jql=project=PROJ AND status=Open}")
        assert '<ac:structured-macro ac:name="jira">' in result
        assert '<ac:parameter ac:name="jqlQuery">project=PROJ AND status=Open</ac:parameter>' in result

    def test_recently_updated(self):
        result = convert_markdown("{recently-updated}")
        assert '<ac:structured-macro ac:name="recently-updated">' in result

    def test_recently_updated_with_params(self):
        result = convert_markdown("{recently-updated:max=10}")
        assert '<ac:parameter ac:name="max">10</ac:parameter>' in result

    def test_excerpt_include(self):
        result = convert_markdown("{excerpt-include:Getting Started}")
        assert '<ac:structured-macro ac:name="excerpt-include">' in result
        assert 'ri:content-title="Getting Started"' in result

    def test_excerpt_include_with_space(self):
        result = convert_markdown("{excerpt-include:Getting Started|space=DEV}")
        assert 'ri:content-title="Getting Started"' in result
        assert 'ri:space-key="DEV"' in result

    def test_include_macro(self):
        result = convert_markdown("{include:API Reference|space=DOCS}")
        assert '<ac:structured-macro ac:name="include">' in result
        assert 'ri:content-title="API Reference"' in result
        assert 'ri:space-key="DOCS"' in result


# ---------------------------------------------------------------------------
# Excerpt container
# ---------------------------------------------------------------------------


class TestExcerptContainer:
    def test_excerpt_hidden(self):
        md = "::: excerpt hidden\nThis is an excerpt.\n:::"
        result = convert_markdown(md)
        assert '<ac:structured-macro ac:name="excerpt">' in result
        assert '<ac:parameter ac:name="hidden">true</ac:parameter>' in result
        assert "<ac:rich-text-body>" in result
        assert "This is an excerpt." in result
        assert "</ac:rich-text-body></ac:structured-macro>" in result

    def test_excerpt_visible(self):
        md = "::: excerpt\nVisible excerpt content.\n:::"
        result = convert_markdown(md)
        assert '<ac:structured-macro ac:name="excerpt">' in result
        assert "hidden" not in result
        assert "Visible excerpt content." in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestMacroEdgeCases:
    def test_in_code_block_not_parsed(self):
        md = "```\n{toc}\n```"
        result = convert_markdown(md)
        assert '<ac:structured-macro ac:name="toc">' not in result
        assert "{toc}" in result

    def test_in_inline_code_not_parsed(self):
        result = convert_markdown("Use `{toc}` syntax.")
        assert '<ac:structured-macro ac:name="toc">' not in result
        assert "{toc}" in result

    def test_unknown_braces_not_parsed(self):
        result = convert_markdown("A {variable} in text.")
        assert "<ac:structured-macro" not in result
        assert "{variable}" in result

    def test_multiple_inline_macros(self):
        result = convert_markdown("A {status:Done|colour=Green} and {status:TODO|colour=Red} item.")
        assert result.count('ac:name="status"') == 2
        assert "Done" in result
        assert "TODO" in result

    def test_jql_value_with_equals(self):
        result = convert_markdown("{jira:jql=project=PROJ AND status=Open}")
        assert '<ac:parameter ac:name="jqlQuery">project=PROJ AND status=Open</ac:parameter>' in result

    def test_regular_list_not_affected(self):
        result = convert_markdown("- Item one\n- Item two")
        assert "<ul>" in result
        assert "<li>" in result
        assert "<ac:structured-macro" not in result


# ---------------------------------------------------------------------------
# Reverse conversion
# ---------------------------------------------------------------------------


class TestMacroReverseConversion:
    def test_status(self):
        html = (
            '<ac:structured-macro ac:name="status">'
            '<ac:parameter ac:name="title">Done</ac:parameter>'
            '<ac:parameter ac:name="colour">Green</ac:parameter>'
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(html)
        assert "{status:Done|colour=Green}" in result.markdown

    def test_toc(self):
        html = (
            '<ac:structured-macro ac:name="toc">'
            '<ac:parameter ac:name="maxLevel">3</ac:parameter>'
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(html)
        assert "{toc:maxLevel=3}" in result.markdown

    def test_toc_no_params(self):
        html = '<ac:structured-macro ac:name="toc"></ac:structured-macro>'
        result = convert_storage_to_markdown(html)
        assert "{toc}" in result.markdown

    def test_anchor(self):
        html = (
            '<ac:structured-macro ac:name="anchor">'
            '<ac:parameter ac:name="">my-section</ac:parameter>'
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(html)
        assert "{anchor:my-section}" in result.markdown

    def test_children(self):
        html = (
            '<ac:structured-macro ac:name="children">'
            '<ac:parameter ac:name="depth">3</ac:parameter>'
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(html)
        assert "{children:depth=3}" in result.markdown

    def test_jira_key(self):
        html = (
            '<ac:structured-macro ac:name="jira">'
            '<ac:parameter ac:name="key">PROJ-42</ac:parameter>'
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(html)
        assert "{jira:PROJ-42}" in result.markdown

    def test_jira_jql(self):
        html = (
            '<ac:structured-macro ac:name="jira">'
            '<ac:parameter ac:name="jqlQuery">status=Open</ac:parameter>'
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(html)
        assert "{jira:jql=status=Open}" in result.markdown

    def test_recently_updated(self):
        html = (
            '<ac:structured-macro ac:name="recently-updated">'
            '<ac:parameter ac:name="max">10</ac:parameter>'
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(html)
        assert "{recently-updated:max=10}" in result.markdown

    def test_excerpt_include(self):
        html = (
            '<ac:structured-macro ac:name="excerpt-include">'
            '<ac:parameter ac:name="">'
            '<ac:link><ri:page ri:content-title="Getting Started" /></ac:link>'
            "</ac:parameter>"
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(html)
        assert "{excerpt-include:Getting Started}" in result.markdown

    def test_include(self):
        html = (
            '<ac:structured-macro ac:name="include">'
            '<ac:parameter ac:name="">'
            '<ac:link><ri:page ri:content-title="API Docs" ri:space-key="DEV" /></ac:link>'
            "</ac:parameter>"
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(html)
        assert "{include:API Docs|space=DEV}" in result.markdown

    def test_excerpt_container(self):
        html = (
            '<ac:structured-macro ac:name="excerpt">'
            '<ac:parameter ac:name="hidden">true</ac:parameter>'
            "<ac:rich-text-body><p>Hidden content</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        result = convert_storage_to_markdown(html)
        assert "::: excerpt hidden" in result.markdown
        assert "Hidden content" in result.markdown
        assert ":::" in result.markdown


# ---------------------------------------------------------------------------
# Round-trip tests (Markdown → Storage → Markdown)
# ---------------------------------------------------------------------------


class TestMacroRoundTrips:
    def _round_trip(self, md: str) -> str:
        """Convert MD → Confluence → MD and return the final markdown."""
        storage = convert_markdown(md)
        result = convert_storage_to_markdown(storage)
        return result.markdown

    def test_status_round_trip(self):
        md = self._round_trip("The task is {status:Done|colour=Green}.")
        assert "{status:Done|colour=Green}" in md

    def test_toc_round_trip(self):
        md = self._round_trip("{toc:maxLevel=3}")
        assert "{toc:maxLevel=3}" in md

    def test_excerpt_include_round_trip(self):
        md = self._round_trip("{excerpt-include:Getting Started}")
        assert "{excerpt-include:Getting Started}" in md

    def test_excerpt_container_round_trip(self):
        md = self._round_trip("::: excerpt hidden\nSome excerpt text.\n:::")
        assert "::: excerpt hidden" in md
        assert "Some excerpt text." in md

    def test_jira_key_round_trip(self):
        md = self._round_trip("{jira:PROJ-42}")
        assert "{jira:PROJ-42}" in md
