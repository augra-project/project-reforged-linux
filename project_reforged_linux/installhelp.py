# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""What to install when the chosen build cannot run: only the missing pieces, in the system's
own package names."""

from enum import Enum
from pathlib import Path

from project_reforged_linux.builds import Build
from project_reforged_linux.nativecheck import GLIBC_FLOOR, NativeCheck

__all__ = ["WINEHQ", "Family", "family", "hint"]

WINEHQ = "https://gitlab.winehq.org/wine/wine/-/wikis/Download"
OS_RELEASE = Path("/etc/os-release")


class Family(Enum):
    DEBIAN = "sudo apt install"
    FEDORA = "sudo dnf install"
    ARCH = "sudo pacman -S"
    OTHER = ""


_PACKAGES = {
    Family.DEBIAN: {"vulkan": "mesa-vulkan-drivers libvulkan1", "curl": "libcurl4",
                    "fuse": "fuse3", "wine": "wine"},
    Family.FEDORA: {"vulkan": "mesa-vulkan-drivers vulkan-loader", "curl": "libcurl",
                    "fuse": "fuse3", "wine": "wine"},
    Family.ARCH: {"vulkan": "vulkan-icd-loader", "curl": "curl", "fuse": "fuse3",
                  "wine": "wine"},
}
_PLAIN = {"vulkan": "the Vulkan loader and your graphics card's Vulkan driver",
          "curl": "libcurl", "fuse": "FUSE 3", "wine": "Wine"}
_LIKE = {"debian": Family.DEBIAN, "ubuntu": Family.DEBIAN, "fedora": Family.FEDORA,
         "rhel": Family.FEDORA, "centos": Family.FEDORA, "arch": Family.ARCH}


def family(release: Path = OS_RELEASE) -> Family:
    try:
        text = release.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return Family.OTHER
    fields = {}
    for line in text.splitlines():
        key, _, value = line.partition("=")
        fields[key.strip()] = value.strip().strip('"').strip("'")
    for word in [fields.get("ID", ""), *fields.get("ID_LIKE", "").split()]:
        if word in _LIKE:
            return _LIKE[word]
    return Family.OTHER


def _install(kinds: list[str], fam: Family) -> str:
    if fam is Family.OTHER:
        names = ", ".join(_PLAIN[k] for k in kinds)
        text = f"Install {names} with your distribution's package manager."
        return text + (f" Wine: {WINEHQ}" if "wine" in kinds else "")
    packages = " ".join(_PACKAGES[fam][k] for k in kinds)
    return f"Install it with:\n{fam.value} {packages}"


def hint(build: Build, check: NativeCheck, *, wine_missing: bool, family: Family) -> str:
    """The line the player can act on, or "" when nothing is missing."""
    if build is Build.WINDOWS:
        return _install(["wine"], family) if wine_missing else ""
    if check.glibc is None:
        return (f"This system's glibc version could not be read; his Linux builds need "
                f"{GLIBC_FLOOR[0]}.{GLIBC_FLOOR[1]} or newer.")
    if check.glibc < GLIBC_FLOOR:
        return ("This system is older than his Linux builds allow; no package changes that. "
                "The Windows build (under Wine) runs here instead.")
    kinds = [kind for kind, present in (("vulkan", check.vulkan), ("curl", check.curl))
             if not present]
    if build is Build.LINUX_APPIMAGE and not check.fuse:
        kinds.append("fuse")
    return _install(kinds, family) if kinds else ""
