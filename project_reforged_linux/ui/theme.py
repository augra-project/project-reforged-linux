# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The launcher's look: the colours of Dan's site, the bundled fonts, one stylesheet.

A themed window on purpose: it is meant to look like the game, not like the desktop,
so the colours are fixed here instead of taken from the system palette.
"""

import logging
from dataclasses import dataclass

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QWidget

from project_reforged_linux.ui.assets import FONTS_DIR

__all__ = ["BASE_PT", "Fonts", "apply", "load_fonts", "stylesheet"]

logger = logging.getLogger(__name__)

# His site's style.css, read 2026-11-14.
NIGHT, PLUM, INK = "#170d27", "#241339", "#0f0819"
GOLD, GOLD_HI, GOLD_LO, BRASS = "#d6a23e", "#f7d98a", "#8a5a17", "#b4842c"
TEXT, TEXT_DIM = "#efe3c6", "#bfae8c"
VIOLET = "#8a5cf0"
LEATHER, LEATHER_HI = "#2b1a11", "#4a2e1c"
# The window's margin outside the rail, and the rail's layers from the outside in
# (colours from the corner ornament, widths in logical pixels; tuned on screen).
MARGIN = "#0F071E"
RAIL_INSET = 7.0
RAIL: tuple[tuple[str, float], ...] = (
    ("#3A1E0C", 0.5), ("#ECBD61", 0.5), ("#CE973A", 1.5), ("#8E5821", 0.5), ("#3A1E0C", 0.5))
# The bezel around buttons, boxes and the progress line, layers from the outside in.
BEZEL_FRAME: tuple[tuple[str, float], ...] = (
    ("#3A1E0C", 1.0), ("#ECBD61", 0.75), ("#CE973A", 1.5), ("#8E5821", 0.75), ("#3A1E0C", 1.0))
BEZEL_BUTTON: tuple[tuple[str, float], ...] = (
    ("#3A1E0C", 1.0), ("#CE973A", 1.25), ("#8E5821", 0.75), ("#3A1E0C", 0.75))
LEATHER_TOP = "#3d2618"
# RUN GAME and the progress fill wear the ornament's gold (Stefan, 2026-11-16).
GOLD_TOP, GOLD_BOTTOM = RAIL[1][0], RAIL[2][0]
RUN_TEXT = "#2a1606"
STATE_OK, STATE_ERROR = "#7fbf4d", "#d2553f"
BASE_PT = 11


@dataclass(frozen=True, slots=True)
class Fonts:
    heading: str
    decorative: str
    text: str


def load_fonts() -> Fonts:
    """Register the bundled fonts; a missing one falls back to serif and is logged loudly."""
    families: set[str] = set()
    for path in sorted(FONTS_DIR.glob("*/*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            logger.error("Qt could not load the bundled font %s", path)
            continue
        families.update(QFontDatabase.applicationFontFamilies(font_id))
    wanted = ("Cinzel", "Cinzel Decorative", "EB Garamond")
    found = [name if name in families else "serif" for name in wanted]
    for name, got in zip(wanted, found, strict=True):
        if got != name:
            logger.error("font %s is missing from the package; using serif", name)
    return Fonts(*found)


def stylesheet(fonts: Fonts, base_pt: int = BASE_PT) -> str:
    if base_pt <= 0:
        raise ValueError(f"base font size must be positive, got {base_pt}")

    def pt(factor: float) -> str:
        return f"{round(base_pt * factor)}pt"

    return f"""
QWidget#root {{ color: {TEXT}; font-family: "{fonts.text}"; font-size: {pt(1)}; }}
QLabel {{ background: transparent; color: {TEXT}; }}
QLabel#subtitle {{ font-family: "{fonts.text}"; font-size: {pt(1.9)}; font-weight: 600;
    color: {GOLD_HI}; }}
QLabel#statusText {{ font-size: {pt(1.25)}; }}
QLabel#statusDetail {{ font-size: {pt(1.15)}; color: {TEXT_DIM}; }}
QLabel#welcome {{ font-size: {pt(1.05)}; }}
QLabel#version, QLabel#footer {{ font-size: {pt(0.9)}; color: {TEXT_DIM}; }}
QPushButton {{ font-family: "{fonts.text}"; font-size: {pt(1.4)}; font-weight: 600; }}
QPushButton#rowButton {{ font-size: {pt(1.15)}; }}
QPushButton#runGame {{ font-family: "{fonts.heading}"; font-size: {pt(1.9)};
    font-weight: bold; }}
QWidget#progressLine {{ font-size: {pt(0.95)}; }}
QToolTip {{ color: {TEXT}; background-color: {PLUM}; border: 1px solid {GOLD_LO}; }}
"""


def apply(widget: QWidget, fonts: Fonts, base_pt: int = BASE_PT) -> None:
    """Give a window the launcher's look: its stylesheet and its text font."""
    # A stylesheet's font on #root does not reach the children; the widget's own font
    # does, but only when set before the stylesheet (Qt 6.11, measured). The specific
    # rules (buttons, headings) still override it.
    font = QFont(fonts.text)
    font.setPointSize(base_pt)
    widget.setFont(font)
    widget.setStyleSheet(stylesheet(fonts, base_pt))
