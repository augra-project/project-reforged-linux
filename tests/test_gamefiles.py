# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
from pathlib import Path

import pytest

from project_reforged_linux.gamefiles import (
    LEVEL_FILES,
    find_6r51,
    missing_level_files,
    to_wine_path,
    validate,
    write_game_folder_txt,
)


def make_6r51(base: Path, name: str = "6r51", upper: bool = False) -> Path:
    folder = base / name
    folder.mkdir(parents=True)
    for level in LEVEL_FILES:
        (folder / (level.upper() if upper else level)).write_bytes(b"\0")
    return folder


def test_level_file_count() -> None:
    assert len(LEVEL_FILES) == 21
    assert "delfhide.zmp" in LEVEL_FILES


def test_find_accepts_the_folder_itself(tmp_path: Path) -> None:
    folder = make_6r51(tmp_path)
    assert find_6r51(folder) == folder


def test_find_accepts_parent(tmp_path: Path) -> None:
    folder = make_6r51(tmp_path, "6R51")
    assert find_6r51(tmp_path) == folder


def test_find_accepts_memory_card_root(tmp_path: Path) -> None:
    folder = make_6r51(tmp_path / "system" / "apps")
    assert find_6r51(tmp_path) == folder


def test_find_is_case_insensitive(tmp_path: Path) -> None:
    folder = make_6r51(tmp_path / "System" / "Apps", "6R51")
    assert find_6r51(tmp_path) == folder


def test_find_returns_none_when_absent(tmp_path: Path) -> None:
    (tmp_path / "something").mkdir()
    assert find_6r51(tmp_path) is None


def test_find_rejects_ambiguous(tmp_path: Path) -> None:
    make_6r51(tmp_path, "6r51")
    make_6r51(tmp_path, "6R51")
    with pytest.raises(ValueError, match="more than one"):
        find_6r51(tmp_path)


def test_find_rejects_non_directory(tmp_path: Path) -> None:
    f = tmp_path / "file"
    f.write_bytes(b"")
    with pytest.raises(NotADirectoryError):
        find_6r51(f)


def test_missing_level_files_case_insensitive(tmp_path: Path) -> None:
    folder = make_6r51(tmp_path, upper=True)
    assert missing_level_files(folder) == []


def test_missing_level_files_lists_gaps(tmp_path: Path) -> None:
    folder = make_6r51(tmp_path)
    (folder / "delfhide.zmp").unlink()
    (folder / "azra.zmp").unlink()
    assert missing_level_files(folder) == ["azra.zmp", "delfhide.zmp"]


def test_validate_returns_folder(tmp_path: Path) -> None:
    folder = make_6r51(tmp_path / "system" / "apps")
    assert validate(tmp_path) == folder


def test_validate_names_missing_files(tmp_path: Path) -> None:
    folder = make_6r51(tmp_path)
    (folder / "lakvan.zmp").unlink()
    with pytest.raises(ValueError, match="lakvan.zmp"):
        validate(folder)


def test_validate_without_6r51(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        validate(tmp_path)


def test_to_wine_path() -> None:
    assert to_wine_path(Path("/home/a/games/6r51")) == "Z:\\home\\a\\games\\6r51"


def test_to_wine_path_rejects_relative() -> None:
    with pytest.raises(ValueError):
        to_wine_path(Path("games/6r51"))


def test_write_game_folder_txt_format(tmp_path: Path) -> None:
    port = tmp_path / "ShadowkeyPort"
    port.mkdir()
    folder = make_6r51(tmp_path / "card")
    write_game_folder_txt(port, folder)
    data = (port / "game_folder.txt").read_bytes()
    assert data == to_wine_path(folder).encode("utf-8") + b"\r\n"
    assert not data.startswith(b"\xef\xbb\xbf")


def test_write_game_folder_txt_non_ascii(tmp_path: Path) -> None:
    port = tmp_path / "ShadowkeyPort"
    port.mkdir()
    folder = make_6r51(tmp_path / "Zoë's café games")
    write_game_folder_txt(port, folder)
    text = (port / "game_folder.txt").read_bytes().decode("utf-8")
    assert "Zoë's café games" in text
