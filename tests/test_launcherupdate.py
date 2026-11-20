# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import json

import pytest
from fakes import FakeTransport, response

from project_reforged_linux.launcherupdate import (
    RELEASES_URL,
    UpdateCheckError,
    latest_release,
    newer_launcher,
)


def release(tag: object) -> bytes:
    return json.dumps({"tag_name": tag, "name": "x"}).encode()


def test_no_release_yet() -> None:
    assert latest_release(FakeTransport(response(404))) is None


def test_reads_the_tag() -> None:
    transport = FakeTransport(response(200, release("v0.2.0")))
    assert latest_release(transport) == "0.2.0"
    assert transport.calls[0].url == RELEASES_URL
    assert transport.calls[0].headers == {"Accept": "application/vnd.github+json"}


def test_newer_only_when_newer() -> None:
    assert newer_launcher(FakeTransport(response(200, release("v0.2.0"))), "0.1.0") == "0.2.0"
    assert newer_launcher(FakeTransport(response(200, release("0.1.0"))), "0.1.0") is None
    assert newer_launcher(FakeTransport(response(404)), "0.1.0") is None


@pytest.mark.parametrize("body", [release("latest"), release(3), b"[]", b"not json"])
def test_bad_answers(body: bytes) -> None:
    with pytest.raises(UpdateCheckError):
        latest_release(FakeTransport(response(200, body)))


def test_server_error() -> None:
    with pytest.raises(UpdateCheckError, match="500"):
        latest_release(FakeTransport(response(500)))


def test_an_oversized_answer_is_refused_even_when_it_is_valid() -> None:
    body = json.dumps({"tag_name": "v0.2.0", "padding": "x" * (256 * 1024)}).encode()
    with pytest.raises(UpdateCheckError, match="larger"):
        latest_release(FakeTransport(response(200, body)))


def test_nesting_too_deep_for_json_is_a_bad_answer() -> None:
    with pytest.raises(UpdateCheckError):
        latest_release(FakeTransport(response(200, b"[" * 60_000)))
