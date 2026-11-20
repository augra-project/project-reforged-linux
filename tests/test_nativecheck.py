# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import subprocess
from pathlib import Path

import pytest

from project_reforged_linux import nativecheck
from project_reforged_linux.nativecheck import NativeCheck

LDCONFIG_OUT = (
    "1234 libs found in cache `/etc/ld.so.cache'\n"
    "\tlibvulkan.so.1 (libc6,x86-64) => /lib/x86_64-linux-gnu/libvulkan.so.1\n"
    "\tlibvulkan.so.1 (libc6) => /usr/lib32/libvulkan.so.1\n"
    "\tlibcurl-gnutls.so.4 (libc6,x86-64) => /lib/x86_64-linux-gnu/libcurl-gnutls.so.4\n"
    "\tlibcurl.so.4 (libc6) => /usr/lib32/libcurl.so.4\n"
)


def fake_run(outputs: dict[str, str], seen: list[dict]):  # type: ignore[no-untyped-def]
    def run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        seen.append({"cmd": cmd, **kwargs})
        name = Path(cmd[0]).name
        if name not in outputs:
            raise FileNotFoundError(cmd[0])
        return subprocess.CompletedProcess(cmd, 0, outputs[name], "")
    return run


def test_glibc_is_read_from_the_host_tool_with_a_clean_environment() -> None:
    seen: list[dict] = []
    assert nativecheck.host_glibc(fake_run({"getconf": "glibc 2.41\n"}, seen)) == (2, 41)
    assert seen[0]["cmd"] == ["getconf", "GNU_LIBC_VERSION"]
    env = seen[0]["env"]
    assert set(env) == {"PATH", "LC_ALL"}
    assert env["PATH"] == nativecheck.CLEAN_PATH


@pytest.mark.parametrize("out", ["", "musl\n", "glibc two\n", "glibc 2\n", "glibc 2.41 x\n"])
def test_unreadable_glibc_is_none(out: str) -> None:
    assert nativecheck.host_glibc(fake_run({"getconf": out}, [])) is None


def test_a_glibc_development_snapshot_reads_as_its_release() -> None:
    # Fedora Rawhide's getconf: a third part, and newer than any floor we set.
    assert nativecheck.host_glibc(fake_run({"getconf": "glibc 2.41.9000\n"}, [])) == (2, 41)


def test_missing_getconf_is_none() -> None:
    assert nativecheck.host_glibc(fake_run({}, [])) is None


def test_hanging_getconf_is_none() -> None:
    def run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
    assert nativecheck.host_glibc(run) is None


def test_only_64_bit_libraries_count() -> None:
    seen: list[dict] = []
    names = nativecheck.ldconfig_names(fake_run({"ldconfig": LDCONFIG_OUT}, seen))
    assert names == frozenset({"libvulkan.so.1", "libcurl-gnutls.so.4"})
    assert seen[0]["cmd"] == ["ldconfig", "-p"]
    assert set(seen[0]["env"]) == {"PATH", "LC_ALL"}


def test_missing_ldconfig_gives_no_cache() -> None:
    assert nativecheck.ldconfig_names(fake_run({}, [])) is None


def test_the_cache_decides_when_there_is_one(tmp_path: Path) -> None:
    (tmp_path / "libcurl.so.4").touch()
    cache = frozenset({"libvulkan.so.1"})
    assert nativecheck.has_library(("libvulkan.so.1",), cache, dirs=(tmp_path,))
    assert not nativecheck.has_library(("libcurl.so.4",), cache, dirs=(tmp_path,))


def test_library_dirs_are_the_fallback_without_ldconfig(tmp_path: Path) -> None:
    (tmp_path / "libvulkan.so.1").touch()
    assert nativecheck.has_library(("libvulkan.so.1",), None, dirs=(tmp_path,))
    assert not nativecheck.has_library(("libcurl.so.4",), None, dirs=(tmp_path,))


def test_good_host_runs_both_native_builds() -> None:
    check = NativeCheck(glibc=(2, 41), vulkan=True, curl=True, fuse=True)
    assert check.tarball_problem() is None
    assert check.appimage_problem() is None


def test_floor_is_2_35_exactly() -> None:
    assert NativeCheck((2, 35), True, True, True).tarball_problem() is None
    assert NativeCheck((2, 34), True, True, True).tarball_problem() == (
        "The Linux builds need glibc 2.35; this system has 2.34.")


def test_a_newer_major_passes() -> None:
    assert NativeCheck((3, 0), True, True, True).tarball_problem() is None


@pytest.mark.parametrize(("check", "problem"), [
    (NativeCheck(None, True, True, True), "This system's glibc version could not be read."),
    (NativeCheck((2, 41), False, True, True), "No Vulkan driver loader (libvulkan.so.1)."),
    (NativeCheck((2, 41), True, False, True), "No libcurl (libcurl.so.4)."),
])
def test_each_missing_piece_names_itself(check: NativeCheck, problem: str) -> None:
    assert check.tarball_problem() == problem
    assert check.appimage_problem() == problem


def test_appimage_alone_needs_fuse() -> None:
    check = NativeCheck((2, 41), True, True, fuse=False)
    assert check.tarball_problem() is None
    assert check.appimage_problem() == "No FUSE (/dev/fuse and fusermount) for the AppImage."


def test_fuse_needs_device_and_fusermount(tmp_path: Path) -> None:
    device = tmp_path / "fuse"
    device.touch()
    seen: list[tuple[str, str | None]] = []

    def which(name: str, path: str | None = None) -> str | None:
        seen.append((name, path))
        return "/usr/bin/" + name

    assert nativecheck.host_fuse(which, device)
    assert seen[0] == ("fusermount3", nativecheck.CLEAN_PATH)
    assert not nativecheck.host_fuse(lambda name, path=None: None, device)
    assert not nativecheck.host_fuse(which, tmp_path / "absent")


def test_old_fusermount_alone_is_enough(tmp_path: Path) -> None:
    device = tmp_path / "fuse"
    device.touch()
    assert nativecheck.host_fuse(
        lambda name, path=None: "/bin/fusermount" if name == "fusermount" else None, device)


def test_check_native_puts_the_pieces_together(tmp_path: Path) -> None:
    run = fake_run({"getconf": "glibc 2.36\n", "ldconfig": LDCONFIG_OUT}, [])
    device = tmp_path / "fuse"
    device.touch()
    check = nativecheck.check_native(run, lambda name, path=None: None, device)
    assert check == NativeCheck(glibc=(2, 36), vulkan=True, curl=True, fuse=False)


def test_a_failing_ldconfig_falls_back_to_the_library_folders() -> None:
    # Without /etc/ld.so.cache (some containers) ldconfig fails; its empty answer is no answer.
    def run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(cmd, 1, "", "ldconfig: no cache\n")

    assert nativecheck.ldconfig_names(run) is None
