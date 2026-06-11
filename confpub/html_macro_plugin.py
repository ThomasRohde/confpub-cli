"""Custom markdown-it-py plugin for ::: html blocks.

Recognises fenced blocks starting with `::: html` (case-insensitive) and
emits ``html_macro`` tokens that the ConfluenceRenderer wraps in the
configured Confluence HTML macro storage shape.

Block-level only — inline HTML macro syntax is a non-goal.
"""

from __future__ import annotations

import re
from markdown_it import MarkdownIt
from markdown_it.rules_block import StateBlock

# Opening fence: 3+ colons, whitespace, "html" (case-insensitive), end of line
_OPEN_RE = re.compile(r"^:{3,}\s+html\s*$", re.IGNORECASE)

# Closing fence: a line that is ONLY 3+ colons (and optional whitespace)
_CLOSE_RE = re.compile(r"^:{3,}\s*$")


def _html_macro_rule(
    state: StateBlock, startLine: int, endLine: int, silent: bool,
) -> bool:
    """Match a ::: html ... ::: block."""
    pos = state.bMarks[startLine] + state.tShift[startLine]
    max_pos = state.eMarks[startLine]
    line_text = state.src[pos:max_pos]

    if not _OPEN_RE.match(line_text):
        return False

    if silent:
        return True

    # Scan forward for closing fence
    next_line = startLine + 1
    found_close = False
    while next_line < endLine:
        line_pos = state.bMarks[next_line] + state.tShift[next_line]
        line_end = state.eMarks[next_line]
        candidate = state.src[line_pos:line_end]
        if _CLOSE_RE.match(candidate):
            found_close = True
            break
        next_line += 1

    if not found_close:
        return False

    # Extract raw content between fences
    content_start = state.bMarks[startLine + 1]
    content_end = state.bMarks[next_line]
    content = state.src[content_start:content_end]

    # Remove trailing newline if present (consistent with fence behavior)
    if content.endswith("\n"):
        content = content[:-1]

    token = state.push("html_macro", "", 0)
    token.content = content
    token.block = True
    token.map = [startLine, next_line + 1]

    state.line = next_line + 1
    return True


def html_macro_plugin(md: MarkdownIt) -> None:
    """Install block rule for ::: html fenced blocks."""
    md.block.ruler.before("fence", "html_macro", _html_macro_rule)
