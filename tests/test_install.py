# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import io
import stat
import struct
import time
import zipfile
from pathlib import Path

import pytest
from kista.testing import HOSTILE_FILE_PATHS, HOSTILE_PATH_COMPONENTS

from project_reforged_linux.gamefiles import find_6r51_below
from project_reforged_linux.install import (
    GAME_EXE,
    GAME_FOLDER,
    MAX_CARD,
    MAX_DIRECTORY,
    InstallError,
    check_members,
    directory_sizes,
    game_exe,
    install_card_zip,
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


CARD_DATE = (2004, 10, 26, 12, 0, 0)
LEVELS = ("azra.zmp", "crypt1.zmp")


def card_zip(path: Path, wrap: str = "", levels: tuple[str, ...] = LEVELS) -> Path:
    return make_zip(path, [
        (f"{wrap}game.id", b"id", (1996, 12, 24, 23, 32, 0)),
        (f"{wrap}system/", b"", CARD_DATE),
        (f"{wrap}system/apps/", b"", CARD_DATE),
        (f"{wrap}system/apps/6r51/", b"", CARD_DATE),
        *((f"{wrap}system/apps/6r51/{name}", b"level", CARD_DATE) for name in levels),
    ])


def find(root: Path) -> Path | None:
    return find_6r51_below(root)


@pytest.mark.parametrize("wrap", ["", "Shadowkey/"])
def test_a_card_zip_unpacks_with_its_dates(paths: AppPaths, tmp_path: Path, wrap: str) -> None:
    folder = install_card_zip(card_zip(tmp_path / "card.zip", wrap), paths, find)
    assert folder == paths.card / wrap / "system" / "apps" / "6r51"
    assert sorted(p.name for p in folder.iterdir()) == sorted(LEVELS)
    assert (folder / "azra.zmp").stat().st_mtime == local(CARD_DATE)
    assert (paths.card / wrap / "game.id").stat().st_mtime == local((1996, 12, 24, 23, 32, 0))
    assert folder.stat().st_mtime == local(CARD_DATE)
    assert hidden(paths) == []


def test_a_zip_without_a_card_leaves_the_old_one(paths: AppPaths, tmp_path: Path) -> None:
    install_card_zip(card_zip(tmp_path / "card.zip"), paths, find)
    other = make_zip(tmp_path / "photos.zip", [("holiday.jpg", b"jpeg", CARD_DATE)])
    with pytest.raises(InstallError, match="no 6R51 folder in photos.zip"):
        install_card_zip(other, paths, find)
    assert (paths.card / "system" / "apps" / "6r51" / "azra.zmp").is_file()
    assert hidden(paths) == []


@pytest.mark.parametrize("name", ["../escape.zmp", "/etc/passwd", "system/../../x"])
def test_a_hostile_card_zip_is_refused(paths: AppPaths, tmp_path: Path, name: str) -> None:
    bad = make_zip(tmp_path / "bad.zip", [("system/apps/6r51/azra.zmp", b"x", CARD_DATE),
                                          (name, b"x", CARD_DATE)])
    with pytest.raises(InstallError):
        install_card_zip(bad, paths, find)
    assert not paths.card.exists()
    assert not (tmp_path / "escape.zmp").exists()


def test_a_card_zip_with_a_link_is_refused(paths: AppPaths, tmp_path: Path) -> None:
    path = tmp_path / "link.zip"
    with zipfile.ZipFile(path, "w") as archive:
        link = zipfile.ZipInfo("system/apps/6r51/azra.zmp", date_time=CARD_DATE)
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "/etc/passwd")
    with pytest.raises(InstallError, match="not a plain file"):
        install_card_zip(path, paths, find)


