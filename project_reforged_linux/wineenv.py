# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The environment the game's Wine process starts with."""

from collections.abc import Mapping
from pathlib import Path

__all__ = ["build_env", "clean_env"]

# Anything here could change which DLLs load or how Wine behaves behind our back.
# The graphics backend is his own setting in settings.cfg, never an SDL variable.
_CLEARED_PREFIXES = ("WINE", "DXVK_", "VKD3D_", "PROTON_")
_CLEARED_NAMES = frozenset({"LD_PRELOAD", "SDL_GPU_DRIVER"})

# Without these, the first prefix start offers to install Mono and Gecko
_DLL_OVERRIDES = "mscoree=;mshtml="


def clean_env(base: Mapping[str, str]) -> dict[str, str]:
    """The session's environment without anything that steers Wine or the loader."""
    return {k: v for k, v in base.items()
            if not k.startswith(_CLEARED_PREFIXES) and k not in _CLEARED_NAMES}


def build_env(base: Mapping[str, str], prefix: Path, *, debug: str | None = None) -> dict[str, str]:
    if not prefix.is_absolute():
        raise ValueError(f"prefix must be absolute: {prefix}")
    env = clean_env(base)
    env["WINEPREFIX"] = str(prefix)
    env["WINEDEBUG"] = debug if debug is not None else "-all"
    env["WINEDLLOVERRIDES"] = _DLL_OVERRIDES
    return env
