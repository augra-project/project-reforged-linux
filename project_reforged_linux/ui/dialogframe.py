# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPaintEvent, QPixmap
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from project_reforged_linux.ui import theme
from project_reforged_linux.ui.assets import EMBLEM
from project_reforged_linux.ui.banner import Wordmark, paint_rule
from project_reforged_linux.ui.frame import FrameWidget

__all__ = ["ACROSS", "DOWN", "SIZE", "TOWER", "TOWER_RIGHT", "Backdrop", "Cut", "DialogHeader",
           "Shade", "ThemedDialog", "button_row"]

SIZE = QSize(800, 520)
MARGINS = (30, 14, 30, 22)  # left, top, right, bottom
SPACING = 8
EMBLEM_SIZE = 58
MARK_HEIGHT = 50
EMBLEM_GAP = 10
TITLE_RULE = 150  # how far each rule reaches out from the title
TITLE_GAP = 8  # between a rule's diamond and the title
BUTTON_WIDTH = 130
SHADE_RGB = (10, 5, 18)


@dataclass(frozen=True, slots=True)
class Cut:
    """Which part of the window's picture a dialog shows, as shares of the picture.

    The height follows from the width and the dialog's proportions.
    """

    left: float
    top: float
    width: float

    def __post_init__(self) -> None:
        if not (0 <= self.left and 0 <= self.top and 0 < self.width
                and self.left + self.width <= 1):
            raise ValueError(f"cut lies outside the picture: {self}")

    def of(self, picture: QPixmap, size: QSize) -> QPixmap:
        if picture.isNull():
            raise ValueError("no picture to cut from")
        if size.isEmpty():
            raise ValueError(f"cut needs a size, got {size}")
        w = picture.width() * self.width
        h = w * size.height() / size.width()
        top = picture.height() * self.top
        if top + h > picture.height():
            raise ValueError(f"cut runs below the picture: {self} at {size}")
        return picture.copy(round(picture.width() * self.left), round(top), round(w), round(h))


@dataclass(frozen=True, slots=True)
class Shade:
    """A dark gradient over the picture: (position 0..1, alpha 0..255) stops."""

    vertical: bool
    stops: tuple[tuple[float, int], ...]

    def __post_init__(self) -> None:
        if not self.stops:
            raise ValueError("a shade needs stops")
        for position, alpha in self.stops:
            if not (0 <= position <= 1 and 0 <= alpha <= 255):
                raise ValueError(f"shade stop out of range: {(position, alpha)}")

    def over(self, picture: QPixmap) -> QPixmap:
        """The picture with the shade baked in, so the rail and guardians stay at full light."""
        shaded = QPixmap(picture)
        painter = QPainter(shaded)
        w, h = shaded.width(), shaded.height()
        gradient = QLinearGradient(0, 0, 0, h) if self.vertical else QLinearGradient(0, 0, w, 0)
        for position, alpha in self.stops:
            gradient.setColorAt(position, QColor(*SHADE_RGB, alpha))
        painter.fillRect(shaded.rect(), gradient)
        painter.end()
        return shaded


# The tower and its moon on the right; dark toward the bottom where the text sits (Options).
TOWER = Cut(0.50, 0.0, 0.50)
DOWN = Shade(vertical=True, stops=((0.0, 55), (0.35, 119), (1.0, 158)))
# The tower at about 82 percent of the dialog's width; dark only under the text (About).
TOWER_RIGHT = Cut(0.37, 0.0, 0.50)
ACROSS = Shade(vertical=False, stops=((0.0, 150), (0.55, 120), (0.75, 0)))


class Backdrop(FrameWidget):
    """The window's frame around a shaded cut of its picture."""

    def __init__(self, cut: Cut, shade: Shade, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # FrameWidget logged a missing picture already; the dialog then sits on plain night.
        if not self._background.isNull():
            self._background = shade.over(cut.of(self._background, SIZE))


class DialogHeader(QWidget):
    """Emblem and wordmark, small, and the dialog's name between two tapering rules."""

    def __init__(self, fonts: theme.Fonts, title: str, parent: QWidget | None = None) -> None:
        if not title.strip():
            raise ValueError("a dialog needs a title")
        super().__init__(parent)
        emblem = QSvgWidget(str(EMBLEM))
        emblem.setFixedSize(EMBLEM_SIZE, EMBLEM_SIZE)
        self.mark = Wordmark(fonts, height=MARK_HEIGHT)
        self.title = QLabel(title)
        self.title.setObjectName("dialogTitle")
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(emblem)
        top.addSpacing(EMBLEM_GAP)
        top.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignVCenter)
        # As much room on the right as the emblem takes on the left: the wordmark sits on the
        # dialog's axis and the emblem hangs off its side.
        top.addSpacing(EMBLEM_SIZE + EMBLEM_GAP)
        top.addStretch(1)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addLayout(top)
        column.addWidget(self.title, 0, Qt.AlignmentFlag.AlignHCenter)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt's name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.title.geometry()
        y = t.center().y() + 0.5
        paint_rule(painter, QPointF(t.left() - TITLE_RULE, y), QPointF(t.left() - TITLE_GAP, y))
        paint_rule(painter, QPointF(t.right() + TITLE_RULE, y), QPointF(t.right() + TITLE_GAP, y))
        painter.end()


class ThemedDialog(QDialog):
    """A launcher dialog: the backdrop, the header, and `content` for the dialog's own rows.

    The stylesheet sits on the backdrop, never on the dialog, so the message boxes it parents
    keep their own palette.
    """

    def __init__(self, fonts: theme.Fonts, title: str, *, cut: Cut = TOWER, shade: Shade = DOWN,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.fonts = fonts
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon(str(EMBLEM)))
        self.setFixedSize(SIZE)
        self.setModal(True)
        self.backdrop = Backdrop(cut, shade, self)
        self.backdrop.setGeometry(0, 0, SIZE.width(), SIZE.height())
        theme.apply(self.backdrop, fonts, dialog=True)
        outer = QVBoxLayout(self.backdrop)
        outer.setContentsMargins(*MARGINS)
        outer.setSpacing(SPACING)
        self.header = DialogHeader(fonts, title)
        outer.addWidget(self.header)
        self.content = QVBoxLayout()
        self.content.setSpacing(SPACING)
        outer.addLayout(self.content, 1)


def button_row(*buttons: QPushButton) -> QHBoxLayout:
    if not buttons:
        raise ValueError("a button row needs buttons")
    row = QHBoxLayout()
    row.addStretch(1)
    for button in buttons:
        button.setMinimumWidth(BUTTON_WIDTH)
        row.addWidget(button)
    row.addStretch(1)
    return row
