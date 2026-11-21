# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import math
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

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
    # The corner carries the release's full part number.
    assert f"v{__version__} - {PART_NUMBER}-{RELEASE_DATE}" in labels
    welcome = window.findChild(QLabel, "welcome")
    assert welcome is not None and "Dan Whelan" in welcome.text()
    assert "Please do not pass it on bundled with either." in welcome.text()
    # The ZeniMax note waits for About, kept word for word.
    assert "ZeniMax" not in welcome.text() and "ZeniMax Media Inc." in TRADEMARK


def test_links(window: MainWindow) -> None:
    button(window, "homepage").click()
    button(window, "reforged").click()
    assert window.opened == [HOMEPAGE, REFORGED]  # type: ignore[attr-defined]


def test_rows_follow_the_status(window: MainWindow) -> None:
    window.show_status(Status(True, "0.2.33", True, Path("/card/6r51"), None, CHECKED, None,
                              None))
    assert window.rows["game"].state is State.OK
    assert window.rows["game"].detail_text() == "Windows build v0.2.33"
    assert window.rows["files"].state is State.OK
    assert window.rows["files"].detail_text() == "/card/6r51"
    assert window.rows["files"].toolTip() == "/card/6r51"
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
    assert not button(window, "locate").isEnabled()


def test_options_needs_a_controller_about_does_not(window: MainWindow) -> None:
    assert not button(window, "options").isEnabled()
    assert button(window, "about").isEnabled()


def test_every_button_is_a_bezel_button(window: MainWindow) -> None:
    # RUN GAME and the rest are one class, painted differently.
    run = button(window, "runGame")
    assert isinstance(run, BezelButton) and run.bezel is GOLD
    for name in ("homepage", "reforged", "options", "about", "quit", "install", "locate"):
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
    # Everything a bit up except the progress line, so the line stands
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
    # No gap; the ornaments sit right at the button's frame.
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
    # Both centred; the copyright names the PR Linux Launcher.
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
    # The version in the corner must not pull the three buttons aside.
    run = placed(window, window.run_button)
    left, right = placed(window, button(window, "options")), placed(window, button(window, "quit"))
    group_centre = (left.left() + right.right()) / 2
    assert abs(group_centre - (run.left() + run.right()) / 2) <= 1, (group_centre, run)
    assert abs((run.left() + run.right()) / 2 - (window.width() - 1) / 2) <= 1, run


def test_side_buttons_are_equally_wide_and_wider(window: MainWindow) -> None:
    # Launcher Homepage and Project Reforged wider, as in the mockup.
    home, reforged = button(window, "homepage"), button(window, "reforged")
    assert home.width() == reforged.width() >= home.sizeHint().width() + 40


def test_buttons_are_thick_and_set_like_the_mockup(window: MainWindow) -> None:
    # Thicker buttons, mixed case in the text serif, not Cinzel capitals;
    # RUN GAME keeps the heading face.
    from PySide6.QtGui import QFont, QFontInfo

    from project_reforged_linux.ui import theme

    fonts = theme.load_fonts()
    for name in ("homepage", "reforged", "options", "about", "quit", "install", "locate"):
        b = button(window, name)
        b.ensurePolished()
        assert QFontInfo(b.font()).family() == fonts.text, name
        assert b.font().weight() >= QFont.Weight.DemiBold, name
        assert b.height() >= 40 and b.bezel.thickness >= 5, name
    run = button(window, "runGame")
    run.ensurePolished()
    assert QFontInfo(run.font()).family() == fonts.heading


def test_the_window_wears_the_emblem(window: MainWindow) -> None:
    # The title bar shows the gold emblem, not the WM's placeholder.
    assert not window.windowIcon().isNull()


def test_version_sits_under_launcher_homepage(window: MainWindow) -> None:
    # Below the button, flush with its left edge.
    labels = [label for label in window.findChildren(QLabel, "version") if not label.isHidden()]
    assert len(labels) == 1
    version = placed(window, labels[0])
    home = placed(window, button(window, "homepage"))
    assert version.left() == home.left(), (version, home)
    assert 2 <= version.top() - home.bottom() - 1 <= 6, (version, home)


def test_update_and_locate_sit_side_by_side_centred(window: MainWindow) -> None:
    # Locate sits beside Update Reforged, not in the files row.
    assert window.rows["files"].button is None
    # The buttons sit in a layout inside the box, which Qt lays out when it is shown.
    window.show()
    QApplication.processEvents()
    update = placed(window, button(window, "install"))
    locate = placed(window, button(window, "locate"))
    assert update.top() == locate.top() and update.right() < locate.left()
    box = placed(window, window.rows["game"].parentWidget())
    pair = (update.left() + locate.right()) / 2
    assert abs(pair - (box.left() + box.right()) / 2) <= 1, (pair, box)


