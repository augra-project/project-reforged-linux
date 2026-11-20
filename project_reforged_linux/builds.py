# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import re
from enum import Enum

from project_reforged_linux.nativecheck import NativeCheck

__all__ = ["PREFERENCE", "SITE_UPDATE", "Build", "effective_build"]

SITE_UPDATE = "https://project-reforged.danwhelan.ie/update/"
# Only the extension is fixed: his file names have changed before, his extensions have not.
_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]*"


class Build(Enum):
    """The value is the game row's label."""

    LINUX_APPIMAGE = "Linux AppImage"
    LINUX_TARBALL = "Linux tarball"
    WINDOWS = "Windows"

    @property
    def key(self) -> str:
        """The word in settings.json and the stamp's file name."""
        return _KEYS[self]

    @classmethod
    def from_key(cls, key: str) -> "Build":
        for build, word in _KEYS.items():
            if word == key:
                return build
        raise ValueError(f"unknown build: {key!r}")

    @property
    def manifest_url(self) -> str:
        return SITE_UPDATE + _MANIFESTS[self]

    def accepts_download(self, name: str) -> bool:
        return _DOWNLOADS[self].fullmatch(name) is not None


_KEYS = {Build.LINUX_APPIMAGE: "appimage", Build.LINUX_TARBALL: "tarball",
         Build.WINDOWS: "windows"}
# The tarball has its own manifest since 0.2.48.
_MANIFESTS = {Build.LINUX_APPIMAGE: "linux.json", Build.LINUX_TARBALL: "linux-tar.json",
              Build.WINDOWS: "win.json"}
_DOWNLOADS = {Build.LINUX_APPIMAGE: re.compile(_NAME + r"\.AppImage"),
              Build.LINUX_TARBALL: re.compile(_NAME + r"\.tar\.gz"),
              Build.WINDOWS: re.compile(_NAME + r"\.zip")}

# With nothing chosen, the best build that runs here.
PREFERENCE = (Build.LINUX_APPIMAGE, Build.LINUX_TARBALL, Build.WINDOWS)


def _native_problem(build: Build, check: NativeCheck) -> str | None:
    if build is Build.LINUX_APPIMAGE:
        return check.appimage_problem()
    if build is Build.LINUX_TARBALL:
        return check.tarball_problem()
    return None  # Wine is the Windows build's requirement; the runtime row reports it


def effective_build(chosen: Build | None, check: NativeCheck) -> tuple[Build, str | None]:
    """The build that runs here, and a note when it is not the chosen one.

    A chosen build that cannot run here gives way to the best that can, said in the note; the
    choice itself stays saved and comes back on a system that runs it.
    """
    problem = None if chosen is None else _native_problem(chosen, check)
    if chosen is not None and problem is None:
        return chosen, None
    for build in PREFERENCE:
        if _native_problem(build, check) is None:
            if chosen is None:
                return build, None
            return build, (f"{chosen.value} is chosen but cannot run here: {problem} "
                           f"{build.value} runs instead.")
    raise AssertionError("the Windows build has no native problem")
