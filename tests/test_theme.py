# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import re

import pytest
from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from project_reforged_linux.ui import assets, theme


def test_fonts_load(qapp) -> None:  # type: ignore[no-untyped-def]
    fonts = theme.load_fonts()
    assert (fonts.heading, fonts.decorative, fonts.text) == (
        "Cinzel", "Cinzel Decorative", "EB Garamond")


def test_stylesheet_has_no_holes(qapp) -> None:  # type: ignore[no-untyped-def]
    qss = theme.stylesheet(theme.load_fonts())
    assert "{" in qss and not re.search(r"\{[a-z_]+\}", qss)


def test_qt_parses_the_stylesheet(qapp) -> None:  # type: ignore[no-untyped-def]
    warnings: list[str] = []

    def collect(kind, context, message):  # type: ignore[no-untyped-def]
        if kind != QtMsgType.QtDebugMsg:
            warnings.append(message)

    previous = qInstallMessageHandler(collect)
    try:
        root = QWidget()
        root.setStyleSheet(theme.stylesheet(theme.load_fonts()))
        for child in (QPushButton("Run", root), QLabel("text", root)):
            child.ensurePolished()
        root.ensurePolished()
    finally:
        qInstallMessageHandler(previous)
    assert [w for w in warnings if "stylesheet" in w.lower()] == []


def test_sizes_come_from_one_base(qapp) -> None:  # type: ignore[no-untyped-def]
    small = theme.stylesheet(theme.load_fonts(), base_pt=10)
    large = theme.stylesheet(theme.load_fonts(), base_pt=20)
    assert "font-size: 10pt" in small and "font-size: 20pt" in large


def test_gold_icon_takes_the_colour(qapp) -> None:  # type: ignore[no-untyped-def]
    svg = assets.icon_svg("house", "#d6a23e")
    assert b"currentColor" not in svg and b"#d6a23e" in svg
    pixmap = assets.icon_pixmap("house", "#d6a23e", 24, 2.0)
    assert pixmap.width() == 48 and not pixmap.isNull()


def test_every_asset_is_packaged() -> None:
    for name in assets.UI_ICONS:
        assert (assets.ICONS_DIR / f"{name}.svg").is_file()
    for path in (assets.BACKGROUND, assets.CORNER, assets.FLEURON, assets.EMBLEM):
        assert path.is_file(), path


@pytest.mark.parametrize("name, colour", [
    ("house", "gold"), ("house", "#d6a23e\" onload=\"x"), ("house", "#d6a"), ("castle", "#d6a23e")])
def test_icon_svg_refuses_bad_input(name: str, colour: str) -> None:
    with pytest.raises(ValueError):
        assets.icon_svg(name, colour)


@pytest.mark.parametrize("size, ratio", [(0, 1.0), (-4, 1.0), (24, 0.0), (24, -2.0)])
def test_svg_pixmap_refuses_empty_sizes(qapp, size: int, ratio: float) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        assets.svg_pixmap(assets.icon_svg("house", "#d6a23e"), size, ratio)


def test_svg_pixmap_refuses_broken_svg(qapp) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        assets.svg_pixmap(b"<svg", 24, 1.0)


@pytest.mark.parametrize("base_pt", [0, -11])
def test_stylesheet_refuses_empty_base(qapp, base_pt: int) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        theme.stylesheet(theme.load_fonts(), base_pt=base_pt)


def test_packaged_svgs_load_without_qt_warnings(qapp) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtSvg import QSvgRenderer

    warnings: list[str] = []

    def collect(kind, context, message):  # type: ignore[no-untyped-def]
        if kind != QtMsgType.QtDebugMsg:
            warnings.append(message)

    paths = [assets.CORNER, assets.FLEURON, assets.EMBLEM,
             *(assets.ICONS_DIR / f"{name}.svg" for name in assets.UI_ICONS)]
    previous = qInstallMessageHandler(collect)
    try:
        for path in paths:
            assert QSvgRenderer(str(path)).isValid(), path
    finally:
        qInstallMessageHandler(previous)
    assert warnings == []


def test_apply_gives_children_the_text_font(qapp) -> None:  # type: ignore[no-untyped-def]
    # A stylesheet rule on #root does not reach the children's font family; the
    # widget's own QFont does, and the specific rules (buttons) still override it.
    from PySide6.QtGui import QFontInfo
    from PySide6.QtWidgets import QVBoxLayout

    fonts = theme.load_fonts()
    root = QWidget()
    root.setObjectName("root")
    theme.apply(root, fonts)
    layout = QVBoxLayout(root)
    label, button = QLabel("text"), QPushButton("Run")
    button.setObjectName("runGame")  # its own rule asks for the heading face
    layout.addWidget(label)
    layout.addWidget(button)
    for widget in (root, label, button):
        widget.ensurePolished()
    assert QFontInfo(label.font()).family() == fonts.text
    assert label.font().pointSize() == theme.BASE_PT
    assert QFontInfo(button.font()).family() == fonts.heading


def test_buttons_are_painted_not_styled(qapp) -> None:  # type: ignore[no-untyped-def]
    qss = theme.stylesheet(theme.load_fonts())
    for rule in qss.split("}"):
        if rule.strip().startswith(("QPushButton", "QFrame#panel")):
            assert "background" not in rule and "border" not in rule, rule


def test_run_game_wears_the_ornament_gold() -> None:
    # Stefan, 2026-11-16: the button in the same gold as the fleurons and the corner knots.
    assert (theme.GOLD_TOP, theme.GOLD_BOTTOM) == (theme.RAIL[1][0], theme.RAIL[2][0])
