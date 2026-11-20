# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontInfo, QImage, QPainter, QPainterPath, QRegion
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from project_reforged_linux.ui import theme
from project_reforged_linux.ui.banner import (
    DIAMOND,
    RULE_OVERHANG,
    STRETCH_Y,
    WORDMARK,
    WORDMARK_HEIGHT,
    Banner,
    Wordmark,
    paint_rule,
    text_outline,
    wordmark_font,
)


def golden(colour: QColor) -> bool:
    return colour.red() > 150 and colour.green() > 100 and colour.blue() < 120


def gold_leaning(colour: QColor) -> bool:
    """Any gold ink, even a half-covered edge pixel; the night background leans violet."""
    return colour.red() > colour.blue() + 40


def grab(widget, width: int, height: int) -> QImage:  # type: ignore[no-untyped-def]
    """The widget drawn over the window's night, as it sits in the window."""
    widget.resize(width, height)
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(theme.NIGHT))
    widget.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return image


def test_wordmark_words() -> None:
    assert WORDMARK == ("PROJECT", "REFORGED")


def test_wordmark_paints_gold(qapp) -> None:  # type: ignore[no-untyped-def]
    image = grab(Wordmark(theme.load_fonts()), 520, 160)
    gold = sum(golden(QColor(image.pixel(x, y)))
               for x in range(0, image.width(), 4) for y in range(0, image.height(), 4))
    assert gold > 200


def test_wordmark_both_lines_centred(qapp) -> None:  # type: ignore[no-untyped-def]
    mark = Wordmark(theme.load_fonts())
    image = grab(mark, mark.width(), mark.height())
    empty = image.pixel(0, 0)
    split = round(image.height() * 0.62)
    for top, bottom in ((0, split), (split, image.height())):
        columns = [x for x in range(image.width())
                   if any(image.pixel(x, y) != empty for y in range(top, bottom))]
        left, right = columns[0], image.width() - 1 - columns[-1]
        assert abs(left - right) <= 6, (top, left, right)


def inked(path: QPainterPath, rule: Qt.FillRule, width: int = 520, height: int = 160) -> int:
    filled = QPainterPath(path)
    filled.setFillRule(rule)
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.fillPath(filled, QColor("white"))
    painter.end()
    return sum(QColor(image.pixel(x, y)).red() > 128
               for x in range(width) for y in range(height))


def test_wordmark_outline_has_no_overlap_holes(qapp) -> None:  # type: ignore[no-untyped-def]
    # Cinzel's glyphs overlap their own contours; filled odd-even, every overlap is a
    # hole the shadow shows through. A clean outline fills the same either way.
    mark = Wordmark(theme.load_fonts())
    mark.resize(520, 160)
    outline = mark.outline()
    odd_even = inked(outline, Qt.FillRule.OddEvenFill)
    winding = inked(outline, Qt.FillRule.WindingFill)
    assert odd_even > 1000
    assert abs(winding - odd_even) <= winding * 0.002, (odd_even, winding)


def test_wordmark_font_is_really_heavier(qapp) -> None:  # type: ignore[no-untyped-def]
    # QFont's weight does not reach a variable font's wght axis in addText paths.
    family = theme.load_fonts().heading
    regular = QFont(family)
    regular.setPixelSize(80)
    paths = []
    for font in (regular, wordmark_font(family, 80)):
        path = QPainterPath()
        path.addText(QPointF(4, 100), font, "PROJECT")
        paths.append(path)
    plain, heavy = (inked(path, Qt.FillRule.WindingFill) for path in paths)
    assert heavy > plain * 1.3, (plain, heavy)


def test_wordmark_font_refuses_empty_size() -> None:
    with pytest.raises(ValueError):
        wordmark_font("Cinzel", 0)


def test_text_outline_keeps_what_the_glyphs_cover(qapp) -> None:  # type: ignore[no-untyped-def]
    font = wordmark_font(theme.load_fonts().heading, 80)
    raw = QPainterPath()
    raw.addText(QPointF(4, 100), font, "REFORGED")
    covered = inked(raw, Qt.FillRule.WindingFill)
    # The precondition: the font really overlaps, or this test proves nothing.
    assert inked(raw, Qt.FillRule.OddEvenFill) < covered * 0.995
    clean = inked(text_outline(font, QPointF(4, 100), "REFORGED"), Qt.FillRule.OddEvenFill)
    assert abs(clean - covered) <= covered * 0.002, (clean, covered)


