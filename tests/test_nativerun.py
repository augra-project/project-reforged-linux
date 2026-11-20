# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import os
import signal
import stat
from pathlib import Path
from typing import Any

import pytest

from project_reforged_linux.builds import Build
from project_reforged_linux.gamelog import Art
from project_reforged_linux.install import executable
from project_reforged_linux.nativerun import (
    FOLLOW_WINDOW,
    GAME_OUTPUT,
    STOP_GRACE,
    NativeSession,
    list_processes,
)
from project_reforged_linux.paths import AppPaths, ensure_dirs, native_port_dir, resolve
from project_reforged_linux.runner import LOG_NAME

ME = os.getuid()
CHILD = 4100
HEAD = "Shadowkey 0.2.48, Linux, 2026-11-18 08:01:44\n"
FETCHING = HEAD + "00:00.577 Art: 3 of 847 pictures to download (2.1 MB), 4 at a time\n"
GAVE_UP = HEAD + "00:00.500 Shadowkey couldn't start its graphics; giving up\n"


class FakeProcess:
    def __init__(self) -> None:
        self.pid = CHILD
        self.code: int | None = None

    def poll(self) -> int | None:
        return self.code


class World:
    def __init__(self) -> None:
        self.process = FakeProcess()
        self.popen_calls: list[tuple[list[str], dict[str, Any]]] = []
        self.kills: list[tuple[int, int]] = []
        self.table: list[tuple[int, int, list[str]]] = []
        self.now = 100.0

    def popen(self, command: list[str], **kwargs: Any) -> FakeProcess:
        self.popen_calls.append((command, kwargs))
        return self.process

    def kill(self, pgid: int, sig: int) -> None:
        self.kills.append((pgid, sig))

    def processes(self) -> list[tuple[int, int, list[str]]]:
        return list(self.table)

    def clock(self) -> float:
        return self.now


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return {"HOME": str(tmp_path / "home"), "XDG_DATA_HOME": str(tmp_path / "his-data"),
            "APPIMAGE": "/home/a/project-reforged-linux.AppImage"}


@pytest.fixture(params=[Build.LINUX_TARBALL, Build.LINUX_APPIMAGE])
def build(request: pytest.FixtureRequest) -> Build:
    return request.param


@pytest.fixture
def paths(xdg_home: Path, build: Build) -> AppPaths:
    p = resolve()
    ensure_dirs(p)
    exe = executable(p, build)
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"\x7fELF")
    return p


def start(paths: AppPaths, build: Build, env: dict[str, str], home: Path,
          world: World) -> NativeSession:
    return NativeSession.start(build, paths, env, home=home, popen=world.popen,
                               kill=world.kill, processes=world.processes, clock=world.clock)


def write_log(env: dict[str, str], home: Path, text: str) -> None:
    port = native_port_dir(env, home)
    port.mkdir(parents=True, exist_ok=True)
    (port / LOG_NAME).write_text(text, encoding="utf-8")


def test_starts_his_program_with_a_clean_environment(paths: AppPaths, build: Build,
                                                     env: dict[str, str], home: Path) -> None:
    world = World()
    start(paths, build, env, home, world)
    (command, kwargs), = world.popen_calls
    assert command == [str(executable(paths, build))]
    assert kwargs["cwd"] == executable(paths, build).parent
    assert "APPIMAGE" not in kwargs["env"]  # ours; his updater would replace it
    assert kwargs["env"]["XDG_DATA_HOME"] == env["XDG_DATA_HOME"]
    assert kwargs["start_new_session"] is True
    assert stat.S_IMODE((paths.state / GAME_OUTPUT).stat().st_mode) == 0o600


def test_a_missing_program_is_an_error(paths: AppPaths, build: Build, env: dict[str, str],
                                       home: Path) -> None:
    executable(paths, build).unlink()
    with pytest.raises(FileNotFoundError):
        start(paths, build, env, home, World())


def test_reads_his_native_log(paths: AppPaths, build: Build, env: dict[str, str],
                              home: Path) -> None:
    session = start(paths, build, env, home, World())
    assert session.poll().log.art is Art.UNKNOWN
    write_log(env, home, FETCHING)
    status = session.poll()
    assert status.running and status.log.art is Art.FETCHING


def test_an_old_log_is_ignored(paths: AppPaths, build: Build, env: dict[str, str],
                               home: Path) -> None:
    write_log(env, home, GAVE_UP)
    world = World()
    session = start(paths, build, env, home, world)
    assert not session.poll().log.gave_up and world.kills == []


def test_giving_up_ends_his_program_and_kills_after_the_grace(paths: AppPaths, build: Build,
                                                              env: dict[str, str],
                                                              home: Path) -> None:
    world = World()
    session = start(paths, build, env, home, world)
    write_log(env, home, GAVE_UP)
    assert session.poll().stopped
    assert world.kills == [(CHILD, signal.SIGTERM)]
    world.now += STOP_GRACE - 1
    session.poll()
    assert world.kills == [(CHILD, signal.SIGTERM)]  # never blocks the window by waiting
    world.now += 2
    session.poll()
    # he ignored SIGTERM while loading the world.
    assert world.kills == [(CHILD, signal.SIGTERM), (CHILD, signal.SIGKILL)]
    session.poll()
    assert len(world.kills) == 2


