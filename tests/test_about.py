# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import re
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from project_reforged_linux import PART_NUMBER, RELEASE_DATE, __version__
from project_reforged_linux.ui import theme
from project_reforged_linux.ui.about import (
    ABOUT_TEXT,
    LICENSES,
    NOTICE_TEXT,
    TAB,
    TAB_OPEN,
    TABS,
    TITLE,
    AboutDialog,
)
from project_reforged_linux.ui.links import (
    DOSBOX_AUTOMATION_HOME,
    GAME_BOARD,
    GAME_HOME,
    LAUNCHER_HOME,
    LAUNCHER_ISSUES,
    LAUNCHER_LICENSE,
    LAUNCHER_THIRD_PARTY,
    LUDUCAT_HOME,
    LinkLabel,
    checked_url,
)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def opened() -> list[str]:
    return []


@pytest.fixture
def about(qapp, opened: list[str]) -> AboutDialog:  # type: ignore[no-untyped-def]
    d = AboutDialog(theme.load_fonts(), open_url=opened.append)
    d.show()
    QApplication.processEvents()
    yield d
    d.close()


def page_texts(d: AboutDialog) -> list[str]:
    return [label.text() for label in d.pages.currentWidget().findChildren(LinkLabel)]


def test_the_header_and_the_version_line(about: AboutDialog) -> None:
    assert about.header.title.text() == TITLE == "About the Linux Launcher"
    ident = about.ident.text()
    assert __version__ in ident and f"{PART_NUMBER}-{RELEASE_DATE}" in ident
    assert about.ident.geometry().left() == about.tabs[TABS[0]].geometry().left()


def test_the_tabs_are_about_licenses_notice(about: AboutDialog) -> None:
    assert TABS == ("About", "Licenses", "Notice")
    assert list(about.tabs) == list(TABS)
    assert about.current_tab() == "About"


@pytest.mark.parametrize("tab, text", [("About", ABOUT_TEXT), ("Notice", NOTICE_TEXT)])
def test_each_tab_shows_its_text(about: AboutDialog, tab: str, text: str) -> None:
    about.tabs[tab].click()
    assert about.current_tab() == tab
    assert text in page_texts(about)


def test_only_the_open_tab_wears_gold(about: AboutDialog) -> None:
    for tab in TABS:
        about.tabs[tab].click()
        assert [b.bezel for b in about.tabs.values()] == [
            TAB_OPEN if name == tab else TAB for name in TABS]


def test_an_unknown_tab_is_refused(about: AboutDialog) -> None:
    with pytest.raises(ValueError):
        about.show_tab("Privacy")


def test_every_link_shows_its_https_address(about: AboutDialog) -> None:
    hrefs = []
    for tab in TABS:
        about.tabs[tab].click()
        for label in about.pages.currentWidget().findChildren(LinkLabel):
            for href in re.findall(r"href='([^']*)'", label.text()):
                label.linkHovered.emit(href)
                assert label.toolTip() == href
                assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor
                checked_url(href)
                hrefs.append(href)
    assert sorted(hrefs) == sorted([GAME_BOARD, LAUNCHER_HOME, LAUNCHER_ISSUES, GAME_HOME,
                                    LAUNCHER_LICENSE, LAUNCHER_THIRD_PARTY])


def test_a_link_opens_through_the_windows_opener(about: AboutDialog, opened: list[str]) -> None:
    board = next(label for label in about.pages.currentWidget().findChildren(LinkLabel)
                 if GAME_BOARD in label.text())
    board.linkActivated.emit(GAME_BOARD)
    assert opened == [GAME_BOARD]


def test_both_logos_open_their_site(about: AboutDialog, opened: list[str]) -> None:
    for logo in about.logos:
        assert logo.cursor().shape() == Qt.CursorShape.PointingHandCursor
        assert logo.toolTip().count("\n") >= 2  # two or three lines of blurb, then the address
        QTest.mouseClick(logo, Qt.MouseButton.LeftButton)
    assert opened == [LUDUCAT_HOME, DOSBOX_AUTOMATION_HOME]


def test_the_logos_sit_at_the_boxs_right_edge(about: AboutDialog) -> None:
    box = about.pages.parentWidget()
    right = box.mapTo(about, box.rect().topRight()).x()
    last = about.logos[-1]
    assert abs(last.mapTo(about, last.rect().topRight()).x() - right) <= 2
    close = about.close_button
    centre = close.mapTo(about, close.rect().center()).x()
    left = box.mapTo(about, box.rect().topLeft()).x()
    assert abs(centre - (left + right) / 2) <= 2, "Close centred under the box"


def test_close_closes(about: AboutDialog) -> None:
    about.close_button.click()
    assert about.result() == QDialog.DialogCode.Accepted
    assert not about.isVisible()


def third_party_components() -> list[str]:
    text = (ROOT / "THIRD_PARTY_LICENSES.txt").read_text(encoding="utf-8")
    section = text.split("COMPONENTS\n", 1)[1].split("\n=====", 1)[0]
    return [line.strip() for line in section.splitlines()
            if line.strip() and not line.startswith((" ", "="))]


# Each row on the tab and the entries of THIRD_PARTY_LICENSES.txt it stands for.
ROWS = {
    "Qt for Python (PySide6)": ["Qt for Python (PySide6)"],
    "Fonts: Cinzel, EB Garamond": ["Cinzel", "EB Garamond"],
    "Lucide icons": ["Lucide icons"],
    "platformdirs": ["platformdirs"],
    "sjaandi-kista": ["sjaandi-kista"],
    "Progress line, adapted from luducat": ["luducat (progress line painting, adapted)"],
    "Logos: luducat, dosbox-automation": ["luducat application icon (About dialog, unchanged)",
                                          "dosbox-automation application icon (About dialog, "
                                          "unchanged)"],
    # The bundled Wine gets its entry with the bundle.
    "Wine (bundled runtime)": [],
}


def test_the_licenses_tab_matches_third_party_licenses() -> None:
    assert sorted(row for row, _ in LICENSES) == sorted(ROWS)
    covered = [entry for entries in ROWS.values() for entry in entries]
    assert sorted(covered) == sorted(third_party_components())


def test_the_licenses_tab_lists_every_row(about: AboutDialog) -> None:
    about.tabs["Licenses"].click()
    texts = page_texts(about)
    for what, licence in LICENSES:
        assert what in texts and licence in texts
    assert any("THIRD_PARTY_LICENSES.txt" in t for t in texts)
    assert any("GNU General Public License v3+" in t for t in texts)
