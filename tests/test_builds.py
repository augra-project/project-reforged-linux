# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import pytest

from project_reforged_linux.builds import PREFERENCE, Build, effective_build
from project_reforged_linux.nativecheck import NativeCheck

GOOD = NativeCheck(glibc=(2, 41), vulkan=True, curl=True, fuse=True)
NO_FUSE = NativeCheck(glibc=(2, 41), vulkan=True, curl=True, fuse=False)
OLD = NativeCheck(glibc=(2, 28), vulkan=True, curl=True, fuse=True)
NO_VULKAN = NativeCheck(glibc=(2, 41), vulkan=False, curl=True, fuse=True)


def test_labels_for_the_game_row() -> None:
    assert Build.LINUX_APPIMAGE.value == "Linux AppImage"
    assert Build.LINUX_TARBALL.value == "Linux tarball"  # as Options names it
    assert Build.WINDOWS.value == "Windows"


def test_keys_round_trip_and_unknown_keys_fail() -> None:
    assert [b.key for b in Build] == ["appimage", "tarball", "windows"]
    for build in Build:
        assert Build.from_key(build.key) is build
    with pytest.raises(ValueError):
        Build.from_key("amiga")


def test_each_build_has_its_own_manifest() -> None:
    site = "https://project-reforged.danwhelan.ie/update/"
    assert Build.LINUX_APPIMAGE.manifest_url == site + "linux.json"
    assert Build.LINUX_TARBALL.manifest_url == site + "linux-tar.json"
    assert Build.WINDOWS.manifest_url == site + "win.json"


# His real download names (manifests of 2026-11-15 to 2026-11-18, the archive).
REAL_NAMES = {
    Build.LINUX_APPIMAGE: "Shadowkey-0.2.48-linux-x86_64.AppImage",
    Build.LINUX_TARBALL: "Shadowkey-0.2.48-linux-x86_64.tar.gz",
    Build.WINDOWS: "Shadowkey-0.2.32-win-x64-update.zip",
}


@pytest.mark.parametrize("build", list(Build))
def test_each_build_takes_only_its_own_download(build: Build) -> None:
    for other, name in REAL_NAMES.items():
        assert build.accepts_download(name) is (other is build), (build, name)


@pytest.mark.parametrize("name", ["Shadowkey-0.2.48-win-x64.zip"])
def test_the_full_windows_zip_is_accepted_too(name: str) -> None:
    assert Build.WINDOWS.accepts_download(name)


@pytest.mark.parametrize("name", [".hidden.zip", "a.exe", "../a.zip", "a b.zip", "", "zip",
                                  "a.tar.gz.zip.AppImage/", "a.tgz"])
def test_odd_names_are_refused(name: str) -> None:
    assert not any(build.accepts_download(name) for build in Build)


def test_preference_is_appimage_then_tarball_then_windows() -> None:
    assert PREFERENCE == (Build.LINUX_APPIMAGE, Build.LINUX_TARBALL, Build.WINDOWS)


@pytest.mark.parametrize(("check", "build"), [
    (GOOD, Build.LINUX_APPIMAGE),
    (NO_FUSE, Build.LINUX_TARBALL),
    (OLD, Build.WINDOWS),
    (NO_VULKAN, Build.WINDOWS),
])
def test_nothing_chosen_takes_the_best_that_runs(check: NativeCheck, build: Build) -> None:
    assert effective_build(None, check) == (build, None)


def test_a_chosen_build_that_cannot_run_gives_way_with_a_note() -> None:
    assert effective_build(Build.LINUX_APPIMAGE, OLD) == (
        Build.WINDOWS, "Linux AppImage is chosen but cannot run here: The Linux builds need "
                       "glibc 2.35; this system has 2.28. Windows runs instead.")
    assert effective_build(Build.LINUX_TARBALL, NO_VULKAN) == (
        Build.WINDOWS, "Linux tarball is chosen but cannot run here: No Vulkan driver loader "
                       "(libvulkan.so.1). Windows runs instead.")
    # Without FUSE only the AppImage fails: the tarball is the best that runs.
    build, note = effective_build(Build.LINUX_APPIMAGE, NO_FUSE)
    assert build is Build.LINUX_TARBALL and note is not None and "No FUSE" in note


def test_a_chosen_build_that_runs_stays() -> None:
    assert effective_build(Build.LINUX_TARBALL, GOOD) == (Build.LINUX_TARBALL, None)
    assert effective_build(Build.WINDOWS, GOOD) == (Build.WINDOWS, None)


def test_windows_has_no_native_problem() -> None:
    # Its requirement is Wine, which the runtime row reports; the host check has no say.
    assert effective_build(Build.WINDOWS, OLD) == (Build.WINDOWS, None)
