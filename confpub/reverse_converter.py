"""Confluence Storage Format → Markdown converter.

Uses markdownify (subclassed) to convert standard HTML, with BeautifulSoup
pre-processing to handle Confluence-specific ac:*/ri:* namespaced elements.

This module is pure: no network, no file I/O, no side effects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import MarkdownConverter

# Inverse of converter.py ADMONITION_MAP
REVERSE_ADMONITION_MAP: dict[str, str] = {
    "info": "NOTE",
    "tip": "TIP",
    "warning": "WARNING",
    "note": "CAUTION",
}


@dataclass
class ConversionResult:
    """Result of converting Confluence Storage Format to Markdown."""

    markdown: str
    warnings: list[str] = field(default_factory=list)
    unknown_macros: list[str] = field(default_factory=list)


class ConfluenceMarkdownConverter(MarkdownConverter):
    """Subclass of markdownify's MarkdownConverter with Confluence macro support."""

    def __init__(self, attachment_map: dict[str, str] | None = None, **kwargs: Any) -> None:
        self._attachment_map = attachment_map or {}
        self._warnings: list[str] = []
        self._unknown_macros: list[str] = []
        kwargs.setdefault("heading_style", "ATX")
        kwargs.setdefault("bullets", "-")
        kwargs.setdefault("code_language", "")
        # Don't strip spans — we use <span> for inline macros like mathinline.
        # Regular spans are handled in convert_span by returning raw text.
        super().__init__(**kwargs)

    # ------------------------------------------------------------------
    # Definition list support
    # ------------------------------------------------------------------

    def convert_dl(self, el: Tag, text: str, parent_tags: set | None = None) -> str:
        return "\n\n" + text.strip() + "\n\n"

    def convert_dt(self, el: Tag, text: str, parent_tags: set | None = None) -> str:
        return text.strip() + "\n"

    def convert_dd(self, el: Tag, text: str, parent_tags: set | None = None) -> str:
        return ": " + text.strip() + "\n"

    # ------------------------------------------------------------------
    # Confluence macro handlers (dispatched via data-confluence-macro attr)
    # ------------------------------------------------------------------

    def convert_span(self, el: Tag, text: str, parent_tags: set | None = None) -> str:
        macro_name = el.get("data-confluence-macro")
        if macro_name:
            return self._convert_macro(el, text, str(macro_name))
        return text

    def convert_div(self, el: Tag, text: str, parent_tags: set | None = None) -> str:
        macro_name = el.get("data-confluence-macro")
        if macro_name:
            return self._convert_macro(el, text, str(macro_name))
        # Layout containers (from _preprocess_storage_format)
        layout_macro = el.get("data-layout-macro")
        if layout_macro == "layout":
            layout_type = el.get("data-layout-type", "single")
            inner = text.strip()
            return f"\n\n:::: layout {layout_type}\n{inner}\n::::\n\n"
        if layout_macro == "cell":
            inner = text.strip()
            return f"\n::: cell\n{inner}\n:::\n"
        return text

    def _convert_macro(self, el: Tag, text: str, macro_name: str) -> str:
        if macro_name == "code":
            return self._convert_code_macro(el)
        if macro_name in REVERSE_ADMONITION_MAP:
            return self._convert_admonition_macro(el, text, macro_name)
        if macro_name == "mathinline":
            return self._convert_mathinline_macro(el)
        if macro_name == "mathblock":
            return self._convert_mathblock_macro(el)
        if macro_name == "panel":
            return self._convert_panel_macro(el)
        if macro_name == "expand":
            return self._convert_expand_macro(el)
        if macro_name == "status":
            return self._convert_status_macro(el)
        if macro_name in ("toc", "children", "recently-updated"):
            return self._convert_simple_macro(el, macro_name)
        if macro_name == "anchor":
            return self._convert_anchor_macro(el)
        if macro_name == "jira":
            return self._convert_jira_macro(el)
        if macro_name in ("excerpt-include", "include"):
            return self._convert_page_ref_macro(el, macro_name)
        if macro_name == "excerpt":
            return self._convert_excerpt_macro(el)
        if macro_name in ("html", "html-macro"):
            return self._convert_html_macro(el)
        # Unknown macro
        self._unknown_macros.append(macro_name)
        self._warnings.append(f"Unknown macro '{macro_name}' converted to HTML comment")
        params = el.get("data-macro-params", "")
        param_str = f" params={params}" if params else ""
        return f"\n\n<!-- confluence-macro: {macro_name}{param_str} -->\n\n"

    def _convert_mathinline_macro(self, el: Tag) -> str:
        code_el = el.find("pre", class_="confluence-code-body")
        latex = code_el.get_text() if code_el else el.get_text()
        return f"${latex}$"

    def _convert_mathblock_macro(self, el: Tag) -> str:
        code_el = el.find("pre", class_="confluence-code-body")
        latex = code_el.get_text() if code_el else el.get_text()
        return f"\n\n$$\n{latex}\n$$\n\n"

    def _convert_panel_macro(self, el: Tag) -> str:
        params = el.get("data-macro-params", "") or ""
        title = ""
        for part in str(params).split("; "):
            if part.startswith("title="):
                title = part[len("title="):]
                break
        body_el = el.find("div", class_="confluence-rich-text-body")
        if body_el:
            body_text = self.convert(str(body_el)).strip()
        else:
            body_text = el.get_text().strip()
        header = f"panel {title}" if title else "panel"
        return f"\n\n::: {header}\n{body_text}\n:::\n\n"

    def _convert_expand_macro(self, el: Tag) -> str:
        params = el.get("data-macro-params", "") or ""
        title = ""
        for part in str(params).split("; "):
            if part.startswith("title="):
                title = part[len("title="):]
                break
        body_el = el.find("div", class_="confluence-rich-text-body")
        if body_el:
            body_text = self.convert(str(body_el)).strip()
        else:
            body_text = el.get_text().strip()
        header = f"expand {title}" if title else "expand"
        return f"\n\n::: {header}\n{body_text}\n:::\n\n"

    def _convert_code_macro(self, el: Tag) -> str:
        language = el.get("data-macro-language", "") or ""
        # The code content is in the pre-processed plain text
        code_el = el.find("pre", class_="confluence-code-body")
        if code_el:
            code = code_el.get_text()
        else:
            code = el.get_text()
        # Strip trailing newline if present (fenced blocks add their own)
        if code.endswith("\n"):
            code_body = code
        else:
            code_body = code + "\n"
        return f"\n\n```{language}\n{code_body}```\n\n"

    def _convert_admonition_macro(self, el: Tag, text: str, macro_name: str) -> str:
        admonition_type = REVERSE_ADMONITION_MAP[macro_name]
        # The body content is in the rich-text-body div
        body_el = el.find("div", class_="confluence-rich-text-body")
        if body_el:
            body_text = self.convert(str(body_el)).strip()
        else:
            body_text = text.strip()
        # Format as GitHub-flavored admonition
        lines = body_text.split("\n")
        quoted = "\n".join(f"> {line}" if line.strip() else ">" for line in lines)
        return f"\n\n> [!{admonition_type}]\n{quoted}\n\n"

    # ------------------------------------------------------------------
    # Confluence macro helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_macro_params(el: Tag) -> dict[str, str]:
        """Parse ``data-macro-params`` semicolon-delimited string into dict."""
        raw = str(el.get("data-macro-params", "") or "")
        if not raw:
            return {}
        params: dict[str, str] = {}
        for part in raw.split("; "):
            if "=" in part:
                key, _, value = part.partition("=")
                params[key] = value
        return params

    @staticmethod
    def _build_macro_syntax(
        name: str,
        positional: str,
        params: dict[str, str],
        is_block: bool,
    ) -> str:
        """Reconstruct ``{name:pos|k=v}`` string."""
        segments: list[str] = []
        if positional:
            segments.append(positional)
        for k, v in params.items():
            segments.append(f"{k}={v}")
        if segments:
            inner = f"{name}:{"|".join(segments)}"
        else:
            inner = name
        syntax = "{" + inner + "}"
        if is_block:
            return f"\n\n{syntax}\n\n"
        return syntax

    def _convert_status_macro(self, el: Tag) -> str:
        params = self._extract_macro_params(el)
        positional = params.pop("title", "")
        is_block = el.name != "span"
        return self._build_macro_syntax("status", positional, params, is_block)

    def _convert_simple_macro(self, el: Tag, macro_name: str) -> str:
        params = self._extract_macro_params(el)
        is_block = el.name != "span"
        return self._build_macro_syntax(macro_name, "", params, is_block)

    def _convert_anchor_macro(self, el: Tag) -> str:
        params = self._extract_macro_params(el)
        positional = params.pop("", "")
        is_block = el.name != "span"
        return self._build_macro_syntax("anchor", positional, params, is_block)

    def _convert_jira_macro(self, el: Tag) -> str:
        params = self._extract_macro_params(el)
        positional = ""
        if "key" in params:
            positional = params.pop("key")
        elif "jqlQuery" in params:
            params["jql"] = params.pop("jqlQuery")
        is_block = el.name != "span"
        return self._build_macro_syntax("jira", positional, params, is_block)

    def _convert_page_ref_macro(self, el: Tag, macro_name: str) -> str:
        page_title = str(el.get("data-macro-page-title", "") or "")
        space_key = str(el.get("data-macro-space-key", "") or "")
        params: dict[str, str] = {}
        if space_key:
            params["space"] = space_key
        is_block = el.name != "span"
        return self._build_macro_syntax(macro_name, page_title, params, is_block)

    def _convert_excerpt_macro(self, el: Tag) -> str:
        params = self._extract_macro_params(el)
        hidden = params.get("hidden", "").lower() == "true"
        body_el = el.find("div", class_="confluence-rich-text-body")
        if body_el:
            body_text = self.convert(str(body_el)).strip()
        else:
            body_text = el.get_text().strip()
        header = "excerpt hidden" if hidden else "excerpt"
        return f"\n\n::: {header}\n{body_text}\n:::\n\n"

    def _convert_html_macro(self, el: Tag) -> str:
        code_el = el.find("pre", class_="confluence-code-body")
        content = code_el.get_text() if code_el else ""
        return f"\n\n::: html\n{content}\n:::\n\n"

    # ------------------------------------------------------------------
    # Image handling (pre-processed from ac:image)
    # ------------------------------------------------------------------

    def convert_img(self, el: Tag, text: str, parent_tags: set | None = None) -> str:
        src = el.get("src", "")
        alt = el.get("alt", "")
        attachment_name = el.get("data-attachment-name", "")
        if attachment_name and attachment_name in self._attachment_map:
            local_path = self._attachment_map[attachment_name]
            return f"![{alt}]({local_path})"
        if src:
            return f"![{alt}]({src})"
        if attachment_name:
            return f"![{alt}]({attachment_name})"
        return f"![{alt}]()"

    # ------------------------------------------------------------------
    # Confluence link handling (pre-processed from ac:link)
    # ------------------------------------------------------------------

    def convert_a(self, el: Tag, text: str, parent_tags: set | None = None) -> str:
        href = el.get("href", "")
        page_title = el.get("data-confluence-page", "")
        if page_title:
            link_text = text.strip() or page_title
            return f"[{link_text}]({page_title})"
        return super().convert_a(el, text, parent_tags=parent_tags or set())


