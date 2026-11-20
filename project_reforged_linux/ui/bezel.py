# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The bezel: one painter for the gold frame around buttons, boxes and the progress line.

A style is data (frame layers, fill, colours, height); RUN GAME and Options are the
same button class with a different style.
"""

import math
import random
from dataclasses import dataclass, replace
from functools import cache

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout, QWidget

from project_reforged_linux.ui import theme
from project_reforged_linux.ui.assets import UI_ICONS, icon_pixmap

__all__ = ["BAR", "GOLD", "LEATHER", "PANEL", "SMALL", "BezelButton", "BezelStyle", "Panel",
           "paint_bezel"]

ICON_SIZE = 18
ICON_GAP = 8
PADDING = 14
PANEL_PADDING = (14, 10)
PRESSED_DARKER = 118
# A hovered button warms toward the highlight gold and its frame glints; lightening alone
# did not show on the dark leather.
HOVER_GLOW = 0.10
HOVER_FRAME = 110
# The gold is worked metal, not flat paint: lit from above, a little from the
# left, and flecked by a soft grain blended over it.
BEVEL = 140  # the lit edge this much lighter, the far edge this much darker (percent)
GRAIN_OPACITY = 0.6
GRAIN_SEED = 2004


@cache
def _grain() -> QImage:
    """Soft blotches with a fine grain around mid grey, which Overlay leaves unchanged."""
    # A texture, not a secret; a fixed seed makes every start look the same.
    rng = random.Random(GRAIN_SEED)  # noqa: S311  # nosec B311
    coarse = QImage(16, 16, QImage.Format.Format_RGB32)
    for x in range(16):
        for y in range(16):
            v = rng.randint(90, 166)
            coarse.setPixelColor(x, y, QColor(v, v, v))
    image = coarse.scaled(128, 128, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    for x in range(128):
        for y in range(128):
            v = max(0, min(255, image.pixelColor(x, y).red() + rng.randint(-20, 20)))
            image.setPixelColor(x, y, QColor(v, v, v))
    return image


def _toward(colour: QColor, target: QColor, share: float) -> QColor:
    return QColor.fromRgbF(*(a + share * (b - a) for a, b in (
        (colour.redF(), target.redF()), (colour.greenF(), target.greenF()),
        (colour.blueF(), target.blueF()))))


def _rounded(rect: QRectF, inset: float, radius: float) -> QPainterPath:
    path = QPainterPath()
    r = max(radius - inset, 0.0)
    path.addRoundedRect(rect.adjusted(inset, inset, -inset, -inset), r, r)
    return path


@dataclass(frozen=True, slots=True)
class BezelStyle:
    layers: tuple[tuple[str, float], ...]  # outside in: colour, width in logical px
    fill_top: str
    fill_bottom: str
    fill_alpha: int = 255
    radius: float = 4.0
    text: str = theme.TEXT
    icon: str = theme.GOLD_HI
    height: int = 0  # buttons only

    @property
    def thickness(self) -> float:
        return sum(width for _, width in self.layers)


# Thick buttons in the boxes' frame.
LEATHER = BezelStyle(theme.BEZEL_FRAME, theme.LEATHER_TOP, theme.LEATHER, height=40)
SMALL = replace(LEATHER, height=32)
GOLD = BezelStyle(theme.BEZEL_FRAME, theme.GOLD_TOP, theme.GOLD_BOTTOM, radius=3.0,
                  text=theme.RUN_TEXT, icon=theme.RUN_TEXT, height=44)
PANEL = BezelStyle(theme.BEZEL_FRAME, theme.LEATHER, theme.LEATHER, fill_alpha=215, radius=5.0)
BAR = BezelStyle(theme.BEZEL_BUTTON, theme.INK, theme.INK, fill_alpha=220, radius=3.0)


def paint_bezel(painter: QPainter, rect: QRectF, style: BezelStyle, *,
                pressed: bool = False, hovered: bool = False) -> None:
    edge = style.thickness
    if rect.width() <= 2 * edge or rect.height() <= 2 * edge:
        raise ValueError(f"{rect.width()}x{rect.height()} is too small for a {edge} px bezel")
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    inner = rect.adjusted(edge, edge, -edge, -edge)
    top, bottom = QColor(style.fill_top), QColor(style.fill_bottom)
    if pressed:
        top, bottom = top.darker(PRESSED_DARKER), bottom.darker(PRESSED_DARKER)
    elif hovered:
        glow = QColor(theme.GOLD_HI)
        top, bottom = _toward(top, glow, HOVER_GLOW), _toward(bottom, glow, HOVER_GLOW)
    top.setAlpha(style.fill_alpha)
    bottom.setAlpha(style.fill_alpha)
    gradient = QLinearGradient(inner.topLeft(), inner.bottomLeft())
    gradient.setColorAt(0.0, top)
    gradient.setColorAt(1.0, bottom)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    inner_radius = max(style.radius - edge, 0.0)
    painter.drawRoundedRect(inner, inner_radius, inner_radius)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # The light comes from above and a little from the left, whatever the bezel's width.
    lit, far = rect.topLeft(), rect.topLeft() + QPointF(0.35 * rect.height(), rect.height())
    offset = 0.0
    last = len(style.layers) - 1
    for index, (colour, width) in enumerate(style.layers):
        half = offset + width / 2
        radius = max(style.radius - half, 0.0)
        base = QColor(colour)
        if 0 < index < last and hovered and not pressed:
            base = base.lighter(HOVER_FRAME)
        if 0 < index < last:  # the dark outlines stay clean; the gold between them is lit
            light = QLinearGradient(lit, far)
            light.setColorAt(0.0, base.lighter(BEVEL))
            light.setColorAt(0.5, base)
            light.setColorAt(1.0, base.darker(BEVEL))
            painter.setPen(QPen(light, width))
        else:
            painter.setPen(QPen(base, width))
        painter.drawRoundedRect(rect.adjusted(half, half, -half, -half), radius, radius)
        offset += width
    if last >= 2:
        ring = _rounded(rect, style.layers[0][1], style.radius).subtracted(
            _rounded(rect, edge - style.layers[-1][1], style.radius))
        painter.setClipPath(ring)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Overlay)
        painter.setOpacity(painter.opacity() * GRAIN_OPACITY)
        painter.drawTiledPixmap(rect, QPixmap.fromImage(_grain()))
    painter.restore()


class BezelButton(QPushButton):
    """A push button that paints its own bezel, icon and text; the style picks the look."""

    def __init__(self, text: str, *, style: BezelStyle = LEATHER, icon: str | None = None,
                 parent: QWidget | None = None) -> None:
        if not text.strip():
            raise ValueError("a button needs a text")
        if icon is not None and icon not in UI_ICONS:
            raise ValueError(f"not one of the launcher's icons: {icon!r}")
        if style.height <= 2 * style.thickness:
            raise ValueError("this style has no button height")
        super().__init__(text, parent)
        self.bezel = style
        self._icon_name = icon
        self.setFixedHeight(style.height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def _content_width(self) -> float:
        width = float(self.fontMetrics().horizontalAdvance(self.text()))
        if self._icon_name is not None:
            width += ICON_SIZE + ICON_GAP
        return width

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt's name)
        width = self._content_width() + 2 * (PADDING + self.bezel.thickness)
        return QSize(math.ceil(width), self.bezel.height)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt's name)
        return self.sizeHint()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt's name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(theme.DISABLED_OPACITY)
        pressed = self.isDown()
        # Qt keeps underMouse() true on a disabled button; a greyed one does not answer.
        paint_bezel(painter, QRectF(self.rect()), self.bezel, pressed=pressed,
                    hovered=self.isEnabled() and self.underMouse())
        shift = 1.0 if pressed else 0.0
        x = (self.width() - self._content_width()) / 2
        if self._icon_name is not None:
            pixmap = icon_pixmap(self._icon_name, self.bezel.icon, ICON_SIZE,
                                 self.devicePixelRatioF())
            painter.drawPixmap(QPointF(x, (self.height() - ICON_SIZE) / 2 + shift), pixmap)
            x += ICON_SIZE + ICON_GAP
        painter.setFont(self.font())
        painter.setPen(QColor(self.bezel.text))
        # Centred by the capitals, not the font box: its descender room set RUN GAME high.
        baseline = (self.height() + QFontMetricsF(self.font()).capHeight()) / 2 + shift
        painter.drawText(QPointF(x, baseline), self.text())
        painter.end()


class Panel(QFrame):
    """A box in the gold bezel with no pressed state; its content goes into `box`."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        edge = math.ceil(PANEL.thickness)
        across, down = PANEL_PADDING
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(edge + across, edge + down, edge + across, edge + down)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt's name)
        painter = QPainter(self)
        paint_bezel(painter, QRectF(self.rect()), PANEL)
        painter.end()
