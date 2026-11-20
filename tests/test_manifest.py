# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import json
from datetime import date
from pathlib import Path

import pytest
from fakes import FakeTransport, response

from project_reforged_linux.builds import Build
from project_reforged_linux.manifest import (
    ManifestError,
    fetch_manifest,
    parse_manifest,
    version_key,
)

WIN = Build.WINDOWS

# His manifest as served on 2026-11-15 19:12 (notes shortened).
REAL = {
    "format": 1,
    "version": "0.2.32",
    "date": "2026-11-15",
    "url": "https://project-reforged.danwhelan.ie/update/Shadowkey-0.2.32-win-x64-update.zip",
    "size": 13189017,
    "sha256": "c5516605a02462d009e6ee33205ade847539698e37ba3925526c25964c180060",
    "min_os": "10.0",
    "notes_url": "",
    "notes": "- Dragonfields: Teresa behind the Dragonstar gate can now be talked to.",
    "signature": "82d7c51124f0fb9ee856e11e07d0d6021d7e744326c53b735e6a2f641817e321"
                 "d1b79767d36cc91030a9039214fddfb40dde9279689e470ce0d308f033f5900c",
}


def text(**changes: object) -> str:
    data = {**REAL, **changes}
    return json.dumps({k: v for k, v in data.items() if v is not None})


def test_parses_his_manifest() -> None:
    m = parse_manifest(text(), WIN)
    assert m.version == "0.2.32"
    assert m.released == date(2026, 11, 15)
    assert m.size == 13189017
    assert m.filename == "Shadowkey-0.2.32-win-x64-update.zip"
    assert m.signature == REAL["signature"]
    assert m.notes.startswith("- Dragonfields")


def test_signature_is_optional() -> None:
    assert parse_manifest(text(signature=None), WIN).signature is None


@pytest.mark.parametrize("changes", [
    {"format": 2},
    {"version": "abc"},
    {"version": "1"},
    {"url": "http://project-reforged.danwhelan.ie/update/a.zip"},
    {"url": "https://example.org/a.zip"},
    {"url": "https://project-reforged.danwhelan.ie/update/a.exe"},
    {"url": "https://project-reforged.danwhelan.ie/update/.hidden.zip"},
    {"url": 5},
    {"sha256": "abc"},
    {"sha256": REAL["sha256"].upper()},
    {"size": 0},
    {"size": True},
    {"size": "13189017"},
    {"size": 1 << 31},
    {"date": "yesterday"},
    {"signature": "xyz"},
])
def test_rejects_bad_fields(changes: dict[str, object]) -> None:
    with pytest.raises(ManifestError):
        parse_manifest(text(**changes), WIN)


@pytest.mark.parametrize("bad", ["", "[]", "not json", '{"format": 1}'])
def test_rejects_bad_documents(bad: str) -> None:
    with pytest.raises(ManifestError):
        parse_manifest(bad, WIN)


def test_version_order() -> None:
    assert version_key("0.2.10") > version_key("0.2.9")
    assert version_key("0.3") > version_key("0.2.32")
    with pytest.raises(ValueError):
        version_key("0.2.x")


def test_fetch_stores_body_and_etag(tmp_path: Path) -> None:
    transport = FakeTransport(response(200, text().encode(), etag='W/"2a6-1"'))
    m = fetch_manifest(transport, tmp_path, WIN)
    assert m.version == "0.2.32"
    assert transport.calls[0].url == WIN.manifest_url
    assert "If-None-Match" not in transport.calls[0].headers
    assert (tmp_path / "manifest-windows.etag").read_text(encoding="utf-8") == 'W/"2a6-1"'


def test_fetch_asks_only_for_a_changed_copy(tmp_path: Path) -> None:
    fetch_manifest(FakeTransport(response(200, text().encode(), etag='W/"2a6-1"')), tmp_path,
                   WIN)
    transport = FakeTransport(response(304))
    m = fetch_manifest(transport, tmp_path, WIN)
    assert transport.calls[0].headers["If-None-Match"] == 'W/"2a6-1"'
    assert m.version == "0.2.32"


def test_fetch_without_etag_keeps_no_stale_one(tmp_path: Path) -> None:
    (tmp_path / "manifest-windows.etag").write_text('"old"', encoding="utf-8")
    (tmp_path / "manifest-windows.json").write_text(text(), encoding="utf-8")
    transport = FakeTransport(response(200, text(version="0.2.33").encode()))
    assert fetch_manifest(transport, tmp_path, WIN).version == "0.2.33"
    assert not (tmp_path / "manifest-windows.etag").exists()


def test_fetch_304_without_cache_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ManifestError):
        fetch_manifest(FakeTransport(response(304)), tmp_path, WIN)


def test_fetch_http_error(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="503"):
        fetch_manifest(FakeTransport(response(503)), tmp_path, WIN)


