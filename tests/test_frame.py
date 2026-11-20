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
from project_reforged_linux.ui.frame import (
    ART_RAIL,
    CORNER_SHIFT,
    CORNER_SIZE,
    FrameWidget,
    paint_frame,
)

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


def test_no_dark_margin_and_the_rail_near_the_edge(qapp) -> None:  # type: ignore[no-untyped-def]
    image = render()
    assert theme.RAIL_INSET <= 2
    assert colour_at(image, 150, theme.RAIL_INSET / 2) == theme.NIGHT
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
              b'<rect x="0" y="0" width="4" height="4" fill="#ff0000"/></svg>')
    image = render(svg=marker)
    near = CORNER_SIZE * 0.2 + CORNER_SHIFT  # the art moves outward with the rail
    for x, y in ((near, near), (300 - near, near), (near, 200 - near),
                 (300 - near, 200 - near)):
        assert colour_at(image, x, y) == "#ff0000", (x, y)


def test_corner_keeps_its_proportions(qapp) -> None:  # type: ignore[no-untyped-def]
    # Twice as wide as tall, marker low in the art: stretched to a square it would land
    # near CORNER_SIZE * 0.9, kept in proportion near CORNER_SIZE * 0.45 (both shifted out).
    marker = (b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
              b'<rect x="6" y="8" width="2" height="2" fill="#ff0000"/></svg>')
    image = render(svg=marker)
    x = CORNER_SIZE * 0.35 + CORNER_SHIFT
    assert colour_at(image, x, CORNER_SIZE * 0.45 + CORNER_SHIFT) == "#ff0000"
    assert colour_at(image, x, CORNER_SIZE * 0.9 + CORNER_SHIFT) != "#ff0000"


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
    assert QColor(image.pixel(150, 0)).name() != theme.NIGHT  # the picture, up to the edge
    assert QColor(image.pixel(150, 100)).name() != theme.NIGHT


