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
        kwargs.setdefault("strip", ["span"])
        super().__init__(**kwargs)

    # ------------------------------------------------------------------
    # Confluence macro handlers (dispatched via data-confluence-macro attr)
    # ------------------------------------------------------------------

    def convert_div(self, el: Tag, text: str, parent_tags: set | None = None) -> str:
        macro_name = el.get("data-confluence-macro")
        if macro_name:
            return self._convert_macro(el, text, str(macro_name))
        return text

    def _convert_macro(self, el: Tag, text: str, macro_name: str) -> str:
        if macro_name == "code":
            return self._convert_code_macro(el)
        if macro_name in REVERSE_ADMONITION_MAP:
            return self._convert_admonition_macro(el, text, macro_name)
        # Unknown macro
        self._unknown_macros.append(macro_name)
        self._warnings.append(f"Unknown macro '{macro_name}' converted to HTML comment")
        params = el.get("data-macro-params", "")
        param_str = f" params={params}" if params else ""
        return f"\n\n<!-- confluence-macro: {macro_name}{param_str} -->\n\n"

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

    # 1. Transform ac:structured-macro → div[data-confluence-macro]
    for macro in soup.find_all("ac:structured-macro"):
        macro_name = macro.get("ac:name", "unknown")
        div = soup.new_tag("div")
        div["data-confluence-macro"] = macro_name

        # Extract parameters
        params: dict[str, str] = {}
        for param in macro.find_all("ac:parameter"):
            param_name = param.get("ac:name", "")
            param_value = param.get_text()
            params[param_name] = param_value
            if param_name == "language":
                div["data-macro-language"] = param_value

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

    # 3. Transform ac:link → a
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