def test_a_card_zip_too_large_for_a_card_is_refused(paths: AppPaths, tmp_path: Path) -> None:
    path = tmp_path / "big.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo("system/apps/6r51/azra.zmp", date_time=CARD_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        with archive.open(info, "w") as member:
            chunk = b"\0" * (1 << 20)
            for _ in range(MAX_CARD // len(chunk) + 1):
                member.write(chunk)
    with pytest.raises(InstallError, match="more than 256 MiB"):
        install_card_zip(path, paths, find)
    assert not paths.card.exists()


def test_his_zip_still_needs_his_top_folder(tmp_path: Path) -> None:
    # The card takes any top; his build zip keeps its one folder.
    with pytest.raises(InstallError, match="unexpected name"):
        check_members([info("game.id")])
    assert [str(p) for _, p in check_members([info("game.id")], top=None)] == ["game.id"]


def test_an_unsupported_compression_is_refused(paths: AppPaths, tmp_path: Path) -> None:
    entry = info("system/apps/6r51/azra.zmp")
    entry.compress_type = 9  # Deflate64, which 7-Zip writes and zipfile cannot read
    with pytest.raises(InstallError, match="compression"):
        check_members([entry], top=None)


def test_a_corrupt_stream_is_refused_cleanly(paths: AppPaths, tmp_path: Path) -> None:
    path = tmp_path / "card.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(zipfile.ZipInfo("system/apps/6r51/azra.zmp", date_time=CARD_DATE),
                         b"level" * 4000, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(path) as archive:
        member = archive.infolist()[0]
        start = member.header_offset + 30 + len(member.filename.encode()) + len(member.extra)
    raw = bytearray(path.read_bytes())
    raw[start] = 0xFF  # deflate block type 3: invalid
    path.write_bytes(bytes(raw))
    with pytest.raises(InstallError, match="not a usable zip"):
        install_card_zip(path, paths, find)
    assert not paths.card.exists()


def test_his_zip_breaking_oddly_is_an_install_error(paths: AppPaths, tmp_path: Path) -> None:
    path = tmp_path / "his.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(zipfile.ZipInfo(f"{GAME_FOLDER}/{GAME_EXE}", date_time=EXE_DATE),
                         b"MZ" * 4000, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(path) as archive:
        member = archive.infolist()[0]
        start = member.header_offset + 30 + len(member.filename.encode()) + len(member.extra)
    raw = bytearray(path.read_bytes())
    raw[start] = 0xFF
    path.write_bytes(bytes(raw))
    with pytest.raises(InstallError, match="not a usable zip"):
        install_zip(path, paths)


def test_names_differing_only_in_a_folder_s_case_are_refused() -> None:
    # Two folders on Linux, one through Wine: the second file would land beside the first.
    with pytest.raises(InstallError, match="case"):
        check_members([info(f"{GAME_FOLDER}/Data/a.bin"), info(f"{GAME_FOLDER}/data/b.bin")])


def test_a_member_twice_is_refused() -> None:
    with pytest.raises(InstallError, match="twice"):
        check_members([info(f"{GAME_FOLDER}/a.dll"), info(f"{GAME_FOLDER}/a.dll")])


def test_a_folder_entry_and_its_files_share_one_spelling() -> None:
    members = check_members([info(f"{GAME_FOLDER}/patches/a.s"), info(f"{GAME_FOLDER}/patches/"),
                             info(f"{GAME_FOLDER}/patches/b.s")])
    assert len(members) == 3


def test_a_file_and_a_folder_of_one_name_is_his_zip_s_fault(paths: AppPaths,
                                                              tmp_path: Path) -> None:
    install_zip(his_zip(tmp_path / "good.zip"), paths)
    clash = make_zip(tmp_path / "clash.zip", [
        (f"{GAME_FOLDER}/{GAME_EXE}", b"MZ new", EXE_DATE),
        (f"{GAME_FOLDER}/patches", b"a file", DLL_DATE),
        (f"{GAME_FOLDER}/patches/azra.s", b"patch", DLL_DATE)])
    with pytest.raises(InstallError, match="one name twice") as raised:
        install_zip(clash, paths)
    assert str(paths.data) not in str(raised.value)
    assert game_exe(paths).read_bytes() == b"MZ exe"
    assert hidden(paths) == []


def test_an_unfinished_install_is_cleared_by_the_next(paths: AppPaths, tmp_path: Path) -> None:
    # A kill or a power cut leaves the staging folder; up to 2 GiB of his build.
    left = paths.game.parent / f".{paths.game.name}-new-k1ll3d"
    (left / GAME_FOLDER).mkdir(parents=True)
    (left / GAME_FOLDER / GAME_EXE).write_bytes(b"half")
    elsewhere = tmp_path / "keep"
    elsewhere.mkdir()
    (elsewhere / "mine").write_bytes(b"x")
    link = paths.game.parent / f".{paths.game.name}-new-link"
    link.symlink_to(elsewhere)
    install_zip(his_zip(tmp_path / "his.zip"), paths)
    assert not left.exists()
    assert (elsewhere / "mine").read_bytes() == b"x"  # a link is not followed, nor removed
    link.unlink()
    assert hidden(paths) == []


def zip_bytes(names: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(info(name), b"")
    return buffer.getvalue()


def test_the_directory_size_is_the_one_zipfile_reads(tmp_path: Path) -> None:
    raw = zip_bytes([f"{GAME_FOLDER}/{n}.dll" for n in range(40)])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        actual = len(raw) - 22 - archive.start_dir
    assert directory_sizes(io.BytesIO(raw)) == [actual]
    commented = io.BytesIO()
    with zipfile.ZipFile(commented, "w") as archive:
        archive.writestr(info(f"{GAME_FOLDER}/a.dll"), b"")
        archive.comment = b"PK no end record here" * 100
    raw = commented.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        actual = len(raw) - 22 - len(archive.comment) - archive.start_dir
    assert directory_sizes(io.BytesIO(raw)) == [actual]


def zip64_tail(size32: int, size64: int, *, at_locator: bool = True) -> bytes:
    """A zip64 end: record, locator, end record; the central directory itself is left out."""
    padding = b"\0" * 64
    record = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, 1, 1, size64, 0)
    where = len(padding) if at_locator else 0  # a wrong offset leaves zipfile the fixed place
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, where, 1)
    end = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 1, 1, size32, 0, 0)
    return padding + record + locator + end


