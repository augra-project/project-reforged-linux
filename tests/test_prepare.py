# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeTransport, response

from project_reforged_linux.builds import Build
from project_reforged_linux.gamefiles import GAME_FOLDER_TXT, LEVEL_FILES
from project_reforged_linux.gamesettings import FIRST_SETTINGS, SETTINGS_CFG
from project_reforged_linux.install import GAME_EXE, GAME_FOLDER, game_exe
from project_reforged_linux.paths import AppPaths, resolve
from project_reforged_linux.prepare import (
    OLD_STAMP_NAME,
    Step,
    apply_game_files,
    install_requirements,
    installed_version,
    latest_game_version,
    stamp_path,
    status,
)
from project_reforged_linux.runner import LOG_NAME
from project_reforged_linux.runtimes import PREFIX_STAMP, Candidate, Checked, Resolved, Source
from project_reforged_linux.settings import LauncherSettings

RUNTIME = Checked(Candidate(Source.SYSTEM, Path("/opt/wine/bin/wine"),
                            Path("/opt/wine/bin/wineserver")), (10, 0), "wine-10.0", None)
OLD_WINE = Checked(RUNTIME.candidate, (6, 0), "wine-6.0.3", "Wine 6.0 is older than 10.0")
NO_WINE = Resolved(None, problem="No usable Wine: no Wine is installed on this system")
URL = "https://project-reforged.danwhelan.ie/update/Shadowkey-0.2.32-win-x64-update.zip"


def build_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{GAME_FOLDER}/{GAME_EXE}", b"MZ")
    return buffer.getvalue()


ZIP = build_zip()


def manifest(version: str = "0.2.32") -> bytes:
    return json.dumps({"format": 1, "version": version, "date": "2026-11-15", "url": URL,
                       "size": len(ZIP), "sha256": hashlib.sha256(ZIP).hexdigest()}).encode()


class FakeWine:
    def __init__(self, prefix: Path) -> None:
        self.prefix = prefix
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(command)
        if "wineboot" in command:
            (self.prefix / "drive_c" / "users" / "alice").mkdir(parents=True)
            (self.prefix / "system.reg").write_text("WINE", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, b"")


@pytest.fixture
def paths(xdg_home: Path) -> AppPaths:
    return resolve()


@pytest.fixture
def card(tmp_path: Path) -> Path:
    folder = tmp_path / "card" / "system" / "apps" / "6r51"
    folder.mkdir(parents=True)
    for name in LEVEL_FILES:
        (folder / name).write_bytes(b"zmp")
    return folder


def port(paths: AppPaths) -> Path:
    return paths.port_dir("alice")


def test_fresh_install(paths: AppPaths, card: Path) -> None:
    steps: list[Step] = []
    transport = FakeTransport(response(200, manifest(), etag='W/"m"'),
                              response(200, ZIP, etag='"z"'))
    wine = FakeWine(paths.prefix)
    install_requirements(paths, LauncherSettings(game_files=str(card)), transport, RUNTIME,
                         base_env={}, progress=lambda step, done, total: steps.append(step),
                         run=wine)
    assert game_exe(paths).read_bytes() == b"MZ"
    assert (port(paths) / SETTINGS_CFG).read_bytes() == FIRST_SETTINGS
    assert (port(paths) / GAME_FOLDER_TXT).read_text(encoding="utf-8").startswith("Z:\\")
    assert not (paths.cache / "Shadowkey-0.2.32-win-x64-update.zip").exists()
    assert [s for i, s in enumerate(steps) if i == 0 or steps[i - 1] != s] == [
        Step.MANIFEST, Step.DOWNLOAD, Step.INSTALL, Step.PREFIX, Step.CONFIGURE]


def test_second_run_touches_nothing_online(paths: AppPaths, card: Path) -> None:
    first = FakeTransport(response(200, manifest()), response(200, ZIP))
    wine = FakeWine(paths.prefix)
    settings = LauncherSettings(game_files=str(card))
    install_requirements(paths, settings, first, RUNTIME, base_env={}, run=wine)
    calls_before = len(wine.calls)
    install_requirements(paths, settings, FakeTransport(), RUNTIME, base_env={}, run=wine)
    assert len(wine.calls) == calls_before


