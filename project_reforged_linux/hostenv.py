# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The player's own environment, without what our AppImage put into it.

Our AppImage points dozens of variables (driver paths, XDG_DATA_DIRS, locales) into the bundle,
and Wine and his build must see the host's; values are judged by where they point, not by name.
"""

from collections.abc import Mapping

__all__ = ["host_env"]

# The runtime's own variables; some hold the AppImage file's path, not the mount's.
# LD_LIBRARY_PATH is judged by its value instead: one the player set for a system Wine stays.
_RUNTIME_NAMES = frozenset({"APPIMAGE", "APPDIR", "APPOFFSET", "ARG0", "ARGV0", "OWD", "_",
                            "PYTHONHOME", "PYTHONPATH"})
_RUNTIME_PREFIXES = ("APPIMAGE_", "SHARUN_", "URUNTIME", "HOST_", "USE_HOST_")


def _mounts(base: Mapping[str, str]) -> list[str]:
    found = [base.get(name, "").rstrip("/") for name in ("APPDIR", "SHARUN_DIR")]
    return [m for m in found if m.startswith("/") and m != ""]


def _inside(entry: str, mounts: list[str]) -> bool:
    return any(entry == m or entry.startswith(m + "/") for m in mounts)


def _mentions(value: str, mounts: list[str]) -> bool:
    return any(m + "/" in value or value.endswith(m) for m in mounts)


def host_env(base: Mapping[str, str]) -> dict[str, str]:
    mounts = _mounts(base)
    env: dict[str, str] = {}
    for name, value in base.items():
        if name in _RUNTIME_NAMES or name.startswith(_RUNTIME_PREFIXES) or name == "HOSTPATH":
            continue
        if not mounts:
            env[name] = value
            continue
        parts = value.split(":")
        kept = [part for part in parts if not _inside(part, mounts)]
        if len(kept) == len(parts) and not _mentions(value, mounts):
            env[name] = value
            continue
        host_parts = [part for part in kept if part and not _mentions(part, mounts)]
        if host_parts:
            env[name] = ":".join(host_parts)
    if mounts and base.get("HOSTPATH"):
        env["PATH"] = base["HOSTPATH"]  # sharun keeps the host's PATH here, untouched
    return env
