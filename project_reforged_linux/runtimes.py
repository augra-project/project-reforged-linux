# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Which Wine runs the game: the player's choice, the scan, and the check every candidate passes."""

import os
import re
import shutil

# wine --version is the one program this module starts.
import subprocess  # nosec B404
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from kista.fileops import write_atomic

from project_reforged_linux.paths import AppPaths
from project_reforged_linux.wineenv import clean_env
from project_reforged_linux.wineprefix import WineRuntime

__all__ = ["MIN_VERSION", "Candidate", "Checked", "Mode", "Resolved", "Source",
           "bundled_candidate", "check", "chosen_candidate", "mark_prefix", "prefix_downgrade",
           "resolve_runtime", "scan", "system_candidate"]

# The only Wine verified with his build (Debian 10.0, 2026-11-15); target 8 or 9 once tested.
MIN_VERSION: tuple[int, int] = (10, 0)
PROBE_TIMEOUT = 10
BUNDLED_RELATIVE = Path("opt") / "wine"  # inside $APPDIR
WINEHQ_BRANCHES = ("wine-stable", "wine-devel", "wine-staging")
LUTRIS_RUNNERS = Path(".local/share/lutris/runners/wine")
BOTTLES_RUNNERS = Path(".local/share/bottles/runners")
PREFIX_STAMP = "prefix-wine.txt"
# Upstream and WineHQ, older WineHQ and Fedora, Debian and Ubuntu multiarch.
_DLL_DIRS = ("lib/wine", "lib64/wine", "lib/x86_64-linux-gnu/wine")
_VERSION = re.compile(r"^wine-(\d+)\.(\d+)")

Run = Callable[..., subprocess.CompletedProcess[Any]]


class Mode(StrEnum):
    AUTO = "auto"
    SYSTEM = "system"
    BUNDLED = "bundled"
    CHOSEN = "chosen"


class Source(StrEnum):
    SYSTEM = "system"
    BUNDLED = "bundled"
    WINEHQ = "winehq"
    LUTRIS = "lutris"
    BOTTLES = "bottles"
    CHOSEN = "chosen"


@dataclass(frozen=True, slots=True)
class Candidate:
    source: Source
    wine: Path
    wineserver: Path


@dataclass(frozen=True, slots=True)
class Checked:
    candidate: Candidate
    version: tuple[int, int] | None
    version_text: str
    problem: str | None

    @property
    def usable(self) -> bool:
        return self.problem is None

    @property
    def runtime(self) -> WineRuntime:
        if not self.usable:
            raise ValueError(f"not a usable runtime: {self.problem}")
        return WineRuntime(self.candidate.wine, self.candidate.wineserver)


@dataclass(frozen=True, slots=True)
class Resolved:
    checked: Checked | None  # the runtime that runs, when one is usable
    note: str | None = None  # Automatic fell back: one line for the window
    problem: str | None = None  # nothing usable: what is wrong

    @property
    def runtime(self) -> WineRuntime | None:
        return self.checked.runtime if self.checked is not None else None


def _version_name(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]}"


def _is_64bit(wine: Path) -> bool:
    # WineHQ links /usr/bin/wine into /opt; Debian's /usr/bin/wine is a script in place.
    roots = {wine.resolve().parent.parent, wine.parent.parent}
    return any((root / d / "x86_64-windows" / "ntdll.dll").is_file()
               for root in roots for d in _DLL_DIRS)


