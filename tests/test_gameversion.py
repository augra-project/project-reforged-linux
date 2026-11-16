# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
from pathlib import Path

import pytest

from project_reforged_linux.gameversion import parse_log_version, read_installed_version


def test_parse_real_line() -> None:
    assert parse_log_version("Shadowkey 0.2.24, Windows, 2026-11-14 10:51:20") == "0.2.24"


def test_parse_strips_crlf() -> None:
    assert parse_log_version("Shadowkey 0.3.1, Windows, 2026-12-01 08:00:00\r\n") == "0.3.1"


@pytest.mark.parametrize("line", [
    "",
    "Shadowkey, Windows",
    "Morrowind 1.0, Windows, 2002",
    "Shadowkey 0.2.24 Windows",
    "Shadowkey v0.2.24, Windows, x",
])
def test_parse_rejects(line: str) -> None:
    with pytest.raises(ValueError):
        parse_log_version(line)


def test_read_missing_log(tmp_path: Path) -> None:
    assert read_installed_version(tmp_path / "shadowkey.log") is None


def test_read_real_log_bytes(tmp_path: Path) -> None:
    log = tmp_path / "shadowkey.log"
    log.write_bytes(b"Shadowkey 0.2.24, Windows, 2026-11-14 10:51:20\r\n"
                    b"00:00.000 Running from Z:\\home\\x\r\n")
    assert read_installed_version(log) == "0.2.24"


def test_read_tolerates_bom(tmp_path: Path) -> None:
    log = tmp_path / "shadowkey.log"
    log.write_bytes(b"\xef\xbb\xbfShadowkey 0.2.25, Windows, x\r\n")
    assert read_installed_version(log) == "0.2.25"


def test_read_unexpected_first_line(tmp_path: Path) -> None:
    log = tmp_path / "shadowkey.log"
    log.write_bytes(b"garbage\r\n")
    with pytest.raises(ValueError):
        read_installed_version(log)
