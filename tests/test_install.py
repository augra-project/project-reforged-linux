# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import stat
import struct
import time
import zipfile
from pathlib import Path

import pytest
from kista.testing import HOSTILE_FILE_PATHS, HOSTILE_PATH_COMPONENTS

from project_reforged_linux.install import (
    GAME_EXE,
    GAME_FOLDER,
    InstallError,
    check_members,
    game_exe,
    install_zip,
)
from project_reforged_linux.paths import AppPaths, ensure_dirs, resolve

EXE_DATE = (2026, 11, 15, 9, 28, 54)
DLL_DATE = (2026, 10, 2, 17, 5, 10)


def make_zip(path: Path, members: list[tuple[str, bytes, tuple[int, ...]]]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data, when in members:
            info = zipfile.ZipInfo(name, date_time=when)
            archive.writestr(info, data)
    return path


def his_zip(path: Path) -> Path:
    return make_zip(path, [
        (f"{GAME_FOLDER}/", b"", EXE_DATE),
        (f"{GAME_FOLDER}/{GAME_EXE}", b"MZ exe", EXE_DATE),
        (f"{GAME_FOLDER}/SDL3.dll", b"MZ dll", DLL_DATE),
        (f"{GAME_FOLDER}/patches/", b"", DLL_DATE),
        (f"{GAME_FOLDER}/patches/azra.s", b"patch", DLL_DATE),
    ])


@pytest.fixture
def paths(xdg_home: Path) -> AppPaths:
    p = resolve()
    ensure_dirs(p)
    return p


def local(when: tuple[int, ...]) -> float:
    return time.mktime((*when, 0, 0, -1))


def hidden(paths: AppPaths) -> list[str]:
    return sorted(p.name for p in paths.data.iterdir() if p.name.startswith("."))


def test_installs_and_returns_the_exe(paths: AppPaths, tmp_path: Path) -> None:
    exe = install_zip(his_zip(tmp_path / "b.zip"), paths)
    assert exe == game_exe(paths) == paths.game / GAME_FOLDER / GAME_EXE
    assert exe.read_bytes() == b"MZ exe"
    assert (paths.game / GAME_FOLDER / "patches" / "azra.s").read_bytes() == b"patch"


def test_every_member_keeps_its_own_date(paths: AppPaths, tmp_path: Path) -> None:
    install_zip(his_zip(tmp_path / "b.zip"), paths)
    folder = paths.game / GAME_FOLDER
    assert (folder / GAME_EXE).stat().st_mtime == local(EXE_DATE)
    assert (folder / "SDL3.dll").stat().st_mtime == local(DLL_DATE)
    assert (folder / "patches").stat().st_mtime == local(DLL_DATE)
    assert folder.stat().st_mtime == local(EXE_DATE)


def test_ut_extra_field_wins(paths: AppPaths, tmp_path: Path) -> None:
    path = tmp_path / "ut.zip"
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo(f"{GAME_FOLDER}/{GAME_EXE}", date_time=EXE_DATE)
        info.extra = struct.pack("<HHBi", 0x5455, 5, 1, 1_700_000_000)
        archive.writestr(info, b"MZ")
    install_zip(path, paths)
    assert game_exe(paths).stat().st_mtime == 1_700_000_000


def test_replaces_an_old_install(paths: AppPaths, tmp_path: Path) -> None:
    old = paths.game / GAME_FOLDER / "old.dll"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    install_zip(his_zip(tmp_path / "b.zip"), paths)
    assert not old.exists()
    assert sorted(p.name for p in paths.data.iterdir()) == ["game", "prefix"]


def test_game_folder_is_private(paths: AppPaths, tmp_path: Path) -> None:
    install_zip(his_zip(tmp_path / "b.zip"), paths)
    assert stat.S_IMODE(paths.game.stat().st_mode) == 0o700


def test_zip_without_exe_leaves_the_old_game(paths: AppPaths, tmp_path: Path) -> None:
    install_zip(his_zip(tmp_path / "b.zip"), paths)
    bad = make_zip(tmp_path / "bad.zip", [(f"{GAME_FOLDER}/readme.txt", b"x", EXE_DATE)])
    with pytest.raises(InstallError, match=GAME_EXE):
        install_zip(bad, paths)
    assert game_exe(paths).read_bytes() == b"MZ exe"
    assert hidden(paths) == []


def test_hostile_zip_leaves_the_old_game(paths: AppPaths, tmp_path: Path) -> None:
    install_zip(his_zip(tmp_path / "b.zip"), paths)
    bad = make_zip(tmp_path / "bad.zip", [(f"{GAME_FOLDER}/{GAME_EXE}", b"MZ new", EXE_DATE),
                                          (f"{GAME_FOLDER}/../evil.exe", b"x", EXE_DATE)])
    with pytest.raises(InstallError):
        install_zip(bad, paths)
    assert game_exe(paths).read_bytes() == b"MZ exe"
    assert not (paths.game / "evil.exe").exists()
    assert hidden(paths) == []


def test_corrupt_zip(paths: AppPaths, tmp_path: Path) -> None:
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"PK\x03\x04 not really")
    with pytest.raises(InstallError):
        install_zip(junk, paths)
    assert hidden(paths) == []