def test_without_game_files_no_game_folder_txt(paths: AppPaths) -> None:
    install_requirements(paths, LauncherSettings(),
                         FakeTransport(response(200, manifest()), response(200, ZIP)),
                         RUNTIME, base_env={}, run=FakeWine(paths.prefix))
    assert not (port(paths) / GAME_FOLDER_TXT).exists()


def test_bad_game_files_fail_after_the_install(paths: AppPaths, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        install_requirements(paths, LauncherSettings(game_files=str(empty)),
                             FakeTransport(response(200, manifest()), response(200, ZIP)),
                             RUNTIME, base_env={}, run=FakeWine(paths.prefix))
    assert game_exe(paths).is_file()


def test_status_before_anything(paths: AppPaths) -> None:
    s = status(paths, LauncherSettings(), NO_WINE)
    assert (s.game_installed, s.game_version, s.prefix_ready, s.game_files) == (
        False, None, False, None)
    assert s.runtime is None and s.runtime_problem == NO_WINE.problem


def test_status_carries_the_runtime_and_its_note(paths: AppPaths) -> None:
    resolved = Resolved(RUNTIME, note="System Wine not used (too old); the bundled runtime runs")
    s = status(paths, LauncherSettings(), resolved)
    assert s.runtime == RUNTIME and s.runtime_note == resolved.note and s.runtime_problem is None


def test_an_unusable_runtime_stops_before_any_request(paths: AppPaths) -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError, match="older"):
        install_requirements(paths, LauncherSettings(), transport, OLD_WINE, base_env={},
                             run=FakeWine(paths.prefix))
    assert transport.calls == []
    assert not paths.data.exists()


def test_the_prefix_records_its_wine(paths: AppPaths) -> None:
    install_requirements(paths, LauncherSettings(),
                         FakeTransport(response(200, manifest()), response(200, ZIP)),
                         RUNTIME, base_env={}, run=FakeWine(paths.prefix))
    assert (paths.data / PREFIX_STAMP).read_text(encoding="utf-8") == "wine-10.0\n"


def test_status_after_install_and_a_run(paths: AppPaths, card: Path) -> None:
    install_requirements(paths, LauncherSettings(game_files=str(card)),
                         FakeTransport(response(200, manifest()), response(200, ZIP)),
                         RUNTIME, base_env={}, run=FakeWine(paths.prefix))
    (port(paths) / LOG_NAME).write_text("Shadowkey 0.2.32, Windows, 2026-11-15 19:30:00\r\n",
                                        encoding="utf-8", newline="")
    s = status(paths, LauncherSettings(game_files=str(card)), Resolved(RUNTIME))
    assert s.game_installed and s.prefix_ready
    assert s.game_version == "0.2.32"
    assert s.game_files == card
    assert s.game_files_problem is None


def test_status_names_a_game_files_problem(paths: AppPaths, tmp_path: Path) -> None:
    s = status(paths, LauncherSettings(game_files=str(tmp_path / "gone")), NO_WINE)
    assert s.game_files is None and s.game_files_problem


def test_apply_game_files_writes_at_once_when_the_prefix_exists(paths: AppPaths,
                                                                card: Path) -> None:
    assert apply_game_files(paths, card.parent.parent.parent) == card
    install_requirements(paths, LauncherSettings(),
                         FakeTransport(response(200, manifest()), response(200, ZIP)),
                         RUNTIME, base_env={}, run=FakeWine(paths.prefix))
    assert not (port(paths) / GAME_FOLDER_TXT).exists()
    apply_game_files(paths, card)
    assert (port(paths) / GAME_FOLDER_TXT).is_file()


def installed(paths: AppPaths, version: str = "0.2.32") -> None:
    install_requirements(paths, LauncherSettings(),
                         FakeTransport(response(200, manifest(version)), response(200, ZIP)),
                         RUNTIME, base_env={}, run=FakeWine(paths.prefix))


