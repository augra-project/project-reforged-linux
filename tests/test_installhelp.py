# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
from pathlib import Path

import pytest

from project_reforged_linux.builds import Build
from project_reforged_linux.installhelp import Family, family, hint
from project_reforged_linux.nativecheck import NativeCheck

GOOD = NativeCheck((2, 41), vulkan=True, curl=True, fuse=True)


@pytest.mark.parametrize(("text", "expected"), [
    ('ID=debian\nVERSION_ID="13"\n', Family.DEBIAN),
    ('ID=ubuntu\nID_LIKE=debian\n', Family.DEBIAN),
    ('ID=linuxmint\nID_LIKE="ubuntu debian"\n', Family.DEBIAN),
    ('ID="almalinux"\nID_LIKE="rhel centos fedora"\n', Family.FEDORA),
    ("ID=fedora\n", Family.FEDORA),
    ("ID=arch\n", Family.ARCH),
    ("ID=steamos\nID_LIKE=arch\n", Family.ARCH),
    ("ID=gentoo\n", Family.OTHER),
    ("", Family.OTHER),
])
def test_the_family_comes_from_os_release(tmp_path: Path, text: str, expected: Family) -> None:
    release = tmp_path / "os-release"
    release.write_text(text, encoding="utf-8")
    assert family(release) is expected


def test_no_os_release_is_another_family(tmp_path: Path) -> None:
    assert family(tmp_path / "absent") is Family.OTHER


def test_nothing_missing_needs_no_hint() -> None:
    assert hint(Build.LINUX_APPIMAGE, GOOD, wine_missing=False, family=Family.DEBIAN) == ""


@pytest.mark.parametrize(("fam", "command"), [
    (Family.DEBIAN, "sudo apt install mesa-vulkan-drivers libvulkan1"),
    (Family.FEDORA, "sudo dnf install mesa-vulkan-drivers vulkan-loader"),
    (Family.ARCH, "sudo pacman -S vulkan-icd-loader"),
])
def test_a_missing_vulkan_names_its_packages(fam: Family, command: str) -> None:
    check = NativeCheck((2, 41), vulkan=False, curl=True, fuse=True)
    assert command in hint(Build.LINUX_TARBALL, check, wine_missing=False, family=fam)


def test_only_what_is_missing_is_named() -> None:
    check = NativeCheck((2, 41), vulkan=True, curl=False, fuse=False)
    text = hint(Build.LINUX_APPIMAGE, check, wine_missing=False, family=Family.DEBIAN)
    assert "sudo apt install libcurl4 fuse3" in text
    assert "vulkan" not in text


def test_fuse_matters_only_for_the_appimage() -> None:
    check = NativeCheck((2, 41), vulkan=True, curl=True, fuse=False)
    assert hint(Build.LINUX_TARBALL, check, wine_missing=False, family=Family.DEBIAN) == ""


def test_an_old_glibc_cannot_be_installed_away() -> None:
    check = NativeCheck((2, 28), vulkan=True, curl=True, fuse=True)
    text = hint(Build.LINUX_TARBALL, check, wine_missing=False, family=Family.FEDORA)
    assert "sudo" not in text
    assert "Windows build" in text


def test_the_windows_build_asks_only_for_wine() -> None:
    check = NativeCheck((2, 28), vulkan=False, curl=False, fuse=False)
    text = hint(Build.WINDOWS, check, wine_missing=True, family=Family.DEBIAN)
    assert "sudo apt install wine" in text
    assert "libcurl" not in text and "fuse" not in text


def test_another_family_gets_the_names_and_winehq() -> None:
    text = hint(Build.WINDOWS, GOOD, wine_missing=True, family=Family.OTHER)
    assert "Wine" in text and "winehq.org" in text and "sudo" not in text


def test_an_unreadable_glibc_is_not_called_too_old() -> None:
    from project_reforged_linux.builds import Build
    from project_reforged_linux.installhelp import Family, hint
    from project_reforged_linux.nativecheck import NativeCheck

    text = hint(Build.LINUX_TARBALL, NativeCheck(None, True, True, True), wine_missing=False,
                family=Family.DEBIAN)
    assert "could not be read" in text and "older" not in text
    old = hint(Build.LINUX_TARBALL, NativeCheck((2, 28), True, True, True), wine_missing=False,
               family=Family.DEBIAN)
    assert "older than his Linux builds allow" in old and "runs here instead" in old
