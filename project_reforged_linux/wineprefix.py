# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The Wine runtime the launcher uses, and the prefix it creates with it."""

# Wine is a program the launcher starts on purpose.
import subprocess  # nosec B404
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kista.fileops import write_atomic

from project_reforged_linux.wineenv import build_env

__all__ = ["READY_MARK", "PrefixError", "Run", "WineRuntime", "adopt_finished_prefix",
           "create_prefix", "find_wine_user", "prefix_ready"]

WINEBOOT_TIMEOUT = 300
WINESERVER_TIMEOUT = 120
# Written only once wineboot and wineserver -w have both finished: a setup cut short already
# has system.reg and drive_c.
READY_MARK = ".launcher-prefix-ready"

Run = Callable[..., subprocess.CompletedProcess[Any]]


class PrefixError(Exception):
    """Wine is missing or could not set up the prefix."""


@dataclass(frozen=True, slots=True)
class WineRuntime:
    wine: Path
    wineserver: Path


HEADLESS_DROP = ("DISPLAY", "WAYLAND_DISPLAY")


def _has_wines_files(prefix: Path) -> bool:
    return (prefix / "system.reg").is_file() and (prefix / "drive_c").is_dir()


def prefix_ready(prefix: Path) -> bool:
    return _has_wines_files(prefix) and (prefix / READY_MARK).is_file()


def adopt_finished_prefix(prefix: Path, runtime_stamp: Path) -> bool:
    """Mark a prefix set up before the ready mark existed; its runtime stamp vouches for it."""
    if prefix_ready(prefix) or not _has_wines_files(prefix) or not runtime_stamp.is_file():
        return False
    write_atomic(prefix / READY_MARK, b"adopted: set up by an earlier launcher\n")
    return True


def create_prefix(runtime: WineRuntime, prefix: Path, base_env: Mapping[str, str], *,
                  run: Run = subprocess.run) -> None:
    env = build_env(base_env, prefix)
    # wineboot always shows its "configuration is being updated" window (wineboot.c,
    # show_wait_window); without a display Wine takes its null driver and nothing pops up over
    # the launcher. The prefix keeps nothing about the display.
    for name in HEADLESS_DROP:
        env.pop(name, None)
    # A prefix cut short is set up again in place: wineboot -u finishes what it started, and
    # nothing that may already hold saves is moved or deleted.
    (prefix / READY_MARK).unlink(missing_ok=True)
    steps = (("wineboot -u", [str(runtime.wine), "wineboot", "-u"], WINEBOOT_TIMEOUT),
             ("wineserver -w", [str(runtime.wineserver), "-w"], WINESERVER_TIMEOUT))
    for label, command, timeout in steps:
        try:
            result = run(command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            raise PrefixError(f"{label} did not finish within {timeout} s") from error
        if result.returncode != 0:
            tail = (result.stdout or b"").decode("utf-8", "replace")[-2000:]
            raise PrefixError(f"{label} failed ({result.returncode}): {tail}")
    if not _has_wines_files(prefix):
        raise PrefixError(f"Wine finished but {prefix} is not a prefix")
    write_atomic(prefix / READY_MARK, b"wineboot -u and wineserver -w finished\n")


def find_wine_user(prefix: Path) -> str:
    """The one user folder Wine made under drive_c/users, besides Public."""
    users = prefix / "drive_c" / "users"
    names = sorted(p.name for p in users.iterdir()
                   if p.is_dir() and p.name.lower() != "public") if users.is_dir() else []
    if len(names) != 1:
        raise PrefixError(f"expected one user folder in {users}, found {names}")
    return names[0]
