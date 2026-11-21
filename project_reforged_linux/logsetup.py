# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The launcher's log: on the console and in a file a player can attach to a bug report.

Set up after luducat's main.setup_logging; the line format is the house one, which augra-log
writes too ("{timestamp} [{level}] {component}: {message}").
"""

import faulthandler
import getpass
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


# Where a path component ends in a log line; the game's own lines bring Windows paths.
_PATH_END = r"(?=[/\\\s'\",;:)\]]|$)"
# Wine names the prefix's user folder after the login.
_WINE_USER = re.compile(r"((?:drive_c/|[A-Za-z]:\\)users[/\\])(?!(?i:public)" + _PATH_END
                        + r")[^/\\\s'\",;:)\]]+")


def _login() -> str:
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):  # Python before 3.13 raises KeyError here.
        return ""


class _HomeHidingFormatter(logging.Formatter):
    """Masks the finished line, so the traceback the base class appends is masked too."""

    def __init__(self, fmt: str, datefmt: str, login: str) -> None:
        super().__init__(fmt, datefmt=datefmt)
        # A login is also a folder name elsewhere, as in /media/<login>/ for a USB stick.
        self._login = (re.compile(r"(?<=[/\\])" + re.escape(login) + _PATH_END) if login
                       else None)

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        home = str(Path.home())
        if home not in ("", "/"):
            text = re.sub(re.escape(home) + _PATH_END, "~", text)
        text = _WINE_USER.sub(r"\1<user>", text)
        if self._login is not None:
            text = self._login.sub("<user>", text)
        return text


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
    formatter = _HomeHidingFormatter(FORMAT, DATE_FORMAT, _login())
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
