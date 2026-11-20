# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The launcher's main window."""

from __future__ import annotations

import html
import logging
import math
import os
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import PySide6
from PySide6.QtCore import QSize, Qt, QTimer, qVersion
from PySide6.QtGui import QCloseEvent, QColor, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from project_reforged_linux import (
    APP_ID,
    APP_NAME,
    GAME_NAME,
    LAUNCHER_NAME,
    PART_NUMBER,
    RELEASE_DATE,
    __version__,
)
from project_reforged_linux.builds import Build
from project_reforged_linux.desktop import ICON_SIZES, ICONS_SOURCE
from project_reforged_linux.gamefiles import find_6r51
from project_reforged_linux.logsetup import home_as_tilde
from project_reforged_linux.paths import AppPaths, ensure_dirs, native_data_dir, resolve
from project_reforged_linux.prepare import Status
from project_reforged_linux.settings import LauncherSettings
from project_reforged_linux.ui import dialogs, firststart, theme
from project_reforged_linux.ui.about import AboutDialog
from project_reforged_linux.ui.assets import EMBLEM
from project_reforged_linux.ui.banner import Banner
from project_reforged_linux.ui.bezel import GOLD, LEATHER, BezelButton, BezelStyle, Panel
from project_reforged_linux.ui.firststart import FirstStart, FirstStartDialog, IconChoice
from project_reforged_linux.ui.frame import CORNER_SIZE, FrameWidget
from project_reforged_linux.ui.links import GAME_HOME, LAUNCHER_HOME, open_in_browser
from project_reforged_linux.ui.options import BUILD_NAMES, OptionsDialog
from project_reforged_linux.ui.progress import ProgressLine
from project_reforged_linux.ui.widgets import Fleuron, State, StatusRow

if TYPE_CHECKING:
    from project_reforged_linux.ui.controller import LauncherController

__all__ = ["FOOTER", "HOMEPAGE", "REFORGED", "TITLE", "TRADEMARK", "UI_SCALE", "MainWindow",
           "prepare_application", "run_window", "switch_notice", "ui_scale_factor"]

logger = logging.getLogger(__name__)

TITLE = LAUNCHER_NAME
LOCATE_TITLE = "Locate the original game files"
OPTIONS_TITLE = "Launcher Options"
LOCATE_TIP = "Choose the zip with your N-Gage game files, or the card's folder."
CLOSING_TEXT = "Closing as soon as the running step has stopped"
SIZE = QSize(1024, 576)
HOMEPAGE = LAUNCHER_HOME
REFORGED = GAME_HOME
# One centred line in the welcome box: the full names did not fit its
# width, so the launcher is "PR Linux Launcher"; "free fan port" stands above it already.
FOOTER = f"PR Linux Launcher (c) 2026 The Augra Project - {GAME_NAME} (c) 2026 Dan Whelan"
TRADEMARK = ("The Elder Scrolls Travels: Shadowkey belongs to ZeniMax Media Inc. and Bethesda "
             "Softworks LLC. This launcher is not affiliated with them.")
_P = "<p style='margin:0 0 4px 0'>"
WELCOME = (
    "<p align='center' style='margin:0 0 4px 0; "
    "font-family:\"{heading}\"; font-size:{title}pt; color:{gold}'>"
    "Welcome to " + GAME_NAME + "</p>"
    f"{_P}This is the Linux launcher for Dan Whelan's free fan port of "
    "<i>The Elder Scrolls Travels: Shadowkey</i>.</p>"
    f"{_P}The launcher contains neither the game nor the port. It downloads the port from "
    "Dan Whelan's site and uses your own copy of the game files. Please do not pass it on "
    "bundled with either.</p>")
