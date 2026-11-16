# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import socket
import urllib.request

import pytest

from project_reforged_linux import __version__
from project_reforged_linux.net import (
    GAME_HOSTS,
    GITHUB_HOST,
    USER_AGENT,
    HostRefused,
    Net,
    _CheckedRedirects,
    for_launcher,
)

SITE = "https://project-reforged.danwhelan.ie/update/win.json"


def test_guard_is_active() -> None:
    with pytest.raises(RuntimeError):
        socket.create_connection(("127.0.0.1", 9))


@pytest.mark.parametrize("url", [
    SITE,
    "https://shadowkey.omracreative.ie/downloads/x.zip",
    "https://PROJECT-REFORGED.danwhelan.ie/update/win.json",
    "https://project-reforged.danwhelan.ie:443/update/win.json",
])
def test_allowed_urls(url: str) -> None:
    Net(GAME_HOSTS).check_url(url)


@pytest.mark.parametrize("url", [
    "http://project-reforged.danwhelan.ie/update/win.json",
    "https://example.org/",
    "https://danwhelan.ie/",
    "https://evil.project-reforged.danwhelan.ie.example.org/",
    "https://user:pw@project-reforged.danwhelan.ie/",
    "https://project-reforged.danwhelan.ie:8443/",
    "https://project-reforged.danwhelan.ie:notaport/",
    "file:///etc/passwd",
    "ftp://project-reforged.danwhelan.ie/",
])
def test_refused_urls(url: str) -> None:
    with pytest.raises(HostRefused):
        Net(GAME_HOSTS).check_url(url)


def test_get_refuses_before_connecting() -> None:
    # The guard would raise RuntimeError if a socket were opened.
    with pytest.raises(HostRefused):
        Net(GAME_HOSTS).get("https://example.org/", {}, 5.0)


def test_github_only_when_turned_on() -> None:
    url = f"https://{GITHUB_HOST}/repos/x/y/releases/latest"
    with pytest.raises(HostRefused):
        for_launcher(check_launcher_updates=False).check_url(url)
    for_launcher(check_launcher_updates=True).check_url(url)
    assert for_launcher(check_launcher_updates=False).hosts == GAME_HOSTS


def test_redirect_to_a_foreign_host_is_refused() -> None:
    handler = _CheckedRedirects(Net(GAME_HOSTS).check_url)
    request = urllib.request.Request("https://shadowkey.omracreative.ie/downloads/a.zip")
    with pytest.raises(HostRefused):
        handler.redirect_request(request, None, 301, "Moved", {}, "https://example.org/a.zip")


def test_redirect_between_his_hosts_is_followed() -> None:
    handler = _CheckedRedirects(Net(GAME_HOSTS).check_url)
    request = urllib.request.Request("https://shadowkey.omracreative.ie/downloads/a.zip",
                                     headers={"Range": "bytes=10-"})
    new = handler.redirect_request(request, None, 301, "Moved", {},
                                   "https://project-reforged.danwhelan.ie/downloads/a.zip")
    assert new.full_url == "https://project-reforged.danwhelan.ie/downloads/a.zip"
    assert new.get_header("Range") == "bytes=10-"


def test_no_hosts_is_an_error() -> None:
    with pytest.raises(ValueError):
        Net([])


def test_user_agent_names_only_the_launcher_and_version() -> None:
    assert USER_AGENT == f"project-reforged-linux/{__version__}"
