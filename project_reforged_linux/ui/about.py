# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The About dialog: who made what, the licences, and the notice.

The texts follow the launcher design's About section.
"""

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from project_reforged_linux import GAME_NAME, LAUNCHER_NAME, PART_NUMBER, RELEASE_DATE, __version__
from project_reforged_linux.ui import theme
from project_reforged_linux.ui.assets import DOSBOX_AUTOMATION_LOGO, LUDUCAT_LOGO
from project_reforged_linux.ui.bezel import GOLD, SMALL, BezelButton, BezelStyle, Panel
from project_reforged_linux.ui.dialogframe import ACROSS, TOWER_RIGHT, ThemedDialog
from project_reforged_linux.ui.links import (
    DOSBOX_AUTOMATION_HOME,
    GAME_BOARD,
    GAME_HOME,
    LAUNCHER_HOME,
    LAUNCHER_ISSUES,
    LAUNCHER_LICENSE,
    LAUNCHER_THIRD_PARTY,
    LOGO_SIZE,
    LUDUCAT_HOME,
    LinkLabel,
    LogoLink,
    UrlOpener,
    anchor,
    open_in_browser,
)

__all__ = ["ABOUT_TEXT", "CREDITS", "LICENSES", "LOGOS", "NOTICE_TEXT", "TABS", "TITLE",
           "AboutDialog"]

TITLE = "About the Linux Launcher"
TABS = ("About", "Licenses", "Notice")
TAB: BezelStyle = replace(SMALL, height=30)
TAB_OPEN: BezelStyle = replace(GOLD, height=30, radius=3.0)
TAB_WIDTH = 110
TOWER_ROOM = 220  # the tower on the right stays free of text
CLOSE_WIDTH = 130
LOGO_GAP = 8

_P = "<p style='margin:0 0 9px 0'>"
_H = "<p style='margin:0 0 3px 0'><b>"
ABOUT_TEXT = (
    f"{_P}This is a launcher for Dan Whelan's free fan port of <i>The Elder Scrolls Travels: "
    "Shadowkey</i> (by Bethesda and ZeniMax).</p>"
    f"{_P}It is meant to make starting the game on Linux painless and smooth: it sets up a "
    "proper runtime environment and picks the most compatible version of his build.</p>"
    f"{_P}The launcher provides neither the game itself nor the original N-Gage game files.</p>"
    "<p style='margin:0'>For help with the game, please visit Dan Whelan's message board:<br>"
    f"{anchor('project-reforged.danwhelan.ie/board/', GAME_BOARD)}</p>")
CREDITS = (
    "The Elder Scrolls Travels: Shadowkey (c) 2004 ZeniMax Media Inc. and Bethesda Softworks "
    f"LLC<br>{GAME_NAME} (c) 2026 Dan Whelan<br>{LAUNCHER_NAME} (c) 2026 The Augra Project")
LINKS = (f"{anchor('Launcher homepage', LAUNCHER_HOME)} &nbsp;&middot;&nbsp; "
         f"{anchor('Report a launcher issue', LAUNCHER_ISSUES)} &nbsp;&middot;&nbsp; "
         f"{anchor('Game homepage', GAME_HOME)}")
NOTICE_TEXT = (
    f"{_H}The Linux Launcher</b></p>"
    f"{_P}This is a standalone convenience application for starting the game easily on Linux. "
    "It is not associated with Dan Whelan's fan project and is not the same product. Do not "
    "bundle it with the game.</p>"
    f"{_H}{GAME_NAME}</b></p>"
    f"{_P}A fan recreation of <i>The Elder Scrolls Travels: Shadowkey</i> for the PC, not "
    "associated with the makers of the original game.</p>"
    f"{_H}The original N-Gage game</b></p>"
    "<p style='margin:0'>The original N-Gage game files of The Elder Scrolls Travels: "
    "Shadowkey belong to ZeniMax Media Inc. They are not part of this program, and this "
    "license grants no rights to them. Every player brings their own copy. This launcher is not "
    "affiliated with them, and the game is neither distributed nor bundled with it.</p>")
# What ships, in THIRD_PARTY_LICENSES.txt's words.
LICENSES = (
    ("Qt for Python (PySide6)", "LGPL-3.0-only"),
    ("Wine (bundled runtime)", "LGPL-2.1-or-later"),
    ("Fonts: Cinzel, EB Garamond", "SIL Open Font License 1.1"),
    ("Lucide icons", "ISC, parts MIT"),
    ("platformdirs", "MIT"),
    ("sjaandi-kista", "GPL-3.0-or-later"),
    ("Logos: luducat, dosbox-automation", "GPL-3.0+, GPL-2.0+"),
    ("Progress line, adapted from luducat", "GPL-3.0-or-later"),
    ("AppImage runtime libraries", "PSF, Apache, MIT, BSD, MPL, LGPL"),
)
LOGOS = (
    (LUDUCAT_LOGO, LUDUCAT_HOME,
     "luducat - your cross-platform game catalogue: one library for Steam,\n"
     "GOG, Epic and more, kept on your own machine. No accounts, no telemetry."),
    (DOSBOX_AUTOMATION_LOGO, DOSBOX_AUTOMATION_HOME,
     "dosbox-automation - a safer DOSBox with an HTTP API, sandboxed Lua\n"
     "scripting, frame-accurate input recording, and games that run\n"
     "straight from their zip files."),
)


class AboutDialog(ThemedDialog):
    def __init__(self, fonts: theme.Fonts, *, open_url: UrlOpener = open_in_browser,
                 parent: QWidget | None = None) -> None:
        super().__init__(fonts, TITLE, cut=TOWER_RIGHT, shade=ACROSS, parent=parent)
        self._open_url = open_url
        body = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(8)
        body.addLayout(column, 1)
        body.addSpacing(TOWER_ROOM)
        self.content.addLayout(body, 1)

        self.ident = self._label(f"Version {__version__} &nbsp;&middot;&nbsp; "
                                 f"{PART_NUMBER}-{RELEASE_DATE}", "ident", wrap=False)
        column.addWidget(self.ident, 0, Qt.AlignmentFlag.AlignLeft)
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self.tabs: dict[str, BezelButton] = {}
        # A group hands the clicked tab's index to a bound method; a lambda over self would
        # keep the dialog for Python's cycle collector (see MainWindow._wire).
        self._tab_group = QButtonGroup(self)
        for index, name in enumerate(TABS):
            button = BezelButton(name, style=TAB)
            button.setObjectName("rowButton")
            button.setMinimumWidth(TAB_WIDTH)
            self._tab_group.addButton(button, index)
            tabs.addWidget(button)
            self.tabs[name] = button
        self._tab_group.idClicked.connect(self._tab_clicked)
        tabs.addStretch(1)
        column.addLayout(tabs)

        panel = Panel()
        self.pages = QStackedWidget()
        for page in (self._about_page(), self._licenses_page(), self._notice_page()):
            self.pages.addWidget(page)
        panel.box.addWidget(self.pages)
        column.addWidget(panel, 1)
        column.addLayout(self._close_row())
        self.show_tab(TABS[0])

    def _label(self, text: str, name: str = "body", *, wrap: bool = True) -> LinkLabel:
        return LinkLabel(text, name, wrap=wrap, open_url=self._open_url)

    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        return page, column

    def _about_page(self) -> QWidget:
        page, column = self._page()
        column.addWidget(self._label(ABOUT_TEXT))
        column.addStretch(1)
        column.addWidget(self._label(CREDITS, "notice"))
        column.addSpacing(4)
        column.addWidget(self._label(LINKS, "notice"))
        return page

    def _licenses_page(self) -> QWidget:
        page, column = self._page()
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(3)  # eight rows above the licence links
        grid.addWidget(self._label(LAUNCHER_NAME, wrap=False), 0, 0)
        grid.addWidget(self._label("GPL-3.0-or-later, 7(b) notices", "hint", wrap=False), 0, 1)
        grid.setRowMinimumHeight(1, 10)
        for row, (what, licence) in enumerate(LICENSES, start=2):
            grid.addWidget(self._label(what, wrap=False), row, 0)
            grid.addWidget(self._label(licence, "hint", wrap=False), row, 1)
        column.addLayout(grid)
        column.addStretch(1)
        column.addWidget(self._label(anchor("GNU General Public License v3+", LAUNCHER_LICENSE)))
        column.addWidget(self._label(
            "The full texts of the others are in "
            f"{anchor('THIRD_PARTY_LICENSES.txt', LAUNCHER_THIRD_PARTY)}.", "small"))
        return page

    def _notice_page(self) -> QWidget:
        page, column = self._page()
        column.addWidget(self._label(NOTICE_TEXT, "notice"))
        column.addStretch(1)
        return page

    def _close_row(self) -> QHBoxLayout:
        logos = QWidget()
        logo_row = QHBoxLayout(logos)
        logo_row.setContentsMargins(0, 0, 0, 0)
        logo_row.setSpacing(LOGO_GAP)
        self.logos = [LogoLink(path, url, blurb, open_url=self._open_url)
                      for path, url, blurb in LOGOS]
        for logo in self.logos:
            logo_row.addWidget(logo)
        balance = QWidget()
        balance.setFixedWidth(len(LOGOS) * LOGO_SIZE + (len(LOGOS) - 1) * LOGO_GAP)
        self.close_button = BezelButton("Close", style=SMALL)
        self.close_button.setObjectName("close")
        self.close_button.setMinimumWidth(CLOSE_WIDTH)
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(balance)
        row.addStretch(1)
        row.addWidget(self.close_button)
        row.addStretch(1)
        row.addWidget(logos, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _tab_clicked(self, index: int) -> None:
        self.show_tab(TABS[index])

    def show_tab(self, name: str) -> None:
        if name not in TABS:
            raise ValueError(f"no such tab: {name!r}")
        self.pages.setCurrentIndex(TABS.index(name))
        for tab, button in self.tabs.items():
            button.bezel = TAB_OPEN if tab == name else TAB
            button.update()

    def current_tab(self) -> str:
        return TABS[self.pages.currentIndex()]
