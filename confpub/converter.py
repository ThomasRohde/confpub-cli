"""Markdown → Confluence Storage Format converter.

Uses markdown-it-py to parse Markdown into a token stream, then renders
each token into Confluence Storage Format XHTML.

This module is pure: no network, no file I/O, no side effects.
"""

from __future__ import annotations

import hashlib
import re
from html import escape
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

# Admonition types mapping: GitHub [!TYPE] → Confluence macro name
ADMONITION_MAP: dict[str, str] = {
    "NOTE": "info",
    "TIP": "tip",
    "WARNING": "warning",
    "CAUTION": "note",
    "IMPORTANT": "warning",
}

# Regex to detect GitHub-flavored admonition in blockquote first line
_ADMONITION_RE = re.compile(r"^\[!(NOTE|TIP|WARNING|CAUTION|IMPORTANT)\]\s*$", re.IGNORECASE)


class ConfluenceRenderer:
    """Renders markdown-it-py tokens into Confluence Storage Format XHTML."""

    def __init__(self) -> None:
        self._output: list[str] = []
        self._list_stack: list[str] = []  # track nested ol/ul

    def render(self, tokens: list[Token], options: dict[str, Any], env: dict[str, Any]) -> str:
        """Render a list of tokens to Confluence Storage Format."""
        self._output = []
        self._list_stack = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            i = self._render_token(tokens, i, options, env)
        return "".join(self._output)

    def _render_token(
        self, tokens: list[Token], idx: int, options: dict[str, Any], env: dict[str, Any],
    ) -> int:
        """Render a single token. Returns the next index to process."""
        token = tokens[idx]
        handler = getattr(self, f"_render_{token.type}", None)
        if handler:
            return handler(tokens, idx, options, env)
        return idx + 1

    # ------------------------------------------------------------------
    # Block-level tokens
    # ------------------------------------------------------------------

    def _render_heading_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        tag = tokens[idx].tag
        self._output.append(f"<{tag}>")
        return idx + 1

    def _render_heading_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        tag = tokens[idx].tag
        self._output.append(f"</{tag}>")
        return idx + 1

    def _render_paragraph_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<p>")
        return idx + 1

    def _render_paragraph_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</p>")
        return idx + 1

    def _render_inline(self, tokens: list[Token], idx: int, options: Any, env: Any) -> int:
        token = tokens[idx]
        if token.children:
            for child in token.children:
                self._render_inline_token(child)
        return idx + 1

    def _render_inline_token(self, token: Token) -> None:
        """Render a single inline token (child of an inline block)."""
        handler = getattr(self, f"_inline_{token.type}", None)
        if handler:
            handler(token)
        else:
            # Fallback for unknown inline types
            if token.type == "text":
                self._output.append(escape(token.content))

    # ------------------------------------------------------------------
    # Inline tokens
    # ------------------------------------------------------------------

    def _inline_text(self, token: Token) -> None:
        self._output.append(escape(token.content))

    def _inline_softbreak(self, token: Token) -> None:
        self._output.append("\n")

    def _inline_hardbreak(self, token: Token) -> None:
        self._output.append("<br />")

    def _inline_strong_open(self, token: Token) -> None:
        self._output.append("<strong>")

    def _inline_strong_close(self, token: Token) -> None:
        self._output.append("</strong>")

    def _inline_em_open(self, token: Token) -> None:
        self._output.append("<em>")

    def _inline_em_close(self, token: Token) -> None:
        self._output.append("</em>")

    def _inline_s_open(self, token: Token) -> None:
        self._output.append("<del>")

    def _inline_s_close(self, token: Token) -> None:
        self._output.append("</del>")

    def _inline_code_inline(self, token: Token) -> None:
        self._output.append(f"<code>{escape(token.content)}</code>")

    def _inline_link_open(self, token: Token) -> None:
        href = ""
        if token.attrs:
            href = token.attrs.get("href", "") if isinstance(token.attrs, dict) else ""
        self._output.append(f'<a href="{escape(str(href))}">')

    def _inline_link_close(self, token: Token) -> None:
        self._output.append("</a>")

    def _inline_image(self, token: Token) -> None:
        """Render an image as a Confluence-compatible element.

        For local images, the assets module will later rewrite these to
        <ac:image><ri:attachment .../></ac:image>. For now, emit a standard
        img tag with a data attribute marking it for rewriting.
        """
        src = ""
        alt = token.content or ""
        if token.attrs:
            src = token.attrs.get("src", "") if isinstance(token.attrs, dict) else ""
        self._output.append(f'<ac:image><ri:url ri:value="{escape(str(src))}" /></ac:image>')

    # ------------------------------------------------------------------
    # Fenced code blocks → Confluence code macro
    # ------------------------------------------------------------------

    def _render_fence(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        token = tokens[idx]
        info = token.info.strip() if token.info else ""
        lang = info.split()[0] if info else ""
        content = token.content

        self._output.append('<ac:structured-macro ac:name="code">')
        if lang:
            self._output.append(
                f'<ac:parameter ac:name="language">{escape(lang)}</ac:parameter>'
            )
        self._output.append(f"<ac:plain-text-body><![CDATA[{content}]]></ac:plain-text-body>")
        self._output.append("</ac:structured-macro>")
        return idx + 1

    def _render_code_block(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        return self._render_fence(tokens, idx, _o, _e)

    # ------------------------------------------------------------------
    # Blockquotes and admonitions
    # ------------------------------------------------------------------

    def _render_blockquote_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        # Look ahead to detect GitHub-flavored admonitions
        admonition_type = self._detect_admonition(tokens, idx)
        if admonition_type:
            macro_name = ADMONITION_MAP.get(admonition_type.upper(), "info")
            self._output.append(f'<ac:structured-macro ac:name="{macro_name}">')
            self._output.append("<ac:rich-text-body>")
            # Mark that we're in an admonition (use tag as carrier)
            tokens[idx].meta = tokens[idx].meta or {}
            tokens[idx].meta["admonition"] = True
            tokens[idx].meta["admonition_skip_first"] = True
        else:
            self._output.append("<blockquote>")
        return idx + 1

    def _render_blockquote_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        # Find matching open to check if it was an admonition
        open_token = self._find_matching_open(tokens, idx, "blockquote_open", "blockquote_close")
        if open_token and open_token.meta and open_token.meta.get("admonition"):
            self._output.append("</ac:rich-text-body>")
            self._output.append("</ac:structured-macro>")
        else:
            self._output.append("</blockquote>")
        return idx + 1

    def _detect_admonition(self, tokens: list[Token], blockquote_idx: int) -> str | None:
        """Check if a blockquote starts with [!TYPE] admonition syntax."""
        # Walk forward to find the first inline content
        for i in range(blockquote_idx + 1, min(blockquote_idx + 10, len(tokens))):
            tok = tokens[i]
            if tok.type == "inline" and tok.children:
                first_child = tok.children[0]
                if first_child.type == "text":
                    match = _ADMONITION_RE.match(first_child.content.strip())
                    if match:
                        # Remove the admonition marker from the content
                        first_child.content = ""
                        # Remove leading newline if present
                        if len(tok.children) > 1 and tok.children[1].type == "softbreak":
                            tok.children.pop(1)
                        return match.group(1)
                return None
            if tok.type == "blockquote_close":
                return None
        return None

    def _find_matching_open(
        self, tokens: list[Token], close_idx: int, open_type: str, close_type: str,
    ) -> Token | None:
        """Walk backward from a close token to find its matching open."""
        depth = 0
        for i in range(close_idx, -1, -1):
            if tokens[i].type == close_type:
                depth += 1
            elif tokens[i].type == open_type:
                depth -= 1
                if depth == 0:
                    return tokens[i]
        return None

    # ------------------------------------------------------------------
    # Lists
    # ------------------------------------------------------------------

    def _render_ordered_list_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<ol>")
        self._list_stack.append("ol")
        return idx + 1

    def _render_ordered_list_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</ol>")
        if self._list_stack:
            self._list_stack.pop()
        return idx + 1

    def _render_bullet_list_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<ul>")
        self._list_stack.append("ul")
        return idx + 1

    def _render_bullet_list_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</ul>")
        if self._list_stack:
            self._list_stack.pop()
        return idx + 1

    def _render_list_item_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<li>")
        return idx + 1

    def _render_list_item_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</li>")
        return idx + 1

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def _render_table_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<table>")
        return idx + 1

    def _render_table_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</table>")
        return idx + 1

    def _render_thead_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<thead>")
        return idx + 1

    def _render_thead_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</thead>")
        return idx + 1

    def _render_tbody_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<tbody>")
        return idx + 1

    def _render_tbody_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</tbody>")
        return idx + 1

    def _render_tr_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<tr>")
        return idx + 1

    def _render_tr_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</tr>")
        return idx + 1

    def _render_th_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<th>")
        return idx + 1

    def _render_th_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</th>")
        return idx + 1

    def _render_td_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<td>")
        return idx + 1

    def _render_td_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</td>")
        return idx + 1

    # ------------------------------------------------------------------
    # Horizontal rule
    # ------------------------------------------------------------------

    def _render_hr(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<hr />")
        return idx + 1

    # ------------------------------------------------------------------
    # HTML block (pass through)
    # ------------------------------------------------------------------

    def _render_html_block(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append(tokens[idx].content)
        return idx + 1

    def _inline_html_inline(self, token: Token) -> None:
        self._output.append(token.content)


def _create_parser() -> MarkdownIt:
    """Create a configured markdown-it-py parser."""
    md = MarkdownIt("commonmark", {"html": True})
    md.enable("table")
    md.enable("strikethrough")
    return md


def convert_markdown(md_text: str) -> str:
    """Convert Markdown text to Confluence Storage Format.

    Args:
        md_text: Markdown source text.

    Returns:
        Confluence Storage Format XHTML string.
    """
    parser = _create_parser()
    tokens = parser.parse(md_text)
    renderer = ConfluenceRenderer()
    return renderer.render(tokens, {}, {})


def fingerprint_content(content: str) -> str:
    """Return SHA-256 hex digest of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
