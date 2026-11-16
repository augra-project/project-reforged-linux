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

from project_reforged_linux.gamefiles import GAME_FOLDER_TXT, LEVEL_FILES
from project_reforged_linux.gamesettings import FIRST_SETTINGS, SETTINGS_CFG
from project_reforged_linux.install import GAME_EXE, GAME_FOLDER, game_exe
from project_reforged_linux.paths import AppPaths, resolve
from project_reforged_linux.prepare import (
    Step,
    apply_game_files,
    game_update_available,
    install_requirements,
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


def test_game_update_available(paths: AppPaths) -> None:
    install_requirements(paths, LauncherSettings(),
                         FakeTransport(response(200, manifest()), response(200, ZIP)),
                         RUNTIME, base_env={}, run=FakeWine(paths.prefix))
    assert game_update_available(paths, FakeTransport(response(200, manifest()))) is None
    (port(paths) / LOG_NAME).write_text("Shadowkey 0.2.31, Windows, 2026-11-15 19:30:00\r\n",
                                        encoding="utf-8", newline="")
    found = game_update_available(paths, FakeTransport(response(200, manifest("0.2.32"))))
    assert found is not None and found.version == "0.2.32"
    (port(paths) / LOG_NAME).write_text("Shadowkey 0.2.32, Windows, 2026-11-15 19:30:00\r\n",
                                        encoding="utf-8", newline="")
    assert game_update_available(paths, FakeTransport(response(200, manifest()))) is None
