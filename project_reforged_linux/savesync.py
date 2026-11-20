# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Keeping the saves of his Linux and Windows builds in step.

Both builds keep the same slots, {game,auto}<n>.{sav,info,png}, and load each other's; before a
start, the build about to run takes every slot the other has newer, all three files together.
"""

import logging
import re
import shutil
import time
from pathlib import Path

from project_reforged_linux.logsetup import home_as_tilde

__all__ = ["sync_saves"]

logger = logging.getLogger(__name__)

_SLOT = re.compile(r"(?:game|auto)\d+")
_SUFFIXES = (".sav", ".info", ".png")


def _slots(folder: Path) -> list[str]:
    found = []
    for path in folder.iterdir():
        if path.suffix == ".sav" and _SLOT.fullmatch(path.stem):
            found.append(path.stem)
    return sorted(found)


def _files(folder: Path, slot: str) -> list[Path]:
    return [folder / f"{slot}{s}" for s in _SUFFIXES if (folder / f"{slot}{s}").is_symlink()
            or (folder / f"{slot}{s}").exists()]


def _mtime(path: Path) -> float | None:
    return path.stat().st_mtime if path.is_file() else None


def _back_up(files: list[Path], backups: Path, stamp: str) -> None:
    kept = backups / stamp
    kept.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path in files:
        shutil.copy2(path, kept / path.name)


def _take_slot(slot: str, other: Path, mine: Path) -> None:
    """Copy every file first, then swap them all in: a failure leaves the old slot whole."""
    staged: list[tuple[Path, Path]] = []
    try:
        for source in _files(other, slot):
            temp = mine / f".{source.name}.sync"
            shutil.copy2(source, temp)  # copy2 keeps his date
            staged.append((temp, mine / source.name))
    except BaseException:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)
        raise
    taken = {target.name for _, target in staged}
    for stale in _files(mine, slot):
        if stale.name not in taken:
            stale.unlink()  # a picture of the old save beside the new one would mislead
    for temp, target in staged:
        temp.replace(target)


def sync_saves(other: Path, mine: Path, backups: Path, *, stamp: str | None = None) -> list[str]:
    """Bring mine up to date with other's newer slots; returns the slots taken."""
    if not other.is_dir():
        return []
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    taken = []
    for slot in _slots(other):
        theirs, ours = _files(other, slot), _files(mine, slot) if mine.is_dir() else []
        if any(p.is_symlink() for p in (*theirs, *ours)):
            logger.warning("save slot %s skipped: a link in %s or %s", slot,
                           home_as_tilde(other), home_as_tilde(mine))
            continue
        their_time = _mtime(other / f"{slot}.sav")
        our_time = _mtime(mine / f"{slot}.sav")
        if their_time is None or (our_time is not None and our_time >= their_time):
            continue
        mine.mkdir(parents=True, exist_ok=True)
        if ours:
            _back_up(ours, backups, stamp)
        _take_slot(slot, other, mine)
        taken.append(slot)
    if taken:
        logger.info("saves taken from %s: %s", home_as_tilde(other), ", ".join(taken))
    return taken
