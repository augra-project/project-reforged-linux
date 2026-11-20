# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest
from fakes import FakeTransport, response

from project_reforged_linux.artseed import ART, INDEX
from project_reforged_linux.builds import Build
from project_reforged_linux.gamefiles import GAME_FOLDER_TXT, LEVEL_FILES
from project_reforged_linux.gamesettings import SETTINGS_CFG
from project_reforged_linux.install import executable
from project_reforged_linux.paths import AppPaths, native_port_dir, resolve
from project_reforged_linux.prepare import (
    Step,
    install_requirements,
    installed_version,
    status,
)
from project_reforged_linux.runner import LOG_NAME
from project_reforged_linux.runtimes import Resolved
from project_reforged_linux.settings import LauncherSettings
from project_reforged_linux.wineprefix import READY_MARK

SITE = "https://project-reforged.danwhelan.ie/downloads/"
NATIVE = [Build.LINUX_TARBALL, Build.LINUX_APPIMAGE]


def tarball() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data, mode in (("Shadowkey/Shadowkey", b"\x7fELF tar", 0o755),
                                 ("Shadowkey/README.txt", b"readme", 0o644)):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), mode, 1_794_964_479
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


PAYLOAD = {Build.LINUX_TARBALL: (tarball(), "Shadowkey-0.2.48-linux-x86_64.tar.gz"),
           Build.LINUX_APPIMAGE: (b"\x7fELF appimage", "Shadowkey-0.2.48-linux-x86_64.AppImage")}


def manifest(build: Build, version: str = "0.2.48") -> bytes:
    data, name = PAYLOAD[build]
    return json.dumps({"format": 1, "version": version, "date": "2026-11-18",
                       "url": SITE + name, "size": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}).encode()


def his_site(build: Build, version: str = "0.2.48") -> FakeTransport:
    return FakeTransport(response(200, manifest(build, version)),
                         response(200, PAYLOAD[build][0]))


@pytest.fixture
def paths(xdg_home: Path) -> AppPaths:
    return resolve()


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return {"XDG_DATA_HOME": str(tmp_path / "his-data")}


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture
def card(tmp_path: Path) -> Path:
    folder = tmp_path / "card" / "system" / "apps" / "6r51"
    folder.mkdir(parents=True)
    for name in LEVEL_FILES:
        (folder / name).write_bytes(b"zmp")
    return folder


def install(paths: AppPaths, build: Build, env: dict[str, str], home: Path,
            transport: FakeTransport | None = None, **kwargs: object) -> object:
    settings = kwargs.pop("settings", LauncherSettings())
    return install_requirements(paths, settings, transport or his_site(build), None,
                                build=build, base_env=env, home=home, **kwargs)


@pytest.mark.parametrize("build", NATIVE)
def test_a_native_install_needs_no_wine(paths: AppPaths, env: dict[str, str], home: Path,
                                        card: Path, build: Build) -> None:
    steps: list[Step] = []
    transport = his_site(build)
    install(paths, build, env, home, transport, settings=LauncherSettings(game_files=str(card)),
            progress=lambda step, done, total: steps.append(step))
    assert transport.calls[0].url == build.manifest_url
    assert executable(paths, build).read_bytes().startswith(b"\x7fELF")
    assert not paths.prefix.joinpath("drive_c").exists()  # no Wine prefix for his Linux build
    assert installed_version(paths, build) == "0.2.48"
    assert Step.PREFIX not in steps


@pytest.mark.parametrize("build", NATIVE)
def test_the_game_files_go_to_his_native_folder(paths: AppPaths, env: dict[str, str],
                                                home: Path, card: Path, build: Build) -> None:
    install(paths, build, env, home, settings=LauncherSettings(game_files=str(card)))
    port = native_port_dir(env, home)
    assert port == Path(env["XDG_DATA_HOME"]) / "Shadowkey" / "ShadowkeyPort"
    assert (port / GAME_FOLDER_TXT).read_bytes().decode("utf-8") == f"{card.resolve()}\n"
    # His settings and updater stay his: the launcher writes none of his settings natively.
    assert not (port / SETTINGS_CFG).exists()


@pytest.mark.parametrize("build", NATIVE)
def test_the_download_leaves_nothing_in_the_cache(paths: AppPaths, env: dict[str, str],
                                                  home: Path, build: Build) -> None:
    install(paths, build, env, home)
    assert not (paths.cache / PAYLOAD[build][1]).exists()


