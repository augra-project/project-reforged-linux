# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The first start and the desktop icon question on later starts.

Nothing goes online before the player has answered; the icon is offered only on GNOME and only
from the AppImage, which its desktop entry starts.
"""

from dataclasses import dataclass
from enum import Enum

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QMessageBox,
    QRadioButton,
    QWidget,
)

from project_reforged_linux import GAME_NAME
from project_reforged_linux.ui import theme
from project_reforged_linux.ui.bezel import SMALL, BezelButton, Panel
from project_reforged_linux.ui.dialogframe import ThemedDialog, button_row
from project_reforged_linux.ui.links import GAME_HOME, LinkLabel, UrlOpener, anchor, open_in_browser
from project_reforged_linux.ui.options import ICON_TEXT, LAUNCHER_UPDATES

__all__ = ["FirstStart", "FirstStartDialog", "IconChoice", "ask_icon", "icon_question"]

TITLE = "Welcome"
_P = "<p style='margin:0 0 8px 0'>"
WELCOME = (
    f"{_P}This is the Linux launcher for Dan Whelan's free fan port of <i>The Elder Scrolls "
    f"Travels: Shadowkey</i>. It downloads his build from his site, "
    f"{anchor('project-reforged.danwhelan.ie', GAME_HOME)}, and runs it with your own copy of "
    "the original N-Gage game files.</p>"
    "<p style='margin:0'>At every start the launcher asks his site whether a newer build is "
    "out. You can turn that off in Options.</p>")
GITHUB_NOTE = ("When this is on, GitHub sees your IP address and the launcher's version at "
               "every start.")
INSTALL_ICON = "Install it now"
NOT_NOW = "Not now"
NEVER = "Don't ask again"
CONTINUE = "Continue"


class IconChoice(Enum):
    INSTALL = "install"
    NOT_NOW = "not now"  # asked again on a later start
    NEVER = "never"  # remembered; Options can still install it


@dataclass(frozen=True, slots=True)
class FirstStart:
    launcher_updates: bool
    icon: IconChoice | None  # None: the icon was not offered


class FirstStartDialog(ThemedDialog):
    def __init__(self, fonts: theme.Fonts, *, offer_icon: bool,
                 open_url: UrlOpener = open_in_browser, parent: QWidget | None = None) -> None:
        super().__init__(fonts, TITLE, parent=parent)
        self.setWindowTitle(f"{TITLE} to {GAME_NAME}")
        self._offer_icon = offer_icon
        self.answer: FirstStart | None = None
        panel = Panel()
        col = panel.box
        col.setSpacing(4)
        col.addWidget(LinkLabel(WELCOME, open_url=open_url))
        col.addSpacing(8)
        col.addWidget(LinkLabel("Launcher updates", "heading"))
        self.updates = QCheckBox(LAUNCHER_UPDATES)
        self.updates.setChecked(False)
        col.addWidget(self.updates)
        col.addWidget(LinkLabel(GITHUB_NOTE, "hint"))
        self.install_icon = QRadioButton(INSTALL_ICON)
        self.not_now = QRadioButton(NOT_NOW)
        self.never = QCheckBox(NEVER)
        if offer_icon:
            col.addSpacing(8)
            col.addWidget(LinkLabel("Desktop icon", "heading"))
            col.addWidget(LinkLabel(ICON_TEXT, "hint"))
            group = QButtonGroup(panel)
            for radio in (self.install_icon, self.not_now):
                group.addButton(radio)
                col.addWidget(radio)
            # The launcher never installs the icon silently: Not now stays picked.
            self.not_now.setChecked(True)
            col.addWidget(self.never)
            self.install_icon.toggled.connect(self._install_toggled)
        col.addStretch(1)
        self.content.addWidget(panel, 1)
        self.continue_button = BezelButton(CONTINUE, style=SMALL)
        self.continue_button.setObjectName("continue")
        self.continue_button.setDefault(True)
        self.continue_button.clicked.connect(self.accept)
        self.content.addLayout(button_row(self.continue_button))

    def _install_toggled(self, on: bool) -> None:
        self.never.setEnabled(not on)

    def _icon(self) -> IconChoice | None:
        if not self._offer_icon:
            return None
        if self.install_icon.isChecked():
            return IconChoice.INSTALL
        return IconChoice.NEVER if self.never.isChecked() else IconChoice.NOT_NOW

    def accept(self) -> None:
        self.answer = FirstStart(self.updates.isChecked(), self._icon())
        super().accept()

    def reject(self) -> None:
        # Closed without Continue: nothing opted in, nothing installed, asked again later.
        self.answer = FirstStart(False, IconChoice.NOT_NOW if self._offer_icon else None)
        super().reject()


def icon_question(parent: QWidget | None, fonts: theme.Fonts) -> QMessageBox:
    """The later starts' question while the choice is still open."""
    box = QMessageBox(QMessageBox.Icon.Question, GAME_NAME,
                      f"{ICON_TEXT}\n\nInstall the desktop icon now?",
                      QMessageBox.StandardButton.NoButton, parent)
    box.addButton("Install", QMessageBox.ButtonRole.AcceptRole)
    box.addButton(NOT_NOW, QMessageBox.ButtonRole.RejectRole)
    # Parented to the box: PySide6 does not hand the checkbox's ownership to setCheckBox, and a
    # temporary one is collected under the box's feet.
    box.setCheckBox(QCheckBox(NEVER, box))
    theme.apply_dialog(box, fonts)
    return box


def ask_icon(parent: QWidget | None, fonts: theme.Fonts) -> IconChoice:
    box = icon_question(parent, fonts)
    try:
        box.exec()
        clicked = box.clickedButton()
        if clicked is not None and box.buttonRole(clicked) == QMessageBox.ButtonRole.AcceptRole:
            return IconChoice.INSTALL
        checkbox = box.checkBox()
        never = checkbox is not None and checkbox.isChecked()
        return IconChoice.NEVER if never else IconChoice.NOT_NOW
    finally:
        box.deleteLater()
