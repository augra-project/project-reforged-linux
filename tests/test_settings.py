# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import json
import stat
from pathlib import Path

import pytest

from project_reforged_linux.builds import Build
from project_reforged_linux.runtimes import Mode
from project_reforged_linux.settings import (
    SETTINGS_JSON,
    DesktopChoice,
    LauncherSettings,
    load,
    save,
)


def test_defaults_when_missing(tmp_path: Path) -> None:
    loaded = load(tmp_path)
    assert loaded.settings == LauncherSettings()
    assert loaded.problem is None
    assert loaded.settings.check_game_updates
    assert loaded.settings.sync_saves
    assert loaded.settings.game_build is None
    assert not loaded.settings.check_launcher_updates
    assert loaded.settings.desktop is DesktopChoice.ASK
    assert loaded.settings.runtime_mode is Mode.AUTO and loaded.settings.runtime_wine is None


def test_chosen_runtime_round_trip(tmp_path: Path) -> None:
    wanted = LauncherSettings(runtime_mode=Mode.CHOSEN,
                              runtime_wine="/home/a/.local/share/lutris/runners/wine/x/bin/wine")
    save(tmp_path, wanted)
    assert load(tmp_path).settings == wanted


def test_round_trip(tmp_path: Path) -> None:
    wanted = LauncherSettings(game_files="/media/card/system/apps/6r51",
                              check_game_updates=False, desktop=DesktopChoice.DECLINED,
                              first_run_done=True, game_build=Build.LINUX_TARBALL,
                              sync_saves=False)
    save(tmp_path, wanted)
    assert load(tmp_path).settings == wanted
    assert json.loads((tmp_path / SETTINGS_JSON).read_text(encoding="utf-8"))["format"] == 1


def test_file_is_private(tmp_path: Path) -> None:
    save(tmp_path, LauncherSettings())
    assert stat.S_IMODE((tmp_path / SETTINGS_JSON).stat().st_mode) == 0o600


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    (tmp_path / SETTINGS_JSON).write_text('{"format": 1, "later": 5}', encoding="utf-8")
    assert load(tmp_path).settings == LauncherSettings()


@pytest.mark.parametrize("text", [
    "not json",
    "[]",
    '{"format": 2}',
    '{"format": 1, "check_game_updates": "yes"}',
    '{"format": 1, "desktop": "maybe"}',
    '{"format": 1, "game_files": "relative/path"}',
    '{"format": 1, "game_files": 7}',
    '{"format": 1, "runtime_mode": "proton"}',
    '{"format": 1, "runtime_mode": "chosen"}',
    '{"format": 1, "runtime_mode": "system", "runtime_wine": "/usr/bin/wine"}',
    '{"format": 1, "runtime_mode": "chosen", "runtime_wine": "bin/wine"}',
    '{"format": 1, "game_build": "amiga"}',
    '{"format": 1, "game_build": 3}',
    '{"format": 1, "sync_saves": 1}',
])
def test_broken_file_is_put_aside(tmp_path: Path, text: str) -> None:
    (tmp_path / SETTINGS_JSON).write_text(text, encoding="utf-8")
    loaded = load(tmp_path)
    assert loaded.settings == LauncherSettings()
    assert loaded.problem is not None and "settings.json.bad" in loaded.problem
    assert (tmp_path / "settings.json.bad").read_text(encoding="utf-8") == text
    assert not (tmp_path / SETTINGS_JSON).exists()


def test_not_utf8_is_put_aside(tmp_path: Path) -> None:
    (tmp_path / SETTINGS_JSON).write_bytes(b"\xff\xfe{")
    assert load(tmp_path).problem is not None


@pytest.mark.parametrize("kwargs", [
    {"runtime_mode": Mode.CHOSEN},
    {"runtime_mode": Mode.SYSTEM, "runtime_wine": "/usr/bin/wine"},
    {"runtime_mode": Mode.CHOSEN, "runtime_wine": "bin/wine"},
    {"game_files": "relative/6r51"},
])
def test_a_wrong_combination_cannot_be_built(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        LauncherSettings(**kwargs)  # type: ignore[arg-type]


def test_each_build_round_trips_by_its_word(tmp_path: Path) -> None:
    for build in Build:
        save(tmp_path, LauncherSettings(game_build=build))
        stored = json.loads((tmp_path / SETTINGS_JSON).read_text(encoding="utf-8"))
        assert stored["game_build"] == build.key
        assert load(tmp_path).settings.game_build is build


def test_a_file_from_before_the_native_builds_loads(tmp_path: Path) -> None:
    # Older settings.json files have neither game_build nor sync_saves.
    (tmp_path / SETTINGS_JSON).write_text(
        '{"format": 1, "game_files": null, "check_game_updates": false,'
        ' "check_launcher_updates": false, "desktop": "ask", "first_run_done": false,'
        ' "runtime_mode": "auto", "runtime_wine": null}', encoding="utf-8")
    loaded = load(tmp_path)
    assert loaded.problem is None
    assert loaded.settings.game_build is None and loaded.settings.sync_saves
    assert not loaded.settings.check_game_updates  # what the player had stays


def test_nesting_too_deep_is_put_aside(tmp_path: Path) -> None:
    (tmp_path / SETTINGS_JSON).write_text("[" * 60_000, encoding="utf-8")
    loaded = load(tmp_path)
    assert loaded.settings == LauncherSettings() and loaded.problem is not None