@pytest.mark.parametrize("build", NATIVE)
def test_installed_and_nothing_asked_means_nothing_online(paths: AppPaths, env: dict[str, str],
                                                          home: Path, build: Build) -> None:
    install(paths, build, env, home)
    assert install(paths, build, env, home, FakeTransport()) is None


@pytest.mark.parametrize("build", NATIVE)
def test_update_fetches_again(paths: AppPaths, env: dict[str, str], home: Path,
                              build: Build) -> None:
    install(paths, build, env, home)
    install(paths, build, env, home, his_site(build, "0.2.49"), update_game=True)
    assert installed_version(paths, build) == "0.2.49"


def test_the_windows_build_still_needs_its_runtime(paths: AppPaths, env: dict[str, str],
                                                   home: Path) -> None:
    with pytest.raises(ValueError, match="runtime"):
        install_requirements(paths, LauncherSettings(), FakeTransport(), None,
                             build=Build.WINDOWS, base_env=env, home=home)


def windows_art(paths: AppPaths) -> Path:
    art = paths.port_dir("alice") / ART
    art.mkdir(parents=True)
    (art / INDEX).write_text("index\n", encoding="utf-8")
    (paths.prefix / "system.reg").write_text("WINE", encoding="utf-8")
    (paths.prefix / READY_MARK).write_text("ready\n", encoding="utf-8")
    return art


def test_a_native_install_seeds_the_art_from_the_windows_build(paths: AppPaths,
                                                               env: dict[str, str],
                                                               home: Path) -> None:
    windows_art(paths)
    install(paths, Build.LINUX_APPIMAGE, env, home)
    assert (native_port_dir(env, home) / ART / INDEX).read_text(encoding="utf-8") == "index\n"


def native_log(env: dict[str, str], home: Path, version: str) -> None:
    port = native_port_dir(env, home)
    port.mkdir(parents=True, exist_ok=True)
    (port / LOG_NAME).write_text(f"Shadowkey {version}, Linux, 2026-11-18 08:01:44\n",
                                 encoding="utf-8")


@pytest.mark.parametrize("build", NATIVE)
def test_status_of_a_native_build(paths: AppPaths, env: dict[str, str], home: Path,
                                  build: Build) -> None:
    before = status(paths, LauncherSettings(), Resolved(None), build=build, env=env, home=home)
    assert not before.game_installed and before.build is None
    install(paths, build, env, home)
    native_log(env, home, "0.2.49")  # his own updater moved it on after our install
    after = status(paths, LauncherSettings(), Resolved(None), build=build, env=env, home=home)
    assert after.game_installed and after.build is build
    assert after.game_version == "0.2.49"


def test_one_builds_install_is_not_anothers(paths: AppPaths, env: dict[str, str],
                                            home: Path) -> None:
    install(paths, Build.LINUX_TARBALL, env, home)
    other = status(paths, LauncherSettings(), Resolved(None), build=Build.LINUX_APPIMAGE,
                   env=env, home=home)
    assert not other.game_installed and other.game_version is None


def test_his_shared_log_counts_only_for_the_build_that_wrote_it(
        paths: AppPaths, env: dict[str, str], home: Path) -> None:
    # Both Linux builds write one shadowkey.log; it speaks for the build that ran last.
    from project_reforged_linux.paths import ensure_dirs, native_port_dir
    from project_reforged_linux.prepare import _logged_version

    ensure_dirs(paths)
    port = native_port_dir(env, home)
    port.mkdir(parents=True)
    (port / "shadowkey.log").write_text("Shadowkey 0.2.50, Linux, x\n", encoding="utf-8")
    (paths.data / "last-native-build.txt").write_text("appimage\n", encoding="utf-8")
    assert _logged_version(paths, Build.LINUX_APPIMAGE, env, home) == "0.2.50"
    assert _logged_version(paths, Build.LINUX_TARBALL, env, home) is None


@pytest.mark.parametrize("build", NATIVE)
def test_a_log_that_cannot_be_read_leaves_the_version_to_the_stamp(
        paths: AppPaths, env: dict[str, str], home: Path, build: Build) -> None:
    # A stray folder in its place made every refresh fail, and the window stayed at checking.
    install(paths, build, env, home)
    (native_port_dir(env, home) / LOG_NAME).mkdir(parents=True)
    found = status(paths, LauncherSettings(), Resolved(None), build=build, env=env, home=home)
    assert found.game_installed and found.game_version == "0.2.48"
