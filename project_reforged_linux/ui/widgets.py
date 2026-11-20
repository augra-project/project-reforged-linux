# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Small widgets of the window: a status row with its state icon, and the fleurons."""

import logging
from enum import Enum

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPaintEvent, QResizeEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from project_reforged_linux.ui import theme
from project_reforged_linux.ui.assets import FLEURON, icon_pixmap
from project_reforged_linux.ui.bezel import SMALL, BezelButton

__all__ = ["ElidedLabel", "Fleuron", "State", "StatusRow"]

logger = logging.getLogger(__name__)

ICON_SIZE = 26
FLEURON_HEIGHT = 40
# The traced ornament's own colours, mapped onto the guardians' gold.
FLEURON_GOLD = {b"#3E1C07": theme.AGED_DARK, b"#A56209": theme.AGED_MID,
                b"#DFA034": theme.AGED_LIGHT, b"#E0A134": theme.AGED_LIGHT}


def _fleuron_svg() -> bytes:
    data = FLEURON.read_bytes()
    for traced, aged in FLEURON_GOLD.items():
        data = data.replace(traced, aged.encode())
    return data


class State(Enum):
    """Check first, then a tick, a cross or an update; never a question mark."""

    CHECKING = ("", "")  # no symbol yet
    OK = ("circle-check", theme.STATE_OK)
    ERROR = ("circle-x", theme.STATE_ERROR)
    UPDATE = ("circle-arrow-up", theme.STATE_UPDATE)
    # Dimmed, no symbol: the row does not apply now. Its own value, or Enum makes it an
    # alias of CHECKING.
    NOT_NEEDED = ("", theme.TEXT_DIM)


class ElidedLabel(QLabel):
    """A right-aligned label that shortens its text in the middle when the row runs out."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def set_full_text(self, text: str) -> None:
        self._full = text
        self._elide()

    def full_text(self) -> str:
        return self._full

    def _elide(self) -> None:
        self.setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle,
                                                   max(self.width(), 0)))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt's name)
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt's name)
        return QSize(self.fontMetrics().horizontalAdvance(self._full),
                     super().sizeHint().height())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt's name)
        super().resizeEvent(event)
        self._elide()


class StatusRow(QWidget):
    def __init__(self, title: str, *, button: str | None = None,
                 parent: QWidget | None = None) -> None:
        if not title.strip():
            raise ValueError("a status row needs a title")
        super().__init__(parent)
        self.state = State.CHECKING
        self._icon = QLabel()
        self._icon.setObjectName("statusIcon")
        self._icon.setFixedSize(ICON_SIZE, ICON_SIZE)
        self._title = QLabel(title)
        self._title.setObjectName("statusText")
        self._detail = ElidedLabel()
        self._detail.setObjectName("statusDetail")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.addWidget(self._icon)
        row.addWidget(self._title)
        row.addWidget(self._detail, 1)
        self.button: BezelButton | None = None
        if button is not None:
            self.button = BezelButton(button, style=SMALL)
            self.button.setObjectName("rowButton")
            row.addWidget(self.button)
        self.set_state(State.CHECKING, "")

    def set_state(self, state: State, detail: str, *, tooltip: str = "") -> None:
        self.state = state
        name, colour = state.value
        if state in (State.CHECKING, State.NOT_NEEDED):
            self._icon.clear()
        else:
            self._icon.setPixmap(icon_pixmap(name, colour, ICON_SIZE, self.devicePixelRatioF()))
        self._detail.set_full_text(detail)
        self.setToolTip(tooltip)
        if state is State.NOT_NEEDED:
            fade = QGraphicsOpacityEffect(self)
            fade.setOpacity(theme.DISABLED_OPACITY)
            self.setGraphicsEffect(fade)
        else:
            self.setGraphicsEffect(None)  # Qt deletes the previous effect

    def detail_text(self) -> str:
        return self._detail.full_text()


class Fleuron(QWidget):
    """The ornament beside RUN GAME, pointing away from the button."""

    def __init__(self, *, points: Qt.Edge, parent: QWidget | None = None) -> None:
        if points not in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge):
            raise ValueError(f"a fleuron points left or right, not {points}")
        super().__init__(parent)
        self._points = points
        try:
            self._renderer = QSvgRenderer(QByteArray(_fleuron_svg()))
        except OSError:
            self._renderer = QSvgRenderer()
        box = self._renderer.viewBoxF()
        if not self._renderer.isValid() or box.height() <= 0:
            logger.error("fleuron ornament missing or unreadable: %s", FLEURON)
            ratio = 1.4
        else:
            ratio = box.width() / box.height()
        self.setFixedSize(round(FLEURON_HEIGHT * ratio), FLEURON_HEIGHT)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt's name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # The ornament is drawn pointing right; pointing left is its mirror.
        if self._points == Qt.Edge.LeftEdge:
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        self._renderer.render(painter, QRectF(0, 0, self.width(), self.height()))
        painter.end()
