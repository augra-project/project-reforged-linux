# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import stat
from pathlib import Path

import pytest

from project_reforged_linux.builds import Build
from project_reforged_linux.paths import AppPaths, ensure_dirs, native_data_dir, resolve


def test_resolve_follows_xdg(xdg_home: Path) -> None:
    paths = resolve()
    assert paths.data == xdg_home / "data" / "project-reforged-linux"
    assert paths.config == xdg_home / "config" / "project-reforged-linux"
    assert paths.cache == xdg_home / "cache" / "project-reforged-linux"
    assert paths.state == xdg_home / "state" / "project-reforged-linux"


def test_layout_below_data(xdg_home: Path) -> None:
    paths = resolve()
    assert paths.game == paths.data / "game"
    assert paths.runtime == paths.data / "runtime"
    assert paths.prefix == paths.data / "prefix"


def test_port_dir_uses_wine_user(xdg_home: Path) -> None:
    paths = resolve()
    assert paths.port_dir("alice") == (
        paths.prefix / "drive_c" / "users" / "alice" / "AppData" / "Roaming"
        / "Shadowkey" / "ShadowkeyPort"
    )


@pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "a\\b"])
def test_port_dir_rejects_bad_user(xdg_home: Path, bad: str) -> None:
    with pytest.raises(ValueError):
        resolve().port_dir(bad)


def test_resolve_does_not_create_anything(xdg_home: Path) -> None:
    resolve()
    assert not (xdg_home / "data" / "project-reforged-linux").exists()


def test_ensure_dirs_creates_private_dirs(xdg_home: Path) -> None:
    paths = resolve()
    ensure_dirs(paths)
    for d in (paths.data, paths.config, paths.cache, paths.state, paths.game, paths.prefix):
        assert d.is_dir()
        assert stat.S_IMODE(d.stat().st_mode) == 0o700


def test_ensure_dirs_keeps_existing_mode(xdg_home: Path) -> None:
    paths = resolve()
    paths.data.mkdir(mode=0o755)
    paths.data.chmod(0o755)
    ensure_dirs(paths)
    assert stat.S_IMODE(paths.data.stat().st_mode) == 0o755


def test_relative_xdg_is_ignored(xdg_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # XDG spec: relative paths in XDG_* are invalid and must be ignored
    monkeypatch.setenv("XDG_DATA_HOME", "relative/dir")
    assert resolve().data.is_absolute()


def test_app_paths_is_frozen(xdg_home: Path) -> None:
    paths: AppPaths = resolve()
    with pytest.raises(AttributeError):
        paths.data = Path("/elsewhere")  # type: ignore[misc]


def test_each_build_has_its_own_folder(xdg_home: Path) -> None:
    paths = resolve()
    # The Windows folder stays where it always was, so an existing install keeps working.
    assert paths.build_dir(Build.WINDOWS) == paths.game == paths.data / "game"
    # His tarball unpacks to Shadowkey/, which must not land beside Shadowkey.exe's folder.
    assert paths.build_dir(Build.LINUX_TARBALL) == paths.data / "linux"
    assert paths.build_dir(Build.LINUX_APPIMAGE) == paths.data / "appimage"
    assert len({paths.build_dir(b) for b in Build}) == 3


def test_his_native_data_follows_xdg_data_home(tmp_path: Path) -> None:
    data = tmp_path / "xdg-data"
    assert native_data_dir({"XDG_DATA_HOME": str(data)}, tmp_path) == data / "Shadowkey"
    assert native_data_dir({}, tmp_path) == tmp_path / ".local" / "share" / "Shadowkey"


@pytest.mark.parametrize("value", ["", "relative/data"])
def test_an_empty_or_relative_xdg_data_home_means_the_default(tmp_path: Path, value: str) -> None:
    assert native_data_dir({"XDG_DATA_HOME": value}, tmp_path) == (
        tmp_path / ".local" / "share" / "Shadowkey")
