# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The banner: the keyhole emblem, the wordmark, and "Linux Launcher"."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPolygonF,
    QTransform,
)
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from project_reforged_linux.ui import theme
from project_reforged_linux.ui.assets import EMBLEM

__all__ = ["RULE_OVERHANG", "STRETCH_Y", "SUBTITLE", "WORDMARK", "WORDMARK_HEIGHT", "Banner",
           "Wordmark", "paint_rule", "text_outline", "wordmark_font"]

WORDMARK = ("PROJECT", "REFORGED")
SUBTITLE = "Linux Launcher"
EMBLEM_SIZE = 150
WORDMARK_HEIGHT = 150
STRETCH_Y = 1.15  # the mockup's letters are taller than Cinzel's own proportions
# Each line's size as a share of the height; REFORGED a touch smaller.
UPPER_SIZE, LOWER_SIZE = 0.50, 0.28
# Baselines as shares of the height; REFORGED close under PROJECT.
UPPER_BASELINE, LOWER_BASELINE = 0.50, 0.88
SHADOW = (2.5, 3.0)
DIAMOND = 5.0  # half the diagonal, logical px
RULE_OVERHANG = 40  # how far each rule reaches past the wordmark
RULE_GAP = 8  # between a diamond's tip and the subtitle
RULE_THICK, RULE_THIN = 2.4, 0.6
WEIGHT = 700


def wordmark_font(family: str, pixel_size: int) -> QFont:
    if pixel_size <= 0:
        raise ValueError(f"wordmark font needs a positive size, got {pixel_size}")
    font = QFont(family)
    font.setWeight(QFont.Weight(WEIGHT))
    # Qt does not carry the weight onto a variable font's wght axis in addText paths.
    font.setVariableAxis(QFont.Tag("wght"), WEIGHT)
    font.setPixelSize(pixel_size)
    return font


def text_outline(font: QFont, baseline: QPointF, text: str) -> QPainterPath:
    """The text as one outline without overlapping contours.

    Cinzel's glyphs overlap their own contours, and addText fills odd-even, which
    turns every overlap into a hole; merging under winding keeps what the glyphs cover.
    """
    path = QPainterPath()
    path.addText(baseline, font, text)
    path.setFillRule(Qt.FillRule.WindingFill)
    return path.simplified()


class Wordmark(QWidget):
    """The two words as painted paths, so the spelling is exact in any font state."""

    def __init__(self, fonts: theme.Fonts, parent: QWidget | None = None, *,
                 height: int | None = None) -> None:
        """`height` draws the whole mark, shadow and outline included, scaled to that height."""
        super().__init__(parent)
        self._family = fonts.heading
        # Exactly as big as the ink and its shadow: no empty headroom from the font's ascent,
        # and the banner can group the words tightly with the emblem.
        box = self.outline().boundingRect()
        width, full = box.right() + SHADOW[0] + 2, box.bottom() + SHADOW[1] + 2
        if height is not None and height <= 0:
            raise ValueError(f"wordmark height must be positive, got {height}")
        self._scale = 1.0 if height is None else height / full
        self.setFixedSize(round(width * self._scale), round(full * self._scale))

    def outline(self, stretch: float = STRETCH_Y) -> QPainterPath:
        """The two lines laid out at WORDMARK_HEIGHT, stretched, with their ink at the top left."""
        if stretch <= 0:
            raise ValueError(f"stretch must be positive, got {stretch}")
        height = WORDMARK_HEIGHT / stretch
        top = wordmark_font(self._family, round(height * UPPER_SIZE))
        bottom = wordmark_font(self._family, round(height * LOWER_SIZE))
        bottom.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 135)
        upper = text_outline(top, QPointF(0, height * UPPER_BASELINE), WORDMARK[0])
        lower = text_outline(bottom, QPointF(0, height * LOWER_BASELINE), WORDMARK[1])
        tall = QTransform.fromScale(1.0, stretch)
        upper, lower = tall.map(upper), tall.map(lower)
        width = max(upper.boundingRect().width(), lower.boundingRect().width())
        outline = QPainterPath()
        for line in (upper, lower):
            box = line.boundingRect()
            line.translate((width - box.width()) / 2 - box.left(), 0)
            outline.addPath(line)
        whole = outline.boundingRect()
        outline.translate(1 - whole.left(), 1 - whole.top())
        return outline

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt's name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self._scale, self._scale)
        path = self.outline()
        shadow = QPainterPath(path)
        shadow.translate(*SHADOW)
        painter.fillPath(shadow, QColor(18, 10, 4, 190))
        box = path.boundingRect()
        gradient = QLinearGradient(box.topLeft(), box.bottomLeft())
        gradient.setColorAt(0.0, QColor(theme.GOLD_HI))
        gradient.setColorAt(0.5, QColor(theme.GOLD))
        gradient.setColorAt(1.0, QColor(theme.GOLD_LO))
        painter.fillPath(path, gradient)
        painter.setPen(QPen(QColor("#3A1E0C"), 1.0))
        painter.drawPath(path)
        painter.end()


def paint_rule(painter: QPainter, thin_end: QPointF, diamond_end: QPointF) -> None:
    """A gold rule tapering from thin at one end to thick at a hollow diamond."""
    if thin_end.y() != diamond_end.y():
        raise ValueError("a rule runs level")
    y = diamond_end.y()
    toward = 1.0 if diamond_end.x() > thin_end.x() else -1.0
    neck = diamond_end.x() - toward * 2 * DIAMOND
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.GOLD))
    painter.drawPolygon(QPolygonF([
        QPointF(thin_end.x(), y - RULE_THIN / 2), QPointF(neck, y - RULE_THICK / 2),
        QPointF(neck, y + RULE_THICK / 2), QPointF(thin_end.x(), y + RULE_THIN / 2)]))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(theme.GOLD), 1.2))
    centre = diamond_end.x() - toward * DIAMOND
    painter.drawPolygon(QPolygonF([
        QPointF(centre - DIAMOND, y), QPointF(centre, y - DIAMOND),
        QPointF(centre + DIAMOND, y), QPointF(centre, y + DIAMOND)]))
    painter.restore()


class Banner(QWidget):
    def __init__(self, fonts: theme.Fonts, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        emblem = QSvgWidget(str(EMBLEM))
        emblem.setFixedSize(EMBLEM_SIZE, EMBLEM_SIZE)
        self._mark = Wordmark(fonts)
        self._subtitle = QLabel(SUBTITLE)
        self._subtitle.setObjectName("subtitle")
        words = QVBoxLayout()
        words.setSpacing(0)
        words.addWidget(self._mark)
        words.addWidget(self._subtitle, 0, Qt.AlignmentFlag.AlignHCenter)
        # Emblem and words as one group, set left so the tower on
        # the right keeps its sky; the free space splits one to two.
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        # The emblem's top on the wordmark's, not centred on the taller column.
        row.addWidget(emblem, 0, Qt.AlignmentFlag.AlignTop)
        row.addSpacing(14)
        row.addLayout(words)
        row.addStretch(2)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt's name)
        # The rules reach past the words and under the emblem, so the banner paints them.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        mark, words = self._mark.geometry(), self._subtitle.geometry()
        y = words.center().y() + 0.5
        paint_rule(painter, QPointF(mark.left() - RULE_OVERHANG, y),
                   QPointF(words.left() - RULE_GAP, y))
        paint_rule(painter, QPointF(mark.right() + RULE_OVERHANG, y),
                   QPointF(words.right() + RULE_GAP, y))
        painter.end()
