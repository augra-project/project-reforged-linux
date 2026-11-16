# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import subprocess
from pathlib import Path
from typing import Any

import pytest

from project_reforged_linux.wineprefix import (
    PrefixError,
    WineRuntime,
    create_prefix,
    find_wine_user,
    prefix_ready,
)

RUNTIME = WineRuntime(Path("/opt/wine/bin/wine"), Path("/opt/wine/bin/wineserver"))


class FakeRun:
    def __init__(self, prefix: Path, returncode: int = 0, timeout_on: str | None = None,
                 builds: bool = True) -> None:
        self.prefix, self.returncode, self.timeout_on, self.builds = (
            prefix, returncode, timeout_on, builds)
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((command, kwargs))
        if self.timeout_on and self.timeout_on in command:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        if "wineboot" in command and self.builds and self.returncode == 0:
            (self.prefix / "drive_c" / "users" / "alice").mkdir(parents=True)
            (self.prefix / "drive_c" / "users" / "Public").mkdir()
            (self.prefix / "system.reg").write_text("WINE REGISTRY", encoding="utf-8")
        return subprocess.CompletedProcess(command, self.returncode, b"wine says no\n")


def test_creates_the_prefix(tmp_path: Path) -> None:
    run = FakeRun(tmp_path)
    create_prefix(RUNTIME, tmp_path, {"HOME": "/home/a", "LD_PRELOAD": "x.so"}, run=run)
    assert prefix_ready(tmp_path)
    (boot, boot_kw), (wait, _) = run.calls
    assert boot == [str(RUNTIME.wine), "wineboot", "-u"]
    assert wait == [str(RUNTIME.wineserver), "-w"]
    assert boot_kw["env"]["WINEPREFIX"] == str(tmp_path)
    assert "LD_PRELOAD" not in boot_kw["env"]
    assert boot_kw["check"] is False


def test_failure_reports_wine_output(tmp_path: Path) -> None:
    with pytest.raises(PrefixError, match="wine says no"):
        create_prefix(RUNTIME, tmp_path, {}, run=FakeRun(tmp_path, returncode=1))


def test_timeout(tmp_path: Path) -> None:
    with pytest.raises(PrefixError, match="did not finish"):
        create_prefix(RUNTIME, tmp_path, {}, run=FakeRun(tmp_path, timeout_on="wineboot"))


def test_wineserver_timeout(tmp_path: Path) -> None:
    with pytest.raises(PrefixError, match="wineserver -w did not finish"):
        create_prefix(RUNTIME, tmp_path, {}, run=FakeRun(tmp_path, timeout_on="-w"))


def test_wine_that_builds_nothing(tmp_path: Path) -> None:
    with pytest.raises(PrefixError, match="not a prefix"):
        create_prefix(RUNTIME, tmp_path, {}, run=FakeRun(tmp_path, builds=False))


def test_find_wine_user(tmp_path: Path) -> None:
    create_prefix(RUNTIME, tmp_path, {}, run=FakeRun(tmp_path))
    assert find_wine_user(tmp_path) == "alice"


@pytest.mark.parametrize("users", [[], ["alice", "bob"]])
def test_find_wine_user_needs_exactly_one(tmp_path: Path, users: list[str]) -> None:
    base = tmp_path / "drive_c" / "users"
    base.mkdir(parents=True)
    (base / "Public").mkdir()
    for name in users:
        (base / name).mkdir()
    with pytest.raises(PrefixError):
        find_wine_user(tmp_path)


def test_find_wine_user_without_a_prefix(tmp_path: Path) -> None:
    with pytest.raises(PrefixError):
        find_wine_user(tmp_path)


def test_prefix_ready_needs_both(tmp_path: Path) -> None:
    assert not prefix_ready(tmp_path)
    (tmp_path / "system.reg").write_text("x", encoding="utf-8")
    assert not prefix_ready(tmp_path)
    (tmp_path / "drive_c").mkdir()
    assert prefix_ready(tmp_path)
