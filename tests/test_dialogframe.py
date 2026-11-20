# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox
from qtcheck import check_night

from project_reforged_linux.ui import dialogs, theme
from project_reforged_linux.ui.assets import BACKGROUND
from project_reforged_linux.ui.bezel import SMALL, BezelButton
from project_reforged_linux.ui.dialogframe import (
    ACROSS,
    BUTTON_WIDTH,
    DOWN,
    SIZE,
    TOWER,
    TOWER_RIGHT,
    Backdrop,
    Cut,
    DialogHeader,
    Shade,
    ThemedDialog,
    button_row,
)


@pytest.fixture
def fonts(qapp) -> theme.Fonts:  # type: ignore[no-untyped-def]
    return theme.load_fonts()


@pytest.fixture
def dialog(fonts: theme.Fonts) -> ThemedDialog:
    d = ThemedDialog(fonts, "Launcher Options")
    d.show()
    QApplication.processEvents()
    yield d
    d.close()


@pytest.mark.parametrize("cut, shade", [(TOWER, DOWN), (TOWER_RIGHT, ACROSS)])
def test_the_wordmark_sits_on_the_dialogs_axis(fonts: theme.Fonts, cut: Cut, shade: Shade) -> None:
    # Measured without the emblem, which hangs off its left side.
    d = ThemedDialog(fonts, "About the Linux Launcher", cut=cut, shade=shade)
    d.show()
    QApplication.processEvents()
    mark = d.header.mark
    left = mark.mapTo(d, mark.rect().topLeft()).x()
    assert abs(left + mark.width() / 2 - d.width() / 2) <= 1
    title = d.header.title
    title_left = title.mapTo(d, title.rect().topLeft()).x()
    assert abs(title_left + title.width() / 2 - d.width() / 2) <= 1
    d.close()


def test_the_dialog_has_its_fixed_size_and_title(dialog: ThemedDialog) -> None:
    assert dialog.size() == SIZE == QSize(800, 520)
    assert dialog.minimumSize() == dialog.maximumSize() == SIZE
    assert dialog.isModal()
    assert dialog.windowTitle() == "Launcher Options"
    assert dialog.header.title.text() == "Launcher Options"
    assert dialog.backdrop.geometry() == dialog.rect()


def test_the_stylesheet_sits_on_the_backdrop_not_the_dialog(dialog: ThemedDialog) -> None:
    assert dialog.styleSheet() == ""
    assert dialog.backdrop.styleSheet() == (theme.stylesheet(dialog.fonts)
                                            + theme.dialog_stylesheet())


def test_a_message_box_from_the_dialog_keeps_its_own_palette(dialog: ThemedDialog) -> None:
    # A stylesheet above a QMessageBox bleaches it.
    box = dialogs.message_box(dialog, dialog.fonts, QMessageBox.Icon.Warning, "T",
                              "The Windows build needs a runtime first.")
    check_night(box, dialog.fonts)


def test_the_title_wears_the_dialog_title_rule(dialog: ThemedDialog) -> None:
    title = dialog.header.title
    assert title.objectName() == "dialogTitle"
    assert title.font().pointSize() == round(theme.BASE_PT * 1.36)
    assert title.palette().color(title.foregroundRole()).name() == theme.GOLD_HI


def test_a_header_needs_a_title(fonts: theme.Fonts) -> None:
    with pytest.raises(ValueError):
        DialogHeader(fonts, "  ")


def picture(width: int = 2560, height: int = 1440, colour: str = "#ffffff") -> QPixmap:
    p = QPixmap(width, height)
    p.fill(QColor(colour))
    return p


def test_a_cut_keeps_the_dialogs_proportions(qapp) -> None:  # type: ignore[no-untyped-def]
    cut = TOWER.of(picture(), SIZE)
    assert (cut.width(), cut.height()) == (1280, 832)
    assert abs(cut.width() / cut.height() - SIZE.width() / SIZE.height()) < 0.01


