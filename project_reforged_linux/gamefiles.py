# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Finding and checking the player's N-Gage game files."""

from pathlib import Path, PurePosixPath

from kista.fileops import write_atomic

__all__ = [
    "LEVEL_FILES",
    "find_6r51",
    "missing_level_files",
    "to_wine_path",
    "validate",
    "write_game_folder_txt",
]

# The 21 levels of the N-Gage release (ngarchive dump of 26.10.2004)
LEVEL_FILES: frozenset[str] = frozenset({
    "azra.zmp", "broken1.zmp", "broken2.zmp", "crypt1.zmp", "crypt2.zmp",
    "crypt3.zmp", "delfhide.zmp", "drgnfld.zmp", "dstar_e.zmp", "dstar_w.zmp",
    "erthcave.zmp", "fearfrst.zmp", "ffarena.zmp", "ghstpass.zmp",
    "glaciercrawl.zmp", "lakvan.zmp", "lothcav.zmp", "raiders.zmp",
    "snowline.zmp", "stouttp.zmp", "twilite.zmp",
})

GAME_FOLDER_TXT = "game_folder.txt"


def _child_ci(directory: Path, name: str) -> Path | None:
    """The child of directory named name, compared case-insensitively."""
    matches = [p for p in directory.iterdir() if p.name.lower() == name.lower() and p.is_dir()]
    if len(matches) > 1:
        raise ValueError(f"more than one {name} folder in {directory}")
    return matches[0] if matches else None


def find_6r51(chosen: Path) -> Path | None:
    """The 6R51 folder, given that folder, its parent, or a memory card root."""
    if not chosen.is_dir():
        raise NotADirectoryError(f"not a folder: {chosen}")
    if chosen.name.lower() == "6r51":
        return chosen
    direct = _child_ci(chosen, "6r51")
    if direct is not None:
        return direct
    system = _child_ci(chosen, "system")
    apps = _child_ci(system, "apps") if system is not None else None
    return _child_ci(apps, "6r51") if apps is not None else None


def missing_level_files(folder: Path) -> list[str]:
    present = {p.name.lower() for p in folder.iterdir() if p.is_file()}
    return sorted(LEVEL_FILES - present)


def validate(chosen: Path) -> Path:
    """Return the 6R51 folder or fail with a message the player can act on."""
    folder = find_6r51(chosen)
    if folder is None:
        raise FileNotFoundError(f"no 6R51 folder in {chosen}")
    missing = missing_level_files(folder)
    if missing:
        raise ValueError(f"{folder} is missing level files: {', '.join(missing)}")
    return folder


def to_wine_path(path: Path) -> str:
    """The path as Windows programs in the prefix see it, through drive Z:."""
    if not path.is_absolute():
        raise ValueError(f"path must be absolute: {path}")
    return "Z:\\" + "\\".join(PurePosixPath(path).parts[1:])


def write_game_folder_txt(port_dir: Path, folder: Path) -> None:
    """Write the file his setup page writes, so the page never appears."""
    content = to_wine_path(folder.resolve()) + "\r\n"
    write_atomic(port_dir / GAME_FOLDER_TXT, content.encode("utf-8"))
