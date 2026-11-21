# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import time
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QPushButton

from project_reforged_linux import GAME_NAME
from project_reforged_linux.builds import Build
from project_reforged_linux.installhelp import Family
from project_reforged_linux.nativecheck import NativeCheck
from project_reforged_linux.paths import AppPaths, ensure_dirs, resolve
from project_reforged_linux.prepare import Status, Step
from project_reforged_linux.runtimes import Candidate, Checked, Resolved, Source
from project_reforged_linux.settings import LauncherSettings, load, save
from project_reforged_linux.ui import dialogs
from project_reforged_linux.ui.controller import LauncherController
from project_reforged_linux.ui.widgets import State
from project_reforged_linux.ui.window import CLOSING_TEXT, MainWindow

CHECKED = Checked(Candidate(Source.SYSTEM, Path("/usr/bin/wine"), Path("/usr/bin/wineserver")),
                  (10, 0), "wine-10.0", None)
READY = Status(True, "0.2.33", True, Path("/card/6r51"), None, CHECKED, None, None)


@pytest.fixture
def paths(xdg_home: Path) -> AppPaths:
    p = resolve()
    ensure_dirs(p)
    return p


# His Linux builds cannot run here: these tests are about the Windows path.
OLD_HOST = NativeCheck(glibc=(2, 28), vulkan=True, curl=True, fuse=True)


def window_with(paths: AppPaths, tmp_path: Path, **kwargs: Any) -> MainWindow:
    defaults: dict[str, Any] = {"resolve": lambda settings: Resolved(CHECKED),
                                "status": lambda *a, **k: READY, "synchronous": True,
                                "native": lambda: OLD_HOST, "family": lambda: Family.DEBIAN,
                                # Options asks the host's Wine; never a real wine in a test.
                                "probe_runtimes": lambda: (CHECKED, None),
                                # Update Reforged asks his site; offline, nothing newer.
                                "latest": lambda *a: READY.game_version}
    defaults.update(kwargs)
    controller = LauncherController(paths, **defaults)
    return MainWindow(controller, open_url=lambda url: None,
                      choose_folder=lambda parent: str(tmp_path / "card"))


def button(window: MainWindow, name: str) -> QPushButton:
    found = window.findChild(QPushButton, name)
    assert found is not None
    return found