@pytest.mark.parametrize(("chosen", "shown"), [
    (Path.home() / "games" / "ngage-files" / "system" / "apps" / "6r51", "~/games/ngage-files"),
    (Path.home() / "games" / "card" / "System" / "Apps" / "6R51", "~/games/card"),
    (Path("/media/card/system/apps/6r51"), "/media/card"),
    (Path("/srv/elsewhere/6r51"), "/srv/elsewhere/6r51"),
])
def test_files_row_names_the_card_folder(window: MainWindow, chosen: Path, shown: str) -> None:
    window.show_status(Status(True, "0.2.33", True, chosen, None, CHECKED, None, None))
    assert window.rows["files"].detail_text() == shown
    assert window.rows["files"].toolTip() == str(chosen)


def test_the_window_itself_carries_no_stylesheet(window: MainWindow) -> None:
    # Any stylesheet above a dialog keeps its palette and font from its children; the look
    # sits on the frame.
    frame = window.findChild(FrameWidget)
    assert window.styleSheet() == "" and frame is not None and frame.styleSheet() != ""


def test_version_is_as_big_as_the_text(window: MainWindow) -> None:
    # Better readable; no smaller than the window's body text.
    from project_reforged_linux.ui import theme

    window.version.ensurePolished()
    assert window.version.font().pointSize() >= theme.BASE_PT


def test_welcome_text_is_a_bit_bigger(window: MainWindow) -> None:
    # The welcome text a bit bigger than its 1.05 of the base; the copyright
    # line stays as it is.
    from project_reforged_linux.ui import theme

    welcome = window.findChild(QLabel, "welcome")
    footer = window.findChild(QLabel, "footer")
    for label in (welcome, footer):
        assert label is not None
        label.ensurePolished()
    assert welcome.font().pointSize() > round(theme.BASE_PT * 1.05)
    assert footer.font().pointSize() == round(theme.BASE_PT * 0.9)


def test_status_rows_are_set_heavier_and_taller(window: MainWindow) -> None:
    # The rows' font heavier and taller, as in mockup v3, where the text
    # fills about a third of the row pitch (ours filled 0.29).
    from PySide6.QtGui import QFont

    from project_reforged_linux.ui import theme

    for row in window.rows.values():
        title = row.findChild(QLabel, "statusText")
        assert title is not None
        title.ensurePolished()
        assert title.font().weight() >= QFont.Weight.Medium
        assert title.font().pointSize() >= round(theme.BASE_PT * 1.4)


def test_version_reads_over_the_picture(window: MainWindow) -> None:
    # The dim text was lost against the lit tower.
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    from project_reforged_linux.ui import theme

    window.version.ensurePolished()
    colour = window.version.palette().color(window.version.foregroundRole())
    assert colour == QColor(theme.TEXT)
    assert isinstance(window.version.graphicsEffect(), QGraphicsDropShadowEffect)


def test_the_line_follows_the_controller(qapp, xdg_home: Path) -> None:  # type: ignore[no-untyped-def]
    # A known end shows "40%", a busy step its words, a note stands still.
    from project_reforged_linux.paths import ensure_dirs, resolve
    from project_reforged_linux.runtimes import Resolved
    from project_reforged_linux.ui.controller import LauncherController

    paths = resolve()
    ensure_dirs(paths)
    c = LauncherController(paths, resolve=lambda settings: Resolved(CHECKED),
                           status=lambda *a: None, synchronous=True)
    w = MainWindow(c)
    line = w.progress_line
    c.progress.emit(0.4, "Downloading Project Reforged")
    assert line.text() == "40%" and line.fraction == pytest.approx(0.4)
    c.progress.emit(None, "Installing Project Reforged")
    assert line.text() == "Installing Project Reforged" and line.fraction is None
    c.note.emit("Art ready: 805 pictures")
    assert line.text() == "Art ready: 805 pictures" and line.fraction == 0.0


@pytest.mark.parametrize("player, factor", [
    (None, "1.125"), ("", "1.125"), ("2", "2.25"), ("1.5", "1.6875"), ("abc", "1.125"),
    ("0", "1.125"), ("-1", "1.125"), ("nan", "1.125"), ("inf", "1.125")])
def test_the_ui_scale_multiplies_the_players_own(player: str | None, factor: str) -> None:
    # Everything 12.5 % larger.
    from project_reforged_linux.ui.window import UI_SCALE, ui_scale_factor

    assert UI_SCALE == 1.125
    assert ui_scale_factor(player) == factor


def test_an_existing_application_keeps_the_environment(qapp, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from project_reforged_linux.ui import window as window_module

    monkeypatch.setenv("QT_SCALE_FACTOR", "2")
    assert window_module._scaled_application() is qapp
    import os

    assert os.environ["QT_SCALE_FACTOR"] == "2"


def test_update_tip_names_wine_only_for_the_windows_build() -> None:
    from project_reforged_linux.builds import Build
    from project_reforged_linux.ui.window import update_tip

    assert "Wine" in update_tip(Build.WINDOWS)
    for build in (Build.LINUX_TARBALL, Build.LINUX_APPIMAGE):
        assert "Wine" not in update_tip(build)


def test_the_window_opens_links_only_through_the_checked_gate(qapp, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from project_reforged_linux.ui import links

    reached: list[object] = []
    monkeypatch.setattr(links.QDesktopServices, "openUrl", lambda url: reached.append(url))
    window = MainWindow(None)
    with pytest.raises(ValueError):
        window._open("file:///etc/passwd")
    assert reached == []
