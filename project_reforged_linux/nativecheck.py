# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""What the host offers his native Linux builds: glibc, Vulkan, libcurl, FUSE.

Everything is asked of the host's own tools in a clean environment: inside our AppImage this
process runs on the bundle's glibc and libraries, so os.confstr and ctypes would report those.
"""

import logging
import re
import shutil
import subprocess  # nosec B404
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

__all__ = ["CLEAN_PATH", "GLIBC_FLOOR", "NativeCheck", "check_native", "has_library",
           "host_fuse", "host_glibc", "ldconfig_names"]

logger = logging.getLogger(__name__)

# His 0.2.45 binary: hypot/hypotf need GLIBC_2.35, everything else 2.34.
GLIBC_FLOOR = (2, 35)
VULKAN = ("libvulkan.so.1",)
# Every download he makes, the art included, goes through libcurl (no TLS of his own).
CURL = ("libcurl.so.4", "libcurl-gnutls.so.4")
# His AppImage's static type2 runtime brings libfuse; it needs the device and a fusermount.
FUSERMOUNT = ("fusermount3", "fusermount")
FUSE_DEVICE = Path("/dev/fuse")
CLEAN_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
LIB_DIRS = (Path("/usr/lib/x86_64-linux-gnu"), Path("/lib/x86_64-linux-gnu"),
            Path("/usr/lib64"), Path("/lib64"), Path("/usr/lib"), Path("/lib"))
_TIMEOUT = 5.0
_GLIBC = re.compile(r"glibc (\d+)\.(\d+)(?:\.\d+)?")  # 2.41.9000: a development snapshot

Run = Callable[..., "subprocess.CompletedProcess[str]"]
Which = Callable[..., str | None]


def _host(run: Run, cmd: list[str]) -> str | None:
    try:
        done = run(cmd, env={"PATH": CLEAN_PATH, "LC_ALL": "C"}, capture_output=True,
                   text=True, timeout=_TIMEOUT, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as error:
        logger.info("%s: %s", cmd[0], error)
        return None
    if done.returncode != 0:
        logger.info("%s answered %d: %s", cmd[0], done.returncode, (done.stderr or "").strip())
        return None
    return done.stdout


def host_glibc(run: Run = subprocess.run) -> tuple[int, int] | None:
    out = _host(run, ["getconf", "GNU_LIBC_VERSION"])
    match = _GLIBC.fullmatch((out or "").strip())
    return (int(match[1]), int(match[2])) if match else None


def ldconfig_names(run: Run = subprocess.run) -> frozenset[str] | None:
    """The 64-bit sonames in the loader cache, or None when ldconfig cannot be asked."""
    out = _host(run, ["ldconfig", "-p"])
    if out is None:
        return None
    names = set()
    for line in out.splitlines():
        name, _, rest = line.strip().partition(" ")
        if "x86-64" in rest.partition("=>")[0]:
            names.add(name)
    return frozenset(names)


def has_library(names: Iterable[str], cache: frozenset[str] | None, *,
                dirs: Iterable[Path] = LIB_DIRS) -> bool:
    wanted = tuple(names)
    if cache is not None:
        return any(name in cache for name in wanted)
    return any((folder / name).exists() for folder in dirs for name in wanted)


def host_fuse(which: Which = shutil.which, device: Path = FUSE_DEVICE) -> bool:
    return device.exists() and any(which(name, path=CLEAN_PATH) for name in FUSERMOUNT)


@dataclass(frozen=True, slots=True)
class NativeCheck:
    glibc: tuple[int, int] | None
    vulkan: bool
    curl: bool
    fuse: bool

    def tarball_problem(self) -> str | None:
        if self.glibc is None:
            return "This system's glibc version could not be read."
        if self.glibc < GLIBC_FLOOR:
            return (f"The Linux builds need glibc {GLIBC_FLOOR[0]}.{GLIBC_FLOOR[1]}; "
                    f"this system has {self.glibc[0]}.{self.glibc[1]}.")
        if not self.vulkan:
            return "No Vulkan driver loader (libvulkan.so.1)."
        if not self.curl:
            return "No libcurl (libcurl.so.4)."
        return None

    def appimage_problem(self) -> str | None:
        problem = self.tarball_problem()
        if problem is None and not self.fuse:
            return "No FUSE (/dev/fuse and fusermount) for the AppImage."
        return problem


def check_native(run: Run = subprocess.run, which: Which = shutil.which,
                 device: Path = FUSE_DEVICE) -> NativeCheck:
    cache = ldconfig_names(run)
    check = NativeCheck(glibc=host_glibc(run), vulkan=has_library(VULKAN, cache),
                        curl=has_library(CURL, cache), fuse=host_fuse(which, device))
    logger.info("native check: %s", check)
    return check
