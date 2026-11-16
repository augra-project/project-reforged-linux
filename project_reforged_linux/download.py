# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Downloading his build: one connection, resumable, checked against his manifest."""

import email.utils
import json
import logging
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from kista.fileops import stamp_http_mtime, write_atomic
from kista.hashing import file_sha256

from project_reforged_linux.net import Response, Transport

__all__ = ["ATTEMPTS", "FIRST_PAUSE", "MAX_PAUSE", "DownloadError", "Expected", "RateLimited",
           "download"]

logger = logging.getLogger(__name__)

CHUNK = 1 << 16
ATTEMPTS = 5
# His site rate-limits downloads; we wait between tries.
FIRST_PAUSE = 2.0
MAX_PAUSE = 60.0
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


class DownloadError(Exception):
    """The download failed in a way the player should hear about."""


class RateLimited(DownloadError):
    def __init__(self, seconds: float) -> None:
        super().__init__(f"his site asks to wait {seconds:.0f} s before the next download")
        self.seconds = seconds


@dataclass(frozen=True, slots=True)
class Expected:
    size: int
    sha256: str


def _meta_path(part: Path) -> Path:
    return part.with_name(part.name + ".json")


def _load_meta(part: Path, url: str) -> dict[str, str | None]:
    try:
        meta = json.loads(_meta_path(part).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return meta if isinstance(meta, dict) and meta.get("url") == url else {}


def _save_meta(part: Path, meta: dict[str, str | None]) -> None:
    write_atomic(_meta_path(part), json.dumps(meta).encode("utf-8"))


def _validator(headers: Mapping[str, str], fallback: str | None) -> str | None:
    """A strong ETag, else Last-Modified; a weak ETag cannot guard a range (RFC 9110, 13.1.5)."""
    etag = headers.get("etag")
    if etag and not etag.startswith("W/"):
        return etag
    return headers.get("last-modified") or fallback


def _retry_after(value: str | None, now: float) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - now)


def _range_fits(value: str | None, offset: int, total: int) -> bool:
    match = _CONTENT_RANGE.match(value or "")
    return (match is not None and int(match[1]) == offset and int(match[2]) == total - 1
            and int(match[3]) == total)


def _matches(path: Path, expected: Expected) -> bool:
    return path.stat().st_size == expected.size and file_sha256(path) == expected.sha256


def _stream(response: Response, part: Path, mode: str, done: int, total: int,
            progress: Callable[[int, int], None]) -> int:
    too_much = False
    progress(done, total)
    with part.open(mode) as out:
        while chunk := response.body.read(CHUNK):
            if done + len(chunk) > total:
                too_much = True
                break
            out.write(chunk)
            done += len(chunk)
            progress(done, total)
        out.flush()
        os.fsync(out.fileno())
    if too_much:
        part.unlink()
        _meta_path(part).unlink(missing_ok=True)
        raise DownloadError("his site sent more data than his manifest announces")
    return done


def download(transport: Transport, url: str, target: Path, expected: Expected, *,
             progress: Callable[[int, int], None] = lambda done, total: None,
             sleep: Callable[[float], None] = time.sleep,
             clock: Callable[[], float] = time.time,
             attempts: int = ATTEMPTS, timeout: float = 60.0) -> Path:
    """Fetch url into target, resuming a part from an earlier try; returns target."""
    if expected.size <= 0 or not _SHA256.match(expected.sha256):
        raise ValueError(f"bad expectation: {expected}")
    if not target.parent.is_dir():
        raise FileNotFoundError(f"directory does not exist: {target.parent}")
    if target.exists():
        if _matches(target, expected):
            return target
        target.unlink()
    part = target.with_name(target.name + ".part")
    meta = _load_meta(part, url)
    if not meta:
        part.unlink(missing_ok=True)
    pause = FIRST_PAUSE
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            sleep(pause)
            pause = min(pause * 2, MAX_PAUSE)
        offset = part.stat().st_size if part.exists() else 0
        if offset > expected.size or (offset and not meta.get("validator")):
            part.unlink()
            offset = 0
        if offset == expected.size:
            break
        headers = {}
        if offset:
            headers = {"Range": f"bytes={offset}-", "If-Range": str(meta["validator"])}
        try:
            response = transport.get(url, headers, timeout)
        except OSError as error:
            logger.info("download attempt %d of %s failed: %s", attempt, url, error)
            continue
        try:
            if response.status in (429, 503):
                wait = _retry_after(response.headers.get("retry-after"), clock())
                if wait is not None and wait > MAX_PAUSE:
                    raise RateLimited(wait)
                pause = max(pause, wait or 0.0)
                continue
            if response.status == 416:
                part.unlink(missing_ok=True)
                meta = {}
                continue
            if response.status == 206 and offset:
                if not _range_fits(response.headers.get("content-range"), offset, expected.size):
                    part.unlink()
                    meta = {}
                    continue
                mode = "ab"
            elif response.status == 200:
                offset, mode = 0, "wb"
            else:
                raise DownloadError(f"HTTP {response.status} for {url}")
            meta = {"url": url,
                    "validator": _validator(response.headers, meta.get("validator")),
                    "last_modified": response.headers.get("last-modified")
                    or meta.get("last_modified")}
            _save_meta(part, meta)
            _stream(response, part, mode, offset, expected.size, progress)
        except OSError as error:
            logger.info("download attempt %d of %s broke off: %s", attempt, url, error)
            continue
        finally:
            response.close()
        if part.stat().st_size == expected.size:
            break
    size = part.stat().st_size if part.exists() else 0
    if size != expected.size:
        raise DownloadError(f"download incomplete after {attempts} attempts ({size} of "
                            f"{expected.size} bytes); the part is kept for the next try")
    if file_sha256(part) != expected.sha256:
        part.unlink()
        _meta_path(part).unlink(missing_ok=True)
        raise DownloadError("the download does not match the checksum in his manifest; "
                            "it was deleted")
    stamp_http_mtime(part, meta.get("last_modified") or "")
    os.replace(part, target)
    _meta_path(part).unlink(missing_ok=True)
    return target
