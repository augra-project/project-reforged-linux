# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import logging
from html.parser import HTMLParser
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from project_reforged_linux.ui import links
from project_reforged_linux.ui.assets import DOSBOX_AUTOMATION_LOGO, LUDUCAT_LOGO
from project_reforged_linux.ui.links import LinkLabel, LogoLink, anchor, checked_url

BOARD = "https://project-reforged.danwhelan.ie/board/"
LUDUCAT = "https://luducat.org/"


class Opened:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> bool:
        self.urls.append(url)
        return True


@pytest.mark.parametrize("url", [
    BOARD, LUDUCAT, "https://www.dosbox-automation.org/",
    "https://github.com/augra-project/project-reforged-linux-launcher/issues",
    "https://GitHub.com/augra-project",  # hosts compare lower case
])
def test_known_https_links_pass(url: str) -> None:
    assert checked_url(url).scheme() == "https"


@pytest.mark.parametrize("url", [
    "", "#", "board/", "http://luducat.org/", "ftp://github.com/x", "file:///etc/passwd",
    "javascript:alert(1)", "https://example.org/", "https://github.com.example.org/",
    "https://evil.example/github.com", "https://user@github.com/", "https://github.com:8443/",
    "https://luducat.org\x00.example/", "https://dosbox-automation.org/",
    " https://luducat.org/",
])
def test_everything_else_is_refused(url: str) -> None:
    with pytest.raises(ValueError):
        checked_url(url)


def test_the_hosts_are_ours_and_dans() -> None:
    assert links.KNOWN_HOSTS == {"github.com", "project-reforged.danwhelan.ie", "luducat.org",
                                 "www.dosbox-automation.org"}


def href_of(markup: str) -> str:
    found: list[str] = []

    class Parser(HTMLParser):
        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            found.extend(value or "" for name, value in attrs if tag == "a" and name == "href")

    Parser().feed(markup)
    assert len(found) == 1, markup
    return found[0]


def test_anchor_carries_the_address_intact() -> None:
    # A quote in the path must not end the attribute early.
    url = "https://github.com/augra-project/it's"
    markup = anchor("<i>it</i>", url)
    assert href_of(markup) == url
    assert "<i>it</i>" in markup


@pytest.mark.parametrize("text, url", [("", BOARD), ("  ", BOARD), ("board", "http://x.org/")])
def test_anchor_refuses_empty_text_and_foreign_links(text: str, url: str) -> None:
    with pytest.raises(ValueError):
        anchor(text, url)


def test_hovering_a_link_shows_its_address_and_a_hand(qapp) -> None:  # type: ignore[no-untyped-def]
    label = LinkLabel(f"Visit {anchor('his board', BOARD)}")
    label.linkHovered.emit(BOARD)
    assert label.toolTip() == BOARD
    assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor
    label.linkHovered.emit("")
    assert label.toolTip() == ""
    assert label.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_a_link_opens_through_the_given_opener(qapp) -> None:  # type: ignore[no-untyped-def]
    opened = Opened()
    label = LinkLabel(anchor("board", BOARD), open_url=opened)
    label.linkActivated.emit(BOARD)
    assert opened.urls == [BOARD]


@pytest.mark.parametrize("href", ["http://project-reforged.danwhelan.ie/board/",
                                  "file:///home", "https://example.org/"])
def test_a_foreign_href_is_refused_and_logged(qapp, caplog, href: str) -> None:  # type: ignore[no-untyped-def]
    opened = Opened()
    label = LinkLabel(f"<a href='{href}'>x</a>", open_url=opened)
    with caplog.at_level(logging.ERROR, logger=links.__name__):
        label.linkActivated.emit(href)
    assert opened.urls == []
    assert href in caplog.text


def test_the_label_never_opens_links_itself(qapp) -> None:  # type: ignore[no-untyped-def]
    label = LinkLabel("x")
    assert not label.openExternalLinks()
    assert label.textFormat() == Qt.TextFormat.RichText
    assert label.textInteractionFlags() == Qt.TextInteractionFlag.LinksAccessibleByMouse


@pytest.mark.parametrize("path", [LUDUCAT_LOGO, DOSBOX_AUTOMATION_LOGO])
def test_the_packaged_logos_render(qapp, path: Path) -> None:  # type: ignore[no-untyped-def]
    logo = LogoLink(path, LUDUCAT, "a blurb")
    assert logo.renderer().isValid()
    assert logo.size().width() == links.LOGO_SIZE == logo.size().height()


def test_a_logo_shows_its_blurb_and_address(qapp) -> None:  # type: ignore[no-untyped-def]
    logo = LogoLink(LUDUCAT_LOGO, LUDUCAT, "luducat - your game catalogue\nkept at home")
    assert logo.toolTip() == f"luducat - your game catalogue\nkept at home\n{LUDUCAT}"
    assert logo.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_a_click_on_a_logo_opens_its_site(qapp) -> None:  # type: ignore[no-untyped-def]
    opened = Opened()
    logo = LogoLink(LUDUCAT_LOGO, LUDUCAT, "luducat", open_url=opened)
    QTest.mouseClick(logo, Qt.MouseButton.LeftButton)
    assert opened.urls == [LUDUCAT]


def test_only_a_left_release_over_the_logo_counts(qapp) -> None:  # type: ignore[no-untyped-def]
    opened = Opened()
    logo = LogoLink(LUDUCAT_LOGO, LUDUCAT, "luducat", open_url=opened)
    QTest.mouseClick(logo, Qt.MouseButton.RightButton)
    QTest.mousePress(logo, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    QTest.mouseRelease(logo, Qt.MouseButton.LeftButton, pos=QPoint(links.LOGO_SIZE + 20, 5))
    assert opened.urls == []


def test_a_logo_refuses_bad_input(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    broken = tmp_path / "broken.svg"
    broken.write_text("<svg", encoding="utf-8")
    for args, kwargs in (
            ((LUDUCAT_LOGO, "http://luducat.org/", "x"), {}),
            ((LUDUCAT_LOGO, LUDUCAT, " "), {}),
            ((LUDUCAT_LOGO, LUDUCAT, "x"), {"size": 0}),
            ((broken, LUDUCAT, "x"), {}),
            ((tmp_path / "missing.svg", LUDUCAT, "x"), {})):
        with pytest.raises(ValueError):
            LogoLink(*args, **kwargs)


def test_open_in_browser_refuses_before_reaching_the_desktop(qapp, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    reached: list[object] = []
    monkeypatch.setattr(links.QDesktopServices, "openUrl", lambda url: reached.append(url))
    with pytest.raises(ValueError):
        links.open_in_browser("file:///etc/passwd")
    links.open_in_browser(BOARD)
    assert [url.toString() for url in reached] == [BOARD]


def test_an_opened_link_is_logged_once(qapp, monkeypatch, caplog) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(links.QDesktopServices, "openUrl", lambda url: True)
    label = LinkLabel(anchor("board", BOARD))
    logo = LogoLink(LUDUCAT_LOGO, LUDUCAT, "luducat")
    with caplog.at_level(logging.INFO, logger=links.__name__):
        label.linkActivated.emit(BOARD)
        QTest.mouseClick(logo, Qt.MouseButton.LeftButton)
    assert caplog.text.count(f"opening {BOARD}") == 1
    assert caplog.text.count(f"opening {LUDUCAT}") == 1
