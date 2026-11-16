# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The window's frame: margin, background, the gold rail, and its corner ornaments."""

import logging

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from project_reforged_linux.ui import theme
from project_reforged_linux.ui.assets import BACKGROUND, CORNER

__all__ = ["CORNER_SIZE", "FrameWidget", "paint_frame"]

logger = logging.getLogger(__name__)

CORNER_SIZE = 58.0  # logical px, the ornament's width; mockup v3 measured


def _cover(painter: QPainter, target: QRectF, pixmap: QPixmap) -> None:
    source_w, source_h = pixmap.width(), pixmap.height()
    scale = max(target.width() / source_w, target.height() / source_h)
    cut_w, cut_h = target.width() / scale, target.height() / scale
    source = QRectF((source_w - cut_w) / 2, (source_h - cut_h) / 2, cut_w, cut_h)
    painter.drawPixmap(target, pixmap, source)


def _corner_height(corner: QSvgRenderer) -> float:
    box = corner.viewBoxF()
    if box.width() <= 0 or box.height() <= 0:
        return CORNER_SIZE
    return CORNER_SIZE * box.height() / box.width()


def paint_frame(painter: QPainter, rect: QRectF, background: QPixmap | None,
                corner: QSvgRenderer) -> None:
    if rect.width() < 2 * CORNER_SIZE or rect.height() < 2 * CORNER_SIZE:
        raise ValueError(f"frame of {rect.width()}x{rect.height()} has no room for its corners")
    painter.save()
    painter.fillRect(rect, QColor(theme.MARGIN))
    inset = theme.RAIL_INSET
    inside = rect.adjusted(inset, inset, -inset, -inset)
    if background is not None and not background.isNull():
        _cover(painter, inside, background)
    else:
        painter.fillRect(inside, QColor(theme.NIGHT))
    offset = inset
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for colour, width in theme.RAIL:
        half = offset + width / 2
        painter.setPen(QPen(QColor(colour), width))
        painter.drawRect(rect.adjusted(half, half, -half, -half))
        offset += width
    # The ornament is drawn for the top-left corner; the other three are mirrors.
    target = QRectF(0, 0, CORNER_SIZE, _corner_height(corner))
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        painter.save()
        painter.translate(rect.left() if sx > 0 else rect.right(),
                          rect.top() if sy > 0 else rect.bottom())
        painter.scale(sx, sy)
        corner.render(painter, target)
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
        self._corner = QSvgRenderer(str(CORNER))
        if not self._corner.isValid():
            logger.error("corner ornament missing or unreadable: %s", CORNER)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt's name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        paint_frame(painter, QRectF(self.rect()), self._background, self._corner)
        painter.end()
