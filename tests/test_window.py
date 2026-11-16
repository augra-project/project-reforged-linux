# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import math
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from project_reforged_linux import PART_NUMBER, RELEASE_DATE, __version__
from project_reforged_linux.prepare import Status
from project_reforged_linux.runtimes import Candidate, Checked, Source
from project_reforged_linux.ui.banner import Banner
from project_reforged_linux.ui.bezel import GOLD, LEATHER, BezelButton, Panel
from project_reforged_linux.ui.frame import CORNER_SIZE, FrameWidget
from project_reforged_linux.ui.widgets import State
from project_reforged_linux.ui.window import FOOTER, HOMEPAGE, REFORGED, TRADEMARK, MainWindow

CHECKED = Checked(Candidate(Source.SYSTEM, Path("/usr/bin/wine"), Path("/usr/bin/wineserver")),
                  (10, 0), "wine-10.0 (Debian 10.0~repack-6)", None)


@pytest.fixture
def window(qapp) -> MainWindow:  # type: ignore[no-untyped-def]
    opened: list[str] = []
    w = MainWindow(None, open_url=opened.append)
    w.opened = opened  # type: ignore[attr-defined]
    frame = w.findChild(FrameWidget)
    assert frame is not None
    frame.layout().activate()
    return w


def button(window: MainWindow, name: str) -> QPushButton:
    found = window.findChild(QPushButton, name)
    assert found is not None, name
    return found


def placed(window: MainWindow, widget: QWidget) -> QRect:
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


def test_fixed_size_and_title(window: MainWindow) -> None:
    assert (window.minimumSize(), window.maximumSize()) == (window.size(), window.size())
    assert (window.width(), window.height()) == (1024, 576)
    assert window.windowTitle() == f"Project Reforged Linux Launcher v{__version__}"


def test_texts(window: MainWindow) -> None:
    labels = [label.text() for label in window.findChildren(QLabel)]
    assert FOOTER in labels
    # Stefan, 2026-11-16: the version in the title bar, and in the corner the version with
    # the release's full part number.
    assert f"v{__version__} - {PART_NUMBER}-{RELEASE_DATE}" in labels
    welcome = window.findChild(QLabel, "welcome")
    assert welcome is not None and "Dan Whelan" in welcome.text()
    assert "Please do not pass it on bundled with either." in welcome.text()
    # The ZeniMax note waits for About (Plan 3b), kept word for word.
    assert "ZeniMax" not in welcome.text() and "ZeniMax Media Inc." in TRADEMARK


def test_links(window: MainWindow) -> None:
    button(window, "homepage").click()
    button(window, "reforged").click()
    assert window.opened == [HOMEPAGE, REFORGED]  # type: ignore[attr-defined]


def test_rows_follow_the_status(window: MainWindow) -> None:
    window.show_status(Status(True, "0.2.33", True, Path("/card/6r51"), None, CHECKED, None,
                              None))
    assert window.rows["game"].state is State.OK
    assert window.rows["game"].detail_text() == "v0.2.33"
    assert window.rows["files"].state is State.OK
    assert window.rows["runtime"].state is State.OK
    assert "Wine 10.0" in window.rows["runtime"].detail_text()


def test_rows_show_problems(window: MainWindow) -> None:
    window.show_status(Status(False, None, False, None, "no 6R51 folder in /x", None, None,
                              "No usable Wine"))
    assert window.rows["game"].state is State.ERROR
    assert window.rows["files"].state is State.ERROR
    assert window.rows["files"].toolTip() == "no 6R51 folder in /x"
    assert window.rows["runtime"].state is State.ERROR


def test_without_a_controller_nothing_can_start(window: MainWindow) -> None:
    window.show_status(Status(True, "0.2.33", True, Path("/card/6r51"), None, CHECKED, None,
                              None))
    for name in ("runGame", "install"):
        assert not button(window, name).isEnabled()
    choose = window.rows["files"].button
    assert choose is not None and not choose.isEnabled()


def test_dialog_buttons_wait_for_plan_3b(window: MainWindow) -> None:
    assert not button(window, "options").isEnabled()
    assert not button(window, "about").isEnabled()


