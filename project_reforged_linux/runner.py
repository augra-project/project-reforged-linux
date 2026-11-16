# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Starting the game and watching it through his log."""

import logging
import os

# Wine is a program the launcher starts on purpose.
import subprocess  # nosec B404
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from project_reforged_linux.gamelog import LogState, read_log
from project_reforged_linux.install import game_exe
from project_reforged_linux.paths import AppPaths
from project_reforged_linux.wineenv import build_env
from project_reforged_linux.wineprefix import WineRuntime

__all__ = ["LOG_NAME", "WINE_OUTPUT", "GameSession", "GameStatus"]

logger = logging.getLogger(__name__)

LOG_NAME = "shadowkey.log"
WINE_OUTPUT = "wine.log"
_LOG_LIMIT = 4 * 1024 * 1024  # the lines we read come in the first seconds
STOP_TIMEOUT = 30


class _Process(Protocol):
    def poll(self) -> int | None: ...


@dataclass(frozen=True, slots=True)
class GameStatus:
    running: bool
    exit_code: int | None
    log: LogState
    stopped: bool  # the launcher ended Wine after he gave up


def _snapshot(path: Path) -> tuple[int, int, int] | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)


class GameSession:
    def __init__(self, process: _Process, log_path: Path,
                 before: tuple[int, int, int] | None, stop: Callable[[], None]) -> None:
        self._process = process
        self._log_path = log_path
        self._before = before
        self._stop = stop
        self._stopped = False

    @classmethod
    def start(cls, runtime: WineRuntime, paths: AppPaths, wine_user: str,
              base_env: Mapping[str, str], *,
              popen: Callable[..., Any] = subprocess.Popen,
              run: Callable[..., Any] = subprocess.run) -> "GameSession":
        exe = game_exe(paths)
        if not exe.is_file():
            raise FileNotFoundError(f"the game is not installed: {exe}")
        env = build_env(base_env, paths.prefix)
        log_path = paths.port_dir(wine_user) / LOG_NAME
        before = _snapshot(log_path)
        fd = os.open(paths.state / WINE_OUTPUT,
                     os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        try:
            process = popen(
                [str(runtime.wine), str(exe)], cwd=exe.parent, env=env,
                stdin=subprocess.DEVNULL, stdout=fd, stderr=subprocess.STDOUT,
                start_new_session=True)
        finally:
            os.close(fd)

        def stop() -> None:
            run([str(runtime.wineserver), "-k"], env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=STOP_TIMEOUT,
                check=False)

        return cls(process, log_path, before, stop)

    def poll(self) -> GameStatus:
        log = self._read_log()
        if log.gave_up and not self._stopped:
            logger.warning("the game gave up starting (%s); ending Wine", log.problem)
            self._stop()
            self._stopped = True
        code = self._process.poll()
        return GameStatus(code is None, code, log, self._stopped)

    def _read_log(self) -> LogState:
        now = _snapshot(self._log_path)
        if now is None or now == self._before:
            return LogState()
        with self._log_path.open("rb") as handle:
            raw = handle.read(_LOG_LIMIT)
        return read_log(raw.decode("utf-8", errors="replace"))
