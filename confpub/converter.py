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

import yaml

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.tasklists import tasklists_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.container import container_plugin

from confpub.macro_plugin import confluence_macro_plugin

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
        self._list_stack: list[str] = []  # track nested ol/ul ("ol", "ul", "task-list")
        self._task_id: int = 0  # incrementing counter for Confluence task IDs
        self._footnote_refs: dict[int, int] = {}  # meta.id → display number

    def render(self, tokens: list[Token], options: dict[str, Any], env: dict[str, Any]) -> str:
        """Render a list of tokens to Confluence Storage Format."""
        self._output = []
        self._list_stack = []
        self._task_id = 0
        self._footnote_refs = {}
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
        if self._list_stack and self._list_stack[-1] == "task-list":
            return idx + 1  # suppress <p> inside task-body
        self._output.append("<p>")
        return idx + 1

    def _render_paragraph_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        if self._list_stack and self._list_stack[-1] == "task-list":
            return idx + 1  # suppress </p> inside task-body
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
            elif token.type == "math_inline":
                self._inline_math_inline(token)
            elif token.type == "footnote_ref":
                self._inline_footnote_ref(token)

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
        token = tokens[idx]
        attrs = token.attrs or {}
        if isinstance(attrs, dict) and attrs.get("class") == "contains-task-list":
            self._output.append("<ac:task-list>")
            self._list_stack.append("task-list")
        else:
            self._output.append("<ul>")
            self._list_stack.append("ul")
        return idx + 1

    def _render_bullet_list_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        if self._list_stack and self._list_stack[-1] == "task-list":
            self._output.append("</ac:task-list>")
        else:
            self._output.append("</ul>")
        if self._list_stack:
            self._list_stack.pop()
        return idx + 1

    def _render_list_item_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        token = tokens[idx]
        attrs = token.attrs or {}
        if isinstance(attrs, dict) and attrs.get("class") == "task-list-item":
            self._task_id += 1
            checked = self._is_task_checked(tokens, idx)
            status = "complete" if checked else "incomplete"
            self._output.append("<ac:task>")
            self._output.append(f"<ac:task-id>{self._task_id}</ac:task-id>")
            self._output.append(f"<ac:task-status>{status}</ac:task-status>")
            self._output.append("<ac:task-body>")
        else:
            self._output.append("<li>")
        return idx + 1

    def _render_list_item_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        if self._list_stack and self._list_stack[-1] == "task-list":
            self._output.append("</ac:task-body></ac:task>")
        else:
            self._output.append("</li>")
        return idx + 1

    @staticmethod
    def _is_task_checked(tokens: list[Token], list_item_idx: int) -> bool:
        """Look ahead from list_item_open to find the checkbox html_inline and check state."""
        for i in range(list_item_idx + 1, min(list_item_idx + 10, len(tokens))):
            tok = tokens[i]
            if tok.type == "list_item_close":
                break
            if tok.type == "inline" and tok.children:
                for child in tok.children:
                    if child.type == "html_inline" and "checkbox" in (child.content or ""):
                        return 'checked="checked"' in child.content or "checked" in child.content.split()
        return False

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
        # Suppress task-list checkboxes (already handled by _render_list_item_open)
        if "task-list-item-checkbox" in (token.content or ""):
            return
        self._output.append(token.content)

    # ------------------------------------------------------------------
    # Dollar math (inline and block)
    # ------------------------------------------------------------------

    def _inline_math_inline(self, token: Token) -> None:
        latex = token.content
        self._output.append(
            '<ac:structured-macro ac:name="mathinline">'
            f"<ac:plain-text-body><![CDATA[{latex}]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )

    def _render_math_block(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        latex = tokens[idx].content
        self._output.append(
            '<ac:structured-macro ac:name="mathblock">'
            f"<ac:plain-text-body><![CDATA[{latex}]]></ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        return idx + 1

    # ------------------------------------------------------------------
    # Definition lists
    # ------------------------------------------------------------------

    def _render_dl_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<dl>")
        return idx + 1

    def _render_dl_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</dl>")
        return idx + 1

    def _render_dt_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<dt>")
        return idx + 1

    def _render_dt_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</dt>")
        return idx + 1

    def _render_dd_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<dd>")
        return idx + 1

    def _render_dd_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</dd>")
        return idx + 1

    # ------------------------------------------------------------------
    # Footnotes
    # ------------------------------------------------------------------

    def _inline_footnote_ref(self, token: Token) -> None:
        meta_id = token.meta.get("id", 0) if token.meta else 0
        # Display number is 1-based
        display_num = meta_id + 1
        self._footnote_refs[meta_id] = display_num
        self._output.append(
            f'<sup><a id="footnote-ref-{display_num}" href="#footnote-{display_num}">'
            f"[{display_num}]</a></sup>"
        )

    def _render_footnote_block_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<hr /><ol>")
        return idx + 1

    def _render_footnote_block_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</ol>")
        return idx + 1

    def _render_footnote_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        meta_id = tokens[idx].meta.get("id", 0) if tokens[idx].meta else 0
        display_num = meta_id + 1
        self._output.append(f'<li id="footnote-{display_num}">')
        return idx + 1

    def _render_footnote_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</li>")
        return idx + 1

    def _render_footnote_anchor(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        meta_id = tokens[idx].meta.get("id", 0) if tokens[idx].meta else 0
        display_num = meta_id + 1
        self._output.append(
            f' <a href="#footnote-ref-{display_num}">\u21a9</a>'
        )
        return idx + 1

    # ------------------------------------------------------------------
    # Front matter (silently stripped)
    # ------------------------------------------------------------------

    def _render_front_matter(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        return idx + 1  # no output

    # ------------------------------------------------------------------
    # Container: panel
    # ------------------------------------------------------------------

    def _render_container_panel_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        info = tokens[idx].info.strip() if tokens[idx].info else ""
        # info is e.g. "panel My Title" — strip the container name prefix
        title = info[len("panel"):].strip() if info.startswith("panel") else info
        self._output.append('<ac:structured-macro ac:name="panel">')
        if title:
            self._output.append(f'<ac:parameter ac:name="title">{escape(title)}</ac:parameter>')
        self._output.append("<ac:rich-text-body>")
        return idx + 1

    def _render_container_panel_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</ac:rich-text-body></ac:structured-macro>")
        return idx + 1

    # ------------------------------------------------------------------
    # Container: expand
    # ------------------------------------------------------------------

    def _render_container_expand_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        info = tokens[idx].info.strip() if tokens[idx].info else ""
        title = info[len("expand"):].strip() if info.startswith("expand") else info
        self._output.append('<ac:structured-macro ac:name="expand">')
        if title:
            self._output.append(f'<ac:parameter ac:name="title">{escape(title)}</ac:parameter>')
        self._output.append("<ac:rich-text-body>")
        return idx + 1

    def _render_container_expand_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</ac:rich-text-body></ac:structured-macro>")
        return idx + 1

    # ------------------------------------------------------------------
    # Container: layout
    # ------------------------------------------------------------------

    def _render_container_layout_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        info = tokens[idx].info.strip() if tokens[idx].info else ""
        layout_type = info[len("layout"):].strip() if info.startswith("layout") else info
        # Convert hyphens to underscores for Confluence ac:type
        layout_type = layout_type.replace("-", "_") if layout_type else "single"
        self._output.append(f'<ac:layout><ac:layout-section ac:type="{escape(layout_type)}">')
        return idx + 1

    def _render_container_layout_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</ac:layout-section></ac:layout>")
        return idx + 1

    # ------------------------------------------------------------------
    # Container: cell
    # ------------------------------------------------------------------

    def _render_container_cell_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("<ac:layout-cell>")
        return idx + 1

    def _render_container_cell_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</ac:layout-cell>")
        return idx + 1

    # ------------------------------------------------------------------
    # Container: excerpt
    # ------------------------------------------------------------------

    def _render_container_excerpt_open(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        info = tokens[idx].info.strip() if tokens[idx].info else ""
        # info is e.g. "excerpt hidden" — strip the container name prefix
        rest = info[len("excerpt"):].strip() if info.startswith("excerpt") else info
        self._output.append('<ac:structured-macro ac:name="excerpt">')
        if "hidden" in rest.lower():
            self._output.append('<ac:parameter ac:name="hidden">true</ac:parameter>')
        self._output.append("<ac:rich-text-body>")
        return idx + 1

    def _render_container_excerpt_close(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        self._output.append("</ac:rich-text-body></ac:structured-macro>")
        return idx + 1

    # ------------------------------------------------------------------
    # Confluence macros (body-less, from macro_plugin.py)
    # ------------------------------------------------------------------

    def _render_confluence_macro(self, tokens: list[Token], idx: int, _o: Any, _e: Any) -> int:
        """Block-level macro token."""
        token = tokens[idx]
        name = token.info
        meta = token.meta or {}
        self._output.append(self._emit_macro(name, meta.get("positional", ""), meta.get("params", {})))
        return idx + 1

    def _inline_confluence_macro(self, token: Token) -> None:
        """Inline macro token."""
        name = token.info
        meta = token.meta or {}
        self._output.append(self._emit_macro(name, meta.get("positional", ""), meta.get("params", {})))

    def _emit_macro(self, name: str, positional: str, params: dict[str, str]) -> str:
        """Dispatch to per-macro handler or fall back to generic."""
        method_name = f"_macro_{name.replace('-', '_')}"
        handler = getattr(self, method_name, None)
        if handler:
            return handler(positional, params)
        return self._emit_generic_macro(name, positional, params)

    def _emit_generic_macro(self, name: str, positional: str, params: dict[str, str]) -> str:
        parts = [f'<ac:structured-macro ac:name="{escape(name)}">']
        if positional:
            parts.append(f'<ac:parameter ac:name="">{escape(positional)}</ac:parameter>')
        for k, v in params.items():
            parts.append(f'<ac:parameter ac:name="{escape(k)}">{escape(v)}</ac:parameter>')
        parts.append("</ac:structured-macro>")
        return "".join(parts)

    def _macro_status(self, positional: str, params: dict[str, str]) -> str:
        parts = ['<ac:structured-macro ac:name="status">']
        if positional:
            parts.append(f'<ac:parameter ac:name="title">{escape(positional)}</ac:parameter>')
        for k, v in params.items():
            parts.append(f'<ac:parameter ac:name="{escape(k)}">{escape(v)}</ac:parameter>')
        parts.append("</ac:structured-macro>")
        return "".join(parts)

    def _macro_toc(self, positional: str, params: dict[str, str]) -> str:
        parts = ['<ac:structured-macro ac:name="toc">']
        for k, v in params.items():
            parts.append(f'<ac:parameter ac:name="{escape(k)}">{escape(v)}</ac:parameter>')
        parts.append("</ac:structured-macro>")
        return "".join(parts)

    def _macro_anchor(self, positional: str, params: dict[str, str]) -> str:
        parts = ['<ac:structured-macro ac:name="anchor">']
        if positional:
            parts.append(f'<ac:parameter ac:name="">{escape(positional)}</ac:parameter>')
        parts.append("</ac:structured-macro>")
        return "".join(parts)

    def _macro_children(self, positional: str, params: dict[str, str]) -> str:
        parts = ['<ac:structured-macro ac:name="children">']
        for k, v in params.items():
            parts.append(f'<ac:parameter ac:name="{escape(k)}">{escape(v)}</ac:parameter>')
        parts.append("</ac:structured-macro>")
        return "".join(parts)

    def _macro_jira(self, positional: str, params: dict[str, str]) -> str:
        parts = ['<ac:structured-macro ac:name="jira">']
        if "jql" in params or "jqlQuery" in params:
            jql_value = params.pop("jql", "") or params.pop("jqlQuery", "")
            parts.append(f'<ac:parameter ac:name="jqlQuery">{escape(jql_value)}</ac:parameter>')
        elif positional:
            parts.append(f'<ac:parameter ac:name="key">{escape(positional)}</ac:parameter>')
        for k, v in params.items():
            parts.append(f'<ac:parameter ac:name="{escape(k)}">{escape(v)}</ac:parameter>')
        parts.append("</ac:structured-macro>")
        return "".join(parts)

    def _macro_recently_updated(self, positional: str, params: dict[str, str]) -> str:
        parts = ['<ac:structured-macro ac:name="recently-updated">']
        for k, v in params.items():
            parts.append(f'<ac:parameter ac:name="{escape(k)}">{escape(v)}</ac:parameter>')
        parts.append("</ac:structured-macro>")
        return "".join(parts)

    def _macro_excerpt_include(self, positional: str, params: dict[str, str]) -> str:
        space = params.pop("space", "")
        parts = ['<ac:structured-macro ac:name="excerpt-include">']
        parts.append('<ac:parameter ac:name="">')
        ri_attrs = f'ri:content-title="{escape(positional)}"'
        if space:
            ri_attrs += f' ri:space-key="{escape(space)}"'
        parts.append(f"<ac:link><ri:page {ri_attrs} /></ac:link>")
        parts.append("</ac:parameter>")
        for k, v in params.items():
            parts.append(f'<ac:parameter ac:name="{escape(k)}">{escape(v)}</ac:parameter>')
        parts.append("</ac:structured-macro>")
        return "".join(parts)

    def _macro_include(self, positional: str, params: dict[str, str]) -> str:
        space = params.pop("space", "")
        parts = ['<ac:structured-macro ac:name="include">']
        parts.append('<ac:parameter ac:name="">')
        ri_attrs = f'ri:content-title="{escape(positional)}"'
        if space:
            ri_attrs += f' ri:space-key="{escape(space)}"'
        parts.append(f"<ac:link><ri:page {ri_attrs} /></ac:link>")
        parts.append("</ac:parameter>")
        for k, v in params.items():
            parts.append(f'<ac:parameter ac:name="{escape(k)}">{escape(v)}</ac:parameter>')
        parts.append("</ac:structured-macro>")
        return "".join(parts)


def _create_parser() -> MarkdownIt:
    """Create a configured markdown-it-py parser."""
    md = MarkdownIt("commonmark", {"html": True})
    md.enable("table")
    md.enable("strikethrough")
    # mdit-py-plugins
    tasklists_plugin(md)
    dollarmath_plugin(md)
    deflist_plugin(md)
    footnote_plugin(md)
    front_matter_plugin(md)
    container_plugin(md, name="panel")
    container_plugin(md, name="expand")
    container_plugin(md, name="layout")
    container_plugin(md, name="cell")
    container_plugin(md, name="excerpt")
    confluence_macro_plugin(md)
    return md


_LAYOUT_BLOCK_RE = re.compile(r"<ac:layout>.*?</ac:layout>", re.DOTALL)

_LAYOUT_WRAP_PREFIX = (
    '<ac:layout><ac:layout-section ac:type="single"><ac:layout-cell>'
)
_LAYOUT_WRAP_SUFFIX = "</ac:layout-cell></ac:layout-section></ac:layout>"


def _wrap_non_layout_content(html: str) -> str:
    """Wrap content outside ``<ac:layout>`` blocks in single-column layouts.

    Confluence Server's editor cannot handle a mix of layout blocks and
    top-level content on the same page — it enters "layout mode" and makes
    everything outside cells read-only.  This function detects when layout
    blocks are present and wraps any surrounding content in its own
    single-column layout so the entire page is in layout mode.
    """
    if "<ac:layout>" not in html:
        return html

    parts: list[str] = []
    last_end = 0

    for match in _LAYOUT_BLOCK_RE.finditer(html):
        before = html[last_end:match.start()]
        if before.strip():
            parts.append(_LAYOUT_WRAP_PREFIX + before + _LAYOUT_WRAP_SUFFIX)
        parts.append(match.group(0))
        last_end = match.end()

    after = html[last_end:]
    if after.strip():
        parts.append(_LAYOUT_WRAP_PREFIX + after + _LAYOUT_WRAP_SUFFIX)

    return "".join(parts)


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
    html = renderer.render(tokens, {}, {})
    return _wrap_non_layout_content(html)


def extract_h1_title(md_text: str) -> str | None:
    """Extract the text of the first H1 heading from Markdown source.

    Returns the title string, or None if no H1 is found.
    """
    parser = _create_parser()
    tokens = parser.parse(md_text)
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h1":
            # The next token should be an inline token with the heading content
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                inline = tokens[i + 1]
                if inline.children:
                    parts: list[str] = []
                    for child in inline.children:
                        if child.type in ("text", "code_inline"):
                            parts.append(child.content)
                    return "".join(parts) if parts else None
    return None


def extract_front_matter(md_text: str) -> dict[str, Any] | None:
    """Extract YAML front-matter as a raw dict, or None.

    Uses the markdown-it-py front_matter plugin to locate the block,
    then parses with yaml.safe_load.  Returns None if no front-matter
    is present, if the YAML is invalid, or if the result is not a mapping.
    """
    parser = _create_parser()
    tokens = parser.parse(md_text)
    for token in tokens:
        if token.type == "front_matter":
            try:
                data = yaml.safe_load(token.content)
            except yaml.YAMLError:
                return None
            if isinstance(data, dict):
                return data
            return None
    return None


def fingerprint_content(content: str) -> str:
    """Return SHA-256 hex digest of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