# Everything sits a bit high, so the progress line at the bottom stands apart.
SIDE, TOP, BOTTOM = 28, 18, 20
PROGRESS_GAP = 10  # extra room above the progress line, on top of the layout spacing
SIDE_EXTRA = 48  # Launcher Homepage and Project Reforged wider than their text
VERSION_GAP = 3  # between the Launcher Homepage button and the version below it
# The progress line runs along the bottom between the corner ornaments.
PROGRESS_INSET = math.ceil(CORNER_SIZE) + 4 - SIDE


def update_tip(build: Build) -> str:
    if build is Build.WINDOWS:
        return "Fetches his newest build when there is one, and sets up Wine to run it."
    return "Fetches his newest build when there is one."


def _button(text: str, name: str, icon: str | None = None,
            style: BezelStyle = LEATHER) -> BezelButton:
    button = BezelButton(text, style=style, icon=icon)
    button.setObjectName(name)
    return button


class MainWindow(QWidget):
    def __init__(self, controller: LauncherController | None = None, *,
                 open_url: Callable[[str], object] = open_in_browser,
                 choose_folder: Callable[[QWidget], str] | None = None,
                 ask_options: Callable[[MainWindow], LauncherSettings | None] | None = None,
                 show_about: Callable[[MainWindow], object] | None = None,
                 ask_first_start: Callable[[MainWindow, bool], FirstStart] | None = None,
                 ask_icon: Callable[[MainWindow], IconChoice] | None = None,
                 fonts: theme.Fonts | None = None) -> None:
        super().__init__()
        self.controller = controller
        self._open_url = open_url
        self._cursor_pushed = False
        self._close_requested = False
        self.fonts = fonts = fonts or theme.load_fonts()
        self._choose_folder = choose_folder or _choose_game_files
        self._ask_options = ask_options or _options_dialog
        self._show_about = show_about or _about_dialog
        self._ask_first_start = ask_first_start or _first_start_dialog
        self._ask_icon = ask_icon or (lambda window: firststart.ask_icon(window, window.fonts))
        self.setWindowTitle(f"{TITLE} v{__version__}")
        self.setFixedSize(SIZE)
        # A fixed window offers no maximize; the WM honours the buttons only when all are named.
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.CustomizeWindowHint
                            | Qt.WindowType.WindowTitleHint
                            | Qt.WindowType.WindowSystemMenuHint
                            | Qt.WindowType.WindowMinimizeButtonHint
                            | Qt.WindowType.WindowCloseButtonHint)
        self.setWindowIcon(QIcon(str(EMBLEM)))

        frame = FrameWidget(self)
        frame.setGeometry(0, 0, SIZE.width(), SIZE.height())
        # On the picture, not the window, so the dialogs the window parents stay out of it.
        theme.apply(frame, fonts)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(SIDE, TOP, SIDE, BOTTOM)
        layout.setSpacing(8)
        layout.addWidget(Banner(fonts), 0)

        status_panel = Panel()
        self.rows = {
            "game": StatusRow(GAME_NAME),
            "files": StatusRow("Original game files"),
            "runtime": StatusRow("Windows Runtime"),
        }
        for row in self.rows.values():
            status_panel.box.addWidget(row)
        self.install_button = _button("Update Reforged", "install")
        self.locate_button = _button("Locate Original...", "locate")
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.install_button)
        actions.addWidget(self.locate_button)
        actions.addStretch(1)
        status_panel.box.addLayout(actions)

        welcome_panel = Panel()
        welcome = QLabel(WELCOME.format(heading=fonts.heading, gold=theme.GOLD_HI,
                                        title=round(theme.BASE_PT * 1.5)))
        welcome.setObjectName("welcome")
        welcome.setWordWrap(True)
        welcome.setTextFormat(Qt.TextFormat.RichText)
        welcome_panel.box.addWidget(welcome)
        welcome_panel.box.addStretch(1)
        footer = QLabel(FOOTER)
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        welcome_panel.box.addWidget(footer)

        # Equally wide: only the stretch decides, not what each box would like.
        panels = QHBoxLayout()
        for panel in (status_panel, welcome_panel):
            panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            panels.addWidget(panel, 1)
        layout.addLayout(panels, 1)

        self.run_button = _button("RUN GAME", "runGame", style=GOLD)
        run_row = QHBoxLayout()
        home = _button("Launcher Homepage", "homepage", "house")
        reforged = _button(GAME_NAME, "reforged", "key-round")
        run_row.addWidget(home)
        run_row.addStretch(1)
        # The fleurons grow out of the button's frame, no gap.
        winged = QHBoxLayout()
        winged.setSpacing(0)
        winged.addWidget(Fleuron(points=Qt.Edge.LeftEdge), 0, Qt.AlignmentFlag.AlignVCenter)
        winged.addWidget(self.run_button)
        winged.addWidget(Fleuron(points=Qt.Edge.RightEdge), 0, Qt.AlignmentFlag.AlignVCenter)
        run_row.addLayout(winged)
        run_row.addStretch(1)
        run_row.addWidget(reforged)
        layout.addLayout(run_row)
        # Equally wide, so RUN GAME sits in the middle; measured once the buttons are in the
        # window and carry the stylesheet's font.
        for side in (home, reforged):
            side.ensurePolished()
        side_width = max(home.sizeHint().width(), reforged.sizeHint().width()) + SIDE_EXTRA
        home.setFixedWidth(side_width)
        reforged.setFixedWidth(side_width)

        small_row = QHBoxLayout()
        small_row.addStretch(1)
        for text, name, icon in (("Options", "options", "settings"),
                                 ("About", "about", "info"), ("Quit", "quit", "power")):
            small_row.addWidget(_button(text, name, icon))
        small_row.addStretch(1)
        layout.addLayout(small_row)

        # Below Launcher Homepage, flush with its left edge. The window has a fixed size, so the
        # layout is settled once and the label placed on it.
        self.version = QLabel(f"v{__version__} - {PART_NUMBER}-{RELEASE_DATE}", frame)
        self.version.setObjectName("version")
        # Light text with a dark shadow reads over the lit tower too.
        shadow = QGraphicsDropShadowEffect(self.version)
        shadow.setBlurRadius(6)
        shadow.setOffset(0, 1)
        shadow.setColor(QColor(0, 0, 0, 230))
        self.version.setGraphicsEffect(shadow)
        self.version.ensurePolished()
        self.version.adjustSize()

        layout.addSpacing(PROGRESS_GAP)
        self.progress_line = ProgressLine()
        progress_row = QHBoxLayout()
        progress_row.addSpacing(PROGRESS_INSET)
        progress_row.addWidget(self.progress_line)
        progress_row.addSpacing(PROGRESS_INSET)
        layout.addLayout(progress_row)
        # Only once every row is in: the progress row moves the buttons up.
        layout.activate()
        under = home.geometry()
        self.version.move(under.left(), under.bottom() + 1 + VERSION_GAP)

        self._wire()
        self.show_status(None)

    def _find(self, name: str) -> QPushButton:
        found = self.findChild(QPushButton, name)
        if found is None:
            raise LookupError(name)
        return found

    def _wire(self) -> None:
        # Bound methods, not lambdas over self: a lambda keeps the window for Python's cycle
        # collector, and PySide 6.11 crashed collecting such widget graphs.
        self._find("homepage").clicked.connect(self._open_homepage)
        self._find("reforged").clicked.connect(self._open_reforged)
        self._find("homepage").setToolTip(HOMEPAGE)
        self._find("reforged").setToolTip(REFORGED)
        self.install_button.setToolTip(update_tip(Build.WINDOWS))
        self.locate_button.setToolTip(LOCATE_TIP)
        self._find("quit").clicked.connect(self.close)
        self._find("about").clicked.connect(self._about)
        self._find("options").setEnabled(self.controller is not None)
        self._find("options").clicked.connect(self._options)
        self.locate_button.setEnabled(self.controller is not None)
        self.locate_button.clicked.connect(self._choose)
        if self.controller is None:
            return
        c = self.controller
        self.install_button.clicked.connect(lambda: c.install())
        self.run_button.clicked.connect(self._run)
        c.status_changed.connect(self.show_status)
        c.progress.connect(self._show_progress)
        c.note.connect(self.progress_line.set_idle)
        c.message.connect(self._message)
        c.busy_changed.connect(self._busy_changed)
        c.game_running.connect(self._game_running)
        c.launcher_checked.connect(self._launcher_checked)

    def _open_homepage(self) -> None:
        self._open(HOMEPAGE)

    def _open_reforged(self) -> None:
        self._open(REFORGED)

    def _message(self, title: str, text: str) -> None:
        self.warn(text, title)

    def _game_running(self, running: bool) -> None:
        self._update_buttons(busy=running)

    def _open(self, url: str) -> None:
        self._open_url(url)

    def _show_progress(self, fraction: float | None, text: str) -> None:
        if self._close_requested:
            return  # reports queued before the stop; the line says the window is closing
        if fraction is None:
            self.progress_line.set_busy(text)
        else:
            self.progress_line.set_progress(fraction)

    def _busy_changed(self, busy: bool) -> None:
        if not busy:
            self.progress_line.set_idle()
        self._busy_cursor(busy)
        self._update_buttons(busy=busy)
        if not busy and self._close_requested:
            # After the slot: the job's own queued signals have all been delivered by then.
            QTimer.singleShot(0, self.close)

    def _busy_cursor(self, on: bool) -> None:
        # Qt stacks override cursors, so each busy stretch pushes one and pops it once, as
        # luducat does.
        # BusyCursor, not WaitCursor: the window still answers while a job runs.
        if on and not self._cursor_pushed:
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
            self._cursor_pushed = True
        elif not on and self._cursor_pushed:
            QApplication.restoreOverrideCursor()
            self._cursor_pushed = False

    @contextmanager
    def _plain_cursor(self) -> Iterator[None]:
        """A dialog asks for a click, so it gets the plain pointer even while a job runs."""
        pushed = self._cursor_pushed
        if pushed:
            QApplication.restoreOverrideCursor()
            self._cursor_pushed = False
        try:
            yield
        finally:
            # The job may have ended while the dialog was open; only a running one gets it back.
            if pushed and self.controller is not None and self.controller.jobs():
                self._busy_cursor(True)

    def _choose(self) -> None:
        if self.controller is None:
            return
        with self._plain_cursor():
            chosen = self._choose_folder(self)
        if chosen:
            self.controller.choose_game_files(Path(chosen))

    def greet(self) -> None:
        """Before the checks go online: the first start once, later the open icon question."""
        c = self.controller
        if c is None:
            return
        if not c.settings.first_run_done:
            with self._plain_cursor():
                answer = self._ask_first_start(self, c.offers_icon())
            problem = c.finish_first_start(answer)
        elif c.icon_question_due():
            with self._plain_cursor():
                choice = self._ask_icon(self)
            problem = c.answer_icon(choice)
        else:
            return
        if problem is not None:
            self.warn(problem)

    def _launcher_checked(self, newer: str | None, problem: str | None) -> None:
        # The version line answers for the launcher; the progress line carries the news.
        base = f"{LAUNCHER_NAME} v{__version__}"
        if problem is not None:
            self.version.setToolTip(_plain_tip(f"{base}. The check for a newer launcher did "
                                               f"not get through: {problem}"))
        elif newer is not None:
            self.version.setToolTip(f"{base}. Version {newer} is out.")
        else:
            self.version.setToolTip(f"{base} is the newest.")

    def _about(self) -> None:
        with self._plain_cursor():
            self._show_about(self)

    def _options(self) -> None:
        c = self.controller
        if c is None:
            return
        with self._plain_cursor():
            chosen = self._ask_options(self)
        if chosen is None:
            return
        before = c.build
        c.apply_settings(chosen, after=lambda: self._after_options(before))

    def _after_options(self, before: Build) -> None:
        """One box when the build changed, with the Install offer when it is missing."""
        c = self.controller
        if c is None or c.build is before:
            return
        text = switch_notice(c.build, c.settings.sync_saves, c.paths)
        installed = c.status is not None and c.status.game_installed
        if installed:
            with self._plain_cursor():
                dialogs.message(self, self.fonts, QMessageBox.Icon.Information, OPTIONS_TITLE,
                                text)
            return
        name = BUILD_NAMES[c.build]
        with self._plain_cursor():
            answer = dialogs.message(
                self, self.fonts, QMessageBox.Icon.Question, OPTIONS_TITLE,
                f"{text}\n\n{name[0].upper()}{name[1:]} is not installed yet. Install it now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            c.install_when_idle()

    def _run(self) -> None:
        if self.controller is None:
            return
        warning = self.controller.run_game()
        if warning is None:
            return
        if not self.controller.can_run():
            with self._plain_cursor():
                dialogs.message(self, self.fonts, QMessageBox.Icon.Information, TITLE, warning)
            return
        with self._plain_cursor():
            answer = dialogs.message(
                self, self.fonts, QMessageBox.Icon.Question, TITLE,
                warning + "\n\nStart the game anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.run_game(confirmed=True)

    def warn(self, text: str, title: str = TITLE) -> None:
        # A failed job says so before it has ended, with the busy cursor still up.
        with self._plain_cursor():
            dialogs.message(self, self.fonts, QMessageBox.Icon.Warning, title, text)

    def show_status(self, status: Status | None) -> None:
        rows = self.rows
        if status is None:
            for row in rows.values():
                row.set_state(State.CHECKING, "checking...")
        else:
            self._show_game(status)
            if status.game_files is not None:
                rows["files"].set_state(State.OK, _short_path(status.game_files),
                                        tooltip=str(status.game_files))
            elif status.game_files_problem:
                rows["files"].set_state(State.ERROR, "", tooltip=status.game_files_problem)
            else:
                rows["files"].set_state(State.ERROR, "not chosen")
            self._show_runtime(status)
        self._update_buttons(busy=bool(self.controller.jobs()) if self.controller else False)

    def _show_runtime(self, status: Status) -> None:
        row = self.rows["runtime"]
        c = self.controller
        if c is not None and c.build is not Build.WINDOWS:
            row.set_state(State.NOT_NEEDED, "not needed for the Linux build",
                          tooltip="His Linux build runs without Wine.")
        elif status.runtime is not None:
            version = ".".join(str(n) for n in status.runtime.version or ())
            source = status.runtime.candidate.source.value
            row.set_state(State.OK, f"Wine {version} ({source})",
                          tooltip=status.runtime_note or status.runtime.version_text)
        else:
            row.set_state(State.ERROR, "none usable",
                          tooltip=_with_hint(status.runtime_problem or "", c))

    def _show_game(self, status: Status) -> None:
        row = self.rows["game"]
        c = self.controller
        label = (c.build if c is not None else status.build or Build.WINDOWS).value
        note = c.fallback_note() if c is not None else ""
        if not status.game_installed:
            row.set_state(State.ERROR, f"{label} not installed", tooltip=note)
            return
        text = f"{label} v{status.game_version}" if status.game_version else label
        if note:
            row.set_state(State.OK, text, tooltip=note)
            return
        update = self.controller.game_update if self.controller else None
        if update is not None and self.controller is not None \
                and self.controller.update_available():
            row.set_state(State.UPDATE, f"{text} (v{update.latest})",
                          tooltip=f"Version {update.latest} is out. Update Reforged fetches it.")
        elif update is not None and update.problem:
            row.set_state(State.OK, text,
                          tooltip=_plain_tip(f"Could not check for a newer build: "
                                             f"{update.problem}"))
        elif status.game_version is None:
            row.set_state(State.OK, text, tooltip="The version shows after the first start.")
        else:
            row.set_state(State.OK, text)

    def _update_buttons(self, *, busy: bool) -> None:
        c = self.controller
        if c is None:
            self.install_button.setEnabled(False)
            self.run_button.setEnabled(False)
            return
        self.install_button.setToolTip(update_tip(c.build))
        if c.build is Build.WINDOWS:
            can_fetch = c.status is not None and c.status.runtime is not None
        else:
            can_fetch = c.status is not None
        self.install_button.setEnabled(can_fetch and not busy and not c.is_running())
        # Settings and the card change under neither a job nor a running game. Options waits for
        # a first status too: without one it would probe the host on this thread.
        self._find("options").setEnabled(c.status is not None and not busy and not c.is_running())
        self.locate_button.setEnabled(not busy and not c.is_running())
        self.run_button.setEnabled(c.can_run() and not busy)
        self.run_button.setToolTip(_run_hint(c, busy))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt's name)
        c = self.controller
        if c is not None and c.jobs():
            # Waiting here would freeze the window for the rest of a download; it closes itself
            # once the jobs have stopped.
            event.ignore()
            if not self._close_requested:
                self._close_requested = True
                logger.info("closing once the running jobs have stopped")
                c.stop_jobs()
                self.progress_line.set_busy(CLOSING_TEXT)
            return
        if c is not None:
            c.shutdown()
        super().closeEvent(event)


def switch_notice(build: Build, sync: bool, paths: AppPaths,
                  env: Mapping[str, str] = os.environ) -> str:
    """Which build runs from now on, and where its saves are."""
    if build is Build.WINDOWS:
        where = f"in the launcher's Wine prefix ({home_as_tilde(paths.prefix)})"
    else:
        where = f"in {home_as_tilde(native_data_dir(env, Path.home()))}"
    text = f"From now on the launcher runs {BUILD_NAMES[build]}. Its saves are {where}."
    if sync:
        return (text + " While the saves are synced, each start first takes the other build's "
                "newer saves, so you continue where you left off.")
    return (text + " The other build's saves stay where they are; turn on \"Sync native and "
            "Windows saves\" in Options to carry them over.")


def _is_card(folder: Path) -> bool:
    try:
        return find_6r51(folder) is not None
    except (OSError, ValueError):
        return False


def _choose_game_files(window: MainWindow) -> str:
    return dialogs.choose_game_files(window, window.fonts, LOCATE_TITLE, _is_card)


# The dialogs are the window's children, so Qt keeps them after exec(); we delete each once its
# answer is read, or every open would leave one behind for the window's life.
def _first_start_dialog(window: MainWindow, offer_icon: bool) -> FirstStart:
    dialog = FirstStartDialog(window.fonts, offer_icon=offer_icon, open_url=window._open,
                              parent=window)
    try:
        dialog.exec()
        answer = dialog.answer
    finally:
        dialog.deleteLater()
    return answer if answer is not None else FirstStart(
        False, IconChoice.NOT_NOW if offer_icon else None)


def _about_dialog(window: MainWindow) -> None:
    dialog = AboutDialog(window.fonts, open_url=window._open, parent=window)
    try:
        dialog.exec()
    finally:
        dialog.deleteLater()


def _options_dialog(window: MainWindow) -> LauncherSettings | None:
    c = window.controller
    if c is None:
        return None
    dialog = OptionsDialog(window.fonts, c.options_state(), scan=c.find_runtimes,
                           set_icon=c.set_desktop_icon, parent=window)
    try:
        dialog.exec()
        return dialog.chosen
    finally:
        dialog.deleteLater()


def _run_hint(c: LauncherController, busy: bool) -> str:
    """RUN GAME's tooltip: what it does, or what is still missing while it is greyed."""
    s = c.status
    if c.is_running():
        return f"{GAME_NAME} is running."
    if busy or s is None:
        return "Wait until the launcher has finished."
    if c.build is not Build.WINDOWS:
        if not s.game_installed:
            return f"Install {GAME_NAME} first: Update Reforged."
    else:
        if s.runtime is None:
            return _with_hint("No usable Wine: see the Windows Runtime row.", c)
        if not s.game_installed or not s.prefix_ready:
            return f"Install {GAME_NAME} first: Update Reforged."
    if s.game_files is None:
        return "Locate the original game files first."
    return f"Start {GAME_NAME}."


def _with_hint(problem: str, c: LauncherController | None) -> str:
    """The problem, then what the player can install about it."""
    extra = c.install_hint() if c is not None else ""
    return "\n".join(part for part in (problem, extra) if part)


def _plain_tip(text: str) -> str:
    """Escaped server text inside <p>: without a tag Qt shows the entities themselves."""
    return f"<p>{html.escape(text)}</p>"


def _short_path(path: Path) -> str:
    """The card's folder, home as ~: every valid choice ends in system/apps/6r51, so the part
    above it tells one copy from another. The full path stays in the tooltip."""
    parts = [part.lower() for part in path.parts]
    if len(parts) > 3 and parts[-3:-1] == ["system", "apps"]:
        path = path.parents[2]
    try:
        return str(Path("~") / path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _app_icon() -> QIcon:
    """The theme's icon when the desktop entry is installed, else the bundled PNGs."""
    themed = QIcon.fromTheme(APP_ID)
    if not themed.isNull():
        return themed
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addFile(str(ICONS_SOURCE / f"{size}x{size}" / "apps" / f"{APP_ID}.png"),
                     QSize(size, size))
    return icon


def prepare_application(app: QApplication) -> None:
    # The WM class comes from the application name; Wayland matches
    # the desktop file name against the installed entry for the dock icon.
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    QGuiApplication.setDesktopFileName(APP_ID)
    app.setWindowIcon(_app_icon())


# Everything 12.5 % larger than the 1024x576 design: Qt's
# own scale factor grows window, dialogs, text and art evenly, the art rendered sharp.
UI_SCALE = 1.125
SCALE_VAR = "QT_SCALE_FACTOR"


def ui_scale_factor(player: str | None) -> str:
    """The factor Qt starts with: the player's own scale, if any, times UI_SCALE."""
    try:
        base = float(player) if player else 1.0
    except ValueError:
        base = 1.0
    if not math.isfinite(base) or base <= 0:
        base = 1.0
    return f"{base * UI_SCALE:g}"


def _scaled_application() -> QApplication:
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    player = os.environ.get(SCALE_VAR)
    os.environ[SCALE_VAR] = ui_scale_factor(player)
    try:
        return QApplication(sys.argv)
    finally:
        # Qt has read it; Wine and his game get the environment the player started us with.
        if player is None:
            del os.environ[SCALE_VAR]
        else:
            os.environ[SCALE_VAR] = player


def run_window(make_controller: Callable[[AppPaths], LauncherController] | None = None) -> int:
    """The launcher's start; `make_controller` lets a dev tool fake the host."""
    app = _scaled_application()
    prepare_application(app)
    screen = app.primaryScreen()
    logger.info("Qt %s, PySide6 %s, %s, scale %s", qVersion(), PySide6.__version__,
                app.platformName(), screen.devicePixelRatio() if screen else "unknown")
    paths = resolve()
    ensure_dirs(paths)
    logger.info("folders: data %s, config %s, cache %s, state %s",
                *(home_as_tilde(p) for p in (paths.data, paths.config, paths.cache, paths.state)))
    # Imported here: at module level the window knows the controller only for type checking.
    from project_reforged_linux.ui.controller import LauncherController

    controller = (make_controller or LauncherController)(paths)
    window = MainWindow(controller)
    if controller.settings_problem:
        window.warn(controller.settings_problem)
    window.show()
    window.greet()
    controller.start_checks()
    return app.exec()
