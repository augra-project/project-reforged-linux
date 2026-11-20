# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Links in the dialogs: rich-text labels and clickable logos that open the player's browser.

Every address comes from our own texts, so the launcher opens only https to the hosts below;
anything else is a mistake in those texts, and it refuses that loudly instead of handing it on.
"""

import html
import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QMouseEvent
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QLabel, QWidget

from project_reforged_linux.ui import theme

__all__ = ["DOSBOX_AUTOMATION_HOME", "GAME_BOARD", "GAME_HOME", "KNOWN_HOSTS", "LAUNCHER_HOME",
           "LAUNCHER_ISSUES", "LAUNCHER_LICENSE", "LAUNCHER_THIRD_PARTY", "LOGO_SIZE",
           "LUDUCAT_HOME", "LinkLabel", "LogoLink", "UrlOpener", "anchor", "checked_url",
           "open_in_browser"]

logger = logging.getLogger(__name__)

KNOWN_HOSTS = frozenset({
    "github.com",  # the launcher's repository, issues and licence texts
    "project-reforged.danwhelan.ie",  # Dan's site and board
    "luducat.org",
    "www.dosbox-automation.org",
})
LOGO_SIZE = 38

LAUNCHER_HOME = "https://github.com/augra-project/project-reforged-linux-launcher"
LAUNCHER_ISSUES = f"{LAUNCHER_HOME}/issues"
LAUNCHER_LICENSE = f"{LAUNCHER_HOME}/blob/main/LICENSE"
LAUNCHER_THIRD_PARTY = f"{LAUNCHER_HOME}/blob/main/THIRD_PARTY_LICENSES.txt"
GAME_HOME = "https://project-reforged.danwhelan.ie/"
GAME_BOARD = "https://project-reforged.danwhelan.ie/board/"
LUDUCAT_HOME = "https://luducat.org/"
DOSBOX_AUTOMATION_HOME = "https://www.dosbox-automation.org/"
UrlOpener = Callable[[str], object]


def checked_url(url: str) -> QUrl:
    """The address as a QUrl, or ValueError when it is not https to a known host."""
    parsed = QUrl(url, QUrl.ParsingMode.StrictMode)
    if (not parsed.isValid() or parsed.scheme() != "https" or parsed.host() not in KNOWN_HOSTS
            or parsed.userInfo() or parsed.port() != -1):
        raise ValueError(f"not a link the launcher opens: {url!r}")
    return parsed


def open_in_browser(url: str) -> bool:
    checked = checked_url(url)
    logger.info("opening %s", url)
    return QDesktopServices.openUrl(checked)


def anchor(text: str, url: str) -> str:
    """A gold link without underline; `text` is our own rich text and goes in unescaped."""
    if not text.strip():
        raise ValueError("a link needs a text")
    checked_url(url)
    href = html.escape(url, quote=True)
    return f"<a style='color:{theme.GOLD_HI}; text-decoration:none' href='{href}'>{text}</a>"


class LinkLabel(QLabel):
    """Rich text whose links show their address on hover and open in the browser."""

    def __init__(self, text: str, name: str = "body", *, wrap: bool = True,
                 open_url: UrlOpener = open_in_browser, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName(name)
        self.setWordWrap(wrap)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setOpenExternalLinks(False)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._open_url = open_url
        self.linkHovered.connect(self._hovered)
        self.linkActivated.connect(self._activated)

    def _hovered(self, link: str) -> None:
        if link:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(link)
        else:
            self.unsetCursor()
            self.setToolTip("")

    def _activated(self, link: str) -> None:
        try:
            checked_url(link)
        except ValueError:
            logger.error("refused to open a dialog link: %r", link)
            return
        self._open_url(link)


class LogoLink(QSvgWidget):
    """A sister project's logo; a click opens its site, the tooltip says what it is."""

    def __init__(self, path: Path, url: str, blurb: str, *, size: int = LOGO_SIZE,
                 open_url: UrlOpener = open_in_browser, parent: QWidget | None = None) -> None:
        if not blurb.strip():
            raise ValueError("a logo needs a tooltip text")
        if size <= 0:
            raise ValueError(f"logo size must be positive, got {size}")
        checked_url(url)
        super().__init__(str(path), parent)
        if not self.renderer().isValid():
            raise ValueError(f"not a usable SVG: {path}")
        self.url = url
        self._open_url = open_url
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{blurb}\n{url}")

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt's name)
        # Like a button: only a release over the logo counts, so dragging off cancels.
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self._open_url(self.url)
            event.accept()
            return
        super().mouseReleaseEvent(event)
