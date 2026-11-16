# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The .desktop file and icons GNOME needs to show the launcher in the dock."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import platformdirs
from kista.fileops import copy_preserving, write_atomic

from project_reforged_linux import APP_ID, APP_NAME

__all__ = ["ICON_SIZES", "ICONS_SOURCE", "DesktopTargets", "current_appimage", "desktop_entry",
           "install", "installed_exec", "quote_exec_arg", "refresh_exec", "remove", "targets"]

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICONS_SOURCE = Path(__file__).parent / "data" / "icons" / "hicolor"
# Desktop Entry Specification 1.5, "The Exec key": characters that force quoting.
_RESERVED = frozenset(" \t\"'\\><~|&;$*?#()`")
_ESCAPED_IN_QUOTES = frozenset('"`$\\')


@dataclass(frozen=True, slots=True)
class DesktopTargets:
    applications: Path
    icons: Path  # the hicolor theme folder

    @property
    def desktop_file(self) -> Path:
        return self.applications / f"{APP_ID}.desktop"

    def icon_files(self) -> list[Path]:
        files = [self.icons / f"{s}x{s}" / "apps" / f"{APP_ID}.png" for s in ICON_SIZES]
        files.append(self.icons / "scalable" / "apps" / f"{APP_ID}.svg")
        return files


def targets() -> DesktopTargets:
    base = platformdirs.user_data_path()
    return DesktopTargets(base / "applications", base / "icons" / "hicolor")


def current_appimage(env: Mapping[str, str] = os.environ) -> Path | None:
    value = env.get("APPIMAGE")
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() and path.is_file() else None


def quote_exec_arg(arg: str) -> str:
    """One Exec argument, quoted per the spec and then escaped as a string value."""
    if not arg or "\n" in arg or "\r" in arg:
        raise ValueError(f"cannot put this into Exec=: {arg!r}")
    arg = arg.replace("%", "%%")
    if any(c in _RESERVED for c in arg):
        arg = '"' + "".join("\\" + c if c in _ESCAPED_IN_QUOTES else c for c in arg) + '"'
    return arg.replace("\\", "\\\\")


def desktop_entry(exec_path: Path) -> str:
    return ("[Desktop Entry]\n"
            "Type=Application\n"
            "Version=1.5\n"
            "Name=Project Reforged Linux Launcher\n"
            "GenericName=Game Launcher\n"
            "Comment=Downloads Dan Whelan's Project Reforged and starts it under Wine\n"
            f"Exec={quote_exec_arg(str(exec_path))}\n"
            f"Icon={APP_ID}\n"
            "Terminal=false\n"
            f"StartupWMClass={APP_NAME}\n"
            "Categories=Game;RolePlaying;\n"
            "Keywords=Shadowkey;N-Gage;Reforged;\n")


def install(where: DesktopTargets, exec_path: Path, *, source: Path = ICONS_SOURCE) -> list[Path]:
    """Write the icons and the entry; returns every file written, for the player to see."""
    if not exec_path.is_absolute():
        raise ValueError(f"Exec must be an absolute path: {exec_path}")
    pairs = [(source / target.relative_to(where.icons), target) for target in where.icon_files()]
    missing = [str(src) for src, _ in pairs if not src.is_file()]
    if missing:
        raise FileNotFoundError(f"icons missing from the package: {', '.join(missing)}")
    written = []
    for src, target in pairs:
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_preserving(src, target, verify_content=True)
        written.append(target)
    where.applications.mkdir(parents=True, exist_ok=True)
    write_atomic(where.desktop_file, desktop_entry(exec_path).encode("utf-8"))
    written.append(where.desktop_file)
    return written


def remove(where: DesktopTargets) -> list[Path]:
    """Delete exactly the files install writes; returns what was there."""
    removed = []
    for path in (where.desktop_file, *where.icon_files()):
        if path.is_file() or path.is_symlink():
            path.unlink()
            removed.append(path)
    return removed


def installed_exec(where: DesktopTargets) -> str | None:
    try:
        text = where.desktop_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    for line in text.splitlines():
        if line.startswith("Exec="):
            return line[len("Exec="):]
    return None


def refresh_exec(where: DesktopTargets, exec_path: Path) -> bool:
    """Point an installed entry at where the AppImage is now; False when nothing changed."""
    current = installed_exec(where)
    if current is None or current == quote_exec_arg(str(exec_path)):
        return False
    write_atomic(where.desktop_file, desktop_entry(exec_path).encode("utf-8"))
    return True