def test_wordmark_is_as_wide_as_its_words(qapp) -> None:  # type: ignore[no-untyped-def]
    mark = Wordmark(theme.load_fonts())
    words = mark.outline().boundingRect().width()
    assert words <= mark.width() <= words + 12


def themed_banner() -> tuple[QWidget, Banner]:
    root = QWidget()
    root.setObjectName("root")
    theme.apply(root, theme.load_fonts())
    banner = Banner(theme.load_fonts())
    QVBoxLayout(root).addWidget(banner)
    root.resize(976, 230)
    root.layout().activate()
    banner.layout().activate()
    return root, banner


def test_banner_groups_emblem_and_words_left_of_centre(qapp) -> None:  # type: ignore[no-untyped-def]
    # Set left as in the mockup, so the tower on the right keeps its sky.
    _root, banner = themed_banner()
    emblem = banner.findChild(QSvgWidget).geometry()
    mark = banner.findChild(Wordmark).geometry()
    gap = mark.left() - emblem.right()
    assert 0 < gap <= 24, gap
    group_centre = (emblem.left() + mark.right()) / 2
    assert group_centre < banner.width() / 2 - 40, group_centre
    assert emblem.left() > 60, emblem.left()


def test_wordmark_is_taller_and_stretched(qapp) -> None:  # type: ignore[no-untyped-def]
    mark = Wordmark(theme.load_fonts())
    assert WORDMARK_HEIGHT == 150 and mark.height() <= WORDMARK_HEIGHT
    plain, stretched = mark.outline(1.0).boundingRect(), mark.outline().boundingRect()
    ratio = (stretched.height() / stretched.width()) / (plain.height() / plain.width())
    assert abs(ratio - STRETCH_Y) < 0.02, ratio
    # The mockup's letters are visibly taller than Cinzel's own.
    assert ratio >= 1.1, ratio


def test_wordmark_refuses_empty_stretch(qapp) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        Wordmark(theme.load_fonts()).outline(0)


def test_a_small_wordmark_is_the_large_one_scaled(qapp) -> None:  # type: ignore[no-untyped-def]
    fonts = theme.load_fonts()
    large, small = Wordmark(fonts), Wordmark(fonts, height=50)
    assert small.height() == 50
    assert abs(small.width() - large.width() * 50 / large.height()) <= 1
    # Painted at that scale, not cut off: it matches the large mark shrunk to its size.
    image = grab(small, small.width(), small.height())
    shrunk = grab(large, large.width(), large.height()).scaled(
        small.width(), small.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation)
    pixels = [(x, y) for x in range(image.width()) for y in range(image.height())]
    agree = sum(gold_leaning(QColor(image.pixel(x, y))) == gold_leaning(QColor(shrunk.pixel(x, y)))
                for x, y in pixels)
    assert agree / len(pixels) > 0.9, agree / len(pixels)


@pytest.mark.parametrize("height", [0, -50])
def test_wordmark_refuses_empty_height(qapp, height: int) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        Wordmark(theme.load_fonts(), height=height)


def rule_image(width: int = 200, height: int = 20) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(theme.NIGHT))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint_rule(painter, QPointF(4, height / 2), QPointF(width - 12, height / 2))
    painter.end()
    return image


def column_gold(image: QImage, x: int) -> int:
    return sum(max(0, image.pixelColor(x, y).red() - image.pixelColor(x, y).blue())
               for y in range(image.height()))


def test_rule_tapers_towards_its_far_end(qapp) -> None:  # type: ignore[no-untyped-def]
    image = rule_image()
    near_diamond, far_end = column_gold(image, 160), column_gold(image, 12)
    assert far_end > 0
    assert near_diamond > 2 * far_end, (near_diamond, far_end)


