# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import pytest

from project_reforged_linux.nativeenv import native_env

# What our own AppImage (sharun) puts into the environment, and the player's session.
OURS = {
    "APPIMAGE": "/home/a/Apps/project-reforged-linux.AppImage",
    "APPDIR": "/run/user/1000/.mount_projecXYZ",
    "ARGV0": "./project-reforged-linux.AppImage",
    "OWD": "/home/a",
    "LD_LIBRARY_PATH": "/run/user/1000/.mount_projecXYZ/lib",
    "LD_PRELOAD": "/usr/NX/lib/libnxegl.so",
    "PYTHONHOME": "/run/user/1000/.mount_projecXYZ/usr",
    "PYTHONPATH": "/run/user/1000/.mount_projecXYZ/lib/python3",
    "QT_PLUGIN_PATH": "/run/user/1000/.mount_projecXYZ/plugins",
    "QT_QPA_PLATFORM_PLUGIN_PATH": "/run/user/1000/.mount_projecXYZ/plugins/platforms",
    "SHARUN_DIR": "/run/user/1000/.mount_projecXYZ",
    "SHARUN_WORKING_DIR": "/home/a",
}
SESSION = {
    "HOME": "/home/a",
    "USER": "a",
    "DISPLAY": ":0",
    "WAYLAND_DISPLAY": "wayland-0",
    "XDG_RUNTIME_DIR": "/run/user/1000",
    "XDG_DATA_HOME": "/home/a/.local/share",
    "XDG_CONFIG_HOME": "/home/a/.config",
    "LANG": "de_AT.UTF-8",
    "PATH": "/run/user/1000/.mount_projecXYZ/bin:/usr/local/bin:/usr/bin:/bin",
}


def test_our_appimage_does_not_reach_his_build() -> None:
    env = native_env({**OURS, **SESSION})
    assert not set(OURS) & set(env)


def test_the_session_reaches_his_build() -> None:
    env = native_env({**OURS, **SESSION})
    for name in ("HOME", "USER", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
                 "XDG_DATA_HOME", "XDG_CONFIG_HOME", "LANG"):
        assert env[name] == SESSION[name]


def test_our_folders_leave_the_path() -> None:
    env = native_env({**OURS, **SESSION})
    assert env["PATH"] == "/usr/local/bin:/usr/bin:/bin"


def test_without_our_appimage_the_path_stays() -> None:
    assert native_env(SESSION)["PATH"] == SESSION["PATH"]


@pytest.mark.parametrize("value", ["", "relative/data", "./data"])
def test_a_data_home_he_would_misread_is_left_out(value: str) -> None:
    # his build writes into the current folder with such a value.
    assert "XDG_DATA_HOME" not in native_env({**SESSION, "XDG_DATA_HOME": value})


def test_the_players_environment_is_not_changed() -> None:
    base = {**OURS, **SESSION}
    native_env(base)
    assert base == {**OURS, **SESSION}