def test_every_button_is_a_bezel_button(window: MainWindow) -> None:
    # RUN GAME and the rest are one class, painted differently (Stefan, 2026-11-15).
    run = button(window, "runGame")
    assert isinstance(run, BezelButton) and run.bezel is GOLD
    for name in ("homepage", "reforged", "options", "about", "quit", "install"):
        other = button(window, name)
        assert isinstance(other, BezelButton) and other.bezel is LEATHER, name


def test_the_two_boxes_are_equally_wide(window: MainWindow) -> None:
    panels = window.findChildren(Panel)
    assert len(panels) == 2
    left, right = sorted(panels, key=lambda p: placed(window, p).left())
    assert abs(left.width() - right.width()) <= 1, (left.width(), right.width())


def test_footer_sits_in_the_welcome_box(window: MainWindow) -> None:
    welcome = window.findChild(QLabel, "welcome")
    assert welcome is not None
    footers = window.findChildren(QLabel, "footer")
    assert [f.text() for f in footers] == [FOOTER]
    assert all(f.parent() is welcome.parent() for f in footers)


def test_progress_line_is_the_bottom_row_clear_of_the_corners(window: MainWindow) -> None:
    line = placed(window, window.progress_line)
    assert line.width() > window.width() * 0.75
    assert line.top() > placed(window, button(window, "quit")).bottom()
    size = math.ceil(CORNER_SIZE)
    for corner in (QRect(0, window.height() - size, size, size),
                   QRect(window.width() - size, window.height() - size, size, size)):
        assert not line.intersects(corner), (line, corner)
    assert window.progress_line.fraction == 0.0 and window.progress_line.text() == ""


def test_the_progress_line_has_room_above_it(window: MainWindow) -> None:
    # Stefan, 2026-11-16: everything a bit up except the progress line, so the line stands
    # apart from the rest; it keeps its place at the bottom.
    banner = window.findChild(Banner)
    assert banner is not None
    above_banner = placed(window, banner).top()
    line = placed(window, window.progress_line)
    below_line = window.height() - (line.bottom() + 1)
    run, quit_ = placed(window, window.run_button), placed(window, button(window, "quit"))
    between_rows = quit_.top() - run.bottom()
    above_line = line.top() - quit_.bottom()
    assert above_banner < below_line, (above_banner, below_line)
    assert above_line >= 2 * between_rows, (above_line, between_rows)


def test_the_welcome_box_holds_all_its_text(window: MainWindow) -> None:
    # The first build cut the welcome text off under the copyright lines; a label that
    # exists is not a label that can be read.
    welcome = window.findChild(QLabel, "welcome")
    assert welcome is not None
    box = welcome.parentWidget()
    margins = box.layout().contentsMargins()
    inside_w = box.width() - margins.left() - margins.right()
    inside_h = box.height() - margins.top() - margins.bottom()
    footers = window.findChildren(QLabel, "footer")
    needed = (welcome.heightForWidth(inside_w)
              + sum(f.sizeHint().height() + box.layout().spacing() for f in footers))
    assert needed <= inside_h, (needed, inside_h)


def test_fleurons_grow_out_of_run_game(window: MainWindow) -> None:
    # Stefan, 2026-11-16: no gap; the ornaments sit right at the button's frame.
    from project_reforged_linux.ui.widgets import Fleuron

    run = placed(window, window.run_button)
    left, right = sorted((placed(window, f) for f in window.findChildren(Fleuron)),
                         key=lambda r: r.left())
    assert left.right() + 1 == run.left(), (left, run)
    assert right.left() == run.right() + 1, (right, run)


def test_a_fixed_window_offers_no_maximize(window: MainWindow) -> None:
    from PySide6.QtCore import Qt

    flags = window.windowFlags()
    assert not flags & Qt.WindowType.WindowMaximizeButtonHint
    assert flags & Qt.WindowType.WindowMinimizeButtonHint
    assert flags & Qt.WindowType.WindowCloseButtonHint