def write_log(paths: AppPaths, version: str) -> None:
    (port(paths) / LOG_NAME).write_text(f"Shadowkey {version}, Windows, 2026-11-15 19:30:00\r\n",
                                        encoding="utf-8", newline="")


def test_install_stamps_the_version_before_the_first_start(paths: AppPaths) -> None:
    installed(paths, "0.2.32")
    assert installed_version(paths, Build.WINDOWS) == "0.2.32"
    s = status(paths, LauncherSettings(), Resolved(RUNTIME))
    assert s.game_version == "0.2.32" and s.build is Build.WINDOWS


@pytest.mark.parametrize(("stamped", "logged", "shown"), [
    ("0.2.32", "0.2.33", "0.2.33"),  # his own updater moved it on after our install
    ("0.2.40", "0.2.33", "0.2.40"),  # we updated after his last start
    ("0.2.9", "0.2.10", "0.2.10"),  # by number, not by text
])
def test_the_newer_of_stamp_and_log_wins(paths: AppPaths, stamped: str, logged: str,
                                         shown: str) -> None:
    installed(paths, stamped)
    write_log(paths, logged)
    assert status(paths, LauncherSettings(), Resolved(RUNTIME)).game_version == shown


def test_update_rewrites_the_stamp(paths: AppPaths) -> None:
    installed(paths, "0.2.32")
    install_requirements(paths, LauncherSettings(),
                         FakeTransport(response(200, manifest("0.2.33")), response(200, ZIP)),
                         RUNTIME, base_env={}, update_game=True, run=FakeWine(paths.prefix))
    assert installed_version(paths, Build.WINDOWS) == "0.2.33"


def test_no_build_and_no_stamp_when_nothing_is_installed(paths: AppPaths) -> None:
    s = status(paths, LauncherSettings(), Resolved(RUNTIME))
    assert s.build is None and s.game_version is None
    assert not stamp_path(paths, Build.WINDOWS).exists()


@pytest.mark.parametrize("content", [
    b"", b"not json", b"[]", b'{"format": 2, "build": "windows", "version": "0.2.32"}',
    b'{"format": 1, "build": "amiga", "version": "0.2.32"}',
    b'{"format": 1, "build": "windows", "version": "../../etc"}',
    b'{"format": 1, "build": "windows", "version": 32}',
    b'{"format": 1, "build": "windows"}', b"\xff\xfe\x00",
    # Valid JSON even when cut at the read limit, so only the size check refuses it.
    b'{"format": 1, "build": "windows", "version": "0.2.32"}' + b" " * 5000,
])
def test_a_broken_stamp_is_ignored(paths: AppPaths, content: bytes) -> None:
    installed(paths, "0.2.32")
    write_log(paths, "0.2.31")
    stamp_path(paths, Build.WINDOWS).write_bytes(content)
    assert installed_version(paths, Build.WINDOWS) is None
    assert status(paths, LauncherSettings(), Resolved(RUNTIME)).game_version == "0.2.31"


def test_latest_game_version_is_his_manifest(paths: AppPaths) -> None:
    transport = FakeTransport(response(200, manifest("0.2.46")))
    assert latest_game_version(paths, transport, Build.WINDOWS) == "0.2.46"
    assert transport.calls[0].url == Build.WINDOWS.manifest_url


def test_the_stamp_is_kept_per_build(paths: AppPaths) -> None:
    installed(paths, "0.2.32")
    assert stamp_path(paths, Build.WINDOWS).name == "installed-windows.json"
    assert installed_version(paths, Build.LINUX_TARBALL) is None
    assert installed_version(paths, Build.LINUX_APPIMAGE) is None


def test_a_stamp_of_another_build_is_not_taken(paths: AppPaths) -> None:
    paths.data.mkdir(parents=True, exist_ok=True)
    stamp_path(paths, Build.LINUX_TARBALL).write_text(
        '{"format": 1, "build": "windows", "version": "0.2.32"}', encoding="utf-8")
    assert installed_version(paths, Build.LINUX_TARBALL) is None


