# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import gzip
import io
import os
import stat
import tarfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from kista.testing import HOSTILE_FILE_PATHS, HOSTILE_PATH_COMPONENTS

from project_reforged_linux.builds import Build
from project_reforged_linux.install import (
    APPIMAGE_NAME,
    GAME_FOLDER,
    LINUX_BINARY,
    MAX_MEMBERS,
    InstallError,
    check_tar_members,
    executable,
    install_appimage,
    install_tarball,
)
from project_reforged_linux.paths import AppPaths, ensure_dirs, resolve

BIN_TIME = 1_794_964_479  # 2026-11-18 01:34:39, his 0.2.48 build
README_TIME = 1_794_900_000


def member(name: str, data: bytes = b"", *, kind: bytes = tarfile.REGTYPE, mode: int = 0o644,
           mtime: int = README_TIME, link: str = "") -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.type, info.mode, info.mtime, info.linkname = kind, mode, mtime, link
    info.size = len(data) if kind == tarfile.REGTYPE else 0
    return info, data


def make_tar(path: Path, members: list[tuple[tarfile.TarInfo, bytes]]) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for info, data in members:
            archive.addfile(info, io.BytesIO(data) if info.isreg() else None)
    return path


def his_tar(path: Path, binary: bytes = b"\x7fELF new") -> Path:
    # The shape of his 0.2.48 tarball: one top folder, folders, files, one executable.
    return make_tar(path, [
        member(f"{GAME_FOLDER}/", kind=tarfile.DIRTYPE, mode=0o755, mtime=BIN_TIME),
        member(f"{GAME_FOLDER}/README.txt", b"readme"),
        member(f"{GAME_FOLDER}/{LINUX_BINARY}", binary, mode=0o755, mtime=BIN_TIME),
        member(f"{GAME_FOLDER}/fonts/", kind=tarfile.DIRTYPE, mode=0o755, mtime=BIN_TIME),
        member(f"{GAME_FOLDER}/fonts/Cinzel.ttf", b"font", mtime=BIN_TIME),
    ])


@pytest.fixture
def paths(xdg_home: Path) -> AppPaths:
    p = resolve()
    ensure_dirs(p)
    return p


def hidden(paths: AppPaths) -> list[str]:
    return sorted(p.name for p in paths.data.iterdir() if p.name.startswith("."))



def test_installs_the_tarball_into_its_own_folder(paths: AppPaths, tmp_path: Path) -> None:
    exe = install_tarball(his_tar(tmp_path / "s.tar.gz"), paths)
    assert exe == executable(paths, Build.LINUX_TARBALL) == (
        paths.data / "linux" / GAME_FOLDER / LINUX_BINARY)
    assert exe.read_bytes() == b"\x7fELF new"
    assert (exe.parent / "fonts" / "Cinzel.ttf").read_bytes() == b"font"
    assert not (paths.game / GAME_FOLDER).exists()


def test_the_binary_runs_and_the_rest_does_not(paths: AppPaths, tmp_path: Path) -> None:
    exe = install_tarball(his_tar(tmp_path / "s.tar.gz"), paths)
    assert stat.S_IMODE(exe.stat().st_mode) == 0o755
    assert stat.S_IMODE((exe.parent / "README.txt").stat().st_mode) == 0o644


def test_every_member_keeps_its_date(paths: AppPaths, tmp_path: Path) -> None:
    exe = install_tarball(his_tar(tmp_path / "s.tar.gz"), paths)
    assert exe.stat().st_mtime == BIN_TIME
    assert (exe.parent / "README.txt").stat().st_mtime == README_TIME
    assert (exe.parent / "fonts").stat().st_mtime == BIN_TIME
    assert exe.parent.stat().st_mtime == BIN_TIME


def test_a_new_tarball_replaces_the_old_install(paths: AppPaths, tmp_path: Path) -> None:
    install_tarball(his_tar(tmp_path / "a.tar.gz", b"\x7fELF old"), paths)
    leftover = executable(paths, Build.LINUX_TARBALL).parent / "assets.old"
    leftover.mkdir()  # what his own updater leaves behind
    install_tarball(his_tar(tmp_path / "b.tar.gz"), paths)
    assert executable(paths, Build.LINUX_TARBALL).read_bytes() == b"\x7fELF new"
    assert not leftover.exists()
    assert hidden(paths) == []