def test_widget_says_when_art_is_missing(qapp, monkeypatch: pytest.MonkeyPatch,
                                         caplog: pytest.LogCaptureFixture,
                                         tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(frame, "BACKGROUND", tmp_path / "gone.jpg")
    monkeypatch.setattr(frame, "CORNER_TOP", tmp_path / "gone-top.png")
    monkeypatch.setattr(frame, "CORNER_BOTTOM", tmp_path / "gone-bottom.png")
    with caplog.at_level(logging.ERROR, logger=frame.__name__):
        FrameWidget()
    text = caplog.text
    assert "gone.jpg" in text and "gone-top.png" in text and "gone-bottom.png" in text


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
    assert colour_at(image, 0.3, 100) == "#ff0000"  # the picture reaches the window's edge
    assert colour_at(image, 150, 100) == "#00ff00"
    assert colour_at(image, 300 - edge, 100) == "#0000ff"


def marker_image(colour: str, width: int = 10, height: int = 10) -> QImage:
    """Transparent art with a 2x2 dot of colour in its top-left corner."""
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.fillRect(0, 0, 2, 2, QColor(colour))
    painter.end()
    return image


def render_art(top, bottom=None) -> QImage:  # type: ignore[no-untyped-def]
    image = QImage(300 * SCALE, 200 * SCALE, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        painter.scale(SCALE, SCALE)
        paint_frame(painter, QRectF(0, 0, 300, 200), None, top, bottom)
    finally:
        painter.end()  # an active painter on a dying image crashes Qt
    return image


def test_raster_corner_art_is_drawn(qapp) -> None:  # type: ignore[no-untyped-def]
    image = render_art(marker_image("#ff0000"))
    near = 1.0
    for x, y in ((near, near), (300 - near, near), (near, 200 - near), (300 - near, 200 - near)):
        assert colour_at(image, x, y) == "#ff0000", (x, y)


def test_bottom_art_stands_upright(qapp) -> None:  # type: ignore[no-untyped-def]
    # The guardians at the bottom rise from the rail, not hang from it.
    image = render_art(marker_image("#ff0000"), marker_image("#0000ff", 10, 20))
    near = 1.0
    top_of_bottom = 200 - CORNER_SIZE * 2 - CORNER_SHIFT  # shifted outward: down
    for x in (near, 300 - near):
        # the dot at the top of the bottom art stays at its top: not flipped upside down
        assert colour_at(image, x, top_of_bottom + 2) == "#0000ff", x
        assert colour_at(image, x, 200 - near) != "#0000ff", x
        assert colour_at(image, x, near) == "#ff0000", x


def test_too_short_for_both_pieces(qapp) -> None:  # type: ignore[no-untyped-def]
    image = QImage(400, 400, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        with pytest.raises(ValueError):
            paint_frame(painter, QRectF(0, 0, 300, 150), None, marker_image("#ff0000", 10, 15),
                        marker_image("#0000ff", 10, 15))
    finally:
        painter.end()


def test_the_art_s_rail_lies_on_the_window_s_rail(qapp) -> None:  # type: ignore[no-untyped-def]
    # The guardians carry their own rail line ART_RAIL from their outer edge; it must land on
    # the painted rail, which moved out to the window's edge.
    size = round(CORNER_SIZE)
    art = QImage(size, size, QImage.Format.Format_ARGB32)
    art.fill(0)
    painter = QPainter(art)
    painter.fillRect(QRectF(ART_RAIL - 0.5, ART_RAIL - 0.5, 1, 1), QColor("#00ff00"))
    painter.end()
    image = render_art(art)
    rail = theme.RAIL_INSET + sum(width for _, width in theme.RAIL) / 2
    assert colour_at(image, rail, rail) == "#00ff00"


def test_the_bottom_piece_has_its_own_width_and_rail(qapp) -> None:  # type: ignore[no-untyped-def]
    # The extended bottom guardian is wider than tall, its bar and base line lie close to its
    # edges; both must still land on the painted rail.
    width, height, rail_x, rail_y = 94, 90, 2.5, 1.3
    art = QImage(width, height, QImage.Format.Format_ARGB32)
    art.fill(0)
    painter = QPainter(art)
    painter.fillRect(QRectF(rail_x - 0.5, height - rail_y - 0.5, 1, 1), QColor("#00ff00"))
    painter.fillRect(QRectF(width - 3, height - 3, 2, 2), QColor("#ff00ff"))
    painter.end()
    image = QImage(300 * SCALE, 200 * SCALE, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        painter.scale(SCALE, SCALE)
        paint_frame(painter, QRectF(0, 0, 300, 200), None, marker_image("#ff0000"), art,
                    bottom_width=width, bottom_rail=(rail_x, rail_y))
    finally:
        painter.end()
    rail = theme.RAIL_INSET + sum(w for _, w in theme.RAIL) / 2
    assert colour_at(image, rail, 200 - rail) == "#00ff00"
    assert colour_at(image, 300 - rail, 200 - rail) == "#00ff00"  # mirrored on the right
    # drawn at its own width: its far end reaches about `width` in from the edge
    reach = rail - rail_x + width - 2
    assert colour_at(image, reach, 200 - (rail - rail_y) - 2) == "#ff00ff"


def _row_ink(image: QImage, y: int) -> int:
    return sum(image.pixelColor(x, y).alpha() for x in range(image.width()))


def test_guardians_fade_into_the_rail(qapp) -> None:  # type: ignore[no-untyped-def]
    # The top piece's column foot and the bottom piece's
    # bar top and tail met the rail too abruptly; their ends fade out onto it now.
    from project_reforged_linux.ui.assets import CORNER_BOTTOM, CORNER_TOP

    top, bottom = QImage(str(CORNER_TOP)), QImage(str(CORNER_BOTTOM))
    foot = _row_ink(top, top.height() - 1)
    assert foot < 0.2 * _row_ink(top, round(top.height() * 0.8)), foot
    bar_top = _row_ink(bottom, 0)
    assert bar_top < 0.2 * _row_ink(bottom, round(bottom.height() * 0.2)), bar_top
    tail_end = max(bottom.pixelColor(x, y).alpha() for x in range(bottom.width() - 12,
                                                                  bottom.width())
                   for y in range(bottom.height()))
    assert tail_end < 64, tail_end
