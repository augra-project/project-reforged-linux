# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The Options dialog: which of his builds runs, updates, the desktop icon, the Windows runtime.

It reads a snapshot and hands back new settings; the Wine search and the desktop icon, which
act at once, come in as callbacks.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QCheckBox,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from project_reforged_linux.builds import Build
from project_reforged_linux.nativecheck import NativeCheck
from project_reforged_linux.runtimes import MIN_VERSION, Checked, Mode, Resolved, Source
from project_reforged_linux.settings import DesktopChoice, LauncherSettings
from project_reforged_linux.ui import dialogs, theme
from project_reforged_linux.ui.bezel import SMALL, BezelButton, BezelStyle, Panel
from project_reforged_linux.ui.dialogframe import ThemedDialog, button_row
from project_reforged_linux.ui.links import LinkLabel

__all__ = ["BUILD_LABELS", "BUILD_NAMES", "RUNTIME_LABELS", "OptionsDialog", "OptionsState",
           "runtime_label"]

logger = logging.getLogger(__name__)

TITLE = "Launcher Options"
# Shown in this order, not in the preference order.
BUILD_LABELS = {
    Build.LINUX_TARBALL: "Linux tarball (glibc 2.35+)",
    Build.LINUX_APPIMAGE: "Linux AppImage (the above plus FUSE)",
    Build.WINDOWS: "Windows 64-bit (via Wine)",
}
BUILD_NAMES = {Build.LINUX_TARBALL: "the Linux tarball",
                Build.LINUX_APPIMAGE: "the Linux AppImage", Build.WINDOWS: "the Windows build"}
RUNTIME_LABELS = {
    Mode.AUTO: "Automatic (recommended)",
    Mode.SYSTEM: "System Wine",
    Mode.BUNDLED: "Bundled runtime",
    Mode.CHOSEN: "Another Wine on this system",
}
_SOURCES = {Source.SYSTEM: "system", Source.BUNDLED: "bundled with the launcher",
            Source.WINEHQ: "WineHQ", Source.LUTRIS: "Lutris", Source.BOTTLES: "Bottles",
            Source.CHOSEN: "chosen"}
_WHOSE = {Source.SYSTEM: "the system's", Source.BUNDLED: "the bundled one",
          Source.WINEHQ: "WineHQ's", Source.LUTRIS: "from Lutris", Source.BOTTLES: "from Bottles",
          Source.CHOSEN: "the chosen one"}
SYNC_TEXT = "Sync native and Windows saves"
LAUNCHER_UPDATES = "Check for new launcher versions on start"
GAME_UPDATES = "Check for new game versions on start"
ICON_TEXT = ("GNOME needs a copy of the bundled icon in ~/.local/share to show the application "
             "icon in your dock.")
NO_SYSTEM_WINE = "No Wine is installed on this system."
NO_BUNDLED = "Only the launcher's AppImage brings a bundled runtime."
PICK_ONE = "Pick one from the list; without a pick, Automatic stays."
LIST_HEIGHT = 96
ROW_BUTTON: BezelStyle = replace(SMALL, height=30)
_WINE_PATH = Qt.ItemDataRole.UserRole

Scan = Callable[[Callable[[list[Checked]], None]], None]
SetIcon = Callable[[bool], str | None]


@dataclass(frozen=True, slots=True)
class OptionsState:
    """What the dialog shows; taken from the controller when it opens."""

    settings: LauncherSettings
    native: NativeCheck
    build: Build  # the build that runs now: chosen, or the best that runs here
    game_version: str | None  # that build's installed version, when known
    game_installed: bool
    resolved: Resolved | None  # the Windows runtime the saved choice gives
    icon_installed: bool
    system: Checked | None = None  # the system's Wine on PATH; None when there is none
    bundled: Checked | None = None  # the launcher's own; None outside its AppImage
    icon_problem: str | None = None  # why Install cannot work here (no AppImage to point at)


def runtime_label(checked: Checked) -> str:
    """One line in the list: version or folder, its source, and why it cannot be used.

    The full reason goes into the item's tooltip; the line keeps it short enough to read.
    """
    source = checked.candidate.source
    if source in (Source.LUTRIS, Source.BOTTLES):
        name = checked.candidate.wine.parent.parent.name  # the runner's folder: <name>/bin/wine
    elif checked.version_text.startswith("wine-"):
        name = "Wine " + checked.version_text[len("wine-"):]
    else:
        name = checked.version_text or str(checked.candidate.wine)
    text = f"{name} - {_SOURCES[source]}"
    if checked.problem is None:
        return text
    if checked.version is not None and checked.version < MIN_VERSION:
        return f"{text} - too old, needs {MIN_VERSION[0]}.{MIN_VERSION[1]}"
    return f"{text} - not usable"