def check(candidate: Candidate, base_env: Mapping[str, str], *,
          run: Run = subprocess.run) -> Checked:
    def refused(problem: str, version: tuple[int, int] | None = None, text: str = "") -> Checked:
        return Checked(candidate, version, text, problem)

    for tool in (candidate.wine, candidate.wineserver):
        if not tool.is_file() or not os.access(tool, os.X_OK):
            return refused(f"{tool} is missing or cannot be run")
    if not _is_64bit(candidate.wine):
        return refused(f"{candidate.wine} is not a 64-bit Wine; his build needs one")
    try:
        result = run([str(candidate.wine), "--version"], env=clean_env(base_env),
                     stdin=subprocess.DEVNULL, capture_output=True, text=True,
                     timeout=PROBE_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        return refused(f"{candidate.wine} --version did not answer within {PROBE_TIMEOUT} s")
    except OSError as error:
        return refused(f"{candidate.wine} cannot start: {error}")
    lines = (result.stdout or "").strip().splitlines()
    text = lines[0] if lines else ""
    match = _VERSION.match(text)
    if result.returncode != 0 or match is None:
        return refused(f"{candidate.wine} --version answered {text!r}")
    version = (int(match[1]), int(match[2]))
    if version < MIN_VERSION:
        return refused(f"Wine {_version_name(version)} is older than "
                       f"{_version_name(MIN_VERSION)}, the oldest this launcher supports",
                       version, text)
    return Checked(candidate, version, text, None)


def system_candidate(which: Callable[[str], str | None] = shutil.which) -> Candidate | None:
    wine, server = which("wine"), which("wineserver")
    if wine is None or server is None:
        return None
    return Candidate(Source.SYSTEM, Path(wine), Path(server))


def bundled_candidate(env: Mapping[str, str] = os.environ) -> Candidate | None:
    appdir = env.get("APPDIR")
    if not appdir or not Path(appdir).is_absolute():
        return None
    root = Path(appdir) / BUNDLED_RELATIVE
    return Candidate(Source.BUNDLED, root / "bin" / "wine", root / "bin" / "wineserver")


def chosen_candidate(wine: Path) -> Candidate:
    return Candidate(Source.CHOSEN, wine, wine.with_name("wineserver"))


def _trees(source: Source, roots: Iterable[Path]) -> list[Candidate]:
    found = []
    for root in roots:
        wine = root / "bin" / "wine"
        if wine.is_file():
            found.append(Candidate(source, wine, root / "bin" / "wineserver"))
    return found


def _children(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []


def scan(base_env: Mapping[str, str], *, home: Path, opt: Path = Path("/opt"),
         which: Callable[[str], str | None] = shutil.which,
         run: Run = subprocess.run) -> list[Checked]:
    """Every Wine in the places we look, checked; usable first, newest first."""
    candidates = []
    system = system_candidate(which)
    if system is not None:
        candidates.append(system)
    candidates += _trees(Source.WINEHQ, (opt / branch for branch in WINEHQ_BRANCHES))
    candidates += _trees(Source.LUTRIS, _children(home / LUTRIS_RUNNERS))
    candidates += _trees(Source.BOTTLES, _children(home / BOTTLES_RUNNERS))
    seen: set[Path] = set()
    checked = []
    for found in candidates:
        key = found.wine.resolve()
        if key in seen:
            continue
        seen.add(key)
        checked.append(check(found, base_env, run=run))
    return sorted(checked, key=lambda c: (not c.usable, [-n for n in c.version or (0, 0)]))


def _single(found: Candidate | None, missing: str, base_env: Mapping[str, str],
            run: Run) -> Resolved:
    if found is None:
        return Resolved(None, problem=missing)
    checked = check(found, base_env, run=run)
    return Resolved(checked) if checked.usable else Resolved(None, problem=checked.problem)


def resolve_runtime(mode: Mode, chosen: Path | None, base_env: Mapping[str, str], *,
                    which: Callable[[str], str | None] = shutil.which,
                    env: Mapping[str, str] = os.environ,
                    run: Run = subprocess.run) -> Resolved:
    """The runtime the saved choice gives; only Automatic falls back."""
    no_system = "no Wine is installed on this system"
    no_bundled = "this launcher has no bundled runtime"
    if mode is Mode.CHOSEN:
        if chosen is None:
            raise ValueError("the chosen mode needs the path of a wine binary")
        return _single(chosen_candidate(chosen), "", base_env, run)
    if mode is Mode.SYSTEM:
        return _single(system_candidate(which), f"System Wine: {no_system}", base_env, run)
    if mode is Mode.BUNDLED:
        return _single(bundled_candidate(env), f"Bundled runtime: {no_bundled}", base_env, run)
    system = _single(system_candidate(which), no_system, base_env, run)
    if system.checked is not None:
        return system
    bundled = _single(bundled_candidate(env), no_bundled, base_env, run)
    if bundled.checked is not None:
        return Resolved(bundled.checked,
                        note=f"System Wine not used ({system.problem}); "
                             "the bundled runtime runs the game.")
    return Resolved(None, problem=f"No usable Wine: {system.problem}; {bundled.problem}.")


def _stamped(paths: AppPaths) -> tuple[str, tuple[int, int]] | None:
    try:
        text = (paths.data / PREFIX_STAMP).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    match = _VERSION.match(text)
    return (text, (int(match[1]), int(match[2]))) if match else None


def mark_prefix(paths: AppPaths, checked: Checked) -> None:
    """Record the Wine that set up or ran the prefix."""
    if not checked.usable:
        raise ValueError(f"not a usable runtime: {checked.problem}")
    write_atomic(paths.data / PREFIX_STAMP, (checked.version_text + "\n").encode("utf-8"))


def prefix_downgrade(paths: AppPaths, checked: Checked) -> str | None:
    """The warning before an older Wine runs a prefix a newer one already upgraded."""
    stamped = _stamped(paths)
    if stamped is None or checked.version is None or checked.version >= stamped[1]:
        return None
    return (f"The prefix was last run by {stamped[0]}; {checked.version_text} is older and "
            "may not cope with it. Your saves and settings live in that prefix.")
