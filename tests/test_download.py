# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import hashlib
import io
import json
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest
from fakes import Dropping, FakeTransport, response

from project_reforged_linux.download import (
    FIRST_PAUSE,
    DownloadError,
    Expected,
    RateLimited,
    download,
)

URL = "https://project-reforged.danwhelan.ie/update/Shadowkey-0.2.32-win-x64-update.zip"
DATA = bytes(range(256)) * 40
SIZE = len(DATA)
EXPECTED = Expected(SIZE, hashlib.sha256(DATA).hexdigest())
LM = "Sun, 15 Nov 2026 17:53:19 GMT"
ETAG = '"6af9f18f-c93f99"'


class Sleeps(list[float]):
    def __call__(self, seconds: float) -> None:
        self.append(seconds)


def target(tmp_path: Path) -> Path:
    return tmp_path / "Shadowkey-0.2.32-win-x64-update.zip"


def part_with(tmp_path: Path, data: bytes, validator: str | None = ETAG) -> Path:
    part = tmp_path / (target(tmp_path).name + ".part")
    part.write_bytes(data)
    meta = {"url": URL, "validator": validator, "last_modified": LM}
    part.with_name(part.name + ".json").write_text(json.dumps(meta), encoding="utf-8")
    return part


def run(tmp_path: Path, transport: FakeTransport, sleeps: Sleeps | None = None,
        progress: list[tuple[int, int]] | None = None) -> Path:
    seen = progress if progress is not None else []
    return download(transport, URL, target(tmp_path), EXPECTED,
                    progress=lambda done, total: seen.append((done, total)),
                    sleep=sleeps if sleeps is not None else Sleeps(),
                    clock=lambda: 1_000_000.0)


def test_fresh_download(tmp_path: Path) -> None:
    progress: list[tuple[int, int]] = []
    sleeps = Sleeps()
    out = run(tmp_path, FakeTransport(response(200, DATA, etag=ETAG, last_modified=LM)),
              sleeps, progress)
    assert out.read_bytes() == DATA
    assert out.stat().st_mtime == parsedate_to_datetime(LM).timestamp()
    assert progress[-1] == (SIZE, SIZE)
    assert sleeps == []
    assert sorted(p.name for p in tmp_path.iterdir()) == [out.name]


def test_resumes_a_part(tmp_path: Path) -> None:
    part_with(tmp_path, DATA[:4000])
    transport = FakeTransport(response(206, DATA[4000:], etag=ETAG, last_modified=LM,
                                       content_range=f"bytes 4000-{SIZE - 1}/{SIZE}"))
    assert run(tmp_path, transport).read_bytes() == DATA
    assert transport.calls[0].headers == {"Range": "bytes=4000-", "If-Range": ETAG}


def test_part_without_record_starts_over(tmp_path: Path) -> None:
    (tmp_path / (target(tmp_path).name + ".part")).write_bytes(b"junk")
    transport = FakeTransport(response(200, DATA, etag=ETAG))
    assert run(tmp_path, transport).read_bytes() == DATA
    assert transport.calls[0].headers == {}


def test_record_for_another_url_starts_over(tmp_path: Path) -> None:
    part = part_with(tmp_path, DATA[:4000])
    meta = part.with_name(part.name + ".json")
    meta.write_text(json.dumps({"url": URL + "?old", "validator": ETAG}), encoding="utf-8")
    transport = FakeTransport(response(200, DATA, etag=ETAG))
    assert run(tmp_path, transport).read_bytes() == DATA
    assert transport.calls[0].headers == {}


def test_dropped_connection_resumes_after_a_pause(tmp_path: Path) -> None:
    sleeps = Sleeps()
    transport = FakeTransport(
        response(200, Dropping(DATA, 3000), etag=ETAG, last_modified=LM),
        response(206, DATA[3000:], etag=ETAG, content_range=f"bytes 3000-{SIZE - 1}/{SIZE}"))
    assert run(tmp_path, transport, sleeps).read_bytes() == DATA
    assert transport.calls[1].headers == {"Range": "bytes=3000-", "If-Range": ETAG}
    assert sleeps == [FIRST_PAUSE]


def test_changed_file_on_the_server_replaces_the_part(tmp_path: Path) -> None:
    part_with(tmp_path, b"\xff" * 4000, validator='"old"')
    transport = FakeTransport(response(200, DATA, etag=ETAG))
    assert run(tmp_path, transport).read_bytes() == DATA


def test_wrong_content_range_starts_over(tmp_path: Path) -> None:
    part_with(tmp_path, DATA[:4000])
    transport = FakeTransport(
        response(206, DATA[5000:], etag=ETAG, content_range=f"bytes 5000-{SIZE - 1}/{SIZE}"),
        response(200, DATA, etag=ETAG))
    assert run(tmp_path, transport).read_bytes() == DATA
    assert transport.calls[1].headers == {}


def test_416_starts_over(tmp_path: Path) -> None:
    part_with(tmp_path, DATA[:4000])
    transport = FakeTransport(response(416), response(200, DATA, etag=ETAG))
    assert run(tmp_path, transport).read_bytes() == DATA


