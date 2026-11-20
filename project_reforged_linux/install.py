# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import gzip
import logging
import lzma
import os
import shutil
import stat
import struct
import tarfile
import tempfile
import time
import zipfile
import zlib
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from kista.paths import normalize_archive_entry

from project_reforged_linux.builds import Build
from project_reforged_linux.paths import AppPaths

__all__ = ["APPIMAGE_NAME", "GAME_EXE", "GAME_FOLDER", "LINUX_BINARY", "MAX_CARD",
           "MAX_DIRECTORY", "InstallError", "check_directory", "check_members",
           "check_tar_members", "directory_sizes", "executable", "game_exe", "install_appimage",
           "install_card_zip", "install_tarball", "install_zip"]

logger = logging.getLogger(__name__)

# Names in his zip and build, unchanged by his rename of 2026-11-14 (checked in 0.2.31).
GAME_FOLDER = "Shadowkey"
GAME_EXE = "Shadowkey.exe"
LINUX_BINARY = "Shadowkey"  # in the tarball's Shadowkey/ folder (0.2.45 to 0.2.48)
# His updater keeps whatever name the AppImage has; this one stays.
APPIMAGE_NAME = "Shadowkey.AppImage"
_ELF = b"\x7fELF"
_TAR_PLAIN = frozenset({tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE})
MAX_MEMBERS = 10_000
MAX_MTIME = 2**32  # the year 2106
_ZIP_METHODS = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2,
                          zipfile.ZIP_LZMA})
MAX_TOTAL = 2 * 1024**3
_UT_EXTRA = 0x5455  # Info-ZIP extended timestamp, mtime in UTC seconds
# 10,000 members with long names and extras stay below it; his 0.2.54 zip needs 17 KB.
MAX_DIRECTORY = 4 * 1024**2
# End records per APPNOTE.TXT 6.3.10, sections 4.3.14 to 4.3.16.
_EOCD = struct.Struct("<4s4H2LH")
_EOCD_SIG = b"PK\x05\x06"
_ZIP64_LOCATOR = struct.Struct("<4sLQL")
_ZIP64_LOCATOR_SIG = b"PK\x06\x07"
_ZIP64_EOCD = struct.Struct("<4sQ2H2L4Q")
_ZIP64_EOCD_SIG = b"PK\x06\x06"
_MAX_COMMENT = 0xFFFF
# His folder is read by a Windows program; Wine would have to mangle such names.
_WINDOWS_INVALID = frozenset('<>:"|?*')
# What unpacking raises on a name that is already taken; a full disk stays an OSError of its own.
_NAME_CLASH = (FileExistsError, NotADirectoryError, IsADirectoryError)


class InstallError(Exception):
    """His zip cannot be installed; the previous install is untouched."""


def game_exe(paths: AppPaths) -> Path:
    return paths.game / GAME_FOLDER / GAME_EXE


def executable(paths: AppPaths, build: Build) -> Path:
    if build is Build.WINDOWS:
        return game_exe(paths)
    if build is Build.LINUX_TARBALL:
        return paths.build_dir(build) / GAME_FOLDER / LINUX_BINARY
    return paths.build_dir(build) / APPIMAGE_NAME


def _member_path(entry: zipfile.ZipInfo, top: str | None) -> PurePosixPath:
    try:
        path = PurePosixPath(normalize_archive_entry(entry.filename))
    except ValueError as error:
        raise InstallError(f"unsafe name in the zip: {error}") from error
    if top is not None and path.parts[0] != top:
        raise InstallError(f"unexpected name in the zip: {entry.filename!r}")
    for part in path.parts:
        if part.endswith((".", " ")) or any(c in _WINDOWS_INVALID for c in part):
            raise InstallError(f"a name Windows cannot hold: {entry.filename!r}")
    return path


def check_members(
        entries: Iterable[zipfile.ZipInfo], *, top: str | None = GAME_FOLDER,
        max_total: int = MAX_TOTAL) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    entries = list(entries)
    if len(entries) > MAX_MEMBERS:
        raise InstallError(f"the zip has {len(entries)} members, more than {MAX_MEMBERS}")
    if sum(e.file_size for e in entries) > max_total:
        raise InstallError(f"the zip unpacks to more than {max_total // 1024**2} MiB; "
                           "too large for what it should hold")
    members = []
    spellings: dict[str, str] = {}
    folded_members: set[str] = set()
    for entry in entries:
        path = _member_path(entry, top)
        if entry.flag_bits & 0x1:
            raise InstallError(f"encrypted member in the zip: {entry.filename}")
        if entry.compress_type not in _ZIP_METHODS:
            raise InstallError(f"a compression the launcher cannot read: {entry.filename}")
        # Many zip writers store permission bits only; refuse a type that is set and wrong.
        kind = stat.S_IFMT(entry.external_attr >> 16)
        if kind and kind not in (stat.S_IFREG, stat.S_IFDIR):
            raise InstallError(f"not a plain file or folder: {entry.filename}")
        _check_case(path, entry.filename, spellings, folded_members)
        members.append((entry, path))
    return members


