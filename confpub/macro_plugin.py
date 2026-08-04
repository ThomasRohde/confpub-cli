"""Custom markdown-it-py plugin for Confluence macro syntax.

Recognises ``{macro-name:params}`` inside Markdown and emits
``confluence_macro`` tokens that the ConfluenceRenderer converts to
``<ac:structured-macro>`` elements.

Block rule: a line that contains *only* the macro syntax (after trimming)
becomes a block-level token (no ``<p>`` wrapping).

Inline rule: a macro embedded within running text becomes an inline token.

Parameter syntax::

    {name:positional|key1=value1|key2=value2}

The first segment without ``=`` is the *positional* value (e.g. page title,
issue key); remaining ``key=value`` pairs become named parameters.
"""

from __future__ import annotations

import re
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.rules_block import StateBlock
from markdown_it.rules_inline import StateInline

# Whitelisted macro names — prevents ``{variable}`` false positives.
KNOWN_MACROS: frozenset[str] = frozenset(
    [
        "status",
        "toc",
        "anchor",
        "children",
        "jira",
        "recently-updated",
        "excerpt-include",
        "include",
        "macro",
    ]
)

# Build alternation from known names (longest first to avoid partial matches).
_NAMES_ALT = "|".join(sorted(KNOWN_MACROS, key=len, reverse=True))

# Regex: ``{name}`` or ``{name:params}``
MACRO_RE = re.compile(r"\{(" + _NAMES_ALT + r")(?::([^}]*))?\}")


def parse_macro_params(raw: str | None) -> tuple[str, dict[str, str]]:
    """Parse a macro parameter string into positional + named params.

    >>> parse_macro_params("Done|colour=Green")
    ('Done', {'colour': 'Green'})
    >>> parse_macro_params(None)
    ('', {})
    """
    if not raw:
        return "", {}
    parts = raw.split("|")
    positional = ""
    params: dict[str, str] = {}
    for i, part in enumerate(parts):
        if "=" in part:
            key, _, value = part.partition("=")
            params[key.strip()] = value.strip()
        elif i == 0:
            positional = part.strip()
        # Extra positional segments (shouldn't happen) are silently ignored.
    return positional, params


# ---------------------------------------------------------------------------
# Block rule
# ---------------------------------------------------------------------------


def _macro_block_rule(
    state: StateBlock, startLine: int, endLine: int, silent: bool,
) -> bool:
    """Match a line that is *only* a macro invocation."""
    pos = state.bMarks[startLine] + state.tShift[startLine]
    max_pos = state.eMarks[startLine]
    line_text = state.src[pos:max_pos].strip()

    m = MACRO_RE.fullmatch(line_text)
    if not m:
        return False

    if silent:
        return True

    name = m.group(1)
    raw_params = m.group(2) or ""
    positional, params = parse_macro_params(raw_params)

    token = state.push("confluence_macro", "", 0)
    token.info = name
    token.meta = {"positional": positional, "params": params}
    token.block = True
    token.map = [startLine, startLine + 1]

    state.line = startLine + 1
    return True


# ---------------------------------------------------------------------------
# Inline rule
# ---------------------------------------------------------------------------


def _macro_inline_rule(state: StateInline, silent: bool) -> bool:
    """Match ``{macro:params}`` at the current position within text."""
    src = state.src
    pos = state.pos

    # Quick guard: must start with ``{``
    if pos >= state.posMax or src[pos] != "{":
        return False

    # Guard against backslash-escaped brace
    if pos > 0 and src[pos - 1] == "\\":
        return False

    m = MACRO_RE.match(src, pos)
    if not m:
        return False

    if silent:
        return True

    name = m.group(1)
    raw_params = m.group(2) or ""
    positional, params = parse_macro_params(raw_params)

    token = state.push("confluence_macro", "", 0)
    token.info = name
    token.meta = {"positional": positional, "params": params}

    state.pos = m.end()
    return True


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def confluence_macro_plugin(md: MarkdownIt) -> None:
    """Install block + inline rules for Confluence macro syntax."""
    md.block.ruler.before("fence", "confluence_macro", _macro_block_rule)
    md.inline.ruler.before("escape", "confluence_macro", _macro_inline_rule)
