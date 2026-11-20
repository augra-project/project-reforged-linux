# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The launcher's only way onto the network: HTTPS to a fixed list of hosts."""

import http.client
import logging
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from email.message import Message
from typing import Protocol
from urllib.parse import urlsplit

from project_reforged_linux import __version__

__all__ = ["GAME_HOSTS", "GITHUB_HOST", "USER_AGENT", "Body", "HostRefused", "Net", "Response",
           "Transport", "for_launcher"]

logger = logging.getLogger(__name__)

# His site since 2026-11-15, and the old one that still answers.
GAME_HOSTS: frozenset[str] = frozenset({"project-reforged.danwhelan.ie",
                                        "shadowkey.omracreative.ie"})
GITHUB_HOST = "api.github.com"
USER_AGENT = f"project-reforged-linux/{__version__}"
MAX_REDIRECTS = 3


class HostRefused(Exception):
    """A URL that is not HTTPS to an allowed host."""


class Body(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: Mapping[str, str]  # names in lower case
    body: Body

    def close(self) -> None:
        self.body.close()


class Transport(Protocol):
    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> Response: ...


class _SafeBody:
    """Turns http.client's protocol errors into ConnectionError, which callers already handle."""

    def __init__(self, raw: Body) -> None:
        self._raw = raw

    def read(self, size: int = -1, /) -> bytes:
        try:
            return self._raw.read(size)
        except http.client.HTTPException as error:
            raise ConnectionError(f"broken response: {error!r}") from error

    def close(self) -> None:
        self._raw.close()


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def __init__(self, check: Callable[[str], None]) -> None:
        super().__init__()
        self._check = check

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self._check(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _lower(message: Message) -> dict[str, str]:
    return {name.lower(): value for name, value in message.items()}


class Net:
    def __init__(self, hosts: Iterable[str]) -> None:
        self._hosts = frozenset(host.lower() for host in hosts)
        if not self._hosts:
            raise ValueError("no hosts allowed")
        opener = urllib.request.OpenerDirector()
        for handler in (urllib.request.ProxyHandler(),
                        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
                        _CheckedRedirects(self.check_url),
                        urllib.request.HTTPDefaultErrorHandler(),
                        urllib.request.HTTPErrorProcessor(),
                        urllib.request.UnknownHandler()):
            opener.add_handler(handler)
        self._opener = opener

    @property
    def hosts(self) -> frozenset[str]:
        return self._hosts

    def check_url(self, url: str) -> None:
        try:
            parts = urlsplit(url)
        except ValueError as error:
            logger.warning("refused an address urllib cannot split: %r", url)
            raise HostRefused(f"not an allowed address: {url!r}") from error
        try:
            port = parts.port
        except ValueError:
            port = -1
        host = (parts.hostname or "").lower()
        if (parts.scheme != "https" or host not in self._hosts or parts.username is not None
                or parts.password is not None or port not in (None, 443)):
            logger.warning("refused a connection to %s", url)
            raise HostRefused(f"not an allowed address: {url}")

    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> Response:
        self.check_url(url)
        # Scheme and host are checked above.
        request = urllib.request.Request(  # noqa: S310  # nosec B310
            url, headers={**headers, "User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
        try:
            raw = self._opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            return Response(error.code, _lower(error.headers), _SafeBody(error))
        except http.client.HTTPException as error:
            # A garbled status line or oversized headers are no OSError; the callers catch those.
            raise ConnectionError(f"broken response: {error!r}") from error
        return Response(raw.status, _lower(raw.headers), _SafeBody(raw))


def for_launcher(check_launcher_updates: bool) -> Net:
    """His sites always; GitHub only when the player turned the launcher update check on."""
    hosts = set(GAME_HOSTS)
    if check_launcher_updates:
        hosts.add(GITHUB_HOST)
    return Net(hosts)