def test_refresh_fills_the_rows(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window = window_with(paths, tmp_path)
    window.controller.refresh()  # type: ignore[union-attr]
    assert all(row.state is State.OK for row in window.rows.values())
    assert button(window, "runGame").isEnabled() and button(window, "install").isEnabled()


def test_install_shows_progress(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    shown: list[str] = []

    def install(*args: Any, progress: Any, **kwargs: Any) -> None:
        progress(Step.INSTALL, None, None)
        shown.append(window.progress_line.text())
        progress(Step.DOWNLOAD, 2, 5)
        shown.append(window.progress_line.text())

    def offline(*args: Any) -> str:
        raise OSError("network unreachable")

    window = window_with(paths, tmp_path, install=install, latest=offline)
    window.controller.refresh()  # type: ignore[union-attr]
    button(window, "install").click()
    assert shown == ["Installing Project Reforged", "40%"]
    # Idle afterwards, with one line on what happened; his site did not answer.
    assert window.progress_line.text() == ("Everything is in place. The check for a newer "
                                           "build did not get through.")


def manifest_of(version: str) -> Any:
    from datetime import date

    from project_reforged_linux.manifest import Manifest

    url = f"https://project-reforged.danwhelan.ie/update/Shadowkey-{version}-win-x64-update.zip"
    return Manifest(version, date(2026, 11, 17), url, 1, "0" * 64, "", None)


@pytest.mark.parametrize(("latest", "fetched", "said"), [
    ("0.2.46", "0.2.46", "Updated Project Reforged to v0.2.46."),
    ("0.2.33", None, "Project Reforged is up to date (v0.2.33)."),
])
def test_update_reforged_says_what_it_did(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                          latest: str, fetched: str | None, said: str) -> None:
    def install(*args: Any, **kwargs: Any) -> Any:
        return manifest_of(fetched) if fetched else None

    window = checked_window(paths, tmp_path, lambda p, t, b: latest, install=install)
    button(window, "install").click()
    assert window.progress_line.text() == said


def test_a_first_install_says_installed(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    empty = Status(False, None, False, None, None, CHECKED, None, None)
    window = checked_window(paths, tmp_path, lambda p, t, b: "0.2.46", status=lambda *a, **k: empty,
                            install=lambda *a, **k: manifest_of("0.2.46"))
    button(window, "install").click()
    assert window.progress_line.text() == "Installed Project Reforged v0.2.46."


def test_an_unreadable_version_is_fetched_once(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    # An earlier launcher installed the build and nobody started it, so there is no version to
    # compare; the launcher fetches the current build and writes the stamp.
    unknown = Status(True, None, True, Path("/card/6r51"), None, CHECKED, None, None)
    asked: list[bool] = []
    window = checked_window(paths, tmp_path, lambda p, t, b: "0.2.46",
                            status=lambda *a, **k: unknown,
                            install=lambda *a, update_game, **k: asked.append(update_game))
    button(window, "install").click()
    assert asked == [True]


def test_locate_goes_through_the_controller(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    folder = tmp_path / "card" / "system" / "apps" / "6r51"
    window = window_with(paths, tmp_path, apply_files=lambda paths, chosen: folder)
    assert button(window, "locate").isEnabled()
    button(window, "locate").click()
    assert load(paths.config).settings.game_files == str(folder)


def checked_window(paths: AppPaths, tmp_path: Path, latest: Any, **kwargs: Any) -> MainWindow:
    window = window_with(paths, tmp_path, latest=latest, **kwargs)
    window.controller.refresh()  # type: ignore[union-attr]
    window.controller.check_game_update()  # type: ignore[union-attr]
    return window


def test_a_newer_build_turns_the_row_orange(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    # Installed on the left, the new one in brackets.
    window = checked_window(paths, tmp_path, lambda p, t, b: "0.2.46")
    row = window.rows["game"]
    assert row.state is State.UPDATE
    assert row.detail_text() == "Windows build v0.2.33 (v0.2.46)"
    assert "0.2.46" in row.toolTip()


def test_the_same_build_stays_green(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window = checked_window(paths, tmp_path, lambda p, t, b: "0.2.33")
    assert window.rows["game"].state is State.OK
    assert window.rows["game"].detail_text() == "Windows build v0.2.33"


def test_a_failed_check_is_a_tooltip_not_a_box(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    # An update check that fails says so in one line and carries on.
    def offline(p: Any, t: Any, b: Any) -> str:
        raise ConnectionError("his site did not answer")

    messages: list[tuple[Any, ...]] = []
    # A real box would wait modally for a click and hang the run instead of failing it.
    monkeypatch.setattr(dialogs, "message", lambda *a, **k: messages.append(a))
    window = window_with(paths, tmp_path, latest=offline)
    window.controller.refresh()  # type: ignore[union-attr]
    window.controller.check_game_update()  # type: ignore[union-attr]
    assert messages == []
    row = window.rows["game"]
    assert row.state is State.OK and "his site did not answer" in row.toolTip()
    assert button(window, "runGame").isEnabled()


@pytest.mark.parametrize(("latest", "fetched"), [("0.2.46", True), ("0.2.33", False)])
def test_update_reforged_fetches_only_a_newer_build(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                                    latest: str, fetched: bool) -> None:
    asked: list[bool] = []

    def install(*args: Any, update_game: bool, **kwargs: Any) -> None:
        asked.append(update_game)

    window = checked_window(paths, tmp_path, lambda p, t, b: latest, install=install)
    button(window, "install").click()
    assert asked == [fetched]


def test_the_application_names_itself(qapp) -> None:  # type: ignore[no-untyped-def]
    # The WM class comes from the application name, and Wayland matches the
    # desktop file name against the installed entry for the dock icon.
    from PySide6.QtGui import QGuiApplication

    from project_reforged_linux import APP_ID, APP_NAME, __version__
    from project_reforged_linux.ui.window import prepare_application

    prepare_application(qapp)
    assert qapp.applicationName() == APP_NAME and qapp.applicationVersion() == __version__
    assert QGuiApplication.desktopFileName() == APP_ID
    assert not qapp.windowIcon().isNull()


@pytest.fixture
def no_cursor_left(qapp) -> Any:  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QApplication

    yield
    left = 0
    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()
        left += 1
    assert left == 0, f"{left} override cursor(s) left on the stack"


def cursor_shape() -> Any:
    from PySide6.QtWidgets import QApplication

    cursor = QApplication.overrideCursor()
    return None if cursor is None else cursor.shape()


def test_busy_cursor_while_update_reforged_works(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                                 no_cursor_left: None) -> None:
    # A busy cursor while Wine is set up, then back.
    from PySide6.QtCore import Qt

    seen: list[Any] = []
    window = window_with(paths, tmp_path,
                         install=lambda *a, **k: seen.append(cursor_shape()))
    window.controller.refresh()  # type: ignore[union-attr]
    assert cursor_shape() is None
    button(window, "install").click()
    assert seen == [Qt.CursorShape.BusyCursor]
    assert cursor_shape() is None, "back to the plain cursor once the job is done"


def test_a_failed_job_shows_its_box_with_the_plain_cursor(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                          tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch,
                                                          no_cursor_left: None) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("his site did not answer")

    at_box: list[Any] = []
    monkeypatch.setattr(dialogs, "message", lambda *a, **k: at_box.append(cursor_shape()))
    window = window_with(paths, tmp_path, install=broken)
    window.controller.refresh()  # type: ignore[union-attr]
    button(window, "install").click()
    assert at_box == [None]
    assert cursor_shape() is None


def test_the_folder_dialog_gets_the_plain_cursor(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                                 no_cursor_left: None) -> None:
    seen: list[Any] = []
    controller = LauncherController(paths, resolve=lambda settings: Resolved(CHECKED),
                                    status=lambda *a, **k: READY, synchronous=True)
    window = MainWindow(controller, open_url=lambda url: None,
                        choose_folder=lambda parent: seen.append(cursor_shape()) or "")
    window._busy_cursor(True)  # as while a job runs
    button(window, "locate").click()
    assert seen == [None]
    window._busy_cursor(False)


def test_the_links_show_where_they_go(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from project_reforged_linux.ui.window import HOMEPAGE, REFORGED

    window = window_with(paths, tmp_path)
    assert button(window, "homepage").toolTip() == HOMEPAGE
    assert button(window, "reforged").toolTip() == REFORGED
    assert button(window, "install").toolTip() and button(window, "locate").toolTip()


NO_GAME = Status(False, None, False, None, None, CHECKED, None, None)
NO_FILES = Status(True, "0.2.46", True, None, None, CHECKED, None, None)
NO_WINE = Status(True, "0.2.46", True, Path("/card/6r51"), None, None, None, "no Wine")


@pytest.mark.parametrize(("state", "hint"), [
    (NO_GAME, "Install Project Reforged first: Update Reforged."),
    (NO_FILES, "Locate the original game files first."),
    (NO_WINE, "No usable Wine: see the Windows Runtime row.\nInstall it with:\n"
              "sudo apt install wine"),
    (READY, "Start Project Reforged."),
])
def test_run_game_says_what_is_missing(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                       state: Status, hint: str) -> None:
    window = window_with(paths, tmp_path, status=lambda *a, **k: state)
    window.controller.refresh()  # type: ignore[union-attr]
    assert button(window, "runGame").toolTip() == hint
    assert button(window, "runGame").isEnabled() is (state is READY)



GOOD_HOST = NativeCheck(glibc=(2, 41), vulkan=True, curl=True, fuse=True)
NO_VULKAN = NativeCheck(glibc=(2, 41), vulkan=False, curl=True, fuse=True)


def native_status(build: Build, installed: bool = True) -> Status:
    return Status(installed, "0.2.48" if installed else None, False, Path("/card/6r51"), None,
                  None, None, "No usable Wine: no Wine is installed on this system",
                  build if installed else None)


def native_window(paths: AppPaths, tmp_path: Path, check: NativeCheck = GOOD_HOST,
                  installed: bool = True, **kwargs: Any) -> MainWindow:
    window = window_with(paths, tmp_path, native=lambda: check,
                         resolve=lambda settings: Resolved(None, problem="No usable Wine"),
                         status=lambda *a, **k: native_status(a[3], installed),
                         **kwargs)
    window.controller.refresh()  # type: ignore[union-attr]
    return window


def test_the_game_row_names_the_linux_build(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window = native_window(paths, tmp_path)
    assert window.rows["game"].state is State.OK
    assert window.rows["game"].detail_text() == "Linux AppImage v0.2.48"


def test_a_missing_linux_build_says_which(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window = native_window(paths, tmp_path, installed=False)
    assert window.rows["game"].state is State.ERROR
    assert window.rows["game"].detail_text() == "Linux AppImage not installed"
    assert button(window, "install").isEnabled()  # no Wine needed to fetch it


def test_the_runtime_row_steps_back_for_a_linux_build(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                      tmp_path: Path) -> None:
    window = native_window(paths, tmp_path)
    row = window.rows["runtime"]
    assert row.state is State.NOT_NEEDED
    assert row.detail_text() == "not needed for the Linux build"


def test_a_linux_build_runs_without_wine(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window = native_window(paths, tmp_path)
    assert button(window, "runGame").isEnabled()
    assert button(window, "runGame").toolTip() == f"Start {GAME_NAME}."
    assert button(window, "install").isEnabled()


def test_a_chosen_build_that_cannot_run_says_what_to_install(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                             tmp_path: Path) -> None:
    save(paths.config, LauncherSettings(game_build=Build.LINUX_TARBALL))
    window = native_window(paths, tmp_path, check=NO_VULKAN)
    row = window.rows["game"]
    assert row.state is State.OK and row.detail_text().startswith("Windows")
    assert "Linux tarball is chosen but cannot run here" in row.toolTip()
    assert "sudo apt install mesa-vulkan-drivers libvulkan1" in row.toolTip()
    # This fixture has no Wine: what is missing now is the Windows build's runtime.
    run = button(window, "runGame")
    assert not run.isEnabled() and "No usable Wine" in run.toolTip()


def test_no_wine_for_the_windows_build_says_what_to_install(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                            tmp_path: Path) -> None:
    empty = Status(True, "0.2.33", True, Path("/card/6r51"), None, None, None,
                   "No usable Wine: no Wine is installed on this system")
    window = window_with(paths, tmp_path, status=lambda *a, **k: empty,
                         resolve=lambda settings: Resolved(None, problem="No usable Wine"))
    window.controller.refresh()  # type: ignore[union-attr]
    row = window.rows["runtime"]
    assert row.state is State.ERROR
    assert "sudo apt install wine" in row.toolTip()
    assert "sudo apt install wine" in button(window, "runGame").toolTip()


GOOD_HOST = NativeCheck(glibc=(2, 41), vulkan=True, curl=True, fuse=True)


def options_window(paths: AppPaths, tmp_path: Path, answer: LauncherSettings | None,
                   **kwargs: Any) -> tuple[MainWindow, list[int]]:
    asked: list[int] = []
    # A switched build asks his site for its manifest; offline here.
    kwargs.setdefault("latest", lambda paths, transport, build: "0.2.48")
    window = window_with(paths, tmp_path, **kwargs)

    def ask(w: MainWindow) -> LauncherSettings | None:
        asked.append(1)
        return answer

    window._ask_options = ask
    return window, asked


def test_options_opens_with_a_controller(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    window, asked = options_window(paths, tmp_path, None)
    window.controller.refresh()  # type: ignore[union-attr]
    assert button(window, "options").isEnabled()
    button(window, "options").click()
    assert asked == [1]
    assert not (paths.config / "settings.json").exists(), "Cancel saves nothing"


def test_options_waits_while_a_job_runs(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    seen: list[bool] = []
    window, _ = options_window(paths, tmp_path, None,
                               install=lambda *a, **k: seen.append(
                                   button(window, "options").isEnabled()))
    window.controller.refresh()  # type: ignore[union-attr]
    button(window, "install").click()
    assert seen == [False]
    assert button(window, "options").isEnabled()


def test_a_build_switch_says_which_runs_now(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[tuple[Any, ...]] = []
    monkeypatch.setattr(dialogs, "message", lambda *a, **k: shown.append(a))
    # GOOD_HOST: the AppImage runs by default; the player switches to Windows, installed.
    window, _ = options_window(paths, tmp_path, LauncherSettings(game_build=Build.WINDOWS),
                               native=lambda: GOOD_HOST)
    window.controller.refresh()  # type: ignore[union-attr]
    assert window.controller.build is Build.LINUX_APPIMAGE  # type: ignore[union-attr]
    button(window, "options").click()
    assert window.controller.build is Build.WINDOWS  # type: ignore[union-attr]
    assert len(shown) == 1
    text = shown[0][4]
    assert text.startswith("From now on the launcher runs the Windows build.")
    assert "Install it now?" not in text


def test_no_notice_when_the_build_stays(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[tuple[Any, ...]] = []
    monkeypatch.setattr(dialogs, "message", lambda *a, **k: shown.append(a))
    window, _ = options_window(paths, tmp_path, LauncherSettings(sync_saves=False))
    window.controller.refresh()  # type: ignore[union-attr]
    button(window, "options").click()
    assert shown == []
    assert load(paths.config).settings.sync_saves is False


@pytest.mark.parametrize("yes", [True, False])
def test_a_missing_build_is_offered_for_install(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                               monkeypatch: pytest.MonkeyPatch, yes: bool) -> None:
    from PySide6.QtWidgets import QMessageBox

    shown: list[str] = []
    installed: list[Build] = []

    def answer(*a: Any, **k: Any) -> Any:
        shown.append(a[4])
        return QMessageBox.StandardButton.Yes if yes else QMessageBox.StandardButton.No

    monkeypatch.setattr(dialogs, "message", answer)
    missing = Status(False, None, True, Path("/card/6r51"), None, CHECKED, None, None)
    window, _ = options_window(
        paths, tmp_path, LauncherSettings(game_build=Build.LINUX_TARBALL),
        native=lambda: GOOD_HOST,
        status=lambda p, settings, resolved, build, **k: READY if build is Build.LINUX_APPIMAGE
        else missing,
        install=lambda *a, build, **k: installed.append(build))
    window.controller.refresh()  # type: ignore[union-attr]
    button(window, "options").click()
    assert len(shown) == 1 and shown[0].endswith(
        "The Linux tarball is not installed yet. Install it now?")
    assert installed == ([Build.LINUX_TARBALL] if yes else [])


def test_the_switch_notice_names_where_the_saves_are(paths: AppPaths) -> None:
    from project_reforged_linux.ui.window import switch_notice

    native = switch_notice(Build.LINUX_TARBALL, True, paths, {"XDG_DATA_HOME": "/srv/d"})
    assert "runs the Linux tarball. Its saves are in /srv/d/Shadowkey." in native
    assert "takes the other build's newer saves" in native
    windows = switch_notice(Build.WINDOWS, False, paths, {})
    assert "Its saves are in the launcher's Wine prefix" in windows
    assert '"Sync native and Windows saves"' in windows


def test_about_opens_its_dialog(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    # Ids, not the window: a window holding a list that holds it is a cycle PySide crashed on.
    shown: list[int] = []
    window = window_with(paths, tmp_path)
    window._show_about = lambda w: shown.append(id(w))
    assert button(window, "about").isEnabled()
    button(window, "about").click()
    assert shown == [id(window)]


def test_the_first_start_comes_once(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from project_reforged_linux.ui.firststart import FirstStart

    asked: list[bool] = []

    def ask(w: MainWindow, offer_icon: bool) -> FirstStart:
        asked.append(offer_icon)
        return FirstStart(True, None)

    window = window_with(paths, tmp_path)
    window._ask_first_start = ask
    window.greet()
    assert asked == [False]  # not GNOME from an AppImage here
    assert load(paths.config).settings.first_run_done
    window.greet()
    assert asked == [False]


def test_the_first_start_goes_nowhere_online(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from project_reforged_linux.ui.firststart import FirstStart

    calls: list[str] = []
    window = window_with(paths, tmp_path, latest=lambda *a: calls.append("his site") or "0.2.48",
                         newer=lambda t: calls.append("github") or None)
    window._ask_first_start = lambda w, offer: FirstStart(True, None)
    window.greet()
    assert calls == [] and window.controller.jobs() == 0  # type: ignore[union-attr]


def test_a_later_start_asks_about_the_icon_only_when_due(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    from project_reforged_linux.ui.controller import LauncherController
    from project_reforged_linux.ui.firststart import IconChoice

    save(paths.config, LauncherSettings(first_run_done=True))
    asked: list[int] = []
    window = window_with(paths, tmp_path)
    window._ask_icon = lambda w: asked.append(1) or IconChoice.NEVER
    monkeypatch.setattr(LauncherController, "icon_question_due", lambda self: False)
    window.greet()
    assert asked == []
    monkeypatch.setattr(LauncherController, "icon_question_due", lambda self: True)
    window.greet()
    assert asked == [1]
    assert load(paths.config).settings.desktop.value == "declined"


def test_a_failed_icon_install_is_said(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    from project_reforged_linux.ui.firststart import FirstStart, IconChoice

    shown: list[tuple[Any, ...]] = []
    monkeypatch.setattr(dialogs, "message", lambda *a, **k: shown.append(a))
    window = window_with(paths, tmp_path)  # no $APPIMAGE: the install must refuse
    window._ask_first_start = lambda w, offer: FirstStart(False, IconChoice.INSTALL)
    window.greet()
    assert len(shown) == 1 and "AppImage" in shown[0][4]


@pytest.mark.parametrize("newer, problem, tip", [
    ("1.1.0", None, "Version 1.1.0 is out."),
    (None, None, "is the newest."),
    (None, "HTTP 503 from GitHub", "did not get through: HTTP 503 from GitHub")])
def test_the_version_line_answers_for_the_launcher(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                                   newer: str | None, problem: str | None,
                                                   tip: str) -> None:
    window = window_with(paths, tmp_path)
    window.controller.launcher_checked.emit(newer, problem)  # type: ignore[union-attr]
    assert tip in window.version.toolTip()


@pytest.mark.modal
@pytest.mark.parametrize("which", ["options", "about", "first start"])
def test_a_closed_dialog_does_not_stay_behind(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                              monkeypatch: pytest.MonkeyPatch, which: str) -> None:
    # A dialog parented to the window must not outlive its answer.
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication, QDialog

    from project_reforged_linux.ui import window as window_module

    def accept_at_once(dialog: QDialog) -> int:
        dialog.accept()
        return int(QDialog.DialogCode.Accepted.value)

    monkeypatch.setattr(QDialog, "exec", accept_at_once)
    window = window_with(paths, tmp_path)
    window.controller.refresh()  # type: ignore[union-attr]
    if which == "options":
        assert window_module._options_dialog(window) is not None
    elif which == "about":
        window_module._about_dialog(window)
    else:
        window_module._first_start_dialog(window, False)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()
    assert window.findChildren(QDialog) == []


def test_yes_to_install_waits_for_a_running_job(qapp, paths: AppPaths, tmp_path: Path,  # type: ignore[no-untyped-def]
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    # The Yes can come while his manifest is still asked for; it must not be lost.
    installed: list[Build] = []
    window = window_with(paths, tmp_path, install=lambda *a, build, **k: installed.append(build))
    c = window.controller
    c.refresh()  # type: ignore[union-attr]
    c._jobs.append(object())  # type: ignore[union-attr]  # a job still out
    c.install_when_idle()  # type: ignore[union-attr]
    assert installed == []
    c._jobs.clear()  # type: ignore[union-attr]
    c._went_idle()  # type: ignore[union-attr]
    assert installed == [Build.WINDOWS]


def test_locate_waits_while_a_job_runs(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    # With a zip, Locate replaces the card; not under a job or a running game.
    seen: list[bool] = []
    window = window_with(paths, tmp_path,
                         install=lambda *a, **k: seen.append(button(window, "locate").isEnabled()))
    window.controller.refresh()  # type: ignore[union-attr]
    button(window, "install").click()
    assert seen == [False] and button(window, "locate").isEnabled()


def test_a_status_during_a_job_keeps_the_buttons_busy(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                      tmp_path: Path) -> None:
    window = window_with(paths, tmp_path)
    c = window.controller
    c.refresh()  # type: ignore[union-attr]
    c._jobs.append(object())  # type: ignore[union-attr]  # a job still out
    window.show_status(READY)
    assert not button(window, "install").isEnabled() and not button(window, "locate").isEnabled()
    c._jobs.clear()  # type: ignore[union-attr]


def test_server_text_in_a_tooltip_is_escaped(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    def bad(*args: Any) -> str:
        raise ValueError("<b>repair</b> at <a href='https://phish.example/'>here</a>")

    window = checked_window(paths, tmp_path, bad)
    tip = window.rows["game"].toolTip()
    assert "&lt;a href" in tip and "<a href" not in tip


def test_closing_during_a_job_neither_waits_nor_stays_open(qapp, paths: AppPaths,  # type: ignore[no-untyped-def]
                                                          tmp_path: Path) -> None:
    # close() used to come back after the job, 5.7 s of a window that paints nothing.
    from PySide6.QtCore import QCoreApplication, QDeadlineTimer

    def pump_until(done: Any, ms: int = 5000) -> bool:
        deadline = QDeadlineTimer(ms)
        while not done() and not deadline.hasExpired():
            QCoreApplication.processEvents()
        return bool(done())

    stopped_at: list[int] = []

    def install(*args: Any, progress: Any, **kwargs: Any) -> None:
        for n in range(2000):
            try:
                progress(Step.DOWNLOAD, n, 2000)
            except BaseException:
                stopped_at.append(n)
                raise
            time.sleep(0.005)

    window = window_with(paths, tmp_path, install=install, synchronous=False)
    c = window.controller
    assert c is not None
    try:
        window.show()
        c.refresh()
        assert pump_until(lambda: c.status is not None and c.jobs() == 0)
        c.install(update_game=True)
        assert pump_until(lambda: window.progress_line.text().endswith("%"))
        started = time.monotonic()
        window.close()
        assert time.monotonic() - started < 0.5
        assert window.isVisible() and window.progress_line.text() == CLOSING_TEXT
        assert pump_until(lambda: not window.isVisible(), 3000)
        assert stopped_at and c.jobs() == 0
    finally:
        c.shutdown()


def test_a_quote_in_server_text_reads_as_a_quote(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    # Escaped text without a tag was shown as plain text: &#x27; on the screen.
    from PySide6.QtGui import Qt as QtGui

    def bad(*args: Any) -> str:
        raise ValueError("unexpected download name: 'x.exe' & more")

    window = checked_window(paths, tmp_path, bad)
    tip = window.rows["game"].toolTip()
    assert QtGui.mightBeRichText(tip)
    assert "&#x27;x.exe&#x27; &amp; more" in tip


def test_options_waits_for_a_first_status(qapp, paths: AppPaths, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    # After a failed refresh it would probe the host's Wine on the window's thread.
    def broken(*args: Any, **kwargs: Any) -> Status:
        raise OSError("status failed")

    probes: list[int] = []
    window = window_with(paths, tmp_path, status=broken,
                         probe_runtimes=lambda: probes.append(1) or (CHECKED, None))
    window.controller.refresh()  # type: ignore[union-attr]
    assert not button(window, "options").isEnabled()
    assert probes == []
