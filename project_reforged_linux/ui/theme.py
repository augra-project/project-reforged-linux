# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The launcher's look: the colours of Dan's site, the bundled fonts, one stylesheet.

A themed window on purpose: it is meant to look like the game, not like the desktop,
so the colours are fixed here instead of taken from the system palette.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QDir
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QWidget

from project_reforged_linux.ui.assets import CHECKMARK, FONTS_DIR

__all__ = ["BASE_PT", "Fonts", "apply", "apply_dialog", "dialog_palette", "dialog_stylesheet",
           "load_fonts", "stylesheet"]

logger = logging.getLogger(__name__)

# His site's style.css, read 2026-11-14.
NIGHT, PLUM, INK = "#170d27", "#241339", "#0f0819"
GOLD, GOLD_HI, GOLD_LO, BRASS = "#d6a23e", "#f7d98a", "#8a5a17", "#b4842c"
TEXT, TEXT_DIM = "#efe3c6", "#bfae8c"
DISABLED_TEXT = "#7f745d"  # TEXT_DIM a third darker, for greyed dialog controls
DISABLED_OPACITY = 0.45
VIOLET = "#8a5cf0"
LEATHER, LEATHER_HI = "#2b1a11", "#4a2e1c"
# The rail's distance from the window's edge, and its layers from the outside in (colours
# from the corner ornament, widths in logical pixels). Nearly at the edge, so the picture
# fills the window without a dark margin.
RAIL_INSET = 1.5
RAIL: tuple[tuple[str, float], ...] = (
    ("#3A1E0C", 0.5), ("#ECBD61", 0.5), ("#CE973A", 1.5), ("#8E5821", 0.5), ("#3A1E0C", 0.5))
# The bezel around buttons, boxes and the progress line, layers from the outside in.
BEZEL_FRAME: tuple[tuple[str, float], ...] = (
    ("#3A1E0C", 1.0), ("#ECBD61", 0.75), ("#CE973A", 1.5), ("#8E5821", 0.75), ("#3A1E0C", 1.0))
BEZEL_BUTTON: tuple[tuple[str, float], ...] = (
    ("#3A1E0C", 1.0), ("#CE973A", 1.25), ("#8E5821", 0.75), ("#3A1E0C", 0.75))
LEATHER_TOP = "#3d2618"
# RUN GAME and the progress fill wear the ornament's gold.
GOLD_TOP, GOLD_BOTTOM = RAIL[1][0], RAIL[2][0]
EDGE_DARK, EDGE_BRONZE = RAIL[0][0], RAIL[3][0]
RUN_TEXT = "#2a1606"
# The Dragon Guardians' aged gold, dark to light, measured off corner-top.png (8th, 50th and
# 85th percentile of its brightness); the fleurons wear it.
AGED_DARK, AGED_MID, AGED_LIGHT = "#5C2F11", "#B0702D", "#EBB562"
STATE_OK, STATE_ERROR, STATE_UPDATE = "#7fbf4d", "#d2553f", "#e8913a"
BASE_PT = 11


@dataclass(frozen=True, slots=True)
class Fonts:
    heading: str
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
    wanted = ("Cinzel", "EB Garamond")
    found = [name if name in families else "serif" for name in wanted]
    for name, got in zip(wanted, found, strict=True):
        if got != name:
            logger.error("font %s is missing from the package; using serif", name)
    return Fonts(*found)


def _sizer(base_pt: int) -> Callable[[float], str]:
    if base_pt <= 0:
        raise ValueError(f"base font size must be positive, got {base_pt}")
    return lambda factor: f"{round(base_pt * factor)}pt"


def _rgba(colour: str, alpha: int) -> str:
    c = QColor(colour)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


_SEARCH_PREFIX = "launcherart"


def _qss_url(path: Path) -> str:
    """A file for a stylesheet's url(), reached through a Qt search path.

    The folder never enters the rule, so a quote or a backslash in the install path cannot end
    it early; the file name is ours.
    """
    if any(c in path.name for c in "\"\n\r\\"):
        raise ValueError(f"cannot put this file name into a stylesheet: {path.name!r}")
    if str(path.parent) not in QDir.searchPaths(_SEARCH_PREFIX):
        QDir.addSearchPath(_SEARCH_PREFIX, str(path.parent))
    return f'url("{_SEARCH_PREFIX}:{path.name}")'


def stylesheet(fonts: Fonts, base_pt: int = BASE_PT) -> str:
    pt = _sizer(base_pt)
    return f"""
QWidget#root {{ color: {TEXT}; font-family: "{fonts.text}"; font-size: {pt(1)}; }}
QLabel {{ background: transparent; color: {TEXT}; }}
QLabel#subtitle {{ font-family: "{fonts.text}"; font-size: {pt(1.9)}; font-weight: 600;
    color: {GOLD_HI}; }}
QLabel#statusText {{ font-size: {pt(1.45)}; font-weight: 500; }}
QLabel#statusDetail {{ font-size: {pt(1.3)}; color: {TEXT_DIM}; }}
QLabel#welcome {{ font-size: {pt(1.15)}; }}
QLabel#footer {{ font-size: {pt(0.9)}; color: {TEXT_DIM}; }}
QLabel#version {{ font-size: {pt(1)}; font-weight: 600; color: {TEXT}; }}
QPushButton {{ font-family: "{fonts.text}"; font-size: {pt(1.4)}; font-weight: 600; }}
QPushButton#rowButton {{ font-size: {pt(1.15)}; }}
QPushButton#runGame {{ font-family: "{fonts.heading}"; font-size: {pt(1.9)};
    font-weight: bold; }}
QWidget#progressLine {{ font-size: {pt(0.95)}; }}
QToolTip {{ color: {TEXT}; background-color: {PLUM}; border: 1px solid {GOLD_LO}; }}
"""