def test_fetch_refuses_oversized_manifest(tmp_path: Path) -> None:
    # Valid JSON, so only the size limit can refuse it.
    body = text(notes="x" * (64 * 1024)).encode()
    with pytest.raises(ManifestError, match="64 KiB"):
        fetch_manifest(FakeTransport(response(200, body)), tmp_path, WIN)
    assert not (tmp_path / "manifest-windows.json").exists()


def test_fetch_refuses_a_header_injection_etag(tmp_path: Path) -> None:
    fetch_manifest(FakeTransport(response(200, text().encode(), etag='"a"\r\nX-Evil: 1')),
                   tmp_path, WIN)
    assert not (tmp_path / "manifest-windows.etag").exists()


def test_fetch_keeps_cache_when_the_new_copy_is_bad(tmp_path: Path) -> None:
    fetch_manifest(FakeTransport(response(200, text().encode(), etag='"a"')), tmp_path, WIN)
    with pytest.raises(ManifestError):
        fetch_manifest(FakeTransport(response(200, b"{}", etag='"b"')), tmp_path, WIN)
    cached = (tmp_path / "manifest-windows.json").read_text(encoding="utf-8")
    assert parse_manifest(cached, WIN).version == "0.2.32"
    assert (tmp_path / "manifest-windows.etag").read_text(encoding="utf-8") == '"a"'


def test_fetch_not_utf8(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="UTF-8"):
        fetch_manifest(FakeTransport(response(200, b'{"format": 1, "notes": "\xff"}')), tmp_path,
                       WIN)


# His Linux manifests as served on 2026-11-18 (notes and signature shortened).
LINUX_TAR = {
    "format": 1, "version": "0.2.48", "date": "2026-11-18",
    "url": "https://project-reforged.danwhelan.ie/downloads/Shadowkey-0.2.48-linux-x86_64.tar.gz",
    "size": 13685172,
    "sha256": "da6133d6b3fa27e2e1d8414cc84fa600c7a390265d1ca2235dd2bba6d691bbd4",
    "min_os": "", "notes_url": "", "notes": "- Fixed: Modern no longer stutters.",
}
LINUX_APP = {
    **LINUX_TAR,
    "url": "https://project-reforged.danwhelan.ie/downloads/Shadowkey-0.2.48-linux-x86_64.AppImage",
    "size": 13740536,
    "sha256": "84dd9819fefdbb2d166d6d9d2dfd0db44529115c27deed7855abee1b5b0249d1",
}


def test_parses_his_linux_manifests() -> None:
    tar = parse_manifest(json.dumps(LINUX_TAR), Build.LINUX_TARBALL)
    assert (tar.version, tar.size, tar.filename) == (
        "0.2.48", 13685172, "Shadowkey-0.2.48-linux-x86_64.tar.gz")
    app = parse_manifest(json.dumps(LINUX_APP), Build.LINUX_APPIMAGE)
    assert app.filename == "Shadowkey-0.2.48-linux-x86_64.AppImage"


@pytest.mark.parametrize(("data", "wrong"), [
    (LINUX_TAR, Build.WINDOWS), (LINUX_TAR, Build.LINUX_APPIMAGE),
    (LINUX_APP, Build.LINUX_TARBALL), (REAL, Build.LINUX_APPIMAGE),
])
def test_a_manifest_naming_another_builds_download_is_refused(data: dict[str, object],
                                                               wrong: Build) -> None:
    with pytest.raises(ManifestError, match="unexpected download name"):
        parse_manifest(json.dumps(data), wrong)


def test_each_build_asks_its_own_manifest_and_keeps_its_own_cache(tmp_path: Path) -> None:
    transport = FakeTransport(response(200, json.dumps(LINUX_TAR).encode(), etag='"t"'))
    assert fetch_manifest(transport, tmp_path, Build.LINUX_TARBALL).version == "0.2.48"
    assert transport.calls[0].url == Build.LINUX_TARBALL.manifest_url
    # The tarball's cached copy must not answer for the AppImage's manifest.
    with pytest.raises(ManifestError, match="304"):
        fetch_manifest(FakeTransport(response(304)), tmp_path, Build.LINUX_APPIMAGE)
    assert sorted(f.name for f in tmp_path.iterdir()) == [
        "manifest-tarball.etag", "manifest-tarball.json"]


@pytest.mark.parametrize("bad", [
    "[" * 60_000,  # deeper than Python's stack: RecursionError
    '{"format": 1, "size": ' + "9" * 5001 + "}",  # past int's digit limit: a plain ValueError
])
def test_documents_json_cannot_take_are_manifest_errors(bad: str) -> None:
    with pytest.raises(ManifestError):
        parse_manifest(bad, WIN)


@pytest.mark.parametrize("url", [
    "https://[/Shadowkey.zip",
    "https://project-reforged.danwhelan.ie\uff20evil.example/Shadowkey.zip",
])
def test_urls_urllib_cannot_split_are_manifest_errors(url: str) -> None:
    with pytest.raises(ManifestError):
        parse_manifest(text(url=url), WIN)
