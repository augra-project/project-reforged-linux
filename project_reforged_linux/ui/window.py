# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The launcher's main window."""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from project_reforged_linux import PART_NUMBER, RELEASE_DATE, __version__
from project_reforged_linux.prepare import Status
from project_reforged_linux.ui import theme
from project_reforged_linux.ui.assets import EMBLEM
from project_reforged_linux.ui.banner import Banner
from project_reforged_linux.ui.bezel import GOLD, LEATHER, BezelButton, BezelStyle, Panel
from project_reforged_linux.ui.frame import CORNER_SIZE, FrameWidget
from project_reforged_linux.ui.progress import ProgressLine
from project_reforged_linux.ui.widgets import Fleuron, State, StatusRow

if TYPE_CHECKING:
    from project_reforged_linux.ui.controller import LauncherController

__all__ = ["FOOTER", "HOMEPAGE", "REFORGED", "TITLE", "TRADEMARK", "MainWindow"]

TITLE = "Project Reforged Linux Launcher"
SIZE = QSize(1024, 576)
HOMEPAGE = "https://github.com/augra-project/project-reforged-linux"
REFORGED = "https://project-reforged.danwhelan.ie/"
# One centred line in the welcome box (Stefan, 2026-11-16): the full names did not fit its
# width, so the launcher is "PR Linux Launcher"; "free fan port" stands above it already.
FOOTER = "PR Linux Launcher (c) 2026 The Augra Project - Project Reforged (c) 2026 Dan Whelan"
# Moved to About (Plan 3b) so the welcome box can hold its text (Stefan, 2026-11-16).
TRADEMARK = ("The Elder Scrolls Travels: Shadowkey belongs to ZeniMax Media Inc. and Bethesda "
             "Softworks LLC. This launcher is not affiliated with them.")
_P = "<p style='margin:0 0 4px 0'>"
WELCOME = (
    "<p align='center' style='margin:0 0 4px 0; "
    "font-family:\"{heading}\"; font-size:{title}pt; color:{gold}'>"
    "Welcome to Project Reforged</p>"
    f"{_P}This is the Linux launcher for Dan Whelan's free fan port of "
    "<i>The Elder Scrolls Travels: Shadowkey</i>.</p>"
    f"{_P}The launcher contains neither the game nor the port. It downloads the port from "
    "Dan Whelan's site and uses your own copy of the game files. Please do not pass it on "
    "bundled with either.</p>")
# Everything sits a bit high, so the progress line at the bottom stands apart
# (Stefan, 2026-11-16, at the screen).
SIDE, TOP, BOTTOM = 28, 18, 20
PROGRESS_GAP = 10  # extra room above the progress line, on top of the layout spacing
SIDE_EXTRA = 48  # Launcher Homepage and Project Reforged wider than their text (Stefan)
VERSION_GAP = 3  # between the version and the welcome box below it
# The progress line runs along the bottom between the corner ornaments.
PROGRESS_INSET = math.ceil(CORNER_SIZE) + 4 - SIDE


def _button(text: str, name: str, icon: str | None = None,
            style: BezelStyle = LEATHER) -> BezelButton:
    button = BezelButton(text, style=style, icon=icon)
    button.setObjectName(name)
    return button