@pytest.mark.parametrize("left, top, width", [
    (-0.1, 0, 0.5), (0, -0.1, 0.5), (0, 0, 0), (0.6, 0, 0.5), (0, 0, 1.01)])
def test_a_cut_outside_the_picture_is_refused(left: float, top: float, width: float) -> None:
    with pytest.raises(ValueError):
        Cut(left, top, width)


def test_a_cut_running_below_the_picture_is_refused(qapp) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        Cut(0, 0.5, 0.5).of(picture(), SIZE)
    with pytest.raises(ValueError):
        TOWER.of(QPixmap(), SIZE)
    with pytest.raises(ValueError):
        TOWER.of(picture(), QSize(0, 520))


@pytest.mark.parametrize("stops", [(), ((1.5, 10),), ((0.5, 256),), ((-0.1, 0),)])
def test_a_shade_refuses_stops_out_of_range(stops: tuple[tuple[float, int], ...]) -> None:
    with pytest.raises(ValueError):
        Shade(vertical=True, stops=stops)


def brightness(p: QPixmap, x: int, y: int) -> int:
    return QColor(p.toImage().pixel(x, y)).value()


def test_down_darkens_toward_the_bottom(qapp) -> None:  # type: ignore[no-untyped-def]
    shaded = DOWN.over(picture(800, 520))
    top, middle, bottom = (brightness(shaded, 400, y) for y in (0, 260, 519))
    assert 255 > top > middle > bottom
    # The last stop, 158 of 255 of the night over white; its blue (18) is the brightest part.
    alpha = 158 / 255
    assert abs(bottom - round(255 * (1 - alpha) + 18 * alpha)) <= 1


def test_across_leaves_the_tower_side_lit(qapp) -> None:  # type: ignore[no-untyped-def]
    shaded = ACROSS.over(picture(800, 520))
    assert brightness(shaded, 10, 260) < brightness(shaded, 400, 260) < 255
    assert brightness(shaded, 700, 260) == 255


def test_the_backdrop_shows_the_shaded_cut(qapp) -> None:  # type: ignore[no-untyped-def]
    backdrop = Backdrop(TOWER, DOWN)
    assert (backdrop._background.width(), backdrop._background.height()) == (1280, 832)
    raw = TOWER.of(QPixmap(str(BACKGROUND)), SIZE)

    def mean(pixmap: QPixmap) -> float:
        points = [(x, y) for x in range(0, 1280, 64) for y in range(0, 832, 64)]
        return sum(brightness(pixmap, x, y) for x, y in points) / len(points)

    assert mean(backdrop._background) < 0.8 * mean(raw)
    assert backdrop.objectName() == "root"


def test_the_button_row_centres_its_buttons(qapp) -> None:  # type: ignore[no-untyped-def]
    ok, cancel = BezelButton("OK", style=SMALL), BezelButton("Cancel", style=SMALL)
    row = button_row(ok, cancel)
    assert row.count() == 4
    assert row.itemAt(0).spacerItem() is not None and row.itemAt(3).spacerItem() is not None
    assert ok.minimumWidth() == cancel.minimumWidth() == BUTTON_WIDTH
    with pytest.raises(ValueError):
        button_row()


def test_the_bottom_guardians_stay_at_full_light(dialog: ThemedDialog) -> None:
    # The shade is baked into the picture, under the rail and the guardians: the bottom
    # corner's brightest gold is as bright as in an unshaded frame.
    shaded = dialog.backdrop.grab().toImage()
    plain = Backdrop(TOWER, Shade(vertical=True, stops=((0.0, 0),)))
    plain.resize(SIZE)
    unshaded = plain.grab().toImage()

    def brightest(image) -> int:  # type: ignore[no-untyped-def]
        ratio = image.devicePixelRatio()
        return max(QColor(image.pixel(round(x * ratio), round(y * ratio))).value()
                   for x in range(0, 60) for y in range(SIZE.height() - 60, SIZE.height()))

    assert brightest(shaded) == brightest(unshaded)
