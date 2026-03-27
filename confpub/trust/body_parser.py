"""HTML body analysis for the Structure subscore.

Parses Confluence Storage Format HTML to extract structural features
using BeautifulSoup4 (already a project dependency).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

# Case-insensitive placeholder patterns scanned in stripped body text
_PLACEHOLDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bTBD\b"),
    re.compile(r"\bTODO\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"(?i)\bcoming soon\b"),
    re.compile(r"(?i)\bplaceholder\b"),
]

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


@dataclass
class BodyFeatures:
    """Structural features extracted from a page body."""

    has_excerpt: bool = False
    heading_count: int = 0
    text_length: int = 0
    placeholder_texts: list[str] = field(default_factory=list)
    empty_section_count: int = 0
    outbound_link_count: int = 0
    internal_link_count: int = 0
    external_link_count: int = 0
    jira_macro_count: int = 0
    table_count: int = 0
    image_count: int = 0
    macro_names: list[str] = field(default_factory=list)
    anti_signal_matches: list[str] = field(default_factory=list)


def analyze_body(
    html: str,
    anti_signal_patterns: list[str] | None = None,
) -> BodyFeatures:
    """Analyze Confluence Storage Format HTML and return structural features.

    Args:
        html: Page body in Confluence Storage Format.
        anti_signal_patterns: Regex patterns for hard-cap anti-signals
            (e.g. "deprecated", "do not use").

    Returns:
        BodyFeatures with all structural signals populated.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    features = BodyFeatures()

    # --- Text length ---
    features.text_length = len(text)

    # --- Excerpt detection ---
    # Check for Confluence excerpt macro
    for tag in soup.find_all(["ac:structured-macro", "structured-macro"]):
        macro_name = (
            tag.get("ac:name") or tag.get("name") or ""  # type: ignore[union-attr]
        )
        if macro_name == "excerpt":
            features.has_excerpt = True
            break
    # Fallback: first <p> with substantial content
    if not features.has_excerpt:
        first_p = soup.find("p")
        if first_p and len(first_p.get_text(strip=True)) >= 50:
            features.has_excerpt = True

    # --- Headings ---
    headings = soup.find_all(_HEADING_TAGS)
    features.heading_count = len(headings)

    # --- Empty sections (heading followed by heading with no content) ---
    for i, heading in enumerate(headings):
        if i + 1 >= len(headings):
            break
        next_heading = headings[i + 1]
        # Walk siblings between this heading and the next
        has_content = False
        sibling = heading.next_sibling
        while sibling and sibling is not next_heading:
            if isinstance(sibling, Tag):
                sib_text = sibling.get_text(strip=True)
                if sib_text and sibling.name not in _HEADING_TAGS:
                    has_content = True
                    break
            elif isinstance(sibling, str) and sibling.strip():
                has_content = True
                break
            sibling = sibling.next_sibling
        if not has_content:
            features.empty_section_count += 1

    # --- Links (external, internal, total) ---
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        features.outbound_link_count += 1
        if href.startswith(("http://", "https://")):
            features.external_link_count += 1
        else:
            features.internal_link_count += 1
    # Confluence internal links (<ac:link>)
    for tag in soup.find_all(["ac:link", "link"]):
        features.outbound_link_count += 1
        features.internal_link_count += 1

    # --- Tables ---
    features.table_count = len(soup.find_all("table"))

    # --- Images / attachments ---
    features.image_count = len(soup.find_all("img"))
    features.image_count += len(soup.find_all(["ac:image", "image"]))

    # --- Confluence macros (jira, status, toc, etc.) ---
    for tag in soup.find_all(["ac:structured-macro", "structured-macro"]):
        macro_name = tag.get("ac:name") or tag.get("name") or ""
        if macro_name:
            features.macro_names.append(macro_name)
            if macro_name == "jira":
                features.jira_macro_count += 1

    # --- Placeholder text ---
    for pattern in _PLACEHOLDER_PATTERNS:
        matches = pattern.findall(text)
        features.placeholder_texts.extend(matches)

    # --- Anti-signal body matches (for hard caps) ---
    if anti_signal_patterns:
        for pat_str in anti_signal_patterns:
            pat = re.compile(pat_str)
            matches = pat.findall(text)
            features.anti_signal_matches.extend(matches)

    return features