class MainWindow(QWidget):
    def __init__(self, controller: LauncherController | None = None, *,
                 open_url: Callable[[str], object] = lambda url: QDesktopServices.openUrl(
                     QUrl(url)),
                 choose_folder: Callable[[QWidget], str] = lambda parent:
                 QFileDialog.getExistingDirectory(parent, "Choose the original game files"),
                 fonts: theme.Fonts | None = None) -> None:
        super().__init__()
        self.controller = controller
        self._open_url = open_url
        self._choose_folder = choose_folder
        fonts = fonts or theme.load_fonts()
        self.setWindowTitle(f"{TITLE} v{__version__}")
        self.setFixedSize(SIZE)
        # A fixed window offers no maximize; the WM honours the buttons only when all are named.
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.CustomizeWindowHint
                            | Qt.WindowType.WindowTitleHint
                            | Qt.WindowType.WindowSystemMenuHint
                            | Qt.WindowType.WindowMinimizeButtonHint
                            | Qt.WindowType.WindowCloseButtonHint)
        theme.apply(self, fonts)
        self.setWindowIcon(QIcon(str(EMBLEM)))

        frame = FrameWidget(self)
        frame.setGeometry(0, 0, SIZE.width(), SIZE.height())
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(SIDE, TOP, SIDE, BOTTOM)
        layout.setSpacing(8)
        layout.addWidget(Banner(fonts), 0)

        status_panel = Panel()
        self.rows = {
            "game": StatusRow("Project Reforged"),
            "files": StatusRow("Required original game files", button="Choose..."),
            "runtime": StatusRow("Windows Runtime"),
        }
        for row in self.rows.values():
            status_panel.box.addWidget(row)
        self.install_button = _button("Install / Update Requirements", "install")
        status_panel.box.addWidget(self.install_button, 0, Qt.AlignmentFlag.AlignHCenter)

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

        # Equally wide (Look review 1): only the stretch decides, not what each box would like.
        panels = QHBoxLayout()
        for panel in (status_panel, welcome_panel):
            panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            panels.addWidget(panel, 1)
        layout.addLayout(panels, 1)

        self.run_button = _button("RUN GAME", "runGame", style=GOLD)
        run_row = QHBoxLayout()
        home = _button("Launcher Homepage", "homepage", "house")
        reforged = _button("Project Reforged", "reforged", "key-round")
        run_row.addWidget(home)
        run_row.addStretch(1)
        # The fleurons grow out of the button's frame, no gap (Stefan, 2026-11-16).
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

        # Just above the welcome box, its right edge on the box's (Stefan, 2026-11-16). The
        # window has a fixed size, so the layout is settled once and the label placed on it.
        self.version = QLabel(f"v{__version__} - {PART_NUMBER}-{RELEASE_DATE}", frame)
        self.version.setObjectName("version")
        self.version.ensurePolished()
        self.version.adjustSize()
        layout.activate()
        box = welcome_panel.geometry()
        self.version.move(box.right() + 1 - self.version.width(),
                          box.top() - VERSION_GAP - self.version.height())

        layout.addSpacing(PROGRESS_GAP)
        self.progress_line = ProgressLine()
        progress_row = QHBoxLayout()
        progress_row.addSpacing(PROGRESS_INSET)
        progress_row.addWidget(self.progress_line)
        progress_row.addSpacing(PROGRESS_INSET)
        layout.addLayout(progress_row)

        self._wire()
        self.show_status(None)

    def _find(self, name: str) -> QPushButton:
        found = self.findChild(QPushButton, name)
        if found is None:
            raise LookupError(name)
        return found

    def _wire(self) -> None:
        self._find("homepage").clicked.connect(lambda: self._open_url(HOMEPAGE))
        self._find("reforged").clicked.connect(lambda: self._open_url(REFORGED))
        self._find("quit").clicked.connect(self.close)
        for name in ("options", "about"):
            self._find(name).setEnabled(False)
            self._find(name).setToolTip("Comes with the next build.")
        choose = self.rows["files"].button
        if choose is not None:
            choose.setEnabled(self.controller is not None)
            choose.clicked.connect(self._choose)
        if self.controller is None:
            return
        c = self.controller
        self.install_button.clicked.connect(lambda: c.install())
        self.run_button.clicked.connect(self._run)
        c.status_changed.connect(self.show_status)
        # The controller reports steps as text without a known end (Task 10).
        c.progress.connect(self.progress_line.set_busy)
        c.message.connect(lambda title, text: QMessageBox.warning(self, title, text))
        c.busy_changed.connect(self._busy_changed)
        c.game_running.connect(lambda running: self._update_buttons(busy=running))

    def _busy_changed(self, busy: bool) -> None:
        if not busy:
            self.progress_line.set_idle()
        self._update_buttons(busy=busy)

    def _choose(self) -> None:
        if self.controller is None:
            return
        chosen = self._choose_folder(self)
        if chosen:
            self.controller.choose_game_files(Path(chosen))

    def _run(self) -> None:
        if self.controller is None:
            return
        warning = self.controller.run_game()
        if warning is None:
            return
        if not self.controller.can_run():
            QMessageBox.information(self, TITLE, warning)
            return
        answer = QMessageBox.question(self, TITLE, warning + "\n\nStart the game anyway?")
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.run_game(confirmed=True)

    def show_status(self, status: Status | None) -> None:
        rows = self.rows
        if status is None:
            for row in rows.values():
                row.set_state(State.CHECKING, "checking...")
        else:
            if status.game_installed and status.game_version:
                rows["game"].set_state(State.OK, f"v{status.game_version}")
            elif status.game_installed:
                rows["game"].set_state(State.OK, "installed")
            else:
                rows["game"].set_state(State.ERROR, "not installed")
            if status.game_files is not None:
                rows["files"].set_state(State.OK, "", tooltip=str(status.game_files))
            elif status.game_files_problem:
                rows["files"].set_state(State.ERROR, "", tooltip=status.game_files_problem)
            else:
                rows["files"].set_state(State.ERROR, "not chosen")
            if status.runtime is not None:
                version = ".".join(str(n) for n in status.runtime.version or ())
                source = status.runtime.candidate.source.value
                rows["runtime"].set_state(State.OK, f"Wine {version} ({source})",
                                          tooltip=status.runtime_note or
                                          status.runtime.version_text)
            else:
                rows["runtime"].set_state(State.ERROR, "none usable",
                                          tooltip=status.runtime_problem or "")
        self._update_buttons(busy=False)

    def _update_buttons(self, *, busy: bool) -> None:
        c = self.controller
        if c is None:
            self.install_button.setEnabled(False)
            self.run_button.setEnabled(False)
            return
        runtime_ok = c.status is not None and c.status.runtime is not None
        self.install_button.setEnabled(runtime_ok and not busy and not c.is_running())
        self.run_button.setEnabled(c.can_run() and not busy)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt's name)
        if self.controller is not None:
            self.controller.shutdown()
        super().closeEvent(event)