def test_a_plain_end_reports_the_exit_code(paths: AppPaths, build: Build, env: dict[str, str],
                                           home: Path) -> None:
    world = World()
    session = start(paths, build, env, home, world)
    world.process.code = 3
    status = session.poll()
    assert not status.running and status.exit_code == 3


def his_restart(paths: AppPaths, build: Build, pid: int = 4200,
                uid: int = ME) -> tuple[int, int, list[str]]:
    return pid, uid, [str(executable(paths, build)), "--wait-for", str(CHILD)]


def test_his_restart_after_an_update_is_followed(paths: AppPaths, build: Build,
                                                env: dict[str, str], home: Path) -> None:
    # After installing an update he exits with 0 and carries on as
    # "<program> --wait-for <pid>" in a session of his own.
    world = World()
    session = start(paths, build, env, home, world)
    world.process.code = 0
    world.table = [his_restart(paths, build)]
    status = session.poll()
    assert status.running and status.exit_code is None
    world.table = []
    assert not session.poll().running


def test_the_follower_may_come_a_moment_later(paths: AppPaths, build: Build,
                                              env: dict[str, str], home: Path) -> None:
    world = World()
    session = start(paths, build, env, home, world)
    world.process.code = 0
    assert session.poll().running  # waiting: he may still be starting the new one
    world.now += 1
    world.table = [his_restart(paths, build)]
    assert session.poll().running
    world.table = []
    assert not session.poll().running


def test_no_follower_in_time_means_the_game_ended(paths: AppPaths, build: Build,
                                                 env: dict[str, str], home: Path) -> None:
    world = World()
    session = start(paths, build, env, home, world)
    world.process.code = 0
    assert session.poll().running
    world.now += FOLLOW_WINDOW + 0.1
    status = session.poll()
    assert not status.running and status.exit_code == 0


@pytest.mark.parametrize("label", ["other user", "other program", "no wait-for"])
def test_strangers_are_not_followed(paths: AppPaths, build: Build, env: dict[str, str],
                                    home: Path, label: str) -> None:
    world = World()
    session = start(paths, build, env, home, world)
    world.process.code = 0
    pid, uid, argv = his_restart(paths, build)
    if label == "other user":
        uid = ME + 1
    elif label == "other program":
        argv = ["/usr/bin/Shadowkey", *argv[1:]]
    else:
        argv = argv[:1]
    world.table = [(pid, uid, argv)]
    assert session.poll().running  # the exit is seen here, the wait for a restart begins
    world.now += FOLLOW_WINDOW + 0.1
    assert not session.poll().running


def test_a_followed_game_that_gives_up_is_ended_too(paths: AppPaths, build: Build,
                                                    env: dict[str, str], home: Path) -> None:
    world = World()
    session = start(paths, build, env, home, world)
    world.process.code = 0
    world.table = [his_restart(paths, build, pid=4200), his_restart(paths, build, pid=4201)]
    session.poll()
    write_log(env, home, GAVE_UP)
    session.poll()
    assert sorted(world.kills) == [(4200, signal.SIGTERM), (4201, signal.SIGTERM)]


def test_list_processes_sees_this_test(paths: AppPaths, build: Build) -> None:
    mine = [p for p in list_processes() if p[0] == os.getpid()]
    assert len(mine) == 1 and mine[0][1] == ME and mine[0][2]


def test_an_unchanged_log_is_read_once(paths: AppPaths, build: Build, env: dict[str, str],
                                       home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from project_reforged_linux import nativerun

    reads: list[str] = []
    real = nativerun.read_log
    monkeypatch.setattr(nativerun, "read_log", lambda text: reads.append(text) or real(text))
    session = start(paths, build, env, home, World())
    write_log(env, home, FETCHING)
    assert session.poll().log.art is Art.FETCHING
    assert session.poll().log.art is Art.FETCHING
    assert len(reads) == 1


def test_a_reused_pid_is_not_his_game(paths: AppPaths, build: Build, env: dict[str, str],
                                      home: Path) -> None:
    world = World()
    session = start(paths, build, env, home, world)
    world.process.code = 0
    world.table = [his_restart(paths, build)]
    assert session.poll().running
    world.table = [(4200, ME, ["/usr/bin/vim", "notes.txt"])]  # his pid, now another program
    write_log(env, home, GAVE_UP)
    assert not session.poll().running
    assert world.kills == []


def test_a_restart_without_its_own_group_is_signalled_alone(
        paths: AppPaths, build: Build, env: dict[str, str], home: Path,
        caplog: pytest.LogCaptureFixture) -> None:
    world = World()
    singles: list[tuple[int, int]] = []

    def no_group(pgid: int, sig: int) -> None:
        raise ProcessLookupError(pgid)

    session = NativeSession.start(
        build, paths, env, home=home, popen=world.popen, kill=no_group,
        kill_one=lambda pid, sig: singles.append((pid, sig)), processes=world.processes,
        clock=world.clock)
    world.process.code = 0
    world.table = [his_restart(paths, build)]
    session.poll()
    write_log(env, home, GAVE_UP)
    session.poll()
    assert singles == [(4200, signal.SIGTERM)]
    assert "leads no process group" in caplog.text