def _check_case(path: PurePosixPath, name: str, spellings: dict[str, str],
                folded_members: set[str]) -> None:
    """One spelling per folder on the way and per member: Wine folds case for his build."""
    for depth in range(1, len(path.parts) + 1):
        spelled = "/".join(path.parts[:depth])
        if spellings.setdefault(spelled.casefold(), spelled) != spelled:
            raise InstallError(f"two names differ only in case: {name}")
    folded = str(path).casefold()
    if folded in folded_members:
        raise InstallError(f"a member is in the zip twice: {name}")
    folded_members.add(folded)


def _read_at(handle: BinaryIO, offset: int, size: int) -> bytes:
    if offset < 0:
        return b""
    handle.seek(offset)
    return handle.read(size)


def directory_sizes(handle: BinaryIO) -> list[int]:
    """Every central directory size zipfile could take from the file's end records.

    zipfile parses the whole directory, at about ten times its size in memory, before anyone
    can count members; it goes by this size field, not by the count.
    """
    handle.seek(0, os.SEEK_END)
    end = handle.tell()
    start = max(end - _MAX_COMMENT - _EOCD.size, 0)
    tail = _read_at(handle, start, end - start)
    places = {end - _EOCD.size, start + tail.rfind(_EOCD_SIG)} - {start - 1}
    sizes = []
    for place in sorted(places):
        record = _read_at(handle, place, _EOCD.size)
        if len(record) != _EOCD.size or not record.startswith(_EOCD_SIG):
            continue
        locator = _read_at(handle, place - _ZIP64_LOCATOR.size, _ZIP64_LOCATOR.size)
        if len(locator) != _ZIP64_LOCATOR.size or not locator.startswith(_ZIP64_LOCATOR_SIG):
            sizes.append(_EOCD.unpack(record)[5])
            continue
        # With a zip64 locator zipfile takes the zip64 size; the 32-bit one may be 0xFFFFFFFF.
        given = _ZIP64_LOCATOR.unpack(locator)[2]
        for at in (given, place - _ZIP64_LOCATOR.size - _ZIP64_EOCD.size):
            record64 = _read_at(handle, at, _ZIP64_EOCD.size)
            if len(record64) == _ZIP64_EOCD.size and record64.startswith(_ZIP64_EOCD_SIG):
                sizes.append(_ZIP64_EOCD.unpack(record64)[8])
    return sizes


def check_directory(zip_path: Path, limit: int = MAX_DIRECTORY) -> None:
    with zip_path.open("rb") as handle:
        largest = max(directory_sizes(handle), default=0)
    if largest > limit:
        raise InstallError(f"the zip's table of contents is {largest // 1024} KiB, more than "
                           f"{limit // 1024} KiB; too large for what it should hold")


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