def _runs_now(state: OptionsState) -> str:
    name = BUILD_NAMES[state.build]
    if not state.game_installed:
        return f"Runs now: {name}, not installed yet."
    if state.game_version:
        return f"Runs now: {name}, v{state.game_version}."
    return f"Runs now: {name}."


def _build_hint(state: OptionsState) -> str:
    """Why a build is greyed out; with nothing greyed, which one runs."""
    problems: list[str] = []
    for problem in (state.native.tarball_problem(), state.native.appimage_problem()):
        if problem is not None and problem not in problems:
            problems.append(problem)
    return " ".join(problems) if problems else _runs_now(state)


def _runtime_hint(resolved: Resolved | None) -> str:
    if resolved is None:
        return ""
    if resolved.checked is None:
        return resolved.problem or ""
    if resolved.note:
        return resolved.note
    checked = resolved.checked
    version = (f"Wine {checked.version[0]}.{checked.version[1]}" if checked.version
               else checked.version_text)
    return f"Runs now: {version}, {_WHOSE[checked.candidate.source]}."


def _version(checked: Checked) -> str:
    if checked.version is None:
        return checked.version_text
    return f"{checked.version[0]}.{checked.version[1]}"


def _same_wine(a: str | Path, b: str | Path) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def _heading(text: str) -> LinkLabel:
    return LinkLabel(text, "heading")


def _hint(text: str) -> LinkLabel:
    return LinkLabel(text, "hint")


def _row_button(text: str, name: str) -> BezelButton:
    button = BezelButton(text, style=ROW_BUTTON)
    button.setObjectName(name)
    return button