def test_welcome_heading_and_copyright_are_centred(window: MainWindow) -> None:
    # Stefan, 2026-11-16: both centred, and the copyright names the PR Linux Launcher.
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextDocument

    welcome = window.findChild(QLabel, "welcome")
    assert welcome is not None
    doc = QTextDocument()
    doc.setHtml(welcome.text())
    first = doc.firstBlock()
    assert first.text() == "Welcome to Project Reforged"
    assert first.blockFormat().alignment() & Qt.AlignmentFlag.AlignHCenter
    assert not first.next().blockFormat().alignment() & Qt.AlignmentFlag.AlignHCenter
    footer = window.findChild(QLabel, "footer")
    assert footer is not None and footer.text().startswith("PR Linux Launcher (c) 2026")
    assert footer.alignment() & Qt.AlignmentFlag.AlignHCenter
    box = footer.parentWidget()
    margins = box.layout().contentsMargins()
    assert footer.sizeHint().width() <= box.width() - margins.left() - margins.right()


def test_rows_check_first_then_tick_or_cross(window: MainWindow) -> None:
    window.show_status(None)
    assert all(row.state is State.CHECKING for row in window.rows.values())
    window.show_status(Status(True, None, False, None, None, CHECKED, None, None))
    assert window.rows["game"].state is State.OK  # installed, not started yet
    assert window.rows["files"].state is State.ERROR  # nothing chosen yet
    assert window.rows["runtime"].state is State.OK


def test_options_about_quit_sit_centred_under_run_game(window: MainWindow) -> None:
    # Stefan, 2026-11-16: the version in the corner must not pull the three buttons aside.
    run = placed(window, window.run_button)
    left, right = placed(window, button(window, "options")), placed(window, button(window, "quit"))
    group_centre = (left.left() + right.right()) / 2
    assert abs(group_centre - (run.left() + run.right()) / 2) <= 1, (group_centre, run)
    assert abs((run.left() + run.right()) / 2 - (window.width() - 1) / 2) <= 1, run


def test_side_buttons_are_equally_wide_and_wider(window: MainWindow) -> None:
    # Stefan, 2026-11-16: Launcher Homepage and Project Reforged wider, as in the mockup.
    home, reforged = button(window, "homepage"), button(window, "reforged")
    assert home.width() == reforged.width() >= home.sizeHint().width() + 40


def test_buttons_are_thick_and_set_like_the_mockup(window: MainWindow) -> None:
    # Stefan, 2026-11-16: thicker buttons, mixed case in the text serif, not Cinzel capitals;
    # RUN GAME keeps the heading face.
    from PySide6.QtGui import QFont, QFontInfo

    from project_reforged_linux.ui import theme

    fonts = theme.load_fonts()
    for name in ("homepage", "reforged", "options", "about", "quit", "install"):
        b = button(window, name)
        b.ensurePolished()
        assert QFontInfo(b.font()).family() == fonts.text, name
        assert b.font().weight() >= QFont.Weight.DemiBold, name
        assert b.height() >= 40 and b.bezel.thickness >= 5, name
    run = button(window, "runGame")
    run.ensurePolished()
    assert QFontInfo(run.font()).family() == fonts.heading
    choose = window.rows["files"].button
    assert choose is not None
    choose.ensurePolished()
    assert choose.fontMetrics().height() <= choose.height() - 2 * choose.bezel.thickness


def test_the_window_wears_the_emblem(window: MainWindow) -> None:
    # Stefan, 2026-11-16: the title bar shows the gold emblem, not the WM's placeholder.
    assert not window.windowIcon().isNull()


def test_version_sits_on_the_welcome_box(window: MainWindow) -> None:
    # Stefan, 2026-11-16: just above the welcome box, its right edge on the box's.
    labels = [label for label in window.findChildren(QLabel, "version") if not label.isHidden()]
    assert len(labels) == 1
    version = placed(window, labels[0])
    welcome = window.findChild(QLabel, "welcome")
    assert welcome is not None
    box = placed(window, welcome.parentWidget())
    assert version.right() == box.right(), (version, box)
    assert 2 <= box.top() - version.bottom() - 1 <= 6, (version, box)
