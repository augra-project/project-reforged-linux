# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import logging
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from project_reforged_linux.ui import theme, widgets
from project_reforged_linux.ui.assets import FLEURON
from project_reforged_linux.ui.widgets import Fleuron, State, StatusRow


def on_night(widget: QWidget) -> QImage:
    """The widget drawn over the window's night, as it sits in the window."""
    image = QImage(widget.width(), widget.height(), QImage.Format.Format_ARGB32)
    image.fill(QColor(theme.NIGHT))
    widget.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return image


def test_status_row_shows_state_text_and_detail(qapp) -> None:  # type: ignore[no-untyped-def]
    row = StatusRow("Project Reforged")
    row.set_state(State.OK, "v0.2.33", tooltip="installed")
    assert row.state is State.OK
    assert row.detail_text() == "v0.2.33" and row.toolTip() == "installed"
    row.set_state(State.ERROR, "none usable", tooltip="no Wine")
    assert row.state is State.ERROR and row.toolTip() == "no Wine"


@pytest.mark.parametrize("state, channel", [
    (State.OK, "green"), (State.ERROR, "red")])
def test_status_icon_takes_the_state_colour(qapp, state: State, channel: str) -> None:  # type: ignore[no-untyped-def]
    row = StatusRow("Project Reforged")
    row.set_state(state, "")
    icon = row.findChild(QLabel, "statusIcon").pixmap().toImage()
    want = QColor(state.value[1])
    # pixelColor, not QColor(pixel()): built from a bare QRgb, QColor drops the alpha.
    pixels = [icon.pixelColor(x, y) for x in range(icon.width()) for y in range(icon.height())]
    assert any(c.alpha() == 0 for c in pixels), "the icon has no transparent background"
    inked = [c for c in pixels if c.alpha() == 255]
    assert inked, state
    # Fully covered pixels carry exactly the state's colour.
    assert all(c.rgb() == want.rgb() for c in inked), state
    assert getattr(want, channel)() > 150


def test_status_row_button(qapp) -> None:  # type: ignore[no-untyped-def]
    clicked: list[bool] = []
    row = StatusRow("Required original game files", button="Choose...")
    assert isinstance(row.button, QPushButton)
    row.button.clicked.connect(lambda: clicked.append(True))
    row.button.click()
    assert clicked == [True]


def test_status_row_without_button(qapp) -> None:  # type: ignore[no-untyped-def]
    assert StatusRow("Windows Runtime").button is None


def test_status_row_refuses_empty_title() -> None:
    with pytest.raises(ValueError):
        StatusRow("  ")


def reference(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(theme.NIGHT))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(FLEURON)).render(painter, QRectF(0, 0, width, height))
    painter.end()
    return image


def share_differing(a: QImage, b: QImage) -> float:
    """Share of pixels off by more than 8 in some channel; mirrored antialiasing rounds by a few."""
    def off(x: int, y: int) -> bool:
        p, q = a.pixelColor(x, y), b.pixelColor(x, y)
        return max(abs(p.red() - q.red()), abs(p.green() - q.green()),
                   abs(p.blue() - q.blue())) > 8

    return sum(off(x, y) for x in range(a.width()) for y in range(a.height())) / (
        a.width() * a.height())


@pytest.mark.parametrize("points", [Qt.Edge.LeftEdge, Qt.Edge.RightEdge])
def test_fleuron_points_outward_as_asked(qapp, points: Qt.Edge) -> None:  # type: ignore[no-untyped-def]
    fleuron = Fleuron(points=points)
    image = on_night(fleuron)
    # The ornament is drawn pointing right; the one pointing left is its mirror.
    want = reference(fleuron.width(), fleuron.height())
    if points == Qt.Edge.LeftEdge:
        want = want.flipped(Qt.Orientation.Horizontal)
    gold = sum(QColor(image.pixel(x, y)).red() > QColor(image.pixel(x, y)).blue() + 40
               for x in range(image.width()) for y in range(image.height()))
    assert gold > 0.25 * image.width() * image.height()
    assert share_differing(image, want) < 0.01


def test_fleuron_keeps_its_proportions(qapp) -> None:  # type: ignore[no-untyped-def]
    fleuron = Fleuron(points=Qt.Edge.RightEdge)
    box = QSvgRenderer(str(FLEURON)).viewBoxF()
    assert fleuron.width() == round(fleuron.height() * box.width() / box.height())


def test_fleuron_refuses_other_directions() -> None:
    with pytest.raises(ValueError):
        Fleuron(points=Qt.Edge.TopEdge)


def test_fleuron_says_when_art_is_missing(qapp, monkeypatch: pytest.MonkeyPatch,
                                          caplog: pytest.LogCaptureFixture,
                                          tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(widgets, "FLEURON", tmp_path / "gone.svg")
    with caplog.at_level(logging.ERROR, logger=widgets.__name__):
        Fleuron(points=Qt.Edge.RightEdge)
    assert "gone.svg" in caplog.text


def test_a_row_shows_no_symbol_while_it_checks(qapp) -> None:  # type: ignore[no-untyped-def]
    # Stefan, 2026-11-16: check first, then a tick or a cross; never a question mark.
    row = StatusRow("Project Reforged")
    assert row.state is State.CHECKING
    icon = row.findChild(QLabel, "statusIcon")
    assert icon.pixmap().isNull()
    row.set_state(State.ERROR, "")
    assert not icon.pixmap().isNull()
    row.set_state(State.CHECKING, "checking...")
    assert icon.pixmap().isNull()
    assert {s.name for s in State} == {"CHECKING", "OK", "ERROR"}
