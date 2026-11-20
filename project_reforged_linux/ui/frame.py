# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The window's frame: margin, background, the gold rail, and its corner ornaments."""

import logging

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPaintEvent, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from project_reforged_linux.ui import theme
from project_reforged_linux.ui.assets import BACKGROUND, CORNER_BOTTOM, CORNER_TOP

__all__ = ["ART_RAIL", "CORNER_SHIFT", "CORNER_SIZE", "CornerArt", "FrameWidget", "paint_frame"]

logger = logging.getLogger(__name__)

CORNER_SIZE = 58.0  # logical px, the ornament's width; mockup v3 measured
# Vector art or a picture: the guardians keep their relief as images.
CornerArt = QSvgRenderer | QImage
# The guardians' own rail line, from their outer edges at CORNER_SIZE wide; the art moves
# outward by CORNER_SHIFT so that line lies on the painted rail.
ART_RAIL = 9.5
RAIL_CENTRE = theme.RAIL_INSET + sum(width for _, width in theme.RAIL) / 2
CORNER_SHIFT = RAIL_CENTRE - ART_RAIL
# The extended bottom guardian (Recraft, gold-corrected) is drawn as tall as the top one; its
# bar and base line lie close to its edges, measured from its alpha.
BOTTOM_WIDTH = 94.0
BOTTOM_RAIL = (2.5, 1.3)


def _cover(painter: QPainter, target: QRectF, pixmap: QPixmap) -> None:
    source_w, source_h = pixmap.width(), pixmap.height()
    scale = max(target.width() / source_w, target.height() / source_h)
    cut_w, cut_h = target.width() / scale, target.height() / scale
    source = QRectF((source_w - cut_w) / 2, (source_h - cut_h) / 2, cut_w, cut_h)
    painter.drawPixmap(target, pixmap, source)


def _art_height(art: CornerArt, width: float = CORNER_SIZE) -> float:
    if isinstance(art, QImage):
        art_w, art_h = float(art.width()), float(art.height())
    else:
        box = art.viewBoxF()
        art_w, art_h = box.width(), box.height()
    if art_w <= 0 or art_h <= 0:
        return width
    return width * art_h / art_w


def _draw_art(painter: QPainter, art: CornerArt, target: QRectF) -> None:
    if isinstance(art, QImage):
        painter.drawImage(target, art)
    else:
        art.render(painter, target)


def paint_frame(painter: QPainter, rect: QRectF, background: QPixmap | None,
                corner: CornerArt, bottom: CornerArt | None = None, *,
                bottom_width: float = CORNER_SIZE,
                bottom_rail: tuple[float, float] = (ART_RAIL, ART_RAIL)) -> None:
    """The frame; `bottom` stands upright in the lower corners, else `corner` is mirrored there.

    `bottom_rail` is where the bottom art's own rail runs, from its outer side and its base.
    """
    top_height = _art_height(corner)
    bottom_height = top_height if bottom is None else _art_height(bottom, bottom_width)
    widest = max(CORNER_SIZE, bottom_width if bottom is not None else CORNER_SIZE)
    if rect.width() < 2 * widest or rect.height() < max(2 * CORNER_SIZE,
                                                         top_height + bottom_height):
        raise ValueError(f"frame of {rect.width()}x{rect.height()} has no room for its corners")
    painter.save()
    if background is not None and not background.isNull():
        _cover(painter, rect, background)
    else:
        painter.fillRect(rect, QColor(theme.NIGHT))
    offset = theme.RAIL_INSET
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for colour, width in theme.RAIL:
        half = offset + width / 2
        painter.setPen(QPen(QColor(colour), width))
        painter.drawRect(rect.adjusted(half, half, -half, -half))
        offset += width
    # The art is drawn for the left side; the right side is its mirror.
    for sx in (1, -1):
        x = rect.left() if sx > 0 else rect.right()
        painter.save()
        painter.translate(x, rect.top())
        painter.scale(sx, 1)
        _draw_art(painter, corner, QRectF(CORNER_SHIFT, CORNER_SHIFT, CORNER_SIZE, top_height))
        painter.restore()
        painter.save()
        if bottom is None:
            painter.translate(x, rect.bottom())
            painter.scale(sx, -1)
            _draw_art(painter, corner, QRectF(CORNER_SHIFT, CORNER_SHIFT, CORNER_SIZE, top_height))
        else:
            painter.translate(x, rect.bottom() - bottom_height)
            painter.scale(sx, 1)
            rail_x, rail_y = bottom_rail
            _draw_art(painter, bottom, QRectF(RAIL_CENTRE - rail_x, rail_y - RAIL_CENTRE,
                                              bottom_width, bottom_height))
        painter.restore()
    painter.restore()


class FrameWidget(QWidget):
    """The window's root: everything else is laid out on top of it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("root")
        self._background = QPixmap(str(BACKGROUND))
        if self._background.isNull():
            logger.error("background art missing or unreadable: %s", BACKGROUND)
        self._corner = QImage(str(CORNER_TOP))
        if self._corner.isNull():
            logger.error("top corner art missing or unreadable: %s", CORNER_TOP)
        bottom = QImage(str(CORNER_BOTTOM))
        if bottom.isNull():
            logger.error("bottom corner art missing or unreadable: %s", CORNER_BOTTOM)
        self._bottom = None if bottom.isNull() else bottom

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt's name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        paint_frame(painter, QRectF(self.rect()), self._background, self._corner, self._bottom,
                    bottom_width=BOTTOM_WIDTH, bottom_rail=BOTTOM_RAIL)
        painter.end()
