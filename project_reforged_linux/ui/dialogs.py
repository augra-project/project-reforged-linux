# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Qt's message boxes and folder picker in the launcher's night colours.

Qt's static helpers (QMessageBox.warning, QFileDialog.getExistingDirectory) build their dialog
out of reach, so the launcher builds its own and themes it before showing it.
"""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QWidget

from project_reforged_linux.ui import theme

__all__ = ["GameFilesDialog", "choose_directory", "choose_game_files", "directory_dialog",
           "message", "message_box"]

ZIP_FILTER = "N-Gage game files (*.zip *.ZIP)"
ALL_FILTER = "All files (*)"
PICKER_SIZE = QSize(860, 520)

Button = QMessageBox.StandardButton


def message_box(parent: QWidget | None, fonts: theme.Fonts, icon: QMessageBox.Icon, title: str,
                text: str, buttons: Button = Button.Ok) -> QMessageBox:
    if not text.strip():
        raise ValueError("a message box needs a text")
    box = QMessageBox(icon, title, text, buttons, parent)
    # Server text reaches these boxes; Qt's AutoText would turn markup in it into live links.
    box.setTextFormat(Qt.TextFormat.PlainText)
    theme.apply_dialog(box, fonts)
    return box


def message(parent: QWidget | None, fonts: theme.Fonts, icon: QMessageBox.Icon, title: str,
            text: str, buttons: Button = Button.Ok) -> Button:
    """Show a themed message box and return the button the player chose."""
    box = message_box(parent, fonts, icon, title, text, buttons)
    try:
        box.exec()
        clicked = box.clickedButton()
        return Button.NoButton if clicked is None else box.standardButton(clicked)
    finally:
        box.deleteLater()


def directory_dialog(parent: QWidget | None, fonts: theme.Fonts, title: str) -> QFileDialog:
    # Where the desktop offers its own picker (a portal), Qt shows that one and the colours
    # do not apply; the player then gets the picker they know.
    dialog = QFileDialog(parent, title)
    dialog.setFileMode(QFileDialog.FileMode.Directory)
    dialog.setOption(QFileDialog.Option.ShowDirsOnly)
    theme.apply_dialog(dialog, fonts)
    return dialog


class GameFilesDialog(QFileDialog):
    """Picks the card zip, a file inside the card, or the card folder itself.

    Qt's own dialog, not the desktop's: only here does Open on a folder that holds the card
    take that folder instead of opening it.
    """

    def __init__(self, parent: QWidget | None, fonts: theme.Fonts, title: str,
                 is_card: Callable[[Path], bool]) -> None:
        super().__init__(parent, title)
        self.setFileMode(QFileDialog.FileMode.ExistingFile)
        self.setNameFilters([ZIP_FILTER, ALL_FILTER])
        self.setOption(QFileDialog.Option.DontUseNativeDialog)
        self._is_card = is_card
        self.picked = ""
        # Qt's default cut the dump's long file name short.
        self.resize(PICKER_SIZE)
        theme.apply_dialog(self, fonts)

    def accept(self) -> None:
        chosen = self.selectedFiles()
        if chosen and Path(chosen[0]).is_dir() and self._is_card(Path(chosen[0])):
            self.picked = chosen[0]
            QDialog.accept(self)
            return
        super().accept()
        if self.result() == QDialog.DialogCode.Accepted.value and self.selectedFiles():
            self.picked = self.selectedFiles()[0]


def choose_game_files(parent: QWidget | None, fonts: theme.Fonts, title: str,
                      is_card: Callable[[Path], bool]) -> str:
    """The chosen zip, file or card folder, or an empty string when the player cancels."""
    dialog = GameFilesDialog(parent, fonts, title, is_card)
    try:
        dialog.exec()
        return dialog.picked
    finally:
        dialog.deleteLater()


def choose_directory(parent: QWidget | None, fonts: theme.Fonts, title: str) -> str:
    """The chosen folder, or an empty string when the player cancels."""
    dialog = directory_dialog(parent, fonts, title)
    try:
        if dialog.exec() != QFileDialog.DialogCode.Accepted.value:
            return ""
        chosen = dialog.selectedFiles()
        return chosen[0] if chosen else ""
    finally:
        dialog.deleteLater()