def test_a_tarball_without_his_binary_leaves_the_old_one(paths: AppPaths,
                                                         tmp_path: Path) -> None:
    install_tarball(his_tar(tmp_path / "a.tar.gz"), paths)
    bad = make_tar(tmp_path / "bad.tar.gz", [member(f"{GAME_FOLDER}/README.txt", b"x")])
    with pytest.raises(InstallError, match=LINUX_BINARY):
        install_tarball(bad, paths)
    assert executable(paths, Build.LINUX_TARBALL).read_bytes() == b"\x7fELF new"
    assert hidden(paths) == []


def test_a_hostile_tarball_leaves_the_old_one(paths: AppPaths, tmp_path: Path) -> None:
    install_tarball(his_tar(tmp_path / "a.tar.gz"), paths)
    bad = make_tar(tmp_path / "bad.tar.gz", [
        member(f"{GAME_FOLDER}/{LINUX_BINARY}", b"\x7fELF evil", mode=0o755),
        member(f"{GAME_FOLDER}/../evil", b"x")])
    with pytest.raises(InstallError):
        install_tarball(bad, paths)
    assert executable(paths, Build.LINUX_TARBALL).read_bytes() == b"\x7fELF new"
    assert not (paths.data / "linux" / "evil").exists()
    assert hidden(paths) == []


@pytest.mark.parametrize("content", [b"", b"not gzip at all", b"\x1f\x8b\x08\x00broken"])
def test_a_broken_tarball_is_an_install_error(paths: AppPaths, tmp_path: Path,
                                              content: bytes) -> None:
    junk = tmp_path / "junk.tar.gz"
    junk.write_bytes(content)
    with pytest.raises(InstallError):
        install_tarball(junk, paths)
    assert hidden(paths) == []


HOSTILE_NAMES = [
    *[(label, path) for label, path in HOSTILE_FILE_PATHS if "\x00" not in path],
    *[(label, f"{GAME_FOLDER}/{part}") for label, part in HOSTILE_PATH_COMPONENTS
      if "\x00" not in part],
    ("other-top-folder", "Other/x"),
]


@pytest.mark.parametrize(("label", "name"), HOSTILE_NAMES)
def test_hostile_names_are_refused(label: str, name: str) -> None:
    with pytest.raises(InstallError):
        check_tar_members([member(f"{GAME_FOLDER}/{LINUX_BINARY}")[0], member(name)[0]])


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE,
                                  tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.CONTTYPE])
def test_links_and_special_files_are_refused(kind: bytes) -> None:
    odd = member(f"{GAME_FOLDER}/odd", kind=kind, link=f"{GAME_FOLDER}/README.txt")[0]
    with pytest.raises(InstallError, match="plain"):
        check_tar_members([odd])


def test_member_count_and_size_are_capped() -> None:
    many = [member(f"{GAME_FOLDER}/f{i}")[0] for i in range(10_001)]
    with pytest.raises(InstallError, match="members"):
        check_tar_members(many)
    big = member(f"{GAME_FOLDER}/{LINUX_BINARY}")[0]
    big.size = 3 * 1024**3
    with pytest.raises(InstallError, match="large"):
        check_tar_members([big])


def test_regular_members_pass() -> None:
    names = [str(path) for _, path in check_tar_members(
        [m for m, _ in (member(f"{GAME_FOLDER}/", kind=tarfile.DIRTYPE),
                        member(f"{GAME_FOLDER}/{LINUX_BINARY}", mode=0o755),
                        member(f"{GAME_FOLDER}/assets/a.png"))])]
    assert names == [GAME_FOLDER, f"{GAME_FOLDER}/{LINUX_BINARY}", f"{GAME_FOLDER}/assets/a.png"]



def appimage(tmp_path: Path, content: bytes = b"\x7fELF appimage", mtime: int = BIN_TIME) -> Path:
    path = tmp_path / "Shadowkey-0.2.48-linux-x86_64.AppImage"
    path.write_bytes(content)
    os.utime(path, (mtime, mtime))
    return path


def test_installs_the_appimage_under_one_name(paths: AppPaths, tmp_path: Path) -> None:
    # His updater keeps whatever name the file has, so the name stays.
    exe = install_appimage(appimage(tmp_path), paths)
    assert exe == executable(paths, Build.LINUX_APPIMAGE) == (
        paths.data / "appimage" / APPIMAGE_NAME)
    assert exe.read_bytes() == b"\x7fELF appimage"
    assert stat.S_IMODE(exe.stat().st_mode) == 0o755
    assert exe.stat().st_mtime == BIN_TIME
    # The download stays: the caller removes it once the swap has worked.
    assert (tmp_path / "Shadowkey-0.2.48-linux-x86_64.AppImage").exists()