def dialog_stylesheet(base_pt: int = BASE_PT) -> str:
    """The rules only the Options, About and first-start dialogs need."""
    pt = _sizer(base_pt)
    return f"""
QLabel#dialogTitle {{ font-size: {pt(1.36)}; font-weight: 600; color: {GOLD_HI}; }}
QCheckBox, QRadioButton {{ color: {TEXT}; spacing: 9px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px;
    border: 1px solid {GOLD_BOTTOM}; background: {LEATHER}; }}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {_rgba(TEXT_DIM, 110)}; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    border: 1px solid {_rgba(GOLD_BOTTOM, 90)}; }}
QCheckBox::indicator:checked {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
    stop:0 {GOLD_TOP}, stop:1 {GOLD_BOTTOM}); border: 1px solid {EDGE_DARK};
    image: {_qss_url(CHECKMARK)}; }}
QRadioButton::indicator:checked {{ background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
    fx:0.5, fy:0.5, stop:0 {GOLD_TOP}, stop:0.45 {GOLD_BOTTOM}, stop:0.55 {LEATHER},
    stop:1 {LEATHER}); }}
QLabel#heading {{ color: {GOLD_HI}; font-size: {pt(1.18)}; font-weight: 600; }}
QLabel#hint {{ color: {TEXT_DIM}; font-size: {pt(0.91)}; }}
QLabel#body {{ font-size: {pt(1)}; }}
QLabel#notice {{ font-size: {pt(0.91)}; }}
QLabel#small {{ color: {TEXT_DIM}; font-size: {pt(0.82)}; }}
QLabel#ident {{ color: {TEXT}; font-size: {pt(1)}; }}
QListWidget {{ background: {_rgba(INK, 170)}; color: {TEXT}; border: 1px solid {EDGE_BRONZE};
    font-size: {pt(0.91)}; }}
QListWidget::item {{ padding: 3px 4px; }}
QListWidget::item:selected {{ background: {LEATHER_HI}; color: {GOLD_HI}; }}
QListWidget::item:disabled {{ color: {_rgba(TEXT_DIM, 140)}; }}
QScrollBar:vertical {{ background: {_rgba(INK, 170)}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {EDGE_BRONZE}; min-height: 20px; border-radius: 4px;
    margin: 1px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""


def apply(widget: QWidget, fonts: Fonts, base_pt: int = BASE_PT, *,
          dialog: bool = False) -> None:
    """Give a widget and everything below it the launcher's look: stylesheet and text font.

    Never call it on a window that parents dialogs: a stylesheet above a dialog, even one
    rule, stops the dialog's own palette and font from reaching its labels and buttons.
    """
    # A stylesheet's font on #root does not reach the children; the widget's own font
    # does, but only when set before the stylesheet. The specific
    # rules (buttons, headings) still override it.
    font = QFont(fonts.text)
    font.setPointSize(base_pt)
    widget.setFont(font)
    sheet = stylesheet(fonts, base_pt)
    if dialog:
        sheet += dialog_stylesheet(base_pt)
    widget.setStyleSheet(sheet)


def dialog_palette() -> QPalette:
    """The launcher's night colours for Qt's own dialogs (message boxes, the folder picker)."""
    palette = QPalette()
    roles = QPalette.ColorRole
    for role, colour in ((roles.Window, PLUM), (roles.WindowText, TEXT), (roles.Base, INK),
                         (roles.AlternateBase, NIGHT), (roles.Text, TEXT),
                         (roles.Button, LEATHER_TOP), (roles.ButtonText, TEXT),
                         (roles.BrightText, GOLD_HI), (roles.Highlight, GOLD_LO),
                         (roles.HighlightedText, TEXT), (roles.Link, GOLD_HI),
                         (roles.LinkVisited, BRASS), (roles.ToolTipBase, PLUM),
                         (roles.ToolTipText, TEXT), (roles.PlaceholderText, TEXT_DIM)):
        palette.setColor(role, QColor(colour))
    dimmed = QColor(DISABLED_TEXT)
    for role in (roles.WindowText, roles.Text, roles.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, dimmed)
    return palette


def apply_dialog(dialog: QWidget, fonts: Fonts, base_pt: int = BASE_PT) -> None:
    """Give one of Qt's dialogs the launcher's night colours and plain text font."""
    if base_pt <= 0:
        raise ValueError(f"base font size must be positive, got {base_pt}")
    font = QFont(fonts.text)
    font.setPointSize(base_pt)
    dialog.setFont(font)
    dialog.setPalette(dialog_palette())
