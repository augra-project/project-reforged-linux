# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""A scripted Transport for the modules that download things."""

import io
from collections.abc import Mapping
from dataclasses import dataclass

from project_reforged_linux.net import Response


@dataclass(frozen=True)
class Call:
    url: str
    headers: dict[str, str]


class FakeTransport:
    """Answers from a script of responses or exceptions and records every request."""

    def __init__(self, *script: Response | BaseException) -> None:
        self._script = list(script)
        self.calls: list[Call] = []

    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> Response:
        self.calls.append(Call(url, dict(headers)))
        if not self._script:
            raise AssertionError(f"unexpected request: {url}")
        answer = self._script.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    @property
    def unused(self) -> int:
        return len(self._script)


def response(status: int, body: bytes | io.BytesIO = b"", **headers: str) -> Response:
    """A response; header keywords use underscores (last_modified -> last-modified)."""
    stream = body if isinstance(body, io.BytesIO) else io.BytesIO(body)
    return Response(status, {k.replace("_", "-").lower(): v for k, v in headers.items()}, stream)


class Dropping(io.BytesIO):
    """A body that delivers fail_after bytes and then loses the connection."""

    def __init__(self, data: bytes, fail_after: int) -> None:
        super().__init__(data)
        self._left = fail_after

    def read(self, size: int | None = -1) -> bytes:
        if self._left <= 0:
            raise TimeoutError("connection dropped")
        want = self._left if size is None or size < 0 else min(size, self._left)
        chunk = super().read(want)
        self._left -= len(chunk)
        return chunk