def test_a_failed_swap_keeps_the_download(paths: AppPaths, tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    # Moved into staging, the checked AppImage went with it, and Update fetched it again.
    from project_reforged_linux import install

    install_appimage(appimage(tmp_path, b"\x7fELF old"), paths)
    download = appimage(tmp_path)
    real = os.rename

    def refuse_the_swap(src: object, dst: object) -> None:
        if str(src).startswith(str(paths.data / ".appimage-new-")):
            raise OSError(28, "No space left on device")
        real(src, dst)

    monkeypatch.setattr(install.os, "rename", refuse_the_swap)
    with pytest.raises(OSError, match="No space"):
        install_appimage(download, paths)
    assert download.read_bytes() == b"\x7fELF appimage"
    assert executable(paths, Build.LINUX_APPIMAGE).read_bytes() == b"\x7fELF old"


def test_a_new_appimage_replaces_the_old_one(paths: AppPaths, tmp_path: Path) -> None:
    install_appimage(appimage(tmp_path, b"\x7fELF old"), paths)
    install_appimage(appimage(tmp_path), paths)
    assert executable(paths, Build.LINUX_APPIMAGE).read_bytes() == b"\x7fELF appimage"
    assert sorted(p.name for p in (paths.data / "appimage").iterdir()) == [APPIMAGE_NAME]


def test_something_that_is_no_program_is_refused(paths: AppPaths, tmp_path: Path) -> None:
    install_appimage(appimage(tmp_path), paths)
    with pytest.raises(InstallError, match="not a Linux program"):
        install_appimage(appimage(tmp_path, b"<html>404</html>"), paths)
    assert executable(paths, Build.LINUX_APPIMAGE).read_bytes() == b"\x7fELF appimage"


def test_the_windows_build_keeps_its_exe() -> None:
    paths = AppPaths(Path("/d"), Path("/c"), Path("/k"), Path("/s"))
    assert executable(paths, Build.WINDOWS) == Path("/d/game/Shadowkey/Shadowkey.exe")


@pytest.mark.parametrize("mtime", [10**20, -10**20])
def test_a_member_date_out_of_range_is_refused(mtime: int) -> None:
    member = tarfile.TarInfo(f"{GAME_FOLDER}/{LINUX_BINARY}")
    member.mtime = mtime
    with pytest.raises(InstallError, match="date"):
        check_tar_members([member])


def test_a_disk_problem_is_not_called_a_bad_tarball(paths: AppPaths, tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    from project_reforged_linux import install

    def full(tar_path: Path, staging: Path) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(install, "_unpack_tar", full)
    with pytest.raises(OSError, match="No space left") as raised:
        install_tarball(his_tar(tmp_path / "his.tar.gz"), paths)
    assert not isinstance(raised.value, InstallError)


def test_one_name_twice_in_his_tarball_is_its_fault(paths: AppPaths, tmp_path: Path) -> None:
    install_tarball(his_tar(tmp_path / "a.tar.gz"), paths)
    twice = make_tar(tmp_path / "twice.tar.gz", [
        member(f"{GAME_FOLDER}/{LINUX_BINARY}", b"\x7fELF other", mode=0o755),
        member(f"{GAME_FOLDER}/{LINUX_BINARY}", b"\x7fELF other", mode=0o755)])
    with pytest.raises(InstallError, match="one name twice") as raised:
        install_tarball(twice, paths)
    assert str(paths.data) not in str(raised.value)
    assert executable(paths, Build.LINUX_TARBALL).read_bytes() == b"\x7fELF new"
    assert hidden(paths) == []


def test_a_size_past_the_limit_stops_at_its_header(paths: AppPaths, tmp_path: Path) -> None:
    # The header alone: walking past it would inflate 3 GiB, or here end in a read error.
    huge = tarfile.TarInfo(f"{GAME_FOLDER}/{LINUX_BINARY}")
    huge.size = 3 * 1024**3
    path = tmp_path / "huge.tar.gz"
    with gzip.open(path, "wb") as out:
        out.write(huge.tobuf())
    with pytest.raises(InstallError, match="2 GiB"):
        install_tarball(path, paths)
    assert hidden(paths) == []


def test_the_member_limit_stops_the_walk(tmp_path: Path) -> None:
    pulled = 0

    def members() -> Iterator[tarfile.TarInfo]:
        nonlocal pulled
        while True:
            pulled += 1
            yield member(f"{GAME_FOLDER}/f{pulled}")[0]

    with pytest.raises(InstallError, match="more than"):
        check_tar_members(members())
    assert pulled == MAX_MEMBERS + 1