@pytest.mark.parametrize("at_locator", [True, False])
def test_a_zip64_directory_size_is_read_from_its_record(at_locator: bool) -> None:
    # Its 32-bit size is a placeholder then; only the zip64 one counts, wherever it sits.
    raw = zip64_tail(0xFFFFFFFF, 1234, at_locator=at_locator)
    assert set(directory_sizes(io.BytesIO(raw))) == {1234}


def test_a_lying_zip64_size_is_seen() -> None:
    raw = zip64_tail(10, 64 * 1024**3)
    assert max(directory_sizes(io.BytesIO(raw))) == 64 * 1024**3


@pytest.mark.parametrize("raw", [b"", b"PK", b"not a zip at all" * 10, b"PK\x05\x06" + b"\0" * 5])
def test_no_end_record_means_no_size(raw: bytes) -> None:
    assert directory_sizes(io.BytesIO(raw)) == []


def test_a_table_of_contents_flood_is_refused_before_zipfile_reads_it(
        paths: AppPaths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Records only: zipfile would hold several times their size in memory.
    names = [f"{n:0250d}" for n in range(MAX_DIRECTORY // 250 + 1)]
    flood = tmp_path / "flood.zip"
    flood.write_bytes(zip_bytes(names))
    from project_reforged_linux import install

    def never(*args: object, **kwargs: object) -> None:
        raise AssertionError("zipfile was asked to read the directory")

    monkeypatch.setattr(install.zipfile, "ZipFile", never)
    with pytest.raises(InstallError, match="table of contents"):
        install_card_zip(flood, paths, find)
    assert not paths.card.exists()



def test_a_card_zip_with_backslash_folders_unpacks(paths: AppPaths, tmp_path: Path) -> None:
    # Old Windows zip tools: "System\\Apps\\" with only the DOS folder bit set.
    path = tmp_path / "old-tool.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for folder in ("System\\", "System\\Apps\\", "System\\Apps\\6R51\\"):
            entry = zipfile.ZipInfo(folder, date_time=CARD_DATE)
            entry.external_attr = 0x10
            archive.writestr(entry, b"")
        for level in LEVELS:
            archive.writestr(zipfile.ZipInfo(f"System\\Apps\\6R51\\{level}",
                                             date_time=CARD_DATE), b"zmp")
    folder = install_card_zip(path, paths, find)
    assert sorted(p.name for p in folder.iterdir()) == sorted(LEVELS)


def test_a_corrupt_lzma_member_is_a_named_install_error(paths: AppPaths, tmp_path: Path) -> None:
    # LZMAError is none of the zlib or zipfile errors; the player saw "Corrupt input data".
    path = tmp_path / "card.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_LZMA) as archive:
        archive.writestr(zipfile.ZipInfo("6r51/azra.zmp", date_time=CARD_DATE), b"zmp" * 4000,
                         compress_type=zipfile.ZIP_LZMA)
    with zipfile.ZipFile(path) as archive:
        member = archive.infolist()[0]
        start = member.header_offset + 30 + len(member.filename.encode()) + len(member.extra)
    raw = bytearray(path.read_bytes())
    raw[start + 20 : start + 40] = b"\xff" * 20
    path.write_bytes(bytes(raw))
    with pytest.raises(InstallError, match="card.zip is not a usable zip"):
        install_card_zip(path, paths, find)