def test_the_old_stamp_becomes_the_windows_stamp(paths: AppPaths) -> None:
    # The first launchers wrote one data/installed.json for the only build there was.
    paths.data.mkdir(parents=True, exist_ok=True)
    (paths.data / OLD_STAMP_NAME).write_text(
        '{"format": 1, "build": "windows", "version": "0.2.46"}', encoding="utf-8")
    assert installed_version(paths, Build.WINDOWS) == "0.2.46"
    assert not (paths.data / OLD_STAMP_NAME).exists()
    assert stamp_path(paths, Build.WINDOWS).is_file()


def test_the_old_stamp_never_overwrites_a_new_one(paths: AppPaths) -> None:
    installed(paths, "0.2.48")
    (paths.data / OLD_STAMP_NAME).write_text(
        '{"format": 1, "build": "windows", "version": "0.2.30"}', encoding="utf-8")
    assert installed_version(paths, Build.WINDOWS) == "0.2.48"


def test_a_windows_install_seeds_the_art_from_his_linux_build(paths: AppPaths,
                                                              tmp_path: Path) -> None:
    # The art is the same for both builds.
    env = {"XDG_DATA_HOME": str(tmp_path / "his-data")}
    native_art = tmp_path / "his-data" / "Shadowkey" / "ShadowkeyPort" / "art"
    native_art.mkdir(parents=True)
    (native_art / "index.txt").write_text("index\n", encoding="utf-8")
    install_requirements(paths, LauncherSettings(),
                         FakeTransport(response(200, manifest()), response(200, ZIP)),
                         RUNTIME, base_env=env, run=FakeWine(paths.prefix))
    assert (port(paths) / "art" / "index.txt").read_text(encoding="utf-8") == "index\n"


def test_the_tests_never_see_the_real_home(paths: AppPaths) -> None:
    assert Path.home() == paths.data.parents[1] / "home"


def zip_of(folder: Path, path: Path) -> Path:
    """The card folder packed as a zip, the way the ngarchive dump comes."""
    root = folder.parent.parent.parent
    with zipfile.ZipFile(path, "w") as archive:
        for item in sorted(root.rglob("*")):
            archive.write(item, item.relative_to(root).as_posix())
    return path


def test_a_card_zip_is_taken_and_unpacked(paths: AppPaths, card: Path, tmp_path: Path) -> None:
    folder = apply_game_files(paths, zip_of(card, tmp_path / "Shadowkey_Files.zip"))
    assert folder == paths.card / "system" / "apps" / "6r51"
    assert sorted(p.name for p in folder.iterdir()) == sorted(LEVEL_FILES)


def test_a_file_in_the_card_is_taken_as_its_folder(paths: AppPaths, card: Path) -> None:
    assert apply_game_files(paths, card / "azra.zmp") == card


def test_a_zip_without_the_card_says_so(paths: AppPaths, tmp_path: Path) -> None:
    other = tmp_path / "other.zip"
    with zipfile.ZipFile(other, "w") as archive:
        archive.writestr(zipfile.ZipInfo("readme.txt", date_time=(2020, 1, 1, 0, 0, 0)), "hi")
    with pytest.raises(ValueError, match="no 6R51 folder in other.zip"):
        apply_game_files(paths, other)


def test_a_bad_card_zip_keeps_the_good_card(paths: AppPaths, card: Path, tmp_path: Path) -> None:
    # An incomplete card is refused before it replaces the good one.
    good = apply_game_files(paths, zip_of(card, tmp_path / "good.zip"))
    (card / "azra.zmp").unlink()
    with pytest.raises(ValueError, match="missing level files"):
        apply_game_files(paths, zip_of(card, tmp_path / "bad.zip"))
    assert (good / "azra.zmp").is_file()
    assert sorted(p.name for p in good.iterdir()) == sorted(LEVEL_FILES)