def test_rule_ends_in_a_diamond(qapp) -> None:  # type: ignore[no-untyped-def]
    image = rule_image()
    diamond_centre = image.width() - 12 - DIAMOND
    # Above the line, only the diamond is gold.
    above = [image.pixelColor(x, image.height() // 2 - 3) for x in range(image.width())]
    gold_x = [x for x, c in enumerate(above) if c.red() > c.blue() + 40]
    assert gold_x and all(abs(x - diamond_centre) <= DIAMOND + 1 for x in gold_x), gold_x


def test_rule_refuses_a_slanted_line(qapp) -> None:  # type: ignore[no-untyped-def]
    image = QImage(50, 50, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        with pytest.raises(ValueError):
            paint_rule(painter, QPointF(0, 10), QPointF(40, 20))
    finally:
        painter.end()


def test_rules_reach_past_the_words(qapp) -> None:  # type: ignore[no-untyped-def]
    root, banner = themed_banner()
    image = QImage(root.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(theme.NIGHT))
    root.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    offset = banner.mapTo(root, QPoint(0, 0))
    mark = banner.findChild(Wordmark).geometry().translated(offset)
    subtitle = banner.findChild(QLabel, "subtitle").geometry().translated(offset)
    y = subtitle.center().y()

    def gold_at(x: int) -> bool:
        return any(image.pixelColor(x, yy).red() > image.pixelColor(x, yy).blue() + 40
                   for yy in range(y - 2, y + 3))

    assert gold_at(mark.left() - RULE_OVERHANG + 3)
    assert gold_at(mark.right() + RULE_OVERHANG - 3)
    assert not gold_at(mark.right() + RULE_OVERHANG + 8)


def test_subtitle_is_pronounced(qapp) -> None:  # type: ignore[no-untyped-def]
    _root, banner = themed_banner()
    subtitle = banner.findChild(QLabel, "subtitle")
    subtitle.ensurePolished()
    assert subtitle.text() == "Linux Launcher"
    assert QFontInfo(subtitle.font()).family() == "EB Garamond"
    assert subtitle.font().weight() >= QFont.Weight.DemiBold
    assert subtitle.font().pointSize() == round(theme.BASE_PT * 1.9)


def test_reforged_sits_a_little_narrower_under_project(qapp) -> None:  # type: ignore[no-untyped-def]
    # REFORGED a touch smaller than PROJECT, not as wide.
    mark = Wordmark(theme.load_fonts())
    image = grab(mark, mark.width(), mark.height())
    empty = image.pixel(0, 0)
    split = round(image.height() * 0.62)
    widths = []
    for top, bottom in ((0, split), (split, image.height())):
        columns = [x for x in range(image.width())
                   if any(image.pixel(x, y) != empty for y in range(top, bottom))]
        widths.append(columns[-1] - columns[0])
    upper, lower = widths
    assert lower < upper * 0.95, (upper, lower)


def ink_rows(mark: Wordmark) -> list[bool]:
    image = grab(mark, mark.width(), mark.height())
    empty = image.pixel(0, 0)
    return [any(image.pixel(x, y) != empty for x in range(image.width()))
            for y in range(image.height())]


def test_project_and_reforged_sit_close(qapp) -> None:  # type: ignore[no-untyped-def]
    # The two lines a bit more together (the gap was 11 rows).
    rows = ink_rows(Wordmark(theme.load_fonts()))
    inked = [y for y, r in enumerate(rows) if r]
    gaps, run = [], 0
    for y in range(inked[0], inked[-1] + 1):
        run = run + 1 if not rows[y] else 0
        gaps.append(run)
    assert 2 <= max(gaps) <= 6, max(gaps)


def test_wordmark_has_no_empty_headroom(qapp) -> None:  # type: ignore[no-untyped-def]
    rows = ink_rows(Wordmark(theme.load_fonts()))
    first, last = rows.index(True), len(rows) - 1 - rows[::-1].index(True)
    assert first <= 4 and len(rows) - 1 - last <= 6, (first, len(rows) - 1 - last)


def test_emblem_top_meets_wordmark_top(qapp) -> None:  # type: ignore[no-untyped-def]
    # The emblem moves up to the wordmark's top instead of centring
    # on the taller column of words and subtitle.
    _root, banner = themed_banner()
    emblem = banner.findChild(QSvgWidget)
    mark = banner.findChild(Wordmark)
    assert abs(emblem.geometry().top() - mark.geometry().top()) <= 1
    assert emblem.geometry().bottom() < banner.findChild(QLabel, "subtitle").geometry().bottom()
