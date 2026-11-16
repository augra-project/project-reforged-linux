# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Installing his build from the downloaded zip into the game folder."""

import os
import shutil
import stat
import struct
import tempfile
import time
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from kista.paths import normalize_archive_entry

from project_reforged_linux.paths import AppPaths

__all__ = ["GAME_EXE", "GAME_FOLDER", "InstallError", "check_members", "game_exe",
           "install_zip"]

# Names in his zip and build, unchanged by his rename of 2026-11-14 (checked in 0.2.31).
GAME_FOLDER = "Shadowkey"
GAME_EXE = "Shadowkey.exe"
MAX_MEMBERS = 10_000
MAX_TOTAL = 2 * 1024**3
_UT_EXTRA = 0x5455  # Info-ZIP extended timestamp, mtime in UTC seconds
# His folder is read by a Windows program; Wine would have to mangle such names.
_WINDOWS_INVALID = frozenset('<>:"|?*')


class InstallError(Exception):
    """His zip cannot be installed; the previous install is untouched."""


def game_exe(paths: AppPaths) -> Path:
    return paths.game / GAME_FOLDER / GAME_EXE


def _member_path(entry: zipfile.ZipInfo) -> PurePosixPath:
    try:
        path = PurePosixPath(normalize_archive_entry(entry.filename))
    except ValueError as error:
        raise InstallError(f"unsafe name in the zip: {error}") from error
    if path.parts[0] != GAME_FOLDER:
        raise InstallError(f"unexpected name in the zip: {entry.filename!r}")
    for part in path.parts:
        if part.endswith((".", " ")) or any(c in _WINDOWS_INVALID for c in part):
            raise InstallError(f"a name Windows cannot hold: {entry.filename!r}")
    return path


def check_members(
        entries: Iterable[zipfile.ZipInfo]) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    """Refuse anything but plain files and folders below his one top folder."""
    entries = list(entries)
    if len(entries) > MAX_MEMBERS:
        raise InstallError(f"the zip has {len(entries)} members, more than {MAX_MEMBERS}")
    if sum(e.file_size for e in entries) > MAX_TOTAL:
        raise InstallError("the zip unpacks to more than 2 GiB; too large for his build")
    members, seen = [], set()
    for entry in entries:
        path = _member_path(entry)
        if entry.flag_bits & 0x1:
            raise InstallError(f"encrypted member in the zip: {entry.filename}")
        # Many zip writers store permission bits only; refuse a type that is set and wrong.
        kind = stat.S_IFMT(entry.external_attr >> 16)
        if kind and kind not in (stat.S_IFREG, stat.S_IFDIR):
            raise InstallError(f"not a plain file or folder: {entry.filename}")
        folded = str(path).casefold()
        if folded in seen:
            raise InstallError(f"two members differ only in case: {entry.filename}")
        seen.add(folded)
        members.append((entry, path))
    return members


def _member_mtime(entry: zipfile.ZipInfo) -> float:
    extra, pos = entry.extra, 0
    while pos + 4 <= len(extra):
        header_id, length = struct.unpack_from("<HH", extra, pos)
        body = extra[pos + 4:pos + 4 + length]
        if header_id == _UT_EXTRA and len(body) >= 5 and body[0] & 1:
            return float(struct.unpack_from("<i", body, 1)[0])
        pos += 4 + length
    # Without the UT field a zip holds local time, and unzip reads it so.
    return time.mktime((*entry.date_time, 0, 0, -1))


def _unpack(zip_path: Path, staging: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        folders = []
        for entry, path in check_members(archive.infolist()):
            dest = staging.joinpath(*path.parts)
            if entry.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                folders.append((dest, _member_mtime(entry)))
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, dest.open("xb") as target:
                shutil.copyfileobj(source, target, 1 << 20)
            stamp = _member_mtime(entry)
            os.utime(dest, (stamp, stamp))
        # Folder dates last and deepest first: writing into a folder moves its date.
        for folder, stamp in sorted(folders, key=lambda f: len(f[0].parts), reverse=True):
            os.utime(folder, (stamp, stamp))


def install_zip(zip_path: Path, paths: AppPaths) -> Path:
    """Unpack into a new folder beside game/, then swap it in; returns the exe."""
    staging = Path(tempfile.mkdtemp(prefix=".game-new-", dir=paths.data))
    old = paths.data / ".game-old"
    try:
        try:
            _unpack(zip_path, staging)
        except zipfile.BadZipFile as error:
            raise InstallError(f"{zip_path.name} is not a usable zip: {error}") from error
        if not (staging / GAME_FOLDER / GAME_EXE).is_file():
            raise InstallError(f"{GAME_EXE} is not in {zip_path.name}")
        if old.exists():
            shutil.rmtree(old)
        if paths.game.exists():
            os.rename(paths.game, old)
        os.rename(staging, paths.game)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        if old.exists() and not paths.game.exists():
            os.rename(old, paths.game)
        raise
    shutil.rmtree(old, ignore_errors=True)
    return game_exe(paths)
