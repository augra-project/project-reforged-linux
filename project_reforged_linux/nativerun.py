# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Starting his Linux build and watching it through his log.

Nothing here waits: poll() runs on the window's timer, so a stop that needs SIGKILL sends it
on a later poll, and poll() looks for his restart after an update over several calls.
"""

import logging
import os
import signal

# His Linux build is a program the launcher starts on purpose.
import subprocess  # nosec B404
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from project_reforged_linux.builds import Build
from project_reforged_linux.gamelog import LogState, read_log
from project_reforged_linux.install import executable
from project_reforged_linux.nativeenv import native_env
from project_reforged_linux.paths import AppPaths, native_port_dir
from project_reforged_linux.runner import LOG_NAME, GameStatus

__all__ = ["FOLLOW_WINDOW", "GAME_OUTPUT", "STOP_GRACE", "NativeSession", "list_processes"]

logger = logging.getLogger(__name__)

GAME_OUTPUT = "game.log"
STOP_GRACE = 5.0  # seconds between SIGTERM and SIGKILL
FOLLOW_WINDOW = 5.0  # how long his restarted program may take to appear
_LOG_LIMIT = 4 * 1024 * 1024

Process = tuple[int, int, list[str]]  # pid, owner uid, argv


class _Child(Protocol):
    pid: int

    def poll(self) -> int | None: ...


def list_processes(proc: Path = Path("/proc")) -> list[Process]:
    found = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
            uid = entry.stat().st_uid
        except OSError:
            continue  # gone, or not ours to read
        argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        found.append((int(entry.name), uid, argv))
    return found


def _snapshot(path: Path) -> tuple[int, int, int] | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)


class NativeSession:
    def __init__(self, child: _Child, exe: Path, log_path: Path,
                 before: tuple[int, int, int] | None, *, kill: Callable[[int, int], None],
                 processes: Callable[[], Iterable[Process]], clock: Callable[[], float],
                 uid: int, kill_one: Callable[[int, int], None] = os.kill) -> None:
        self._child, self._exe, self._log_path, self._before = child, exe, log_path, before
        self._kill, self._processes, self._clock, self._uid = kill, processes, clock, uid
        self._kill_one = kill_one
        self._followers: set[int] = set()
        self._ended_at: float | None = None
        self._term_at: float | None = None
        self._killed = False
        self._last: tuple[tuple[int, int, int], LogState] | None = None

    @classmethod
    def start(cls, build: Build, paths: AppPaths, base_env: Mapping[str, str], *,
              home: Path | None = None, popen: Callable[..., Any] = subprocess.Popen,
              kill: Callable[[int, int], None] = os.killpg,
              kill_one: Callable[[int, int], None] = os.kill,
              processes: Callable[[], Iterable[Process]] = list_processes,
              clock: Callable[[], float] = time.monotonic) -> "NativeSession":
        if build is Build.WINDOWS:
            raise ValueError("the Windows build runs under Wine, not here")
        exe = executable(paths, build)
        if not exe.is_file():
            raise FileNotFoundError(f"the game is not installed: {exe}")
        env = native_env(base_env)
        log_path = native_port_dir(env, home or Path.home()) / LOG_NAME
        before = _snapshot(log_path)
        fd = os.open(paths.state / GAME_OUTPUT,
                     os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        try:
            child = popen([str(exe)], cwd=exe.parent, env=env, stdin=subprocess.DEVNULL,
                          stdout=fd, stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            os.close(fd)
        logger.info("started his %s build, pid %d", build.value, child.pid)
        return cls(child, exe, log_path, before, kill=kill, processes=processes, clock=clock,
                   uid=os.getuid(), kill_one=kill_one)

    def poll(self) -> GameStatus:
        log = self._read_log()
        code = self._child.poll()
        if code == 0 and self._term_at is None and not self._followers:
            self._look_for_restart()
        alive = self._alive_followers()
        if log.gave_up and self._term_at is None:
            logger.warning("the game gave up starting (%s); ending it", log.problem)
            self._signal(signal.SIGTERM, code is None, alive)
            self._term_at = self._clock()
        elif (self._term_at is not None and not self._killed
              and self._clock() - self._term_at >= STOP_GRACE):
            self._signal(signal.SIGKILL, code is None, alive)
            self._killed = True
        waiting = (code == 0 and not self._followers and self._term_at is None
                   and self._ended_at is not None
                   and self._clock() - self._ended_at < FOLLOW_WINDOW)
        running = code is None or bool(alive) or waiting
        exit_code = None if (running or self._followers) else code
        return GameStatus(running, exit_code, log, self._term_at is not None)

    def _look_for_restart(self) -> None:
        if self._ended_at is None:
            self._ended_at = self._clock()
        self._followers = {pid for pid, uid, argv in self._processes()
                           if self._is_his_restart(uid, argv)}
        if self._followers:
            logger.info("he restarted himself after an update: following pid %s",
                        ", ".join(map(str, sorted(self._followers))))

    def _is_his_restart(self, uid: int, argv: list[str]) -> bool:
        names = {str(self._exe), os.path.realpath(self._exe)}
        return uid == self._uid and bool(argv) and argv[0] in names and "--wait-for" in argv

    def _alive_followers(self) -> set[int]:
        if not self._followers:
            return set()
        # Checked again each time: a pid the kernel gave to another program is not his game.
        return {pid for pid, uid, argv in self._processes()
                if pid in self._followers and self._is_his_restart(uid, argv)}

    def _signal(self, sig: int, child_alive: bool, followers: set[int]) -> None:
        # Each started in a session of its own (seen in 0.2.47 and 0.2.48), so the pid is also
        # the process group.
        targets = ({self._child.pid} if child_alive else set()) | followers
        for pgid in sorted(targets):
            try:
                self._kill(pgid, sig)
            except ProcessLookupError:
                if pgid in followers:
                    self._signal_one(pgid, sig)

    def _signal_one(self, pid: int, sig: int) -> None:
        """A restart that stayed in another group: the process alone, and the log says so."""
        logger.warning("his restart %d leads no process group; signalling it alone", pid)
        try:
            self._kill_one(pid, sig)
        except ProcessLookupError:
            logger.info("his restart %d had already ended", pid)

    def _read_log(self) -> LogState:
        now = _snapshot(self._log_path)
        if now is None or now == self._before:
            return LogState()
        if self._last is not None and self._last[0] == now:
            return self._last[1]
        with self._log_path.open("rb") as handle:
            raw = handle.read(_LOG_LIMIT)
        state = read_log(raw.decode("utf-8", errors="replace"))
        self._last = (now, state)
        return state
