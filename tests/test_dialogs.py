# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox
from qtcheck import check_night

from project_reforged_linux.ui import dialogs, theme
from project_reforged_linux.ui.window import MainWindow

Button = QMessageBox.StandardButton


@pytest.fixture
def window(qapp) -> MainWindow:  # type: ignore[no-untyped-def]
    w = MainWindow(None)
    w.show()
    return w


def test_a_message_box_over_the_window_is_dark(window: MainWindow) -> None:
    box = dialogs.message_box(window, window.fonts, QMessageBox.Icon.Warning, "T",
                              "no 6R51 folder in /home/x/Downloads")
    check_night(box, window.fonts)


def test_the_folder_dialog_over_the_window_is_dark(window: MainWindow) -> None:
    dialog = dialogs.directory_dialog(window, window.fonts, "Locate the original game files")
    # Offscreen there is no portal; set it anyway so the test never depends on the desktop.
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
    assert dialog.fileMode() == QFileDialog.FileMode.Directory
    assert dialog.testOption(QFileDialog.Option.ShowDirsOnly)
    check_night(dialog, window.fonts)


@pytest.mark.modal
def test_message_returns_the_chosen_button(window: MainWindow) -> None:
    def answer() -> None:
        box = QApplication.activeModalWidget()
        assert isinstance(box, QMessageBox)
        box.button(Button.No).click()

    QTimer.singleShot(0, answer)
    chosen = dialogs.message(window, window.fonts, QMessageBox.Icon.Question, "T", "Start?",
                             Button.Yes | Button.No)
    assert chosen == Button.No


@pytest.mark.modal
def test_choose_directory_is_empty_when_cancelled(window: MainWindow) -> None:
    def cancel() -> None:
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QFileDialog)
        dialog.reject()

    QTimer.singleShot(0, cancel)
    assert dialogs.choose_directory(window, window.fonts, "Locate") == ""


def test_a_message_needs_a_text(window: MainWindow) -> None:
    with pytest.raises(ValueError):
        dialogs.message_box(window, window.fonts, QMessageBox.Icon.Warning, "T", "  ")


@pytest.mark.parametrize("base_pt", [0, -3])
def test_apply_dialog_refuses_empty_sizes(qapp, base_pt: int) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        theme.apply_dialog(QDialog(), theme.load_fonts(), base_pt)


def test_greyed_dialog_text_is_dimmer_than_the_text() -> None:
    palette = theme.dialog_palette()
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        dimmed = palette.color(QPalette.ColorGroup.Disabled, role)
        normal = palette.color(QPalette.ColorGroup.Active, role)
        assert dimmed.lightness() < normal.lightness() - 40, role


def game_files_dialog(window: MainWindow, cards: set[Path]) -> dialogs.GameFilesDialog:
    return dialogs.GameFilesDialog(window, window.fonts, "Locate", lambda p: p in cards)


def test_the_picker_shows_zips_first_in_qts_own_dialog(window: MainWindow) -> None:
    d = game_files_dialog(window, set())
    assert d.nameFilters()[0] == dialogs.ZIP_FILTER and "*.zip" in dialogs.ZIP_FILTER
    assert d.fileMode() == QFileDialog.FileMode.ExistingFile
    assert d.testOption(QFileDialog.Option.DontUseNativeDialog)
    check_night(d, window.fonts)


def test_open_on_a_card_folder_takes_the_folder(window: MainWindow, tmp_path: Path) -> None:
    card = tmp_path / "ngage-files"
    card.mkdir()
    d = game_files_dialog(window, {card})
    d.setDirectory(str(tmp_path))
    d.selectFile(str(card))
    d.accept()
    assert d.result() == QDialog.DialogCode.Accepted.value and d.picked == str(card)


def test_open_on_another_folder_opens_it(window: MainWindow, tmp_path: Path) -> None:
    folder = tmp_path / "Downloads"
    folder.mkdir()
    d = game_files_dialog(window, set())
    d.show()
    d.setDirectory(str(tmp_path))
    d.selectFile(str(folder))
    d.accept()
    assert d.picked == "" and d.isVisible(), "a plain folder is entered, not taken"
    d.hide()


def test_open_on_a_zip_takes_the_zip(window: MainWindow, tmp_path: Path) -> None:
    archive = tmp_path / "Shadowkey_Files.zip"
    archive.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    d = game_files_dialog(window, set())
    d.setDirectory(str(tmp_path))
    d.selectFile(str(archive))
    d.accept()
    assert d.result() == QDialog.DialogCode.Accepted.value and d.picked == str(archive)


@pytest.mark.modal
def test_a_message_box_is_deleted_after_its_answer(window: MainWindow) -> None:
    from PySide6.QtCore import QCoreApplication, QEvent

    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().accept())
    dialogs.message(window, window.fonts, QMessageBox.Icon.Information, "T", "Done.")
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert window.findChildren(QMessageBox) == []


def test_a_message_shows_markup_as_text(window: MainWindow) -> None:
    # Server text reaches these boxes; a link in it must not become clickable.
    box = dialogs.message_box(window, window.fonts, QMessageBox.Icon.Warning, "T",
                              "url outside his sites: <a href='https://phish.example/'>repair</a>")
    assert box.textFormat() == Qt.TextFormat.PlainText
