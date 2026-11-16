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

from project_reforged_linux.wineenv import build_env

__all__ = ["PrefixError", "Run", "WineRuntime", "create_prefix", "find_wine_user",
           "prefix_ready"]

WINEBOOT_TIMEOUT = 300
WINESERVER_TIMEOUT = 120

Run = Callable[..., subprocess.CompletedProcess[Any]]


class PrefixError(Exception):
    """Wine is missing or could not set up the prefix."""


@dataclass(frozen=True, slots=True)
class WineRuntime:
    wine: Path
    wineserver: Path


def prefix_ready(prefix: Path) -> bool:
    return (prefix / "system.reg").is_file() and (prefix / "drive_c").is_dir()


def create_prefix(runtime: WineRuntime, prefix: Path, base_env: Mapping[str, str], *,
                  run: Run = subprocess.run) -> None:
    env = build_env(base_env, prefix)
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
    if not prefix_ready(prefix):
        raise PrefixError(f"Wine finished but {prefix} is not a prefix")


def find_wine_user(prefix: Path) -> str:
    """The one user folder Wine made under drive_c/users, besides Public."""
    users = prefix / "drive_c" / "users"
    names = sorted(p.name for p in users.iterdir()
                   if p.is_dir() and p.name.lower() != "public") if users.is_dir() else []
    if len(names) != 1:
        raise PrefixError(f"expected one user folder in {users}, found {names}")
    return names[0]
