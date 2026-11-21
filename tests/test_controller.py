# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import os
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from project_reforged_linux import desktop
from project_reforged_linux.builds import Build
from project_reforged_linux.gamefiles import GAME_FOLDER_TXT, LEVEL_FILES, to_wine_path
from project_reforged_linux.gamelog import LogState, read_log
from project_reforged_linux.gamesettings import SETTINGS_CFG
from project_reforged_linux.installhelp import Family
from project_reforged_linux.nativecheck import NativeCheck
from project_reforged_linux.paths import AppPaths, ensure_dirs, resolve
from project_reforged_linux.prepare import Status, Step
from project_reforged_linux.runner import GameStatus
from project_reforged_linux.runtimes import Candidate, Checked, Resolved, Source
from project_reforged_linux.settings import DesktopChoice, LauncherSettings, load, save
from project_reforged_linux.ui.controller import (
    ICON_NEEDS_APPIMAGE,
    SETTINGS_TITLE,
    LauncherController,
)
from project_reforged_linux.ui.firststart import FirstStart

CHECKED = Checked(Candidate(Source.SYSTEM, Path("/usr/bin/wine"), Path("/usr/bin/wineserver")),
                  (10, 0), "wine-10.0", None)
READY = Status(True, "0.2.33", True, Path("/card/6r51"), None, CHECKED, None, None)
# His Linux builds cannot run here, so the tests written for the Windows path keep testing it.
OLD_HOST = NativeCheck(glibc=(2, 28), vulkan=True, curl=True, fuse=True)
GOOD_HOST = NativeCheck(glibc=(2, 41), vulkan=True, curl=True, fuse=True)
NO_VULKAN = NativeCheck(glibc=(2, 41), vulkan=False, curl=True, fuse=True)
HEADER = "Shadowkey 0.2.33, Windows, x\r\n"
FETCHING = read_log(HEADER + "00:00.5 Art: 805 of 805 pictures to download (632.6 MB), "
                             "4 at a time\r\n")
ART_DONE = read_log(HEADER + "00:00.5 Art: all 805 pictures up to date\r\n")


class FakeSession:
    def __init__(self, log: LogState = FETCHING) -> None:
        self.polls = 0
        self.log = log

    def poll(self) -> GameStatus:
        self.polls += 1
        running = self.polls < 3
        return GameStatus(running, None if running else 0, self.log if running else LogState(),
                          False)


@pytest.fixture
def paths(xdg_home: Path) -> AppPaths:
    p = resolve()
    ensure_dirs(p)
    return p


def controller(paths: AppPaths, **kwargs: Any) -> LauncherController:
    defaults: dict[str, Any] = {
        "resolve": lambda settings: Resolved(CHECKED),
        "status": lambda *a, **k: READY,
        "native": lambda: OLD_HOST,
        "synchronous": True,
        # Options asks the host's Wine; never a real wine in a test.
        "probe_runtimes": lambda: (CHECKED, None),
        # Update Reforged asks his site when no answer is at hand; offline, nothing newer.
        "latest": lambda *a: READY.game_version,
    }
    defaults.update(kwargs)
    return LauncherController(paths, **defaults)


def starting(session: FakeSession, **kwargs: Any) -> dict[str, Any]:
    return {"start_game": lambda *a, **k: session, "wine_user": lambda paths: "alice",
            "mark": lambda paths, checked: None, "downgrade": lambda paths, checked: None,
            **kwargs}


