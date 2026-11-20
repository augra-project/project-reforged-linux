# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Nothing of our AppImage may reach Wine or his Linux build.

The fixture is a real environment inside a sharun AppImage (luducat's 0.8.6, captured by him
on 2026-11-18), with personal values taken out and the home renamed.
"""

import json
from pathlib import Path

import pytest

from project_reforged_linux.hostenv import host_env
from project_reforged_linux.nativeenv import native_env
from project_reforged_linux.wineenv import build_env

SHARUN = json.loads((Path(__file__).parent / "data" / "sharun-env.json").read_text(
    encoding="utf-8"))
MOUNT = SHARUN["APPDIR"]
RUNTIME_NAMES = ("APPIMAGE", "APPDIR", "APPOFFSET", "APPIMAGE_ARCH", "APPIMAGE_UID", "ARG0",
                 "URUNTIME", "URUNTIME_DIR", "SHARUN_DIR", "HOSTPATH", "HOST_HOME",
                 "HOST_XDG_DATA_HOME", "USE_HOST_XDG_CACHE_HOME", "PYTHONPATH",
                 "CROSS_LIBC_DLOPEN_ROOT", "_")
SESSION_NAMES = ("HOME", "USER", "DISPLAY", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE", "LANG",
                 "DBUS_SESSION_BUS_ADDRESS", "XDG_CURRENT_DESKTOP", "QT_IM_MODULE")

ROUTES = {
    "host": host_env,
    "wine": lambda env: build_env(env, Path("/home/player/prefix")),
    "native": native_env,
}


@pytest.mark.parametrize("route", ROUTES)
def test_no_value_points_into_the_bundle(route: str) -> None:
    env = ROUTES[route](SHARUN)
    leaked = {k: v for k, v in env.items() if MOUNT in v}
    assert leaked == {}


@pytest.mark.parametrize("route", ROUTES)
def test_the_runtimes_own_names_are_gone(route: str) -> None:
    env = ROUTES[route](SHARUN)
    assert not set(RUNTIME_NAMES) & set(env)


@pytest.mark.parametrize("route", ROUTES)
def test_the_session_stays(route: str) -> None:
    env = ROUTES[route](SHARUN)
    for name in SESSION_NAMES:
        assert env[name] == SHARUN[name], name


def test_path_is_the_hosts_own() -> None:
    assert host_env(SHARUN)["PATH"] == SHARUN["HOSTPATH"]


@pytest.mark.parametrize("name", ["XDG_DATA_DIRS", "__EGL_VENDOR_LIBRARY_DIRS",
                                  "GBM_BACKENDS_PATH", "GSETTINGS_SCHEMA_DIR",
                                  "AMDGPU_ASIC_ID_TABLE_PATHS"])
def test_a_mixed_list_keeps_the_hosts_part_in_order(name: str) -> None:
    # The Vulkan loader finds its drivers through XDG_DATA_DIRS: trimmed, not dropped.
    hosts = [e for e in SHARUN[name].split(":") if e and not e.startswith(MOUNT)]
    assert hosts, f"the fixture's {name} should hold host folders too"
    assert host_env(SHARUN)[name].split(":") == hosts


def test_a_list_only_of_the_bundle_is_dropped() -> None:
    assert "LIBGL_DRIVERS_PATH" not in host_env(SHARUN)
    assert "GCONV_PATH" not in host_env(SHARUN)


def test_without_our_appimage_nothing_changes() -> None:
    plain = {name: SHARUN[name] for name in SESSION_NAMES}
    plain["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    plain["XDG_DATA_DIRS"] = "/usr/local/share:/usr/share"
    assert host_env(plain) == plain


def test_without_hostpath_the_path_is_trimmed() -> None:
    env = dict(SHARUN)
    del env["HOSTPATH"]
    path = host_env(env)["PATH"].split(":")
    assert path and not any(entry.startswith(MOUNT) for entry in path)


def test_a_sibling_folder_of_the_mount_is_not_ours() -> None:
    # /tmp/.mount_projecA1B2C3x shares the mount's text but is another folder.
    env = {"APPDIR": MOUNT, "XDG_DATA_DIRS": f"{MOUNT}/share:{MOUNT}x/share:/usr/share"}
    assert host_env(env)["XDG_DATA_DIRS"] == f"{MOUNT}x/share:/usr/share"


def test_the_players_environment_is_left_as_it_was() -> None:
    before = dict(SHARUN)
    host_env(SHARUN)
    assert SHARUN == before


def test_a_library_path_is_judged_by_where_it_points() -> None:
    env = {"APPDIR": MOUNT, "LD_LIBRARY_PATH": f"{MOUNT}/lib:/opt/wine-devel/lib64"}
    assert host_env(env)["LD_LIBRARY_PATH"] == "/opt/wine-devel/lib64"
    assert "LD_LIBRARY_PATH" not in host_env({"APPDIR": MOUNT, "LD_LIBRARY_PATH": f"{MOUNT}/lib"})


def test_the_saved_host_path_wins_over_a_trimmed_one() -> None:
    # A runtime may put more than its mount into PATH; sharun keeps the host's in HOSTPATH.
    env = {"APPDIR": MOUNT, "PATH": f"{MOUNT}/bin:/usr/bin:/opt/runtime-helper/bin",
           "HOSTPATH": "/usr/local/bin:/usr/bin:/bin"}
    assert host_env(env)["PATH"] == "/usr/local/bin:/usr/bin:/bin"
