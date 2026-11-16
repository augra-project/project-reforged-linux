# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import math

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage, QRegion
from PySide6.QtWidgets import QWidget

from project_reforged_linux.ui import theme
from project_reforged_linux.ui.bezel import BAR
from project_reforged_linux.ui.progress import ProgressLine

WIDTH = 400


def draw(line: ProgressLine) -> QImage:
    line.resize(WIDTH, line.sizeHint().height())
    image = QImage(line.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(theme.NIGHT))
    line.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return image


def edge() -> int:
    return math.ceil(BAR.thickness) + 4


def gold(colour: QColor) -> bool:
    return colour.red() > colour.blue() + 80


def test_one_text_line_high(qapp) -> None:  # type: ignore[no-untyped-def]
    line = ProgressLine()
    text = line.fontMetrics().height()
    assert text <= line.sizeHint().height() <= text + 2 * math.ceil(BAR.thickness) + 2


def test_half_fills_the_left_half(qapp) -> None:  # type: ignore[no-untyped-def]
    line = ProgressLine()
    line.set_progress(0.5, "")
    image = draw(line)
    y = image.height() // 2
    assert gold(image.pixelColor(edge(), y))
    assert not gold(image.pixelColor(WIDTH - edge(), y))


def test_idle_has_no_fill(qapp) -> None:  # type: ignore[no-untyped-def]
    line = ProgressLine()
    line.set_idle("Ready")
    assert not gold(draw(line).pixelColor(edge(), draw(line).height() // 2))


def test_text_is_dark_on_gold_and_light_on_the_bar(qapp) -> None:  # type: ignore[no-untyped-def]
    line = ProgressLine()
    line.set_progress(0.5, "M" * 30)  # wide enough to cross the middle
    image = draw(line)
    inside = math.ceil(BAR.thickness) + 1  # the frame's dark edge is not text
    rows = range(inside, image.height() - inside)
    on_gold = [image.pixelColor(x, y) for x in range(edge(), WIDTH // 2 - 2) for y in rows]
    on_bar = [image.pixelColor(x, y) for x in range(WIDTH // 2 + 2, WIDTH - edge()) for y in rows]

    def light(c: QColor) -> int:
        return c.red() + c.green() + c.blue()

    assert any(light(c) < 150 for c in on_gold), "no dark text on the gold"
    assert any(light(c) > 450 for c in on_bar), "no light text on the bar"


def test_busy_fills_all_and_animates_only_while_shown(qapp) -> None:  # type: ignore[no-untyped-def]
    line = ProgressLine()
    line.show()
    assert not line.animating(), "a line that is not busy stays still when shown"
    line.set_busy("Downloading")
    assert line.fraction is None and line.animating()
    image = draw(line)
    y = image.height() // 2
    assert gold(image.pixelColor(edge(), y)) and gold(image.pixelColor(WIDTH - edge(), y))
    line.set_progress(0.3, "30 %")
    assert not line.animating()
    line.set_busy("Downloading")
    line.hide()
    assert not line.animating()


@pytest.mark.parametrize("fraction", [-0.01, 1.01, float("nan")])
def test_refuses_out_of_range(qapp, fraction: float) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        ProgressLine().set_progress(fraction, "")
