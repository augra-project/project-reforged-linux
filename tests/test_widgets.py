# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import logging
from pathlib import Path

import pytest
from PySide6.QtCore import QByteArray, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

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
    (State.OK, "green"), (State.ERROR, "red"), (State.UPDATE, "red")])
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
    QSvgRenderer(QByteArray(widgets._fleuron_svg())).render(painter, QRectF(0, 0, width, height))
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
    row = StatusRow("Project Reforged")
    assert row.state is State.CHECKING
    icon = row.findChild(QLabel, "statusIcon")
    assert icon.pixmap().isNull()
    row.set_state(State.ERROR, "")
    assert not icon.pixmap().isNull()
    row.set_state(State.CHECKING, "checking...")
    assert icon.pixmap().isNull()
    assert {s.name for s in State} == {"CHECKING", "OK", "ERROR", "UPDATE", "NOT_NEEDED"}
    assert "question" not in State.UPDATE.value[0]


def test_detail_is_right_aligned_and_shortened_in_the_middle(qapp) -> None:  # type: ignore[no-untyped-def]
    text = "~/Projects/augra/.workspace/shadowkey/ngage-files"
    row = StatusRow("Original game files")
    row.resize(300, 40)
    row.set_state(State.OK, text)
    # Qt holds resize events back until a widget is shown; the window is shown too.
    row.show()
    QApplication.processEvents()
    label = row.findChild(QLabel, "statusDetail")
    assert label.alignment() & Qt.AlignmentFlag.AlignRight
    shown = label.text()
    assert shown != text and "\u2026" in shown
    assert shown.startswith(text[:3]) and shown.endswith(text[-3:])
    assert label.fontMetrics().horizontalAdvance(shown) <= label.width()
    assert row.detail_text() == text, "the full text stays readable for tests and tooltips"
    row.resize(1000, 40)
    QApplication.processEvents()
    assert label.text() == text, "with room again, nothing is cut"


def opaque_mean(image: QImage) -> tuple[float, float, float]:
    pixels = [image.pixelColor(x, y) for x in range(image.width())
              for y in range(image.height())]
    solid = [p for p in pixels if p.alpha() > 230]
    assert solid, "nothing opaque"
    return tuple(sum(getattr(p, c)() for p in solid) / len(solid)  # type: ignore[return-value]
                 for c in ("red", "green", "blue"))


def test_fleuron_wears_the_guardians_gold(qapp) -> None:  # type: ignore[no-untyped-def]
    # The fleurons were a brighter, oranger gold than
    # the Dragon Guardians' aged one beside them.
    from project_reforged_linux.ui.assets import CORNER_TOP

    fleuron = Fleuron(points=Qt.Edge.RightEdge)
    image = QImage(fleuron.size() * 4, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.scale(4, 4)
    fleuron.render(painter, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    painter.end()
    got, want = opaque_mean(image), opaque_mean(QImage(str(CORNER_TOP)))
    assert max(abs(g - w) for g, w in zip(got, want, strict=True)) <= 20, (got, want)


def test_a_row_that_is_not_needed_is_dimmed_like_a_disabled_button(qapp) -> None:  # type: ignore[no-untyped-def]
    # The Windows Runtime row while a Linux build runs.
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    row = StatusRow("Windows Runtime")
    row.set_state(State.NOT_NEEDED, "not needed for the Linux build", tooltip="why")
    effect = row.graphicsEffect()
    assert isinstance(effect, QGraphicsOpacityEffect)
    assert effect.opacity() == pytest.approx(theme.DISABLED_OPACITY)
    assert row.findChild(QLabel, "statusIcon").pixmap().isNull()
    assert row.detail_text() == "not needed for the Linux build" and row.toolTip() == "why"
    row.set_state(State.OK, "Wine 10.0 (system)")
    assert row.graphicsEffect() is None
