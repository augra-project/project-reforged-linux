# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The launcher's log: on the console and in a file a player can attach to a bug report.

Set up after luducat's main.setup_logging; the line format is the house one, which augra-log
writes too ("{timestamp} [{level}] {component}: {message}").
"""

import faulthandler
import logging
import platform
import re
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import TextIO

from project_reforged_linux import LAUNCHER_NAME, PART_NUMBER, RELEASE_DATE, __version__

__all__ = ["CRASH_NAME", "FORMAT", "LOG_NAME", "home_as_tilde", "log_dir", "setup_logging"]

FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_NAME = "launcher.log"
CRASH_NAME = "crash.log"
KEEP_DAYS = 7

logger = logging.getLogger(__name__)

# Kept open for faulthandler, which writes into it on a hard crash.
_crash_file: TextIO | None = None


def home_as_tilde(path: Path | str) -> str:
    """A path for the log with the home folder as ~: logs get posted, home names a person."""
    text = str(path)
    home = str(Path.home())
    if home not in ("", "/") and (text == home or text.startswith(home + "/")):
        return "~" + text[len(home):]
    return text


class _HomeHidingFormatter(logging.Formatter):
    """Writes the home folder as ~ in every line, exception texts included."""

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        home = str(Path.home())
        if home in ("", "/"):
            return text
        return re.sub(re.escape(home) + r"(?=/|\s|['\"]|$)", "~", text)


def _log_uncaught(kind: type[BaseException], value: BaseException,
                  trace: TracebackType | None) -> None:
    # An exception in a Qt slot ends here; started from the desktop, nothing else would see it.
    if issubclass(kind, KeyboardInterrupt):
        sys.__excepthook__(kind, value, trace)
        return
    logger.critical("uncaught exception", exc_info=(kind, value, trace))


def log_dir(state: Path) -> Path:
    return state / "logs"


def setup_logging(state: Path, *, debug: bool = False, crash_trace: bool = True) -> Path:
    level = logging.DEBUG if debug else logging.INFO
    # Made here before ensure_dirs runs, so the umask must not decide the mode.
    state.mkdir(parents=True, exist_ok=True)
    state.chmod(0o700)
    folder = log_dir(state)
    folder.mkdir(exist_ok=True)
    folder.chmod(0o700)
    path = folder / LOG_NAME
    formatter = _HomeHidingFormatter(FORMAT, datefmt=DATE_FORMAT)
    root = logging.getLogger()
    root.setLevel(level)
    # Without a console (a desktop start may give none) a stream handler fails on every line.
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(level)
        root.addHandler(console)
    file_handler = TimedRotatingFileHandler(path, when="midnight", backupCount=KEEP_DAYS,
                                            encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root.addHandler(file_handler)
    if crash_trace and not faulthandler.is_enabled():
        global _crash_file
        _crash_file = (folder / CRASH_NAME).open("a", encoding="utf-8")
        faulthandler.enable(_crash_file)
    sys.excepthook = _log_uncaught
    logger.info("%s %s (%s-%s), Python %s, %s %s", LAUNCHER_NAME, __version__,
                PART_NUMBER, RELEASE_DATE, platform.python_version(), platform.system(),
                platform.release())
    logger.info("log file %s", home_as_tilde(path))
    return path
