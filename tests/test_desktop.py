# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from project_reforged_linux import APP_ID
from project_reforged_linux.desktop import (
    ICON_SIZES,
    ICONS_SOURCE,
    DesktopTargets,
    current_appimage,
    desktop_entry,
    install,
    installed_exec,
    quote_exec_arg,
    refresh_exec,
    remove,
    targets,
)


@pytest.fixture
def where(tmp_path: Path) -> DesktopTargets:
    return DesktopTargets(tmp_path / "share" / "applications",
                          tmp_path / "share" / "icons" / "hicolor")


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    for size in ICON_SIZES:
        d = root / f"{size}x{size}" / "apps"
        d.mkdir(parents=True)
        (d / f"{APP_ID}.png").write_bytes(f"png {size}".encode())
        os.utime(d / f"{APP_ID}.png", (1_600_000_000, 1_600_000_000))
    (root / "scalable" / "apps").mkdir(parents=True)
    (root / "scalable" / "apps" / f"{APP_ID}.svg").write_bytes(b"<svg/>")
    return root


@pytest.mark.parametrize(("arg", "quoted"), [
    ("/opt/Project_Reforged.AppImage", "/opt/Project_Reforged.AppImage"),
    ("/home/a b/x.AppImage", '"/home/a b/x.AppImage"'),
    ("/home/a/x$y.AppImage", '"/home/a/x\\\\$y.AppImage"'),
    ('/home/a/"q".AppImage', '"/home/a/\\\\"q\\\\".AppImage"'),
    ("/home/a/100%.AppImage", "/home/a/100%%.AppImage"),
    ("/home/a/back\\slash", '"/home/a/back\\\\\\\\slash"'),
])
def test_exec_quoting(arg: str, quoted: str) -> None:
    assert quote_exec_arg(arg) == quoted


@pytest.mark.parametrize("bad", ["/a\nb", "/a\rb", ""])
def test_exec_refuses(bad: str) -> None:
    with pytest.raises(ValueError):
        quote_exec_arg(bad)


@pytest.mark.skipif(shutil.which("desktop-file-validate") is None,
                    reason="desktop-file-validate not installed")
@pytest.mark.parametrize("exec_path", ["/opt/x.AppImage", "/home/a b/x$y%.AppImage"])
def test_entry_is_valid(tmp_path: Path, exec_path: str) -> None:
    path = tmp_path / f"{APP_ID}.desktop"
    path.write_text(desktop_entry(Path(exec_path)), encoding="utf-8")
    result = subprocess.run(["desktop-file-validate", str(path)], capture_output=True,
                            text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "error" not in (result.stdout + result.stderr).lower()


def test_install_writes_icons_and_entry(where: DesktopTargets, source: Path) -> None:
    written = install(where, Path("/opt/x.AppImage"), source=source)
    assert set(written) == {where.desktop_file, *where.icon_files()}
    png = where.icons / "48x48" / "apps" / f"{APP_ID}.png"
    assert png.read_bytes() == b"png 48"
    assert png.stat().st_mtime == 1_600_000_000
    assert installed_exec(where) == "/opt/x.AppImage"
    assert f"Icon={APP_ID}\n" in where.desktop_file.read_text(encoding="utf-8")


def test_install_with_a_missing_icon_writes_nothing(where: DesktopTargets,
                                                    source: Path) -> None:
    (source / "32x32" / "apps" / f"{APP_ID}.png").unlink()
    with pytest.raises(FileNotFoundError):
        install(where, Path("/opt/x.AppImage"), source=source)
    assert not where.icons.exists() and not where.applications.exists()


def test_install_needs_an_absolute_exec(where: DesktopTargets, source: Path) -> None:
    with pytest.raises(ValueError):
        install(where, Path("x.AppImage"), source=source)


def test_remove_takes_only_ours(where: DesktopTargets, source: Path) -> None:
    install(where, Path("/opt/x.AppImage"), source=source)
    other = where.applications / "org.example.Other.desktop"
    other.write_text("[Desktop Entry]\n", encoding="utf-8")
    removed = remove(where)
    assert set(removed) == {where.desktop_file, *where.icon_files()}
    assert other.exists()
    assert remove(where) == []


def test_refresh_exec_after_a_move(where: DesktopTargets, source: Path) -> None:
    install(where, Path("/opt/x.AppImage"), source=source)
    assert refresh_exec(where, Path("/opt/x.AppImage")) is False
    assert refresh_exec(where, Path("/home/a b/x.AppImage")) is True
    assert installed_exec(where) == '"/home/a b/x.AppImage"'


def test_refresh_exec_when_not_installed(where: DesktopTargets) -> None:
    assert refresh_exec(where, Path("/opt/x.AppImage")) is False
    assert installed_exec(where) is None


def test_current_appimage(tmp_path: Path) -> None:
    image = tmp_path / "x.AppImage"
    image.write_bytes(b"ELF")
    assert current_appimage({}) is None
    assert current_appimage({"APPIMAGE": "x.AppImage"}) is None
    assert current_appimage({"APPIMAGE": str(tmp_path / "gone")}) is None
    assert current_appimage({"APPIMAGE": str(image)}) == image


def test_targets_follow_xdg(xdg_home: Path) -> None:
    t = targets()
    assert t.applications == xdg_home / "data" / "applications"
    assert t.icons == xdg_home / "data" / "icons" / "hicolor"


def test_package_carries_every_icon() -> None:
    for size in ICON_SIZES:
        assert (ICONS_SOURCE / f"{size}x{size}" / "apps" / f"{APP_ID}.png").is_file()
    assert (ICONS_SOURCE / "scalable" / "apps" / f"{APP_ID}.svg").is_file()


def test_entry_names_the_window_class() -> None:
    # Measured 2026-11-16 with xprop: Qt puts the application name into WM_CLASS's
    # class part, which run_window sets to APP_NAME.
    from project_reforged_linux import APP_NAME

    assert f"StartupWMClass={APP_NAME}\n" in desktop_entry(Path("/opt/x.AppImage"))
