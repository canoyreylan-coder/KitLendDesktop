"""Shared page-heading look for the student screens (header & label redesign).

Text-focused headings: no box, no border, no background. Hierarchy comes from type size,
spacing and subtle contrast; a few words get a soft lavender accent. Plain strings only (no Qt),
so every screen can append HEADER_QSS to its own stylesheet and stay consistent.
"""
from html import escape

from app import design_tokens as tk

ACCENT_LAVENDER = "#B9A8F5"    # title accent
ACCENT_PERIWINKLE = "#8B8FFF"  # secondary accent
ACCENT_DUSTY_PINK = "#D9A3B8"  # small highlights


def accent_html(text: str, accent: str, color: str = ACCENT_LAVENDER) -> str:
    """`text` with the words `accent` coloured (rich text for a QLabel). Safe for any text."""
    if not accent or accent not in text:
        return escape(text)
    before, _sep, after = text.partition(accent)
    return (f'{escape(before)}<span style="color:{color};">{escape(accent)}</span>'
            f'{escape(after)}')


HEADER_QSS = f"""
/* ---------- page headings (header & label redesign) ---------- */
QFrame#catHeader, QFrame#mlHeader, QFrame#catalogHeader, QFrame#homeWelcome {{
    background: transparent;
    border: none;
    border-radius: 0px;
}}
QLabel#catTag, QLabel#mlTag, QLabel#catalogTag, QLabel#homeEyebrow {{
    background: transparent;
    border: none;
    border-radius: 0px;
    padding: 0px;
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
QLabel#catTitle, QLabel#mlTitle, QLabel#catalogTitle, QLabel#homeTitle {{
    background: transparent;
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: 28px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#catSubtitle, QLabel#mlSubtitle, QLabel#catalogSubtitle, QLabel#homeSummary {{
    background: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY}px;
}}
QLabel#myBorrowSectionTitle {{
    background: transparent;
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_H3}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
"""