def test_refresh_reports_the_status(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    seen: list[Status] = []
    c = controller(paths)
    c.status_changed.connect(seen.append)
    c.refresh()
    assert seen == [READY] and c.can_run()


def test_cannot_run_without_a_runtime(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    broken = Status(True, "0.2.33", True, Path("/card/6r51"), None, None, None, "no Wine")
    c = controller(paths, status=lambda *a, **k: broken)
    c.refresh()
    assert not c.can_run()


def test_choose_saves_the_files(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    folder = tmp_path / "card" / "system" / "apps" / "6r51"
    c = controller(paths, apply_files=lambda paths, chosen: folder)
    c.choose_game_files(tmp_path / "card")
    assert load(paths.config).settings.game_files == str(folder)


def test_choose_reports_a_bad_folder(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    messages: list[tuple[str, str]] = []

    def refuse(paths: AppPaths, chosen: Path) -> Path:
        raise FileNotFoundError(f"no 6R51 folder in {chosen}")

    c = controller(paths, apply_files=refuse)
    c.message.connect(lambda title, text: messages.append((title, text)))
    c.choose_game_files(tmp_path)
    assert messages and "6R51" in messages[0][1]
    assert load(paths.config).settings.game_files is None


def test_install_reports_progress_and_refreshes(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    lines: list[tuple[float | None, str]] = []
    refreshed: list[Status] = []

    def install(paths, settings, transport, runtime, *, build, base_env, progress, update_game):  # type: ignore[no-untyped-def]
        progress(Step.MANIFEST, None, None)
        progress(Step.DOWNLOAD, 6_594_509, 13_189_017)
        return None

    c = controller(paths, install=install)
    c.progress.connect(lambda fraction, text: lines.append((fraction, text)))
    c.status_changed.connect(refreshed.append)
    c.refresh()
    c.install()
    # His site is asked first (no start check ran); a step without a known end is busy, a
    # known one a fraction (the line shows "50%").
    assert lines[0] == (None, "Checking for a newer build")
    assert lines[1] == (None, Step.MANIFEST.value)
    assert lines[2][0] == pytest.approx(0.5, abs=1e-6) and lines[2][1] == Step.DOWNLOAD.value
    assert len(refreshed) == 2


def test_install_failure_is_a_message(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    messages: list[tuple[str, str]] = []

    def install(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("his site did not answer")

    c = controller(paths, install=install)
    c.message.connect(lambda title, text: messages.append((title, text)))
    c.refresh()
    c.install()
    assert messages == [("Update Reforged", "his site did not answer")]


def test_install_without_a_runtime_says_why(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    messages: list[tuple[str, str]] = []
    installed: list[bool] = []
    c = controller(paths, resolve=lambda settings: Resolved(None, problem="No usable Wine"),
                   install=lambda *a, **k: installed.append(True))
    c.message.connect(lambda title, text: messages.append((title, text)))
    c.refresh()
    c.install()
    assert installed == [] and messages == [("Update Reforged", "No usable Wine")]


def test_run_game_polls_until_it_ends(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    session = FakeSession()
    lines: list[tuple[float | None, str]] = []
    running: list[bool] = []
    c = controller(paths, **starting(session))
    c.progress.connect(lambda fraction, text: lines.append((fraction, text)))
    c.game_running.connect(running.append)
    c.refresh()
    assert c.run_game() is None
    assert not c.can_run(), "one game at a time"
    while c.is_running():
        c.poll_game()
    assert running == [True, False]
    assert (None, "Downloading the game's art: 805 of 805 pictures (632.6 MB)") in lines


def test_a_finished_art_check_is_a_note_not_a_busy_line(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    notes: list[str] = []
    busy: list[str] = []
    c = controller(paths, **starting(FakeSession(ART_DONE)))
    c.note.connect(notes.append)
    c.progress.connect(lambda fraction, text: busy.append(text))
    c.refresh()
    c.run_game()
    c.poll_game()
    assert notes == ["Art ready: 805 pictures"] and busy == []


def test_run_game_asks_before_a_downgrade(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    started: list[bool] = []
    c = controller(paths, start_game=lambda *a, **k: started.append(True) or FakeSession(),
                   wine_user=lambda paths: "alice", mark=lambda paths, checked: None,
                   downgrade=lambda paths, checked: "older Wine")
    c.refresh()
    assert c.run_game() == "older Wine" and started == []
    assert c.run_game(confirmed=True) is None and started == [True]


def test_run_game_refuses_before_the_requirements(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    started: list[bool] = []
    c = controller(paths, start_game=lambda *a, **k: started.append(True))
    assert c.run_game() == "The requirements are not complete yet." and started == []


def test_a_failed_start_is_a_message(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    messages: list[tuple[str, str]] = []
    running: list[bool] = []

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise FileNotFoundError("the game is not installed: /x/Shadowkey.exe")

    c = controller(paths, **starting(FakeSession(), start_game=refuse))
    c.message.connect(lambda title, text: messages.append((title, text)))
    c.game_running.connect(running.append)
    c.refresh()
    assert c.run_game() is None
    assert messages == [("Run game", "the game is not installed: /x/Shadowkey.exe")]
    assert running == [] and not c.is_running()


def test_threaded_jobs_end_and_are_pruned(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QCoreApplication, QDeadlineTimer, QThread

    seen: list[Status] = []
    busy: list[bool] = []
    threads: list[QThread] = []
    c = controller(paths, synchronous=False)
    c.status_changed.connect(seen.append)
    # A result handled in the worker would race the window; it must land on its thread.
    c.status_changed.connect(lambda status: threads.append(QThread.currentThread()))
    c.busy_changed.connect(busy.append)
    c.refresh()
    deadline = QDeadlineTimer(5000)
    while not seen and not deadline.hasExpired():
        QCoreApplication.processEvents()
    c.shutdown()
    QCoreApplication.processEvents()
    assert seen == [READY] and busy == [True, False]
    assert threads == [qapp.thread()]
    assert c.jobs() == 0


def test_the_log_tells_the_story_without_the_home_folder(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                         caplog: pytest.LogCaptureFixture) -> None:
    # A log of everything a run did, for bug reports; home names a person.
    import logging

    card = Path.home() / "games" / "ngage-files" / "system" / "apps" / "6r51"
    mine = Status(True, "0.2.46", True, card, None, CHECKED, None, None)
    c = controller(paths, status=lambda *a, **k: mine, install=lambda *a, **k: None,
                   latest=lambda p, t, b: "0.2.46")
    with caplog.at_level(logging.INFO, logger="project_reforged_linux"):
        c.refresh()
        c.check_game_update()
        c.install()
    text = caplog.text
    assert "status: game Windows build v0.2.46" in text and "~/games/ngage-files" in text
    assert "his current build: v0.2.46" in text
    assert "Update Reforged: Project Reforged is up to date (v0.2.46)." in text
    assert str(Path.home()) not in text


@pytest.mark.parametrize(("installed", "said"), [
    (False, "Update Reforged pressed: fetching his build"),
    (True, "Update Reforged pressed: his build stays, checking the rest"),
])
def test_the_pressed_line_says_whether_it_fetches(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                  caplog: pytest.LogCaptureFixture,
                                                  installed: bool, said: str) -> None:
    # The line said "stays" while it fetched.
    import logging

    state = Status(installed, "0.2.46" if installed else None, installed, None, None, CHECKED,
                   None, None)
    c = controller(paths, status=lambda *a, **k: state, install=lambda *a, **k: None,
                   latest=lambda p, t, b: "0.2.46")
    with caplog.at_level(logging.INFO, logger="project_reforged_linux"):
        c.refresh()
        c.check_game_update()
        c.install()
    assert said in caplog.text
    assert "runtime system wine-10.0;" in caplog.text or "runtime system wine-10.0\n" in caplog.text


def test_the_start_check_asks_the_builds_manifest(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    asked: list[Any] = []
    c = controller(paths, latest=lambda p, t, b: asked.append(b) or "0.2.48")
    c.start_checks()
    assert asked == [Build.WINDOWS]  # on the old host, the Windows build


def test_the_start_check_asks_after_the_build_is_known(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    asked: list[Any] = []
    c = controller(paths, native=lambda: GOOD_HOST,
                   latest=lambda p, t, b: asked.append(b) or "0.2.48")
    c.start_checks()
    assert asked == [Build.LINUX_APPIMAGE]


@pytest.mark.parametrize("on", [True, False])
def test_the_start_check_follows_its_setting(qapp, paths: AppPaths, on: bool) -> None:  # type: ignore[no-untyped-def]
    save(paths.config, LauncherSettings(check_game_updates=on))
    asked: list[Any] = []
    c = controller(paths, latest=lambda p, t, b: asked.append(b) or "0.2.48")
    c.start_checks()
    assert c.status is not None  # the requirements are checked either way
    assert len(asked) == (1 if on else 0)


def test_refresh_takes_the_best_build_that_runs(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    asked: list[Any] = []
    c = controller(paths, native=lambda: GOOD_HOST,
                   status=lambda *a, **k: asked.append(k.get("build", a[3] if len(a) > 3 else None))
                   or READY)
    c.refresh()
    assert c.build is Build.LINUX_APPIMAGE and c.build_note is None
    assert asked == [Build.LINUX_APPIMAGE]


def test_a_chosen_build_that_cannot_run_gives_way_and_says_so(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    save(paths.config, LauncherSettings(game_build=Build.LINUX_TARBALL))
    notes: list[str] = []
    c = controller(paths, native=lambda: NO_VULKAN, family=lambda: Family.DEBIAN)
    c.note.connect(notes.append)
    c.refresh()
    assert c.build is Build.WINDOWS
    assert c.build_note is not None and "No Vulkan driver loader" in c.build_note
    assert notes == [c.build_note], "one line on the progress row, never a box"
    # The choice stays saved: on a system that runs the tarball it comes back.
    assert load(paths.config).settings.game_build is Build.LINUX_TARBALL
    assert "sudo apt install mesa-vulkan-drivers libvulkan1" in c.fallback_note()


def test_a_native_install_needs_no_wine(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    # Only what is checked: keeping the progress callback would hold the job in a cycle.
    calls: list[tuple[Build, Any]] = []
    c = controller(paths, native=lambda: GOOD_HOST, resolve=lambda settings: Resolved(None),
                   install=lambda *a, **k: calls.append((k["build"], a[3])))
    c.refresh()
    c.install()
    assert calls == [(Build.LINUX_APPIMAGE, None)]


def test_the_windows_install_still_needs_wine(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    calls: list[Any] = []
    messages: list[tuple[str, str]] = []
    c = controller(paths, resolve=lambda settings: Resolved(None, problem="No usable Wine"),
                   install=lambda *a, **k: calls.append(k))
    c.message.connect(lambda title, text: messages.append((title, text)))
    c.refresh()
    c.install()
    assert calls == [] and "No usable Wine" in messages[0][1]


NATIVE_READY = Status(True, "0.2.48", False, Path("/card/6r51"), None, None, None, None,
                      Build.LINUX_APPIMAGE)


def native(paths: AppPaths, session: FakeSession, **kwargs: Any) -> LauncherController:
    started: list[Any] = kwargs.pop("started", [])
    return controller(paths, native=lambda: GOOD_HOST, resolve=lambda settings: Resolved(None),
                      status=lambda *a, **k: NATIVE_READY,
                      start_native=lambda *a, **k: started.append(a) or session,
                      start_game=lambda *a, **k: pytest.fail("Wine started for a Linux build"),
                      **kwargs)


def test_a_native_build_runs_without_wine_or_prefix(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    started: list[Any] = []
    c = native(paths, FakeSession(ART_DONE), started=started, sync=lambda *a: [])
    c.refresh()
    assert c.can_run()
    assert c.run_game() is None
    assert started and started[0][0] is Build.LINUX_APPIMAGE
    assert c.is_running()


def test_a_native_build_with_a_problem_does_not_run(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    save(paths.config, LauncherSettings(game_build=Build.LINUX_TARBALL))
    c = controller(paths, native=lambda: NO_VULKAN, status=lambda *a, **k: NATIVE_READY)
    c.refresh()
    assert not c.can_run()


def test_the_saves_are_synced_before_a_native_start(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    synced: list[tuple[Path, Path, Path]] = []
    c = native(paths, FakeSession(), sync=lambda *a: synced.append(a) or [],
               wine_user=lambda paths: "alice")
    c.refresh()
    c.run_game()
    (other, mine, backups), = synced
    assert other == paths.port_dir("alice").parent  # the Windows build's saves
    assert mine == Path(os.environ["XDG_DATA_HOME"]) / "Shadowkey"
    assert backups == paths.data / "save-backups"


def test_no_sync_when_the_player_turned_it_off(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    save(paths.config, LauncherSettings(sync_saves=False))
    synced: list[Any] = []
    c = native(paths, FakeSession(), sync=lambda *a: synced.append(a) or [],
               wine_user=lambda paths: "alice")
    c.refresh()
    c.run_game()
    assert synced == [] and c.is_running()


def test_the_windows_build_takes_the_linux_saves(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    synced: list[tuple[Path, Path, Path]] = []
    c = controller(paths, sync=lambda *a: synced.append(a) or [], **starting(FakeSession()))
    c.refresh()
    c.run_game()
    (other, mine, _), = synced
    assert other == Path(os.environ["XDG_DATA_HOME"]) / "Shadowkey"
    assert mine == paths.port_dir("alice").parent


def test_without_a_prefix_there_are_no_windows_saves_to_sync(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    from project_reforged_linux.wineprefix import PrefixError

    def no_prefix(paths: AppPaths) -> str:
        raise PrefixError("no prefix yet")

    synced: list[Any] = []
    c = native(paths, FakeSession(), sync=lambda *a: synced.append(a) or [], wine_user=no_prefix)
    c.refresh()
    assert c.run_game() is None
    assert synced == [] and c.is_running()


def test_options_state_reflects_the_last_refresh(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    c = controller(paths, native=lambda: GOOD_HOST,
                   status=lambda *a, **k: replace_status(READY, build=Build.LINUX_APPIMAGE))
    c.refresh()
    s = c.options_state()
    assert (s.build, s.game_version, s.game_installed) == (Build.LINUX_APPIMAGE, "0.2.33", True)
    assert s.native == GOOD_HOST and s.resolved == Resolved(CHECKED)
    assert s.settings == c.settings and not s.icon_installed


def test_options_state_does_not_claim_another_builds_version(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    # The status still describes the Windows install while the AppImage is the build that runs.
    c = controller(paths, native=lambda: GOOD_HOST,
                   status=lambda *a, **k: replace_status(READY, build=Build.WINDOWS))
    c.refresh()
    s = c.options_state()
    assert s.build is Build.LINUX_APPIMAGE and not s.game_installed and s.game_version is None


def test_apply_settings_saves_and_looks_again(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    builds: list[Build] = []
    c = controller(paths, native=lambda: GOOD_HOST,
                   status=lambda p, settings, resolved, build, **k: builds.append(build) or READY)
    c.refresh()
    after: list[str] = []
    new = LauncherSettings(game_build=Build.WINDOWS, check_game_updates=False)
    c.apply_settings(new, after=lambda: after.append("done"))
    assert load(paths.config).settings == new == c.settings
    assert c.build is Build.WINDOWS and builds[-1] is Build.WINDOWS
    assert after == ["done"]


def test_apply_settings_asks_his_new_builds_manifest(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    asked: list[Build] = []
    c = controller(paths, native=lambda: GOOD_HOST,
                   latest=lambda paths, transport, build: asked.append(build) or "0.2.48")
    c.start_checks()
    assert asked == [Build.LINUX_APPIMAGE]
    c.apply_settings(LauncherSettings(game_build=Build.WINDOWS))
    assert asked == [Build.LINUX_APPIMAGE, Build.WINDOWS]


def test_apply_settings_without_changes_does_nothing(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    refreshed: list[int] = []
    c = controller(paths, status=lambda *a, **k: refreshed.append(1) or READY)
    after: list[str] = []
    c.apply_settings(c.settings, after=lambda: after.append("done"))
    assert refreshed == [] and after == ["done"]
    assert not (paths.config / "settings.json").exists()


def test_find_runtimes_hands_over_the_search(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    got: list[list[Checked]] = []
    c = controller(paths, find_runtimes=lambda: [CHECKED])
    c.find_runtimes(got.append)
    assert got == [[CHECKED]]


def test_a_failed_search_still_answers(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    def denied() -> list[Checked]:
        raise PermissionError("/opt/wine-staging")

    got: list[list[Checked]] = []
    c = controller(paths, find_runtimes=denied)
    c.find_runtimes(got.append)
    assert got == [[]]


def test_the_desktop_icon_needs_the_appimage(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    where = desktop.DesktopTargets(tmp_path / "apps", tmp_path / "icons")
    c = controller(paths, desktop_targets=lambda: where, env={})
    problem = c.set_desktop_icon(True)
    assert problem is not None and "AppImage" in problem
    assert not where.desktop_file.exists()
    assert c.settings.desktop is DesktopChoice.ASK


def test_the_desktop_icon_installs_and_removes(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    image = tmp_path / "Project_Reforged_Launcher.AppImage"
    image.write_bytes(b"\x7fELF")
    where = desktop.DesktopTargets(tmp_path / "apps", tmp_path / "icons")
    c = controller(paths, desktop_targets=lambda: where, env={"APPIMAGE": str(image)})
    assert c.set_desktop_icon(True) is None
    assert desktop.installed_exec(where) == str(image)
    assert load(paths.config).settings.desktop is DesktopChoice.INSTALLED
    assert c.options_state().icon_installed
    assert c.set_desktop_icon(False) is None
    assert not where.desktop_file.exists()
    assert load(paths.config).settings.desktop is DesktopChoice.DECLINED


def test_a_failed_desktop_icon_says_why(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    image = tmp_path / "launcher.AppImage"
    image.write_bytes(b"\x7fELF")
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the folder should be", encoding="utf-8")
    where = desktop.DesktopTargets(blocked / "apps", blocked / "icons")
    c = controller(paths, desktop_targets=lambda: where, env={"APPIMAGE": str(image)})
    problem = c.set_desktop_icon(True)
    assert problem is not None and problem.startswith("The desktop icon could not be installed")
    assert c.settings.desktop is DesktopChoice.ASK


def replace_status(status: Status, **changes: Any) -> Status:
    return replace(status, **changes)


GNOME = {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}


def appimage(tmp_path: Path, name: str = "launcher.AppImage") -> Path:
    image = tmp_path / name
    image.write_bytes(b"\x7fELF")
    return image


def targets(tmp_path: Path) -> desktop.DesktopTargets:
    return desktop.DesktopTargets(tmp_path / "apps", tmp_path / "icons")


def test_first_start_is_saved_once(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    from project_reforged_linux.ui.firststart import FirstStart

    c = controller(paths)
    assert not c.settings.first_run_done
    assert c.finish_first_start(FirstStart(True, None)) is None
    saved = load(paths.config).settings
    assert saved.first_run_done and saved.check_launcher_updates
    assert saved.desktop is DesktopChoice.ASK


def test_first_start_remembers_never(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    from project_reforged_linux.ui.firststart import FirstStart, IconChoice

    c = controller(paths)
    c.finish_first_start(FirstStart(False, IconChoice.NEVER))
    assert load(paths.config).settings.desktop is DesktopChoice.DECLINED


def test_first_start_installs_the_icon_and_says_so(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from project_reforged_linux.ui.firststart import FirstStart, IconChoice

    notes: list[str] = []
    where = targets(tmp_path)
    c = controller(paths, desktop_targets=lambda: where,
                   env={**GNOME, "APPIMAGE": str(appimage(tmp_path))})
    c.note.connect(notes.append)
    assert c.finish_first_start(FirstStart(False, IconChoice.INSTALL)) is None
    assert where.desktop_file.is_file()
    c.refresh()  # the note waits until the start's checks are through
    assert notes == ["Desktop icon installed. Options can remove it again."]


@pytest.mark.parametrize("env, installed, offered", [
    ("gnome+image", False, True), ("image", False, False), ("gnome", False, False),
    ("gnome+image", True, False)])
def test_the_icon_is_offered_on_gnome_from_the_appimage(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                                        env: str, installed: bool,
                                                        offered: bool) -> None:
    where = targets(tmp_path)
    image = appimage(tmp_path)
    values = {**(GNOME if "gnome" in env else {}),
              **({"APPIMAGE": str(image)} if "image" in env else {})}
    if installed:
        desktop.install(where, image)
    c = controller(paths, desktop_targets=lambda: where, env=values)
    assert c.offers_icon() is offered


@pytest.mark.parametrize("choice, due", [
    (DesktopChoice.ASK, True), (DesktopChoice.DECLINED, False), (DesktopChoice.INSTALLED, False)])
def test_the_icon_question_comes_back_only_while_open(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                                      choice: DesktopChoice, due: bool) -> None:
    save(paths.config, LauncherSettings(first_run_done=True, desktop=choice))
    where = targets(tmp_path)
    c = controller(paths, desktop_targets=lambda: where,
                   env={**GNOME, "APPIMAGE": str(appimage(tmp_path))})
    assert c.icon_question_due() is due


def test_a_moved_appimage_is_followed_by_the_entry(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    where = targets(tmp_path)
    old, new = appimage(tmp_path, "old.AppImage"), appimage(tmp_path, "new.AppImage")
    desktop.install(where, old)
    c = controller(paths, desktop_targets=lambda: where, env={"APPIMAGE": str(new)})
    c.start_checks()
    assert desktop.installed_exec(where) == str(new)


def test_no_entry_is_written_by_the_refresh(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    where = targets(tmp_path)
    c = controller(paths, desktop_targets=lambda: where,
                   env={"APPIMAGE": str(appimage(tmp_path))})
    c.start_checks()
    assert not where.desktop_file.exists()


def test_the_launcher_check_waits_for_the_opt_in(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    asked: list[int] = []
    c = controller(paths, newer=lambda transport: asked.append(1) or None,
                   latest=lambda *a: "0.2.48")
    c.start_checks()
    assert asked == []
    save(paths.config, LauncherSettings(check_launcher_updates=True))
    c = controller(paths, newer=lambda transport: asked.append(1) or None,
                   latest=lambda *a: "0.2.48")
    c.start_checks()
    assert asked == [1]


def test_a_newer_launcher_is_one_line(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    save(paths.config, LauncherSettings(check_launcher_updates=True, check_game_updates=False))
    notes: list[str] = []
    checked: list[tuple[Any, Any]] = []
    c = controller(paths, newer=lambda transport: "1.1.0")
    c.note.connect(notes.append)
    c.message.connect(lambda title, text: pytest.fail(f"a box for the launcher check: {text}"))
    c.launcher_checked.connect(lambda newer, problem: checked.append((newer, problem)))
    c.start_checks()
    assert checked == [("1.1.0", None)]
    assert notes == ["Launcher v1.1.0 is out: the Launcher Homepage has it."]


def test_a_failed_launcher_check_stays_quiet(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    from project_reforged_linux.launcherupdate import UpdateCheckError

    def refuse(transport: Any) -> str | None:
        raise UpdateCheckError("HTTP 503 from GitHub")

    save(paths.config, LauncherSettings(check_launcher_updates=True, check_game_updates=False))
    notes: list[str] = []
    checked: list[tuple[Any, Any]] = []
    c = controller(paths, newer=refuse)
    c.note.connect(notes.append)
    c.message.connect(lambda title, text: pytest.fail(f"a box for the launcher check: {text}"))
    c.launcher_checked.connect(lambda newer, problem: checked.append((newer, problem)))
    c.start_checks()
    assert checked == [(None, "HTTP 503 from GitHub")]
    assert notes == []


def test_options_says_why_the_icon_cannot_be_installed(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                       tmp_path: Path) -> None:
    where = targets(tmp_path)
    assert controller(paths, desktop_targets=lambda: where, env={}).options_state() \
        .icon_problem == ICON_NEEDS_APPIMAGE
    image = {"APPIMAGE": str(appimage(tmp_path))}
    assert controller(paths, desktop_targets=lambda: where, env=image).options_state() \
        .icon_problem is None


def test_options_carries_the_probed_wines(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    probed: list[int] = []
    c = controller(paths, probe_runtimes=lambda: probed.append(1) or (CHECKED, None))
    s = c.options_state()
    assert (s.system, s.bundled, probed) == (CHECKED, None, [1])


def test_the_launcher_check_logs_that_nothing_is_newer(qapp, paths: AppPaths, caplog) -> None:  # type: ignore[no-untyped-def]
    import logging

    save(paths.config, LauncherSettings(check_launcher_updates=True, check_game_updates=False))
    c = controller(paths, newer=lambda transport: None)
    with caplog.at_level(logging.INFO, logger="project_reforged_linux.ui.controller"):
        c.start_checks()
    assert "the launcher is the newest on GitHub" in caplog.text


@pytest.mark.parametrize("build", [Build.LINUX_APPIMAGE, Build.LINUX_TARBALL])
def test_a_native_start_writes_where_the_game_files_are(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                                        build: Build) -> None:
    # Located after the install, his build would find no game_folder.txt.
    card = tmp_path / "card" / "system" / "apps" / "6r51"
    card.mkdir(parents=True)
    for name in LEVEL_FILES:
        (card / name).write_bytes(b"zmp")
    save(paths.config, LauncherSettings(game_files=str(card), game_build=build))
    data = tmp_path / "xdg-data"
    status = replace(NATIVE_READY, build=build)
    c = controller(paths, native=lambda: GOOD_HOST, resolve=lambda settings: Resolved(None),
                   status=lambda *a, **k: status, env={"XDG_DATA_HOME": str(data)},
                   start_native=lambda *a, **k: FakeSession(ART_DONE), sync=lambda *a: [])
    c.refresh()
    c.run_game()
    written = data / "Shadowkey" / "ShadowkeyPort" / "game_folder.txt"
    assert written.read_text(encoding="utf-8") == f"{card.resolve()}\n"


def test_a_card_that_breaks_in_an_odd_way_still_says_so(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                         tmp_path: Path) -> None:
    import zlib

    def broken(paths: AppPaths, chosen: Path) -> Path:
        raise zlib.error("Error -3 while decompressing data: invalid block type")

    messages: list[tuple[str, str]] = []
    c = controller(paths, apply_files=broken)
    c.message.connect(lambda title, text: messages.append((title, text)))
    c.choose_game_files(tmp_path / "card.zip")
    assert messages and "invalid block type" in messages[0][1]
    assert load(paths.config).settings.game_files is None


def test_the_status_reads_his_log_where_the_session_writes_it(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    seen: list[dict[str, Any]] = []
    env = {"XDG_DATA_HOME": "/srv/data"}
    c = controller(paths, env=env, status=lambda *a, **k: seen.append(k) or READY)
    c.refresh()
    assert seen[0]["env"] is env


def test_update_reforged_asks_his_site_when_the_start_check_is_off(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    # A press of Update Reforged is the player asking; the start-check setting does not apply.
    save(paths.config, LauncherSettings(check_game_updates=False))
    fetched: list[bool] = []
    c = controller(paths, latest=lambda *a: "0.2.48",
                   install=lambda *a, update_game, **k: fetched.append(update_game))
    c.start_checks()
    assert c.game_update is None
    c.install()
    assert fetched == [True], "READY is 0.2.33, his site has 0.2.48"
    assert c.game_update is not None and c.game_update.latest == "0.2.48"


def test_an_update_answer_belongs_to_its_build(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    c = controller(paths, latest=lambda *a: "0.2.48")
    c.start_checks()
    assert c.update_available()
    c._build = Build.LINUX_TARBALL  # the build that runs changed with nothing chosen
    assert not c.update_available(), "the Windows build's answer says nothing about the tarball"


def test_a_native_start_records_which_build_ran(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    c = native(paths, FakeSession(ART_DONE), sync=lambda *a: [])
    c.refresh()
    c.run_game()
    assert (paths.data / "last-native-build.txt").read_text(encoding="utf-8") == "appimage\n"


def test_a_failed_run_record_still_tracks_the_running_game(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    from project_reforged_linux.ui import controller as controller_module

    def read_only(paths: AppPaths, build: Build) -> None:
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(controller_module, "record_native_run", read_only)
    running: list[bool] = []
    c = native(paths, FakeSession(ART_DONE), sync=lambda *a: [])
    c.game_running.connect(running.append)
    c.refresh()
    c.run_game()
    assert running == [True], "the window must learn the game runs, or it never comes back"


def wait_until(done: Callable[[], bool], ms: int = 5000) -> bool:
    """Deliver queued signals until done() holds or the time is up; the last answer."""
    from PySide6.QtCore import QCoreApplication, QDeadlineTimer

    deadline = QDeadlineTimer(ms)
    while not done() and not deadline.hasExpired():
        QCoreApplication.processEvents()
    return done()


def endless_download(stopped_at: list[int]) -> Callable[..., None]:
    """An install that reports a chunk every 5 ms for ten seconds, unless it is stopped."""
    def install(*args: Any, progress: Any, **kwargs: Any) -> None:
        for n in range(2000):
            try:
                progress(Step.DOWNLOAD, n, 2000)
            except BaseException:
                stopped_at.append(n)
                raise
            time.sleep(0.005)

    return install


def test_a_close_during_the_first_refresh_starts_nothing_after_it(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    # The refresh's result lands after shutdown(), and its online checks
    # started threads that outlived exec(); the process aborted on exit.
    entered = threading.Event()

    def slow(*args: Any, **kwargs: Any) -> Status:
        entered.set()
        time.sleep(0.2)
        return READY

    asked: list[str] = []
    save(paths.config, LauncherSettings(check_game_updates=True, check_launcher_updates=True))
    c = controller(paths, synchronous=False, status=slow,
                   latest=lambda *a: asked.append("his site") or READY.game_version,
                   newer=lambda transport: asked.append("GitHub"))
    c.start_checks()
    try:
        assert entered.wait(5)
        c.shutdown()
        wait_until(lambda: False, 300)
        assert c.status == READY  # the result itself still lands
        assert asked == [] and c.jobs() == 0
        c.refresh()
        assert c.jobs() == 0
    finally:
        c.shutdown()


def test_a_stopped_install_ends_at_its_next_report_without_a_box(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    stopped_at: list[int] = []
    reports: list[float | None] = []
    messages: list[tuple[str, str]] = []
    c = controller(paths, synchronous=False, install=endless_download(stopped_at))
    c.message.connect(lambda title, text: messages.append((title, text)))
    c.progress.connect(lambda fraction, text: reports.append(fraction))
    try:
        c.refresh()
        assert wait_until(lambda: c.status is not None and c.jobs() == 0)
        c.install(update_game=True)
        assert wait_until(lambda: len(reports) >= 3)
        c.stop_jobs()
        assert wait_until(lambda: c.jobs() == 0, 2000), "the job ran on past its stop"
        assert stopped_at and messages == []
    finally:
        c.shutdown()


def test_a_failure_landing_during_the_close_opens_no_box(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                         tmp_path: Path) -> None:
    entered, release = threading.Event(), threading.Event()

    def refuse(paths: AppPaths, chosen: Path) -> Path:
        entered.set()  # past the job's report: this one fails, it is not stopped
        release.wait(5)
        raise ValueError("no 6R51 folder")

    messages: list[tuple[str, str]] = []
    c = controller(paths, synchronous=False, apply_files=refuse)
    c.message.connect(lambda title, text: messages.append((title, text)))
    try:
        c.choose_game_files(tmp_path)
        assert entered.wait(5)
        c.stop_jobs()
        release.set()
        assert wait_until(lambda: c.jobs() == 0)
        assert messages == []
    finally:
        release.set()
        c.shutdown()


def test_settings_the_disk_refuses_hold_for_the_run_and_say_so(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    messages: list[tuple[str, str]] = []
    refreshed: list[Status] = []
    c = controller(paths)
    c.message.connect(lambda title, text: messages.append((title, text)))
    c.status_changed.connect(refreshed.append)
    flipped = not c.settings.check_game_updates
    paths.config.chmod(0o500)
    try:
        c.finish_first_start(FirstStart(launcher_updates=True, icon=None))
        c.apply_settings(replace(c.settings, check_game_updates=flipped))
    finally:
        paths.config.chmod(0o700)
    # The player's answers count for this run, and the refresh after Options still ran.
    assert c.settings.first_run_done and c.settings.check_launcher_updates
    assert c.settings.check_game_updates is flipped
    assert [title for title, _ in messages] == [SETTINGS_TITLE, SETTINGS_TITLE]
    assert "until the launcher closes" in messages[0][1]
    assert refreshed == [READY]
    assert load(paths.config).settings == LauncherSettings()


def test_the_windows_start_writes_the_install_s_last_step_again(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                               tmp_path: Path) -> None:
    # A launcher stopped between the Wine setup and that step must still start him set up.
    card = tmp_path / "card" / "system" / "apps" / "6r51"
    card.mkdir(parents=True)
    for name in LEVEL_FILES:
        (card / name).write_bytes(b"zmp")
    save(paths.config, LauncherSettings(game_files=str(card)))
    c = controller(paths, **starting(FakeSession()))
    c.refresh()
    assert c.run_game() is None and c.is_running()
    port = paths.port_dir("alice")
    assert (port / GAME_FOLDER_TXT).read_bytes() == (to_wine_path(card.resolve()) + "\r\n").encode()
    assert (port / SETTINGS_CFG).is_file()


def test_options_takes_the_wine_answers_from_the_last_refresh(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    # A Wine wrapper that waits would hold the window for 10 s per probe.
    probes: list[int] = []
    c = controller(paths, probe_runtimes=lambda: probes.append(1) or (CHECKED, None))
    c.refresh()
    assert probes == [1]
    assert c.options_state().system == CHECKED
    assert probes == [1]


def test_a_stamp_that_cannot_be_written_still_watches_the_game(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    # It ran past the start: nothing polled the game and every button stayed dead.
    running: list[bool] = []

    def full(paths: AppPaths, checked: Checked) -> None:
        raise OSError(28, "No space left on device")

    c = controller(paths, **starting(FakeSession(ART_DONE), mark=full))
    c.game_running.connect(running.append)
    c.refresh()
    assert c.run_game() is None
    assert running == [True]
    for _ in range(3):
        c.poll_game()
    assert not c.is_running() and running == [True, False]


def test_update_asks_his_site_again_after_a_failed_start_check(qapp, paths: AppPaths) -> None:  # type: ignore[no-untyped-def]
    # The failed answer was reused, and the player had to restart to get the update.
    asked: list[int] = []

    def latest(*args: Any) -> str:
        # Raised fresh: an exception kept in a local here would hold its own frame, a Qt cycle.
        asked.append(1)
        if len(asked) == 1:
            raise OSError("offline")
        return "0.2.40"

    fetched: list[bool] = []
    c = controller(paths, latest=latest,
                   install=lambda *a, update_game, **k: fetched.append(update_game))
    c.refresh()
    c.check_game_update()
    c.install()
    assert asked == [1, 1] and fetched == [True]