# ---------------------------------------------------------------------------
# Pre-processing: transform Confluence namespaced elements to standard HTML
# ---------------------------------------------------------------------------


def _preprocess_storage_format(html: str) -> tuple[BeautifulSoup, list[str]]:
    """Parse and transform Confluence Storage Format into standard HTML.

    Returns the modified soup and a list of warnings.
    """
    warnings: list[str] = []
    soup = BeautifulSoup(html, "html.parser")

    # Inline macro names that should become <span> not <div> to preserve
    # surrounding whitespace when markdownify processes them.
    _INLINE_MACROS = {"mathinline", "status", "anchor", "jira"}

    # 1. Transform ac:structured-macro → div/span[data-confluence-macro]
    for macro in soup.find_all("ac:structured-macro"):
        macro_name = macro.get("ac:name", "unknown")
        tag_name = "span" if macro_name in _INLINE_MACROS else "div"
        div = soup.new_tag(tag_name)
        div["data-confluence-macro"] = macro_name

        # Extract parameters
        params: dict[str, str] = {}
        page_ref_title = ""
        page_ref_space = ""
        for param in macro.find_all("ac:parameter"):
            param_name = param.get("ac:name", "")
            # Detect ri:page inside parameter (excerpt-include, include)
            ri_page = param.find("ri:page")
            if ri_page:
                page_ref_title = ri_page.get("ri:content-title", "")
                page_ref_space = ri_page.get("ri:space-key", "")
                params[param_name] = page_ref_title
            else:
                param_value = param.get_text()
                params[param_name] = param_value
            if param_name == "language":
                div["data-macro-language"] = param.get_text()

        if page_ref_title:
            div["data-macro-page-title"] = page_ref_title
        if page_ref_space:
            div["data-macro-space-key"] = page_ref_space

        if params:
            div["data-macro-params"] = "; ".join(f"{k}={v}" for k, v in params.items())

        # Extract plain-text-body (code blocks)
        plain_body = macro.find("ac:plain-text-body")
        if plain_body:
            # CDATA content is the text content
            code_text = plain_body.get_text()
            pre = soup.new_tag("pre")
            pre["class"] = "confluence-code-body"
            pre.string = code_text
            div.append(pre)

        # Extract rich-text-body (admonitions, etc.)
        rich_body = macro.find("ac:rich-text-body")
        if rich_body:
            body_div = soup.new_tag("div")
            body_div["class"] = "confluence-rich-text-body"
            for child in list(rich_body.children):
                body_div.append(child.extract())
            div.append(body_div)

        macro.replace_with(div)

    # 2. Transform ac:image → img
    for img_macro in soup.find_all("ac:image"):
        img = soup.new_tag("img")

        # Check for ri:attachment (local file)
        ri_att = img_macro.find("ri:attachment")
        if ri_att:
            filename = ri_att.get("ri:filename", "")
            img["data-attachment-name"] = filename
            img["alt"] = filename
            img["src"] = filename

        # Check for ri:url (external URL)
        ri_url = img_macro.find("ri:url")
        if ri_url:
            url = ri_url.get("ri:value", "")
            img["src"] = url
            img["alt"] = ""

        img_macro.replace_with(img)

    # 3. Transform ac:task-list → ul with checkbox text
    for task_list in soup.find_all("ac:task-list"):
        ul = soup.new_tag("ul")
        for task in task_list.find_all("ac:task", recursive=False):
            li = soup.new_tag("li")
            status_el = task.find("ac:task-status")
            status = status_el.get_text().strip() if status_el else "incomplete"
            checkbox = "[x] " if status == "complete" else "[ ] "
            body_el = task.find("ac:task-body")
            body_text = body_el.get_text().strip() if body_el else ""
            li.string = checkbox + body_text
            ul.append(li)
        task_list.replace_with(ul)

    # 4. Transform footnote markup
    # Footnote refs: <sup><a href="#footnote-N">[N]</a></sup>
    for sup in soup.find_all("sup"):
        a_tag = sup.find("a")
        if a_tag and a_tag.get("href", "").startswith("#footnote-"):
            text = a_tag.get_text()
            # e.g. "[1]" → "[^1]"
            if text.startswith("[") and text.endswith("]"):
                num = text[1:-1]
                sup.replace_with(f"[^{num}]")

    # Footnote definitions: detect by id="footnote-N" OR by back-link pattern
    # (Confluence strips id attrs, so we fall back to detecting back-links)
    _footnote_back_re = re.compile(r"#footnote-ref-(\d+)")
    footnote_lis_found = False
    for li in soup.find_all("li"):
        li_id = li.get("id", "")
        num = None
        if li_id.startswith("footnote-"):
            num = li_id[len("footnote-"):]
        else:
            # Fallback: detect by back-link <a href="#footnote-ref-N">
            for back_a in li.find_all("a"):
                m = _footnote_back_re.search(back_a.get("href", ""))
                if m:
                    num = m.group(1)
                    break
        if num:
            footnote_lis_found = True
            # Remove back-links
            for back_a in li.find_all("a"):
                if _footnote_back_re.search(back_a.get("href", "")):
                    back_a.decompose()
            text = li.get_text().strip()
            p = soup.new_tag("p")
            p.string = f"[^{num}]: {text}"
            li.replace_with(p)

    # Remove <hr> before footnote <ol> (the separator)
    if footnote_lis_found:
        for hr in soup.find_all("hr"):
            next_sib = hr.find_next_sibling()
            if next_sib and next_sib.name == "ol":
                hr.decompose()

    # 5. Transform ac:layout → div[data-layout-macro] per section
    for layout in soup.find_all("ac:layout"):
        sections = layout.find_all("ac:layout-section", recursive=False)
        if not sections:
            layout.decompose()
            continue
        # Build one layout div per section, then replace the ac:layout
        section_divs = []
        for section in sections:
            layout_div = soup.new_tag("div")
            layout_div["data-layout-macro"] = "layout"
            layout_type = section.get("ac:type", "single")
            layout_type = layout_type.replace("_", "-")
            layout_div["data-layout-type"] = layout_type
            for cell in section.find_all("ac:layout-cell", recursive=False):
                cell_div = soup.new_tag("div")
                cell_div["data-layout-macro"] = "cell"
                for child in list(cell.children):
                    cell_div.append(child.extract())
                layout_div.append(cell_div)
            section_divs.append(layout_div)
        # Insert all section divs after the layout, then remove it
        for div in reversed(section_divs):
            layout.insert_after(div)
        layout.decompose()

    # 6. Transform ac:link → a
    for link in soup.find_all("ac:link"):
        a = soup.new_tag("a")

        ri_page = link.find("ri:page")
        if ri_page:
            page_title = ri_page.get("ri:content-title", "")
            a["data-confluence-page"] = page_title
            a["href"] = page_title

        # Get link body text
        link_body = link.find("ac:link-body") or link.find("ac:plain-text-link-body")
        if link_body:
            a.string = link_body.get_text()
        elif ri_page:
            a.string = ri_page.get("ri:content-title", "")

        link.replace_with(a)

    return soup, warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def convert_storage_to_markdown(
    storage_format: str,
    *,
    attachment_map: dict[str, str] | None = None,
) -> ConversionResult:
    """Convert Confluence Storage Format HTML to Markdown.

    Args:
        storage_format: Confluence Storage Format XHTML string.
        attachment_map: Mapping of attachment filenames to local paths.

    Returns:
        ConversionResult with markdown, warnings, and unknown_macros.
    """
    if not storage_format or not storage_format.strip():
        return ConversionResult(markdown="")

    soup, preprocess_warnings = _preprocess_storage_format(storage_format)

    converter = ConfluenceMarkdownConverter(attachment_map=attachment_map)
    markdown = converter.convert(str(soup))

    # Clean up excessive blank lines
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip() + "\n"

    warnings = preprocess_warnings + converter._warnings
    unknown_macros = converter._unknown_macros

    return ConversionResult(
        markdown=markdown,
        warnings=warnings,
        unknown_macros=unknown_macros,
    )
