# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
# Portions adapted from luducat (https://github.com/luducat/luducat)
# Copyright (c) shakeyourbunny and luducat contributors
# Licensed under GPL-3.0-or-later
# Local changes: own widget instead of a QProgressBar subclass, gold bezel, fraction API.
"""The window's bottom line: progress as a gold fill with its text in the middle."""

import math

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QHideEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QShowEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from project_reforged_linux.ui import theme
from project_reforged_linux.ui.bezel import BAR, paint_bezel

__all__ = ["ProgressLine"]

STRIPE = 10
FRAME_MS = 30


class ProgressLine(QWidget):
    """One text line high: a fraction fills it in gold, busy runs stripes through it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("progressLine")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._fraction: float | None = 0.0  # None while busy without a known end
        self._text = ""
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._advance)

    @property
    def fraction(self) -> float | None:
        return self._fraction

    def text(self) -> str:
        return self._text

    def animating(self) -> bool:
        return self._timer.isActive()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt's name)
        return QSize(200, self.fontMetrics().height() + 2 * math.ceil(BAR.thickness) + 2)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt's name)
        return QSize(60, self.sizeHint().height())

    def set_progress(self, fraction: float, text: str) -> None:
        # The chained comparison is also false for NaN.
        if not 0.0 <= fraction <= 1.0:
            raise ValueError(f"progress must be between 0 and 1, got {fraction}")
        self._fraction, self._text = fraction, text
        self._timer.stop()
        self.update()

    def set_busy(self, text: str) -> None:
        self._fraction, self._text = None, text
        if self.isVisible():
            self._timer.start()
        self.update()

    def set_idle(self, text: str = "") -> None:
        self.set_progress(0.0, text)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt's name)
        super().showEvent(event)
        if self._fraction is None:
            self._timer.start()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 (Qt's name)
        super().hideEvent(event)
        self._timer.stop()

    def _advance(self) -> None:
        self._offset = (self._offset + 1) % (STRIPE * 2)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt's name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        paint_bezel(painter, rect, BAR)
        edge = BAR.thickness
        inner = rect.adjusted(edge, edge, -edge, -edge)
        if self._fraction is None:
            chunk = QRectF(inner)
        else:
            chunk = QRectF(inner.left(), inner.top(), inner.width() * self._fraction,
                           inner.height())
        if chunk.width() > 0:
            painter.save()
            painter.setClipRect(chunk)
            gradient = QLinearGradient(inner.topLeft(), inner.bottomLeft())
            gradient.setColorAt(0.0, QColor(theme.GOLD_TOP))
            gradient.setColorAt(1.0, QColor(theme.GOLD_BOTTOM))
            painter.fillRect(chunk, QBrush(gradient))
            if self._fraction is None:
                self._paint_stripes(painter, chunk)
            painter.restore()
        self._paint_text(painter, inner, chunk)
        painter.end()

    def _paint_stripes(self, painter: QPainter, area: QRectF) -> None:
        shade = QColor(0, 0, 0, 40)
        height = area.height()
        for x in range(-math.ceil(height) - 2 * STRIPE, math.ceil(area.width()) + 2 * STRIPE,
                       2 * STRIPE):
            left = area.left() + x + self._offset
            stripe = QPainterPath()
            stripe.moveTo(left, area.bottom())
            stripe.lineTo(left + STRIPE, area.bottom())
            stripe.lineTo(left + STRIPE + height, area.top())
            stripe.lineTo(left + height, area.top())
            stripe.closeSubpath()
            painter.fillPath(stripe, shade)

    def _paint_text(self, painter: QPainter, inner: QRectF, chunk: QRectF) -> None:
        if not self._text:
            return
        painter.setFont(self.font())
        empty = QRectF(chunk.right(), inner.top(), inner.right() - chunk.right(), inner.height())
        # The text crosses the fill: dark where it lies on gold, light on the empty bar.
        for clip, colour in ((chunk, theme.RUN_TEXT), (empty, theme.TEXT)):
            if clip.width() <= 0:
                continue
            painter.save()
            painter.setClipRect(clip)
            painter.setPen(QColor(colour))
            painter.drawText(inner, Qt.AlignmentFlag.AlignCenter, self._text)
            painter.restore()