def test_a_failed_art_copy_does_not_fail_the_install(paths: AppPaths, tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    from project_reforged_linux import prepare

    def full(source: Path, target: Path) -> bool:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(prepare, "seed_art", full)
    install_requirements(paths, LauncherSettings(),
                         FakeTransport(response(200, manifest()), response(200, ZIP)),
                         RUNTIME, base_env={"XDG_DATA_HOME": str(tmp_path / "his")},
                         run=FakeWine(paths.prefix))
    assert game_exe(paths).is_file()


def test_a_version_too_long_in_his_log_does_not_break_the_status(paths: AppPaths) -> None:
    installed(paths, "0.2.32")
    write_log(paths, "0.2.46.1.2")
    s = status(paths, LauncherSettings(), Resolved(RUNTIME))
    assert s.game_installed and s.game_version == "0.2.32"


def test_a_prefix_from_before_the_ready_mark_is_adopted(paths: AppPaths) -> None:
    from project_reforged_linux.wineprefix import READY_MARK, prefix_ready

    installed(paths)
    (paths.prefix / READY_MARK).unlink()
    assert not prefix_ready(paths.prefix)
    # No setup began since the stamp was written, so it vouches for the prefix.
    assert (paths.data / PREFIX_STAMP).is_file()
    assert status(paths, LauncherSettings(), Resolved(RUNTIME)).prefix_ready


def test_a_half_built_prefix_without_the_stamp_is_not_adopted(paths: AppPaths) -> None:
    from project_reforged_linux.wineprefix import READY_MARK

    installed(paths)
    (paths.prefix / READY_MARK).unlink()
    (paths.data / PREFIX_STAMP).unlink()
    assert not status(paths, LauncherSettings(), Resolved(RUNTIME)).prefix_ready


def test_a_bad_card_zip_names_the_zip_not_a_temporary_folder(paths: AppPaths, card: Path,
                                                             tmp_path: Path) -> None:
    (card / "azra.zmp").unlink()
    with pytest.raises(ValueError) as raised:
        apply_game_files(paths, zip_of(card, tmp_path / "dump.zip"))
    text = str(raised.value)
    assert "dump.zip" in text and "system/apps/6r51" in text and ".ngage-new" not in text


def test_a_failed_rebuild_is_not_adopted_by_an_old_stamp(paths: AppPaths) -> None:
    # The stamp of the prefix's last runtime is rewritten at every start; it speaks for a
    # finished setup only while no new setup has begun.
    import shutil

    from project_reforged_linux.wineprefix import PrefixError

    installed(paths)
    shutil.rmtree(paths.prefix)  # the player resets Wine

    class HalfBuild(FakeWine):
        def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            result = super().__call__(command, **kwargs)
            if "wineboot" in command:
                return subprocess.CompletedProcess(command, 1, b"wineboot died")
            return result

    with pytest.raises(PrefixError):
        install_requirements(paths, LauncherSettings(),
                             FakeTransport(response(200, manifest()), response(200, ZIP)),
                             RUNTIME, base_env={}, run=HalfBuild(paths.prefix), update_game=False)
    assert not status(paths, LauncherSettings(), Resolved(RUNTIME)).prefix_ready


@pytest.mark.parametrize("layout", ["two cards", "file where the folder is"])
def test_odd_card_zips_name_the_zip(paths: AppPaths, tmp_path: Path, layout: str) -> None:
    path = tmp_path / "odd.zip"
    with zipfile.ZipFile(path, "w") as archive:
        when = (2004, 10, 26, 12, 0, 0)
        if layout == "two cards":
            for wrap in ("Shadowkey (EU)", "Shadowkey (US)"):
                for name in LEVEL_FILES:
                    archive.writestr(zipfile.ZipInfo(f"{wrap}/system/apps/6r51/{name}", when), "x")
        else:
            archive.writestr(zipfile.ZipInfo("card", when), "a file")
            archive.writestr(zipfile.ZipInfo("card/system/apps/6r51/azra.zmp", when), "x")
    with pytest.raises(ValueError) as raised:
        apply_game_files(paths, path)
    text = str(raised.value)
    assert "odd.zip" in text and ".ngage-new" not in text, text
