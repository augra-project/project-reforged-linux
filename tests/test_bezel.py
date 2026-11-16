# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import math

import pytest
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtWidgets import QPushButton, QWidget

from project_reforged_linux.ui import theme
from project_reforged_linux.ui.bezel import (
    GOLD,
    ICON_GAP,
    ICON_SIZE,
    LEATHER,
    PANEL,
    BezelButton,
    Panel,
    paint_bezel,
)

SCALE = 4  # whole device pixels for the thinnest layer


def bezel_image(style, width: float = 120, height: float = 40, **state) -> QImage:  # type: ignore[no-untyped-def]
    image = QImage(round(width * SCALE), round(height * SCALE), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.scale(SCALE, SCALE)
    paint_bezel(painter, QRectF(0, 0, width, height), style, **state)
    painter.end()
    return image


def at(image: QImage, x: float, y: float) -> QColor:
    return image.pixelColor(round(x * SCALE), round(y * SCALE))


def light(colour: QColor) -> int:
    return colour.red() + colour.green() + colour.blue()


def on_night(widget: QWidget) -> QImage:
    image = QImage(widget.width(), widget.height(), QImage.Format.Format_ARGB32)
    image.fill(QColor(theme.NIGHT))
    widget.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return image


@pytest.mark.parametrize("style", [LEATHER, GOLD, PANEL])
def test_outer_layer_on_every_side(qapp, style) -> None:  # type: ignore[no-untyped-def]
    image = bezel_image(style)
    colour, width = style.layers[0]
    for x, y in ((60, width / 2), (60, 40 - width / 2), (width / 2, 20), (120 - width / 2, 20)):
        assert at(image, x, y).name() == colour.lower(), (x, y)


def test_fill_runs_from_top_to_bottom_colour(qapp) -> None:  # type: ignore[no-untyped-def]
    image = bezel_image(LEATHER)
    top, bottom, middle = QColor(LEATHER.fill_top), QColor(LEATHER.fill_bottom), at(image, 60, 20)
    for channel in ("red", "green", "blue"):
        want = (getattr(top, channel)() + getattr(bottom, channel)()) / 2
        assert abs(getattr(middle, channel)() - want) <= 3, channel


def test_pressed_darker_hovered_lighter(qapp) -> None:  # type: ignore[no-untyped-def]
    normal = light(at(bezel_image(GOLD), 60, 20))
    pressed = light(at(bezel_image(GOLD, pressed=True), 60, 20))
    hovered = light(at(bezel_image(GOLD, hovered=True), 60, 20))
    assert pressed < normal < hovered


def test_corners_stay_clear(qapp) -> None:  # type: ignore[no-untyped-def]
    for style in (LEATHER, GOLD, PANEL):
        assert at(bezel_image(style), 0, 0).alpha() == 0, style


def test_too_small_is_refused(qapp) -> None:  # type: ignore[no-untyped-def]
    image = QImage(100, 100, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        with pytest.raises(ValueError):
            paint_bezel(painter, QRectF(0, 0, 2 * LEATHER.thickness, 40), LEATHER)
    finally:
        painter.end()


def test_gold_and_leather_are_one_class(qapp) -> None:  # type: ignore[no-untyped-def]
    run = BezelButton("RUN GAME", style=GOLD)
    options = BezelButton("Options", icon="settings")
    assert type(run) is type(options) is BezelButton and isinstance(run, QPushButton)
    assert run.height() == GOLD.height == 44 and options.height() == LEATHER.height


def test_button_clicks(qapp) -> None:  # type: ignore[no-untyped-def]
    clicked: list[bool] = []
    button = BezelButton("Quit", icon="power")
    button.clicked.connect(lambda: clicked.append(True))
    button.click()
    assert clicked == [True]


def inside(button: BezelButton) -> tuple[int, int]:
    """A point in the fill, left of the centred text."""
    return math.ceil(button.bezel.thickness) + 3, button.height() // 2


@pytest.mark.parametrize("style, gold", [(GOLD, True), (LEATHER, False)])
def test_style_decides_the_fill(qapp, style, gold: bool) -> None:  # type: ignore[no-untyped-def]
    button = BezelButton("RUN GAME", style=style)
    button.resize(button.sizeHint().width() + 60, style.height)
    colour = on_night(button).pixelColor(*inside(button))
    assert (colour.red() > colour.blue() + 80) is gold, colour.name()


def test_pressed_and_disabled_paint_darker(qapp) -> None:  # type: ignore[no-untyped-def]
    button = BezelButton("RUN GAME", style=GOLD)
    button.resize(button.sizeHint().width() + 60, GOLD.height)
    normal = light(on_night(button).pixelColor(*inside(button)))
    button.setDown(True)
    pressed = light(on_night(button).pixelColor(*inside(button)))
    button.setDown(False)
    button.setEnabled(False)
    disabled = light(on_night(button).pixelColor(*inside(button)))
    assert pressed < normal and disabled < normal


def test_icon_widens_and_is_drawn(qapp) -> None:  # type: ignore[no-untyped-def]
    plain, with_icon = BezelButton("Options"), BezelButton("Options", icon="settings")
    assert with_icon.sizeHint().width() == plain.sizeHint().width() + ICON_SIZE + ICON_GAP
    with_icon.resize(with_icon.sizeHint())
    image = on_night(with_icon)
    left = math.ceil(LEATHER.thickness) + 14  # PADDING: where the icon starts
    edge = math.ceil(LEATHER.thickness) + 1  # inside the frame, whose layers are gold too
    icon_gold = [image.pixelColor(x, y) for x in range(left, left + ICON_SIZE)
                 for y in range(edge, image.height() - edge)]
    # The icon is GOLD_HI (blue 0x8a); the text is TEXT (blue 0xc6).
    assert any(c.red() > 200 and c.blue() < 160 for c in icon_gold)


@pytest.mark.parametrize("text, icon, style", [
    ("  ", None, LEATHER), ("Options", "castle", LEATHER), ("Box", None, PANEL)])
def test_button_refuses_bad_input(qapp, text: str, icon, style) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        BezelButton(text, icon=icon, style=style)


def test_panel_frames_its_content(qapp) -> None:  # type: ignore[no-untyped-def]
    panel = Panel()
    panel.resize(200, 120)
    image = on_night(panel)
    # At 1x the 0.75 px layers fall between pixel rows, so the edge row picks up a little
    # of the gold beside it; the exact colours per side are checked at 4x above.
    edge, frame = image.pixelColor(100, 0), QColor(PANEL.layers[0][0])
    assert max(abs(edge.red() - frame.red()), abs(edge.green() - frame.green()),
               abs(edge.blue() - frame.blue())) <= 24, edge.name()
    middle = image.pixelColor(100, 60)
    assert middle.name() != theme.NIGHT and middle.red() > middle.blue()
    margins = panel.box.contentsMargins()
    assert min(margins.left(), margins.top()) >= math.ceil(PANEL.thickness)


def gold_band(image: QImage, style, y: float) -> list[int]:  # type: ignore[no-untyped-def]
    return [light(at(image, x, y)) for x in range(10, 110)]


def middle_of_the_gold(style) -> float:  # type: ignore[no-untyped-def]
    return style.layers[0][1] + style.layers[1][1] + style.layers[2][1] / 2


@pytest.mark.parametrize("style", [LEATHER, PANEL])
def test_the_gold_is_lit_from_above(qapp, monkeypatch, style) -> None:  # type: ignore[no-untyped-def]
    # Stefan, 2026-11-16: worked metal; the light alone, without the grain.
    from project_reforged_linux.ui import bezel

    monkeypatch.setattr(bezel, "GRAIN_OPACITY", 0.0)
    image = bezel_image(style)
    middle = middle_of_the_gold(style)
    top, bottom = gold_band(image, style, middle), gold_band(image, style, 40 - middle)
    assert sum(top) / len(top) > sum(bottom) / len(bottom) + 10


@pytest.mark.parametrize("style", [LEATHER, PANEL])
def test_the_gold_is_flecked(qapp, monkeypatch, style) -> None:  # type: ignore[no-untyped-def]
    # The grain alone, without the light: neighbouring stretches of one edge differ.
    from project_reforged_linux.ui import bezel

    monkeypatch.setattr(bezel, "BEVEL", 100)
    top = gold_band(bezel_image(style), style, middle_of_the_gold(style))
    assert max(top) - min(top) >= 12, (min(top), max(top))


def test_the_grain_is_the_same_every_time(qapp) -> None:  # type: ignore[no-untyped-def]
    from project_reforged_linux.ui import bezel

    first = bezel._grain().copy()
    bezel._grain.cache_clear()
    assert bezel._grain() == first