def test_rate_limit_is_honoured(tmp_path: Path) -> None:
    sleeps = Sleeps()
    transport = FakeTransport(response(429, retry_after="10"), response(200, DATA, etag=ETAG))
    assert run(tmp_path, transport, sleeps).read_bytes() == DATA
    assert sleeps == [10.0]


def test_rate_limit_as_http_date(tmp_path: Path) -> None:
    sleeps = Sleeps()
    # clock() is 1_000_000.0 = Mon, 12 Jan 1970 13:46:40 GMT; 20 s later:
    transport = FakeTransport(response(503, retry_after="Mon, 12 Jan 1970 13:47:00 GMT"),
                              response(200, DATA, etag=ETAG))
    run(tmp_path, transport, sleeps)
    assert sleeps == [20.0]


def test_long_rate_limit_stops_and_says_so(tmp_path: Path) -> None:
    with pytest.raises(RateLimited) as caught:
        run(tmp_path, FakeTransport(response(429, retry_after="600")))
    assert caught.value.seconds == 600.0


def test_http_error_stops_at_once(tmp_path: Path) -> None:
    transport = FakeTransport(response(404))
    with pytest.raises(DownloadError, match="404"):
        run(tmp_path, transport)
    assert len(transport.calls) == 1


def test_checksum_mismatch_deletes_everything(tmp_path: Path) -> None:
    bad = b"\x00" * SIZE
    with pytest.raises(DownloadError, match="checksum"):
        run(tmp_path, FakeTransport(response(200, bad, etag=ETAG)))
    assert list(tmp_path.iterdir()) == []


def test_more_data_than_announced(tmp_path: Path) -> None:
    with pytest.raises(DownloadError, match="more"):
        run(tmp_path, FakeTransport(response(200, DATA + b"x", etag=ETAG)))
    assert list(tmp_path.iterdir()) == []


def test_gives_up_after_five_attempts_and_keeps_the_part(tmp_path: Path) -> None:
    sleeps = Sleeps()
    transport = FakeTransport(response(200, Dropping(DATA, 1000), etag=ETAG),
                              *[ConnectionResetError("reset")] * 4)
    with pytest.raises(DownloadError, match="5 attempts"):
        run(tmp_path, transport, sleeps)
    assert sleeps == [2.0, 4.0, 8.0, 16.0]
    assert (tmp_path / (target(tmp_path).name + ".part")).stat().st_size == 1000


def test_finished_target_is_not_fetched_again(tmp_path: Path) -> None:
    target(tmp_path).write_bytes(DATA)
    assert run(tmp_path, FakeTransport()).read_bytes() == DATA


def test_complete_part_is_finished_without_a_request(tmp_path: Path) -> None:
    part_with(tmp_path, DATA)
    out = run(tmp_path, FakeTransport())
    assert out.read_bytes() == DATA
    assert out.stat().st_mtime == parsedate_to_datetime(LM).timestamp()


def test_weak_etag_falls_back_to_last_modified(tmp_path: Path) -> None:
    transport = FakeTransport(
        response(200, Dropping(DATA, 2000), etag='W/"weak"', last_modified=LM),
        response(206, DATA[2000:], content_range=f"bytes 2000-{SIZE - 1}/{SIZE}"))
    run(tmp_path, transport)
    assert transport.calls[1].headers["If-Range"] == LM


def test_no_validator_means_no_resume(tmp_path: Path) -> None:
    transport = FakeTransport(response(200, Dropping(DATA, 2000)), response(200, DATA))
    run(tmp_path, transport)
    assert transport.calls[1].headers == {}


@pytest.mark.parametrize("expected", [Expected(0, EXPECTED.sha256), Expected(SIZE, "abc")])
def test_bad_expectation(tmp_path: Path, expected: Expected) -> None:
    with pytest.raises(ValueError):
        download(FakeTransport(), URL, target(tmp_path), expected)


def test_a_retry_after_python_cannot_read_is_no_wait(tmp_path: Path) -> None:
    # Headers are Latin-1: a superscript two passes isdigit(), float() refuses it.
    sleeps = Sleeps()
    transport = FakeTransport(response(429, retry_after="\u00b2"), response(200, DATA, etag=ETAG))
    assert run(tmp_path, transport, sleeps).read_bytes() == DATA
    assert sleeps == [FIRST_PAUSE]


class Stopped(BaseException):
    pass


class Trickle(io.BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        return super().read(1000)


def test_a_stop_in_the_progress_keeps_the_part(tmp_path: Path) -> None:
    # The launcher's close stops a job at its next report; the next start resumes.
    def stop_halfway(done: int, total: int) -> None:
        if done >= SIZE // 2:
            raise Stopped

    with pytest.raises(Stopped):
        download(FakeTransport(response(200, Trickle(DATA), etag=ETAG)), URL, target(tmp_path),
                 EXPECTED, progress=stop_halfway, sleep=Sleeps(), clock=lambda: 1_000_000.0)
    kept = (tmp_path / (target(tmp_path).name + ".part")).stat().st_size
    assert SIZE // 2 <= kept < SIZE
    transport = FakeTransport(response(206, DATA[kept:], etag=ETAG,
                                       content_range=f"bytes {kept}-{SIZE - 1}/{SIZE}"))
    assert run(tmp_path, transport).read_bytes() == DATA
    assert transport.calls[0].headers["Range"] == f"bytes={kept}-"
