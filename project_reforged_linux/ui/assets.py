# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Where the window's art lives, and the UI icons drawn in a chosen colour."""

import re
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from project_reforged_linux import APP_ID

__all__ = ["BACKGROUND", "CHECKMARK", "CORNER_BOTTOM", "CORNER_TOP", "DOSBOX_AUTOMATION_LOGO",
           "EMBLEM", "FLEURON", "FONTS_DIR", "ICONS_DIR", "LUDUCAT_LOGO", "UI_ICONS",
           "icon_pixmap", "icon_svg", "svg_pixmap"]

DATA = Path(__file__).resolve().parent.parent / "data"
FONTS_DIR = DATA / "fonts"
ICONS_DIR = DATA / "ui-icons"
BACKGROUND = DATA / "art" / "background.jpg"
# The Dragon Guardians: drawn for the left side, mirrored to the right.
CORNER_TOP = DATA / "art" / "corner-top.png"
CORNER_BOTTOM = DATA / "art" / "corner-bottom.png"
FLEURON = DATA / "art" / "fleuron.svg"
CHECKMARK = DATA / "art" / "check.svg"
EMBLEM = DATA / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"
# Our sister projects' own application icons, copied unchanged.
LUDUCAT_LOGO = DATA / "logos" / "luducat.svg"
DOSBOX_AUTOMATION_LOGO = DATA / "logos" / "dosbox-automation.svg"
UI_ICONS = ("house", "settings", "info", "power", "key-round", "circle-check",
            "circle-question-mark", "circle-x", "circle-arrow-up", "folder-open")
_HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{6}")


def icon_svg(name: str, colour: str) -> bytes:
    """A Lucide icon with its stroke colour filled in (they draw with currentColor)."""
    if name not in UI_ICONS:
        raise ValueError(f"not one of the launcher's icons: {name!r}")
    # The colour lands inside the SVG text, so only a plain #rrggbb gets in.
    if not _HEX_COLOUR.fullmatch(colour):
        raise ValueError(f"icon colour must be #rrggbb: {colour!r}")
    return (ICONS_DIR / f"{name}.svg").read_bytes().replace(b"currentColor", colour.encode())


def svg_pixmap(data: bytes, size: int, ratio: float) -> QPixmap:
    if size <= 0 or ratio <= 0:
        raise ValueError(f"pixmap needs a positive size and ratio, got {size} and {ratio}")
    renderer = QSvgRenderer(QByteArray(data))
    if not renderer.isValid():
        raise ValueError("not a usable SVG")
    pixmap = QPixmap(round(size * ratio), round(size * ratio))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon_pixmap(name: str, colour: str, size: int, ratio: float) -> QPixmap:
    return svg_pixmap(icon_svg(name, colour), size, ratio)
