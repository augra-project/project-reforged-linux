# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from project_reforged_linux.gamelog import Art
from project_reforged_linux.install import game_exe
from project_reforged_linux.paths import AppPaths, ensure_dirs, resolve
from project_reforged_linux.runner import LOG_NAME, WINE_OUTPUT, GameSession
from project_reforged_linux.wineprefix import WineRuntime

RUNTIME = WineRuntime(Path("/opt/wine/bin/wine"), Path("/opt/wine/bin/wineserver"))
USER = "alice"
HEAD = "Shadowkey 0.2.32, Windows, 2026-11-15 19:30:00\r\n"
FETCHING = HEAD + "00:00.577 Art: 805 of 805 pictures to download (632.6 MB), 4 at a time\r\n"
GAVE_UP = HEAD + "00:00.500 Shadowkey couldn't start its graphics; giving up\r\n"


class FakeProcess:
    def __init__(self) -> None:
        self.code: int | None = None

    def poll(self) -> int | None:
        return self.code


class FakePopen:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.process = FakeProcess()

    def __call__(self, command: list[str], **kwargs: Any) -> FakeProcess:
        self.calls.append((command, kwargs))
        return self.process


class FakeRun:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> None:
        self.calls.append(command)


@pytest.fixture
def paths(xdg_home: Path) -> AppPaths:
    p = resolve()
    ensure_dirs(p)
    exe = game_exe(p)
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    p.port_dir(USER).mkdir(parents=True)
    return p


def start(paths: AppPaths) -> tuple[GameSession, FakePopen, FakeRun]:
    popen, run = FakePopen(), FakeRun()
    session = GameSession.start(RUNTIME, paths, USER, {"HOME": "/home/a", "WINEDEBUG": "+all"},
                                popen=popen, run=run)
    return session, popen, run


def write_log(paths: AppPaths, text: str) -> None:
    (paths.port_dir(USER) / LOG_NAME).write_text(text, encoding="utf-8", newline="")


def test_starts_his_exe_under_wine(paths: AppPaths) -> None:
    _, popen, _ = start(paths)
    (command, kwargs), = popen.calls
    assert command == [str(RUNTIME.wine), str(game_exe(paths))]
    assert kwargs["cwd"] == game_exe(paths).parent
    assert kwargs["env"]["WINEPREFIX"] == str(paths.prefix)
    assert kwargs["env"]["WINEDEBUG"] == "-all"
    assert kwargs["start_new_session"] is True
    output = paths.state / WINE_OUTPUT
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_missing_game(paths: AppPaths) -> None:
    game_exe(paths).unlink()
    with pytest.raises(FileNotFoundError):
        start(paths)


def test_reads_progress_from_a_new_log(paths: AppPaths) -> None:
    session, _, _ = start(paths)
    assert session.poll().log.art is Art.UNKNOWN
    write_log(paths, FETCHING)
    status = session.poll()
    assert status.running and status.log.art is Art.FETCHING and not status.stopped


def test_an_old_log_is_ignored(paths: AppPaths) -> None:
    write_log(paths, GAVE_UP)
    session, _, run = start(paths)
    status = session.poll()
    assert not status.log.gave_up and run.calls == []


def test_a_rewritten_log_counts_even_with_the_same_text(paths: AppPaths) -> None:
    write_log(paths, GAVE_UP)
    log = paths.port_dir(USER) / LOG_NAME
    os.utime(log, ns=(1_000_000_000, 1_000_000_000))
    session, _, run = start(paths)
    write_log(paths, GAVE_UP)
    assert session.poll().log.gave_up
    assert run.calls == [[str(RUNTIME.wineserver), "-k"]]


def test_gave_up_ends_wine_once(paths: AppPaths) -> None:
    session, _, run = start(paths)
    write_log(paths, GAVE_UP)
    first = session.poll()
    second = session.poll()
    assert first.stopped and second.stopped
    assert first.log.problem.endswith("giving up")
    assert run.calls == [[str(RUNTIME.wineserver), "-k"]]


def test_exit_code(paths: AppPaths) -> None:
    session, popen, _ = start(paths)
    popen.process.code = 0
    status = session.poll()
    assert not status.running and status.exit_code == 0
