# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import os
import shutil
from pathlib import Path

import pytest

from project_reforged_linux import artseed
from project_reforged_linux.artseed import ART, INDEX, seed_art

WHEN = 1_794_900_000


def his_art(port: Path) -> Path:
    art = port / ART
    (art / "model").mkdir(parents=True)
    (art / INDEX).write_text("sha size path\n", encoding="utf-8")
    picture = art / "model" / "023 male_short_tunic skin9.png"
    picture.write_bytes(b"\x89PNG picture")
    for path in (picture, art / INDEX, art / "model", art):
        os.utime(path, (WHEN, WHEN))
    return art


def test_seeds_an_empty_build_with_the_others_art(tmp_path: Path) -> None:
    source, target = tmp_path / "windows", tmp_path / "linux"
    his_art(source)
    assert seed_art(source, target)
    picture = target / ART / "model" / "023 male_short_tunic skin9.png"
    assert picture.read_bytes() == b"\x89PNG picture"
    assert (target / ART / INDEX).is_file()


def test_the_copy_keeps_every_date(tmp_path: Path) -> None:
    source, target = tmp_path / "windows", tmp_path / "linux"
    his_art(source)
    seed_art(source, target)
    for path in (target / ART, target / ART / "model", target / ART / INDEX,
                 target / ART / "model" / "023 male_short_tunic skin9.png"):
        assert path.stat().st_mtime == WHEN, path


def test_art_already_there_is_left_alone(tmp_path: Path) -> None:
    source, target = tmp_path / "windows", tmp_path / "linux"
    his_art(source)
    (target / ART).mkdir(parents=True)
    (target / ART / INDEX).write_text("mine\n", encoding="utf-8")
    assert not seed_art(source, target)
    assert (target / ART / INDEX).read_text(encoding="utf-8") == "mine\n"


def test_an_empty_art_folder_is_seeded(tmp_path: Path) -> None:
    source, target = tmp_path / "windows", tmp_path / "linux"
    his_art(source)
    (target / ART).mkdir(parents=True)
    assert seed_art(source, target)
    assert (target / ART / INDEX).is_file()


def test_a_source_without_his_index_seeds_nothing(tmp_path: Path) -> None:
    source, target = tmp_path / "windows", tmp_path / "linux"
    (source / ART).mkdir(parents=True)
    (source / ART / "half.png").write_bytes(b"x")
    assert not seed_art(source, target)
    assert not (target / ART).exists()


def test_a_link_in_the_source_seeds_nothing(tmp_path: Path) -> None:
    source, target = tmp_path / "windows", tmp_path / "linux"
    art = his_art(source)
    (art / "model" / "elsewhere.png").symlink_to("/etc/passwd")
    assert not seed_art(source, target)
    assert not (target / ART).exists()


def test_a_failed_copy_leaves_nothing_half_done(tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    source, target = tmp_path / "windows", tmp_path / "linux"
    his_art(source)

    def broken(src: str, dst: str, **kwargs: object) -> str:
        raise OSError("disk full")

    monkeypatch.setattr(artseed.shutil, "copy2", broken)
    with pytest.raises(OSError):
        seed_art(source, target)
    assert not (target / ART).exists()
    assert [p.name for p in target.iterdir()] == []


def test_the_seed_is_a_copy_not_a_move(tmp_path: Path) -> None:
    source, target = tmp_path / "windows", tmp_path / "linux"
    his_art(source)
    seed_art(source, target)
    assert (source / ART / INDEX).is_file()
    shutil.rmtree(target / ART)
    assert (source / ART / "model" / "023 male_short_tunic skin9.png").is_file()
