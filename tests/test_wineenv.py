# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
from pathlib import Path

import pytest

from project_reforged_linux.wineenv import build_env, clean_env

PREFIX = Path("/home/a/.local/share/project-reforged-linux/prefix")


def test_sets_prefix_and_quiet_defaults() -> None:
    env = build_env({"HOME": "/home/a"}, PREFIX)
    assert env["WINEPREFIX"] == str(PREFIX)
    assert env["WINEDEBUG"] == "-all"
    assert env["WINEDLLOVERRIDES"] == "mscoree=;mshtml="
    assert env["HOME"] == "/home/a"


@pytest.mark.parametrize("var", [
    "WINEPREFIX", "WINEDLLOVERRIDES", "WINEDLLPATH", "WINEARCH", "WINELOADER",
    "WINESERVER", "WINEESYNC", "DXVK_HUD", "VKD3D_CONFIG", "PROTON_LOG", "LD_PRELOAD",
    "SDL_GPU_DRIVER",
])
def test_clears_steering_variables(var: str) -> None:
    env = build_env({var: "evil", "PATH": "/usr/bin"}, PREFIX)
    if var in ("WINEPREFIX", "WINEDLLOVERRIDES"):
        assert env[var] != "evil"
    else:
        assert var not in env
    assert env["PATH"] == "/usr/bin"


def test_does_not_modify_input() -> None:
    base = {"WINEDLLOVERRIDES": "d3d12=n"}
    build_env(base, PREFIX)
    assert base == {"WINEDLLOVERRIDES": "d3d12=n"}


def test_keeps_ld_library_path() -> None:
    env = build_env({"LD_LIBRARY_PATH": "/appdir/lib"}, PREFIX)
    assert env["LD_LIBRARY_PATH"] == "/appdir/lib"


def test_debug_channels() -> None:
    assert build_env({}, PREFIX, debug="+loaddll")["WINEDEBUG"] == "+loaddll"


def test_rejects_relative_prefix() -> None:
    with pytest.raises(ValueError):
        build_env({}, Path("prefix"))


def test_clean_env_drops_what_steers_wine() -> None:
    base = {"HOME": "/home/a", "LD_PRELOAD": "/opt/remote/lib/libpreload.so", "WINEPREFIX": "/x",
            "WINEDLLOVERRIDES": "d3d11=n", "SDL_GPU_DRIVER": "vulkan", "DXVK_HUD": "1"}
    assert clean_env(base) == {"HOME": "/home/a"}
