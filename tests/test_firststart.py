# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import gc

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from project_reforged_linux.desktop import is_gnome
from project_reforged_linux.ui import theme
from project_reforged_linux.ui.firststart import (
    GITHUB_NOTE,
    FirstStart,
    FirstStartDialog,
    IconChoice,
    ask_icon,
    icon_question,
)
from project_reforged_linux.ui.links import GAME_HOME, LinkLabel


def first_start(offer_icon: bool = True, opened: list[str] | None = None) -> FirstStartDialog:
    sink = opened if opened is not None else []
    d = FirstStartDialog(theme.load_fonts(), offer_icon=offer_icon, open_url=sink.append)
    d.show()
    QApplication.processEvents()
    return d


def test_continue_with_nothing_touched_opts_into_nothing(qapp) -> None:  # type: ignore[no-untyped-def]
    d = first_start()
    assert not d.updates.isChecked() and d.not_now.isChecked()
    d.continue_button.click()
    assert d.answer == FirstStart(False, IconChoice.NOT_NOW)


def test_ticked_updates_and_install(qapp) -> None:  # type: ignore[no-untyped-def]
    d = first_start()
    d.updates.setChecked(True)
    d.install_icon.click()
    assert not d.never.isEnabled(), "Don't ask again belongs to Not now"
    d.continue_button.click()
    assert d.answer == FirstStart(True, IconChoice.INSTALL)


def test_not_now_remembered(qapp) -> None:  # type: ignore[no-untyped-def]
    d = first_start()
    d.never.setChecked(True)
    d.continue_button.click()
    assert d.answer == FirstStart(False, IconChoice.NEVER)


def test_closing_it_opts_into_nothing(qapp) -> None:  # type: ignore[no-untyped-def]
    d = first_start()
    d.updates.setChecked(True)
    d.install_icon.click()
    d.reject()
    assert d.answer == FirstStart(False, IconChoice.NOT_NOW)


def test_no_icon_offer_off_gnome(qapp) -> None:  # type: ignore[no-untyped-def]
    d = first_start(offer_icon=False)
    assert not d.install_icon.isVisible() and not d.never.isVisible()
    d.continue_button.click()
    assert d.answer == FirstStart(False, None)


def test_it_says_what_github_sees_and_links_his_site(qapp) -> None:  # type: ignore[no-untyped-def]
    opened: list[str] = []
    d = first_start(opened=opened)
    texts = [label.text() for label in d.findChildren(LinkLabel)]
    assert GITHUB_NOTE in texts
    assert "IP address" in GITHUB_NOTE and "version" in GITHUB_NOTE
    welcome = next(label for label in d.findChildren(LinkLabel) if GAME_HOME in label.text())
    welcome.linkActivated.emit(GAME_HOME)
    assert opened == [GAME_HOME]


def test_the_icon_question_keeps_its_checkbox(qapp) -> None:  # type: ignore[no-untyped-def]
    # A temporary QCheckBox handed to setCheckBox was collected and the box crashed on it.
    box = icon_question(None, theme.load_fonts())
    gc.collect()
    box.show()
    QApplication.processEvents()
    checkbox = box.checkBox()
    assert checkbox is not None and checkbox.text() == "Don't ask again" and checkbox.isVisible()
    assert sorted(b.text() for b in box.buttons()) == ["Install", "Not now"]
    box.close()


def answer_with(button_text: str, never: bool = False) -> None:
    def answer() -> None:
        box = QApplication.activeModalWidget()
        assert isinstance(box, QMessageBox)
        box.checkBox().setChecked(never)
        next(b for b in box.buttons() if b.text() == button_text).click()

    QTimer.singleShot(0, answer)


@pytest.mark.modal
@pytest.mark.parametrize("button, never, choice", [
    ("Install", False, IconChoice.INSTALL), ("Not now", False, IconChoice.NOT_NOW),
    ("Not now", True, IconChoice.NEVER), ("Install", True, IconChoice.INSTALL)])
def test_ask_icon_reads_the_answer(qapp, button: str, never: bool, choice: IconChoice) -> None:  # type: ignore[no-untyped-def]
    answer_with(button, never)
    assert ask_icon(None, theme.load_fonts()) is choice


@pytest.mark.parametrize("value, gnome", [
    ("GNOME", True), ("ubuntu:GNOME", True), ("pop:GNOME", True), ("gnome", True),
    ("KDE", False), ("", False), ("GNOME-Flashback:Unity", False), ("XFCE", False)])
def test_is_gnome(value: str, gnome: bool) -> None:
    assert is_gnome({"XDG_CURRENT_DESKTOP": value}) is gnome
    assert is_gnome({}) is False
