# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import os
from pathlib import Path

import pytest

from project_reforged_linux import savesync
from project_reforged_linux.savesync import sync_saves

OLD, NEW = 1_794_900_000, 1_794_985_886


def save_slot(folder: Path, slot: str, text: str, when: int, *, line_end: str = "\n") -> None:
    # His format: a .sav, an .info and a .png per slot.
    folder.mkdir(parents=True, exist_ok=True)
    for suffix, data in ((".sav", f"shadowkey-save\t1{line_end}name\t{text}{line_end}"),
                         (".info", f"shadowkey-saveinfo\t1{line_end}name\t{text}{line_end}"),
                         (".png", f"png {text}")):
        path = folder / f"{slot}{suffix}"
        path.write_bytes(data.encode("utf-8"))
        os.utime(path, (when, when))


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    return tmp_path / "windows", tmp_path / "linux", tmp_path / "backups"


def test_a_slot_only_the_other_build_has_comes_over(dirs: tuple[Path, Path, Path]) -> None:
    other, mine, backups = dirs
    save_slot(other, "game0", "Balshas", NEW, line_end="\r\n")
    assert sync_saves(other, mine, backups) == ["game0"]
    assert names(mine) == ["game0.info", "game0.png", "game0.sav"]
    # Byte for byte: both builds read each other's line ends.
    assert (mine / "game0.sav").read_bytes() == (other / "game0.sav").read_bytes()
    assert (mine / "game0.sav").stat().st_mtime == NEW


def test_the_newer_slot_wins(dirs: tuple[Path, Path, Path]) -> None:
    other, mine, backups = dirs
    save_slot(other, "auto1", "newer", NEW)
    save_slot(mine, "auto1", "older", OLD)
    assert sync_saves(other, mine, backups) == ["auto1"]
    assert b"newer" in (mine / "auto1.sav").read_bytes()
    assert b"newer" in (mine / "auto1.png").read_bytes()  # the picture goes with its save


def test_an_older_slot_never_overwrites(dirs: tuple[Path, Path, Path]) -> None:
    other, mine, backups = dirs
    save_slot(other, "game1", "older", OLD)
    save_slot(mine, "game1", "newer", NEW)
    assert sync_saves(other, mine, backups) == []
    assert b"newer" in (mine / "game1.sav").read_bytes()
    assert not backups.exists()


def test_the_same_slot_on_both_sides_copies_nothing(dirs: tuple[Path, Path, Path]) -> None:
    other, mine, backups = dirs
    save_slot(other, "game0", "same", NEW)
    save_slot(mine, "game0", "same", NEW)
    assert sync_saves(other, mine, backups) == []


def test_what_is_overwritten_is_backed_up_first(dirs: tuple[Path, Path, Path]) -> None:
    other, mine, backups = dirs
    save_slot(other, "auto1", "newer", NEW)
    save_slot(mine, "auto1", "older", OLD)
    sync_saves(other, mine, backups)
    kept, = list(backups.iterdir())
    assert names(kept) == ["auto1.info", "auto1.png", "auto1.sav"]
    assert b"older" in (kept / "auto1.sav").read_bytes()
    assert (kept / "auto1.sav").stat().st_mtime == OLD


def test_only_save_slots_are_touched(dirs: tuple[Path, Path, Path]) -> None:
    other, mine, backups = dirs
    save_slot(other, "game0", "x", NEW)
    (other / "settings.cfg").write_text("fov = 60\n", encoding="utf-8")
    (other / "ShadowkeyPort").mkdir()
    (other / "game0.sav.part").write_text("x", encoding="utf-8")
    (other / "gameX.sav").write_text("x", encoding="utf-8")
    sync_saves(other, mine, backups)
    assert names(mine) == ["game0.info", "game0.png", "game0.sav"]


def test_a_slot_without_its_sav_is_not_a_slot(dirs: tuple[Path, Path, Path]) -> None:
    other, mine, backups = dirs
    other.mkdir()
    (other / "game3.png").write_bytes(b"png")
    assert sync_saves(other, mine, backups) == []


def test_a_link_on_either_side_skips_the_slot(dirs: tuple[Path, Path, Path],
                                              tmp_path: Path) -> None:
    other, mine, backups = dirs
    save_slot(other, "game0", "x", NEW)
    save_slot(other, "game1", "y", NEW)
    mine.mkdir()
    (mine / "game0.sav").symlink_to(tmp_path / "elsewhere")
    os.utime(other / "game1.sav", (NEW, NEW))
    (other / "game1.png").unlink()
    (other / "game1.png").symlink_to("/etc/passwd")
    assert sync_saves(other, mine, backups) == []
    assert not (tmp_path / "elsewhere").exists()
    assert (mine / "game0.sav").is_symlink()


def test_no_other_folder_means_nothing_to_do(dirs: tuple[Path, Path, Path]) -> None:
    other, mine, backups = dirs
    assert sync_saves(other, mine, backups) == []
    assert not mine.exists()


def test_a_failed_copy_leaves_the_old_slot(dirs: tuple[Path, Path, Path],
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    other, mine, backups = dirs
    save_slot(other, "auto1", "newer", NEW)
    save_slot(mine, "auto1", "older", OLD)

    real = savesync.shutil.copy2
    copies: list[object] = []

    def full_after_one(src: object, dst: object, **kwargs: object) -> object:
        # The backup takes three copies; the slot's first file then lands, the second fails.
        copies.append(dst)
        if len(copies) == 5:
            raise OSError("disk full")
        return real(src, dst, **kwargs)

    monkeypatch.setattr(savesync.shutil, "copy2", full_after_one)
    with pytest.raises(OSError):
        sync_saves(other, mine, backups)
    assert b"older" in (mine / "auto1.sav").read_bytes()
    assert names(mine) == ["auto1.info", "auto1.png", "auto1.sav"]  # no half-copied leftovers