class OptionsDialog(ThemedDialog):
    def __init__(self, fonts: theme.Fonts, state: OptionsState, *, scan: Scan,
                 set_icon: SetIcon, parent: QWidget | None = None) -> None:
        super().__init__(fonts, TITLE, parent=parent)
        self.state = state
        self.chosen: LauncherSettings | None = None
        self._scan, self._set_icon = scan, set_icon
        self._desktop = state.settings.desktop
        self._icon_installed = state.icon_installed
        self._closed = False
        self.finished.connect(self._mark_closed)

        panels = QHBoxLayout()
        panels.setSpacing(12)
        panels.addWidget(self._left(), 1)
        panels.addWidget(self._right(), 1)
        self.content.addLayout(panels, 1)
        self.ok_button = BezelButton("OK", style=SMALL)
        self.ok_button.setObjectName("ok")
        self.ok_button.setDefault(True)
        cancel = BezelButton("Cancel", style=SMALL)
        cancel.setObjectName("cancel")
        self.ok_button.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        self.content.addLayout(button_row(self.ok_button, cancel))
        self._windows_changed()

    def _left(self) -> Panel:
        s = self.state.settings
        box = Panel()
        col = box.box
        col.setSpacing(4)
        col.addWidget(_heading("Game version"))
        self.builds = QButtonGroup(box)
        self.build_buttons: dict[Build, QRadioButton] = {}
        problems = {Build.LINUX_TARBALL: self.state.native.tarball_problem(),
                    Build.LINUX_APPIMAGE: self.state.native.appimage_problem(),
                    Build.WINDOWS: None}
        # The build that runs: a chosen one this system cannot run has given way to it.
        checked = self.state.build
        for build, label in BUILD_LABELS.items():
            radio = QRadioButton(label)
            radio.setObjectName(f"build-{build.key}")
            radio.setEnabled(problems[build] is None)
            radio.setChecked(build is checked)
            if problems[build] is not None:
                radio.setToolTip(problems[build])
            self.builds.addButton(radio)
            self.build_buttons[build] = radio
            col.addWidget(radio)
        self.builds.buttonToggled.connect(self._build_toggled)
        self.build_hint = _hint(_build_hint(self.state))
        col.addWidget(self.build_hint)
        self.sync_box = QCheckBox(SYNC_TEXT)
        self.sync_box.setChecked(s.sync_saves)
        col.addWidget(self.sync_box)
        col.addSpacing(6)
        col.addWidget(_heading("Updates"))
        self.launcher_updates = QCheckBox(LAUNCHER_UPDATES)
        self.launcher_updates.setChecked(s.check_launcher_updates)
        self.game_updates = QCheckBox(GAME_UPDATES)
        self.game_updates.setChecked(s.check_game_updates)
        col.addWidget(self.launcher_updates)
        col.addWidget(self.game_updates)
        col.addSpacing(6)
        # The button sits on the heading's row: below the sentence the box ran out of room.
        self.icon_button = _row_button("Remove" if self._icon_installed else "Install", "icon")
        self.icon_button.clicked.connect(self._icon_clicked)
        self._icon_state()
        row = QHBoxLayout()
        row.addWidget(_heading("Desktop icon"))
        row.addStretch(1)
        row.addWidget(self.icon_button)
        col.addLayout(row)
        col.addWidget(_hint(ICON_TEXT))
        col.addStretch(1)
        return box

    def chosen_build(self) -> Build:
        for build, radio in self.build_buttons.items():
            if radio.isChecked():
                return build
        return self.state.build

    def _build_toggled(self, _button: QAbstractButton, on: bool) -> None:
        if on:
            self._windows_changed()

    def warn(self, text: str) -> None:
        dialogs.message(self, self.fonts, QMessageBox.Icon.Warning, TITLE, text)

    def _icon_clicked(self) -> None:
        install = not self._icon_installed
        problem = self._set_icon(install)
        if problem is not None:
            self.warn(problem)
            return
        self._icon_installed = install
        self._desktop = DesktopChoice.INSTALLED if install else DesktopChoice.DECLINED
        self.icon_button.setText("Remove" if install else "Install")
        self.icon_button.updateGeometry()
        self._icon_state()

    def _icon_state(self) -> None:
        # Greyed with the reason instead of a button that only answers with a warning.
        blocked = not self._icon_installed and self.state.icon_problem is not None
        self.icon_button.setEnabled(not blocked)
        self.icon_button.setToolTip(self.state.icon_problem if blocked else "")

    def _right(self) -> Panel:
        s = self.state.settings
        box = Panel()
        # The fade goes on the content, not the panel: the bezel and its leather stay solid.
        self.runtime_box = QWidget()
        col = QVBoxLayout(self.runtime_box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        col.addWidget(_heading("Windows runtime"))
        self.modes = QButtonGroup(self.runtime_box)
        self.mode_buttons: dict[Mode, QRadioButton] = {}
        system = self.state.system
        # A Wine chosen from the list that is the system's own shows as System Wine.
        saved_mode = s.runtime_mode
        if (saved_mode is Mode.CHOSEN and s.runtime_wine is not None and system is not None
                and _same_wine(s.runtime_wine, system.candidate.wine)):
            saved_mode = Mode.SYSTEM
        self._saved_mode = saved_mode
        for mode, label in RUNTIME_LABELS.items():
            radio = QRadioButton(label)
            radio.setObjectName(f"mode-{mode.value}")
            radio.setChecked(mode is saved_mode)
            self.modes.addButton(radio)
            self.mode_buttons[mode] = radio
            col.addWidget(radio)
        self._label_runtimes()
        self.mode_buttons[Mode.CHOSEN].toggled.connect(self._another_toggled)
        self._searched = False
        self.found = QListWidget()
        self.found.setFixedHeight(LIST_HEIGHT)
        self.found.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.found.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.found.currentItemChanged.connect(self._picked)
        col.addWidget(self.found)
        if saved_mode is Mode.CHOSEN and s.runtime_wine is not None:
            self._add_wine(s.runtime_wine, f"{s.runtime_wine} - chosen earlier", None)
        self.search_button = _row_button("Search again", "search")
        self.search_button.clicked.connect(self._search)
        row = QHBoxLayout()
        row.addWidget(self.search_button)
        row.addStretch(1)
        col.addLayout(row)
        self.runtime_hint = _hint(_runtime_hint(self.state.resolved))
        col.addWidget(self.runtime_hint)
        col.addStretch(1)
        box.box.addWidget(self.runtime_box)
        self._fade = QGraphicsOpacityEffect(self.runtime_box)
        self._fade.setOpacity(theme.DISABLED_OPACITY)
        self.runtime_box.setGraphicsEffect(self._fade)
        return box

    def _label_runtimes(self) -> None:
        for mode, checked, missing in ((Mode.SYSTEM, self.state.system, NO_SYSTEM_WINE),
                                       (Mode.BUNDLED, self.state.bundled, NO_BUNDLED)):
            radio = self.mode_buttons[mode]
            if checked is not None and checked.usable:
                radio.setText(f"{RUNTIME_LABELS[mode]} {_version(checked)}")
                radio.setToolTip(str(checked.candidate.wine))
                continue
            # A saved choice that stopped working stays checked, greyed, so the player sees it.
            radio.setEnabled(False)
            radio.setToolTip(missing if checked is None else checked.problem or missing)

    def _another_toggled(self, on: bool) -> None:
        if on and not self._searched and self.search_button.isEnabled():
            self._search()
        elif on and self.found.currentItem() is None:
            self.runtime_hint.setText(PICK_ONE)

    def _windows_changed(self) -> None:
        windows = self.chosen_build() is Build.WINDOWS
        self.runtime_box.setEnabled(windows)
        self._fade.setEnabled(not windows)

    def _add_wine(self, wine: str, text: str, problem: str | None) -> QListWidgetItem:
        item = QListWidgetItem(text)
        item.setData(_WINE_PATH, wine)
        item.setToolTip(f"{wine}\n{problem}" if problem else wine)
        if problem is not None:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable
                          & ~Qt.ItemFlag.ItemIsEnabled)
        self.found.addItem(item)
        if wine == self.state.settings.runtime_wine and problem is None:
            self.found.setCurrentItem(item)
        return item

    def _picked(self, current: QListWidgetItem | None, _previous: object) -> None:
        if current is not None:
            self.mode_buttons[Mode.CHOSEN].setChecked(True)

    def _search(self) -> None:
        self.search_button.setEnabled(False)
        self.runtime_hint.setText("Searching for Wine builds...")
        self._scan(self._found)

    def _found(self, results: list[Checked]) -> None:
        # The search runs in a job; the dialog may be gone when it ends.
        if self._closed or not shiboken6.isValid(self):
            return
        self._searched = True
        keep = self.found.currentItem()
        keep_wine = keep.data(_WINE_PATH) if keep is not None else self.state.settings.runtime_wine
        # The system's and the bundled Wine have their own radios above; by path, so a WineHQ
        # tree that is the system's own behind a link goes too.
        others = [c for c in results
                  if not any(own is not None and _same_wine(c.candidate.wine, own.candidate.wine)
                             for own in (self.state.system, self.state.bundled))]
        self.found.blockSignals(True)
        self.found.clear()
        for checked in others:
            item = self._add_wine(str(checked.candidate.wine), runtime_label(checked),
                                  checked.problem)
            if str(checked.candidate.wine) == keep_wine and checked.problem is None:
                self.found.setCurrentItem(item)
        self.found.blockSignals(False)
        usable = sum(1 for c in others if c.usable)
        if not others:
            text = "No other Wine builds found on this system."
        elif self.mode_buttons[Mode.CHOSEN].isChecked() and self.found.currentItem() is None:
            text = f"Found {len(others)}, {usable} usable. {PICK_ONE}"
        else:
            text = f"Found {len(others)} other Wine builds, {usable} usable."
        self.runtime_hint.setText(text)
        self.search_button.setEnabled(True)

    def chosen_mode(self) -> Mode:
        for mode, radio in self.mode_buttons.items():
            if radio.isChecked():
                return mode
        return Mode.AUTO

    def settings_from_choices(self) -> LauncherSettings:
        """The settings with the player's changes; untouched choices keep their saved value."""
        s = self.state.settings
        build = self.chosen_build()
        # The radio starts on the build that runs; left there, the saved choice stays: none, or
        # one this system cannot run, which comes back on a system that can.
        game_build = s.game_build if build is self.state.build else build
        mode = self.chosen_mode()
        wine = None
        if mode is Mode.CHOSEN:
            item = self.found.currentItem()
            wine = item.data(_WINE_PATH) if item is not None else None
            if wine is None:
                mode = Mode.AUTO
        return replace(s, game_build=game_build, sync_saves=self.sync_box.isChecked(),
                       check_launcher_updates=self.launcher_updates.isChecked(),
                       check_game_updates=self.game_updates.isChecked(),
                       desktop=self._desktop, runtime_mode=mode, runtime_wine=wine)

    def accept(self) -> None:
        self.chosen = c = self.settings_from_choices()
        logger.info("options: build %s, runtime %s, sync %s, updates launcher %s game %s",
                    c.game_build.key if c.game_build else "best", c.runtime_mode.value,
                    c.sync_saves, c.check_launcher_updates, c.check_game_updates)
        super().accept()

    def _mark_closed(self) -> None:
        self._closed = True
