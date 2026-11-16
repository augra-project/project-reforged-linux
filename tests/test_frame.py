# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import logging
from pathlib import Path

import pytest
from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from project_reforged_linux.ui import frame, theme
from project_reforged_linux.ui.frame import CORNER_SIZE, FrameWidget, paint_frame

EMPTY_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
SCALE = 4  # whole device pixels for every 0.5-px band


def render(width: int = 300, height: int = 200, svg: bytes = EMPTY_SVG) -> QImage:
    image = QImage(width * SCALE, height * SCALE, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    painter.scale(SCALE, SCALE)
    paint_frame(painter, QRectF(0, 0, width, height), None, QSvgRenderer(QByteArray(svg)))
    painter.end()
    return image


def colour_at(image: QImage, x: float, y: float) -> str:
    return QColor(image.pixel(round(x * SCALE), round(y * SCALE))).name()


def test_margin_rail_and_inside(qapp) -> None:  # type: ignore[no-untyped-def]
    image = render()
    assert colour_at(image, 150, 3) == theme.MARGIN.lower()
    offset = theme.RAIL_INSET
    for colour, width in theme.RAIL:
        assert colour_at(image, 150, offset + width / 2) == colour.lower()
        offset += width
    assert colour_at(image, 150, 100) == theme.NIGHT


def test_rail_on_all_four_sides(qapp) -> None:  # type: ignore[no-untyped-def]
    image = render()
    body = theme.RAIL_INSET + 0.5 + 0.5 + 0.75
    body_colour = theme.RAIL[2][0].lower()
    assert colour_at(image, 150, body) == body_colour
    assert colour_at(image, 150, 200 - body) == body_colour
    assert colour_at(image, body, 100) == body_colour
    assert colour_at(image, 300 - body, 100) == body_colour


def test_corners_are_drawn_mirrored(qapp) -> None:  # type: ignore[no-untyped-def]
    marker = (b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
              b'<rect x="0" y="0" width="2" height="2" fill="#ff0000"/></svg>')
    image = render(svg=marker)
    near = CORNER_SIZE * 0.1
    for x, y in ((near, near), (300 - near, near), (near, 200 - near),
                 (300 - near, 200 - near)):
        assert colour_at(image, x, y) == "#ff0000", (x, y)


def test_corner_keeps_its_proportions(qapp) -> None:  # type: ignore[no-untyped-def]
    # Twice as wide as tall, marker in the bottom-left: stretched to a square it
    # would land near CORNER_SIZE * 0.9, kept in proportion near CORNER_SIZE * 0.45.
    marker = (b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
              b'<rect x="0" y="8" width="2" height="2" fill="#ff0000"/></svg>')
    image = render(svg=marker)
    near = CORNER_SIZE * 0.05
    assert colour_at(image, near, CORNER_SIZE * 0.45) == "#ff0000"
    assert colour_at(image, near, CORNER_SIZE * 0.9) != "#ff0000"


@pytest.mark.parametrize("width, height", [(2 * CORNER_SIZE - 1, 200), (300, 2 * CORNER_SIZE - 1)])
def test_too_small_for_its_corners(qapp, width: float, height: float) -> None:  # type: ignore[no-untyped-def]
    image = QImage(400, 400, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        with pytest.raises(ValueError):
            paint_frame(painter, QRectF(0, 0, width, height), None,
                        QSvgRenderer(QByteArray(EMPTY_SVG)))
    finally:
        painter.end()


def test_widget_paints_the_real_art(qapp) -> None:  # type: ignore[no-untyped-def]
    widget = FrameWidget()
    widget.resize(300, 200)
    image = widget.grab().toImage()
    assert QColor(image.pixel(150, 3)).name() == theme.MARGIN.lower()
    assert QColor(image.pixel(150, 100)).name() != theme.NIGHT


def test_widget_says_when_art_is_missing(qapp, monkeypatch: pytest.MonkeyPatch,
                                         caplog: pytest.LogCaptureFixture,
                                         tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(frame, "BACKGROUND", tmp_path / "gone.jpg")
    monkeypatch.setattr(frame, "CORNER", tmp_path / "gone.svg")
    with caplog.at_level(logging.ERROR, logger=frame.__name__):
        FrameWidget()
    text = caplog.text
    assert "gone.jpg" in text and "gone.svg" in text


def test_background_is_cropped_from_the_centre(qapp) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtGui import QPixmap

    # Three stripes, wider than the inside: a centred crop keeps a bit of both outer
    # stripes, a crop from the left loses the blue one.
    stripes = QImage(300, 100, QImage.Format.Format_ARGB32)
    for x, colour in ((0, "#ff0000"), (100, "#00ff00"), (200, "#0000ff")):
        painter = QPainter(stripes)
        painter.fillRect(x, 0, 100, 100, QColor(colour))
        painter.end()
    image = QImage(300 * SCALE, 200 * SCALE, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    painter.scale(SCALE, SCALE)
    paint_frame(painter, QRectF(0, 0, 300, 200), QPixmap.fromImage(stripes),
                QSvgRenderer(QByteArray(EMPTY_SVG)))
    painter.end()
    edge = theme.RAIL_INSET + sum(width for _, width in theme.RAIL) + 4
    assert colour_at(image, edge, 100) == "#ff0000"
    assert colour_at(image, 150, 100) == "#00ff00"
    assert colour_at(image, 300 - edge, 100) == "#0000ff"