def info(name: str, mode: int = 0) -> zipfile.ZipInfo:
    entry = zipfile.ZipInfo(name)
    entry.external_attr = mode << 16
    return entry


# zipfile cuts a name at a NUL byte while reading, before our check sees it.
HOSTILE_NAMES = [
    *[(label, path) for label, path in HOSTILE_FILE_PATHS if "\x00" not in path],
    *[(label, f"{GAME_FOLDER}/{part}") for label, part in HOSTILE_PATH_COMPONENTS
      if "\x00" not in part],
    ("other-top-folder", "Other/x.dll"),
    ("windows-colon", f"{GAME_FOLDER}/C:x"),
    ("windows-star", f"{GAME_FOLDER}/a*b.dll"),
    ("trailing-dot", f"{GAME_FOLDER}/x.dll."),
    ("trailing-space", f"{GAME_FOLDER}/patches /a.s"),
]


@pytest.mark.parametrize(("label", "name"), HOSTILE_NAMES)
def test_hostile_names_are_refused(label: str, name: str) -> None:
    with pytest.raises(InstallError):
        check_members([info(f"{GAME_FOLDER}/{GAME_EXE}"), info(name)])


@pytest.mark.parametrize("mode", [stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o644,
                                  stat.S_IFCHR | 0o644])
def test_special_files_are_refused(mode: int) -> None:
    with pytest.raises(InstallError, match="plain"):
        check_members([info(f"{GAME_FOLDER}/odd", mode)])


def test_backslashes_become_folders() -> None:
    (_, path), = check_members([info(f"{GAME_FOLDER}\\patches\\azra.s")])
    assert str(path) == f"{GAME_FOLDER}/patches/azra.s"


def test_encrypted_member_is_refused() -> None:
    entry = info(f"{GAME_FOLDER}/{GAME_EXE}")
    entry.flag_bits |= 0x1
    with pytest.raises(InstallError, match="encrypted"):
        check_members([entry])


def test_names_differing_only_in_case_are_refused() -> None:
    with pytest.raises(InstallError, match="case"):
        check_members([info(f"{GAME_FOLDER}/a.dll"), info(f"{GAME_FOLDER}/A.DLL")])


def test_size_limit() -> None:
    entry = info(f"{GAME_FOLDER}/{GAME_EXE}")
    entry.file_size = 3 * 1024**3
    with pytest.raises(InstallError, match="large"):
        check_members([entry])


def test_regular_members_pass() -> None:
    members = check_members([info(f"{GAME_FOLDER}/"),
                             info(f"{GAME_FOLDER}/{GAME_EXE}", stat.S_IFREG | 0o644),
                             info(f"{GAME_FOLDER}/patches/", stat.S_IFDIR | 0o755),
                             info(f"{GAME_FOLDER}/SDL3.dll", 0o600)])
    assert [str(path) for _, path in members] == [
        GAME_FOLDER, f"{GAME_FOLDER}/{GAME_EXE}", f"{GAME_FOLDER}/patches",
        f"{GAME_FOLDER}/SDL3.dll"]
