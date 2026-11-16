# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""His update manifest (update/win.json): which build is current and how to check it."""

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from kista.fileops import write_atomic

from project_reforged_linux.net import GAME_HOSTS, Transport

__all__ = ["MANIFEST_URL", "Manifest", "ManifestError", "fetch_manifest", "parse_manifest",
           "version_key"]

MANIFEST_URL = "https://project-reforged.danwhelan.ie/update/win.json"
_MAX_BYTES = 64 * 1024
_VERSION = re.compile(r"^\d+(?:\.\d+){1,3}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SIGNATURE = re.compile(r"^[0-9a-f]{128}$")
_ZIP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.zip$")
_CACHE_BODY = "manifest.json"
_CACHE_ETAG = "manifest.etag"


class ManifestError(Exception):
    """His manifest is missing, malformed or points somewhere it should not."""


@dataclass(frozen=True, slots=True)
class Manifest:
    version: str
    released: date
    url: str
    size: int
    sha256: str
    notes: str
    signature: str | None  # his updater checks it; we have no key

    @property
    def filename(self) -> str:
        return PurePosixPath(urlsplit(self.url).path).name


def version_key(version: str) -> tuple[int, ...]:
    if not _VERSION.match(version):
        raise ValueError(f"not a version: {version!r}")
    return tuple(int(part) for part in version.split("."))


def parse_manifest(text: str) -> Manifest:
    """Validate everything the launcher relies on; his server is not trusted blindly."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ManifestError(f"not JSON: {error}") from error
    if not isinstance(data, dict) or data.get("format") != 1:
        raise ManifestError("unknown manifest format")
    version = data.get("version")
    if not isinstance(version, str) or not _VERSION.match(version):
        raise ManifestError(f"bad version: {version!r}")
    url = data.get("url")
    if not isinstance(url, str):
        raise ManifestError("missing url")
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "").lower() not in GAME_HOSTS:
        raise ManifestError(f"url outside his sites: {url}")
    name = PurePosixPath(parts.path).name
    if not _ZIP_NAME.match(name):
        raise ManifestError(f"unexpected download name: {name!r}")
    sha256 = data.get("sha256")
    if not isinstance(sha256, str) or not _SHA256.match(sha256):
        raise ManifestError("bad sha256")
    size = data.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size < 1 << 31:
        raise ManifestError(f"bad size: {size!r}")
    try:
        released = date.fromisoformat(str(data.get("date")))
    except ValueError as error:
        raise ManifestError(f"bad date: {data.get('date')!r}") from error
    notes = data.get("notes") if isinstance(data.get("notes"), str) else ""
    signature = data.get("signature")
    if signature is not None and (not isinstance(signature, str)
                                  or not _SIGNATURE.match(signature)):
        raise ManifestError("bad signature field")
    return Manifest(version, released, url, size, sha256, notes, signature)


def fetch_manifest(transport: Transport, cache_dir: Path, *, timeout: float = 30.0) -> Manifest:
    """His manifest, asking his server only for a changed copy (ETag, If-None-Match)."""
    body_path = cache_dir / _CACHE_BODY
    etag_path = cache_dir / _CACHE_ETAG
    headers: dict[str, str] = {}
    if body_path.is_file() and etag_path.is_file():
        headers["If-None-Match"] = etag_path.read_text(encoding="utf-8").strip()
    response = transport.get(MANIFEST_URL, headers, timeout)
    try:
        if response.status == 304:
            if "If-None-Match" not in headers:
                raise ManifestError("his site answered 304 to a request without a cached copy")
            return parse_manifest(body_path.read_text(encoding="utf-8"))
        if response.status != 200:
            raise ManifestError(f"HTTP {response.status} for {MANIFEST_URL}")
        raw = response.body.read(_MAX_BYTES + 1)
    finally:
        response.close()
    if len(raw) > _MAX_BYTES:
        raise ManifestError("manifest larger than 64 KiB")
    try:
        manifest = parse_manifest(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ManifestError("manifest is not UTF-8") from error
    write_atomic(body_path, raw)
    etag = response.headers.get("etag", "")
    # isprintable() refuses CR and LF, so an ETag cannot smuggle a header into the next request.
    if etag and etag.isprintable():
        write_atomic(etag_path, etag.encode("utf-8"))
    else:
        etag_path.unlink(missing_ok=True)
    return manifest