def _unpack(zip_path: Path, staging: Path, *, top: str | None = GAME_FOLDER,
            max_total: int = MAX_TOTAL) -> None:
    check_directory(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        folders = []
        for entry, path in check_members(archive.infolist(), top=top, max_total=max_total):
            dest = staging.joinpath(*path.parts)
            # Old Windows zip tools end a folder with a backslash and set only the DOS folder bit.
            if entry.is_dir() or entry.filename.endswith("\\") or entry.external_attr & 0x10:
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


def _replace_folder(target: Path, fill: Callable[[Path], None]) -> None:
    """Fill a new folder beside target, then swap it in; on any failure target stays."""
    for stale in target.parent.glob(f".{target.name}-new-*"):
        if stale.is_dir() and not stale.is_symlink():
            logger.info("removing an unfinished install: %s", stale.name)
            shutil.rmtree(stale, ignore_errors=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-new-", dir=target.parent))
    old = target.with_name(f".{target.name}-old")
    try:
        fill(staging)
        if old.exists():
            shutil.rmtree(old)
        if target.exists():
            os.rename(target, old)
        os.rename(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        if old.exists() and not target.exists():
            os.rename(old, target)
        raise
    shutil.rmtree(old, ignore_errors=True)


# Twice the largest N-Gage card (128 MB); the Shadowkey dump unpacks to 19 MB.
MAX_CARD = 256 * 1024**2


def install_card_zip(zip_path: Path, paths: AppPaths, find: Callable[[Path], Path | None]) -> Path:
    """Unpack the player's N-Gage card zip into card/, dates kept; returns its 6R51 folder.

    `find` locates the 6R51 folder in the unpacked tree; without one nothing is replaced.
    """
    found: list[Path] = []

    def fill(staging: Path) -> None:
        try:
            _unpack(zip_path, staging, top=None, max_total=MAX_CARD)
        except (zipfile.BadZipFile, zlib.error, lzma.LZMAError, EOFError) as error:
            raise InstallError(f"{zip_path.name} is not a usable zip: {error}") from error
        except OSError as error:
            # A file and a folder of one name, say; the staging path would mean nothing to them.
            raise InstallError(f"{zip_path.name} does not unpack cleanly: "
                               f"{error.strerror or error}") from error
        folder = find(staging)
        if folder is None:
            raise InstallError(f"no 6R51 folder in {zip_path.name}")
        found.append(folder.relative_to(staging))

    _replace_folder(paths.card, fill)
    return paths.card / found[0]


def install_zip(zip_path: Path, paths: AppPaths) -> Path:
    def fill(staging: Path) -> None:
        try:
            _unpack(zip_path, staging)
        except (zipfile.BadZipFile, zlib.error, lzma.LZMAError, EOFError) as error:
            raise InstallError(f"{zip_path.name} is not a usable zip: {error}") from error
        except _NAME_CLASH as error:
            raise InstallError(f"{zip_path.name} holds one name twice: "
                               f"{error.strerror or error}") from error
        if not (staging / GAME_FOLDER / GAME_EXE).is_file():
            raise InstallError(f"{GAME_EXE} is not in {zip_path.name}")

    _replace_folder(paths.game, fill)
    return game_exe(paths)


def check_tar_members(
        members: Iterable[tarfile.TarInfo]) -> list[tuple[tarfile.TarInfo, PurePosixPath]]:
    """Checked header by header, so a limit stops the walk before more data is inflated.

    tarfile still reads a GNU long-name or PAX header whole before the member arrives here.
    """
    checked = []
    total = 0
    for entry in members:
        if len(checked) == MAX_MEMBERS:
            raise InstallError(f"the tarball has more than {MAX_MEMBERS} members")
        total += entry.size
        if total > MAX_TOTAL:
            raise InstallError("the tarball unpacks to more than 2 GiB; too large for his build")
        # isreg() also passes contiguous and sparse members; his tarball has neither.
        if entry.type not in _TAR_PLAIN:
            raise InstallError(f"not a plain file or folder: {entry.name}")
        try:
            path = PurePosixPath(normalize_archive_entry(entry.name))
        except ValueError as error:
            raise InstallError(f"unsafe name in the tarball: {error}") from error
        if path.parts[0] != GAME_FOLDER:
            raise InstallError(f"unexpected name in the tarball: {entry.name!r}")
        if any(part.endswith((".", " ")) for part in path.parts):
            raise InstallError(f"an odd name in the tarball: {entry.name!r}")
        # os.utime takes a time_t; a base-256 or PAX date can hold far more.
        if not 0 <= entry.mtime < MAX_MTIME:
            raise InstallError(f"a date out of range in the tarball: {entry.name!r}")
        checked.append((entry, path))
    return checked


def _unpack_tar(tar_path: Path, staging: Path) -> None:
    with tarfile.open(tar_path, "r:gz") as archive:
        folders = []
        for entry, path in check_tar_members(archive):
            dest = staging.joinpath(*path.parts)
            if entry.isdir():
                dest.mkdir(parents=True, exist_ok=True)
                folders.append((dest, float(entry.mtime)))
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(entry)
            if source is None:
                raise InstallError(f"cannot read {entry.name} from the tarball")
            with source, dest.open("xb") as target:
                shutil.copyfileobj(source, target, 1 << 20)
            # His executable bit is kept; no other mode bits from the archive.
            dest.chmod(0o755 if entry.mode & 0o111 else 0o644)
            os.utime(dest, (entry.mtime, entry.mtime))
        # Folder dates last and deepest first: writing into a folder moves its date.
        for folder, stamp in sorted(folders, key=lambda f: len(f[0].parts), reverse=True):
            os.utime(folder, (stamp, stamp))


def install_tarball(tar_path: Path, paths: AppPaths) -> Path:
    target = paths.build_dir(Build.LINUX_TARBALL)

    def fill(staging: Path) -> None:
        try:
            _unpack_tar(tar_path, staging)
        except (tarfile.TarError, EOFError, gzip.BadGzipFile, zlib.error) as error:
            raise InstallError(f"{tar_path.name} is not a usable tarball: {error}") from error
        except _NAME_CLASH as error:
            raise InstallError(f"{tar_path.name} holds one name twice: "
                               f"{error.strerror or error}") from error
        if not (staging / GAME_FOLDER / LINUX_BINARY).is_file():
            raise InstallError(f"{LINUX_BINARY} is not in {tar_path.name}")

    _replace_folder(target, fill)
    return executable(paths, Build.LINUX_TARBALL)


def install_appimage(file: Path, paths: AppPaths) -> Path:
    """Put his checked AppImage in place under one name; it keeps its server date."""
    with file.open("rb") as head:
        if head.read(len(_ELF)) != _ELF:
            raise InstallError(f"{file.name} is not a Linux program")

    def fill(staging: Path) -> None:
        # A copy: a swap that fails must not take the checked download with it.
        dest = Path(shutil.copy2(file, staging / APPIMAGE_NAME))
        dest.chmod(0o755)

    _replace_folder(paths.build_dir(Build.LINUX_APPIMAGE), fill)
    return executable(paths, Build.LINUX_APPIMAGE)
