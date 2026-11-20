# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from project_reforged_linux.builds import Build
from project_reforged_linux.nativecheck import NativeCheck
from project_reforged_linux.runtimes import Candidate, Checked, Mode, Resolved, Source
from project_reforged_linux.settings import DesktopChoice, LauncherSettings
from project_reforged_linux.ui import theme
from project_reforged_linux.ui.options import (
    BUILD_LABELS,
    OptionsDialog,
    OptionsState,
    runtime_label,
)

GOOD = NativeCheck((2, 41), True, True, True)
NO_FUSE = NativeCheck((2, 41), True, True, False)
OLD = NativeCheck((2, 28), True, True, True)


def wine(source: Source, root: str, version: tuple[int, int] | None, text: str,
         problem: str | None = None) -> Checked:
    base = Path(root)
    return Checked(Candidate(source, base / "bin" / "wine", base / "bin" / "wineserver"),
                   version, text, problem)


SYSTEM = wine(Source.SYSTEM, "/usr", (10, 0), "wine-10.0 (Debian 10.0~repack-6)")
WINEHQ = wine(Source.WINEHQ, "/opt/wine-staging", (10, 20), "wine-10.20 (Staging)")
LUTRIS = wine(Source.LUTRIS, "/home/a/.local/share/lutris/runners/wine/wine-ge-8-26", (8, 26),
              "wine-8.26", "Wine 8.26 is older than 10.0, the oldest this launcher supports")
BROKEN = wine(Source.BOTTLES, "/home/a/.local/share/bottles/runners/soda-9.0-1", None, "",
              "/home/a/.local/share/bottles/runners/soda-9.0-1/bin/wine is not a 64-bit Wine")


def state(settings: LauncherSettings | None = None, native: NativeCheck = GOOD,
          build: Build = Build.LINUX_APPIMAGE, **kwargs: object) -> OptionsState:
    values: dict[str, object] = {"game_version": "0.2.48", "game_installed": True,
                                 "resolved": Resolved(SYSTEM), "icon_installed": False,
                                 "system": SYSTEM}
    values.update(kwargs)
    return OptionsState(settings or LauncherSettings(), native, build, **values)  # type: ignore[arg-type]


def windows_state(**kwargs: object) -> OptionsState:
    """The Windows build chosen, so the runtime box is live and only a reason greys a radio."""
    return state(LauncherSettings(game_build=Build.WINDOWS), build=Build.WINDOWS, **kwargs)


class Scanner:
    """Search again's callback; answers at once, or keeps the answer for later."""

    def __init__(self, found: list[Checked], *, hold: bool = False) -> None:
        self.found, self.hold = found, hold
        self.calls = 0
        self.pending: Callable[[list[Checked]], None] | None = None

    def __call__(self, done: Callable[[list[Checked]], None]) -> None:
        self.calls += 1
        if self.hold:
            self.pending = done
        else:
            done(self.found)


class Icons:
    def __init__(self, problem: str | None = None) -> None:
        self.problem = problem
        self.calls: list[bool] = []

    def __call__(self, install: bool) -> str | None:
        self.calls.append(install)
        return self.problem


def dialog(s: OptionsState | None = None, scan: Scanner | None = None,
           icons: Icons | None = None) -> OptionsDialog:
    d = OptionsDialog(theme.load_fonts(), s or state(), scan=scan or Scanner([SYSTEM]),
                      set_icon=icons or Icons())
    d.show()
    QApplication.processEvents()
    return d


def test_the_builds_come_tarball_appimage_windows(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog()
    assert [r.text() for r in d.build_buttons.values()] == list(BUILD_LABELS.values())
    assert list(BUILD_LABELS) == [Build.LINUX_TARBALL, Build.LINUX_APPIMAGE, Build.WINDOWS]


def test_with_nothing_chosen_the_build_that_runs_is_checked(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog(state(build=Build.LINUX_APPIMAGE))
    assert d.chosen_build() is Build.LINUX_APPIMAGE
    assert d.build_hint.text() == "Runs now: the Linux AppImage, v0.2.48."


def test_builds_this_system_cannot_run_are_greyed_with_the_reason(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog(state(native=OLD, build=Build.WINDOWS))
    assert not d.build_buttons[Build.LINUX_TARBALL].isEnabled()
    assert not d.build_buttons[Build.LINUX_APPIMAGE].isEnabled()
    assert d.build_buttons[Build.WINDOWS].isEnabled()
    # One line, not the same reason twice.
    assert d.build_hint.text() == "The Linux builds need glibc 2.35; this system has 2.28."
    assert d.build_buttons[Build.LINUX_TARBALL].toolTip() == d.build_hint.text()


def test_without_fuse_only_the_appimage_is_greyed(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog(state(native=NO_FUSE, build=Build.LINUX_TARBALL))
    assert d.build_buttons[Build.LINUX_TARBALL].isEnabled()
    assert not d.build_buttons[Build.LINUX_APPIMAGE].isEnabled()
    assert "FUSE" in d.build_hint.text()


def test_a_greyed_build_cannot_be_chosen(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog(state(native=OLD, build=Build.WINDOWS))
    d.build_buttons[Build.LINUX_APPIMAGE].click()
    assert d.chosen_build() is Build.WINDOWS


def test_the_runtime_box_is_off_for_each_native_build(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog()
    for build in (Build.LINUX_TARBALL, Build.LINUX_APPIMAGE):
        d.build_buttons[build].click()
        assert not d.runtime_box.isEnabled()
        assert d._fade.isEnabled() and d._fade.opacity() == theme.DISABLED_OPACITY
    d.build_buttons[Build.WINDOWS].click()
    assert d.runtime_box.isEnabled() and not d._fade.isEnabled()


def test_untouched_choices_return_the_saved_settings(qapp) -> None:  # type: ignore[no-untyped-def]
    saved = LauncherSettings(game_files="/card/6r51", check_launcher_updates=True)
    d = dialog(state(saved))
    d.ok_button.click()
    assert d.chosen == saved


def test_ok_returns_exactly_the_changes(qapp) -> None:  # type: ignore[no-untyped-def]
    saved = LauncherSettings(game_files="/card/6r51")
    d = dialog(state(saved))
    d.build_buttons[Build.WINDOWS].click()
    d.sync_box.setChecked(False)
    d.launcher_updates.setChecked(True)
    d.game_updates.setChecked(False)
    d.mode_buttons[Mode.SYSTEM].click()
    d.ok_button.click()
    assert d.chosen == replace(saved, game_build=Build.WINDOWS, sync_saves=False,
                               check_launcher_updates=True, check_game_updates=False,
                               runtime_mode=Mode.SYSTEM)


def test_going_back_to_the_build_that_runs_keeps_nothing_chosen(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog(state(build=Build.LINUX_APPIMAGE))
    d.build_buttons[Build.WINDOWS].click()
    d.build_buttons[Build.LINUX_APPIMAGE].click()
    d.ok_button.click()
    assert d.chosen is not None and d.chosen.game_build is None


def test_cancel_returns_nothing(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog()
    d.build_buttons[Build.WINDOWS].click()
    d.findChild(type(d.ok_button), "cancel").click()
    assert d.chosen is None


def test_picking_another_wine_searches_once(qapp) -> None:  # type: ignore[no-untyped-def]
    scanner = Scanner([WINEHQ, SYSTEM, LUTRIS, BROKEN])
    d = dialog(state(LauncherSettings(game_build=Build.WINDOWS), build=Build.WINDOWS),
               scan=scanner)
    assert scanner.calls == 0 and d.found.count() == 0
    d.mode_buttons[Mode.CHOSEN].click()
    assert scanner.calls == 1
    # The system's Wine has its own radio; the list holds only the others.
    assert [d.found.item(i).text() for i in range(d.found.count())] == [
        "Wine 10.20 (Staging) - WineHQ", "wine-ge-8-26 - Lutris - too old, needs 10.0",
        "soda-9.0-1 - Bottles - not usable"]
    assert d.runtime_hint.text() == ("Found 3, 1 usable. Pick one from the list; without a pick, "
                                     "Automatic stays.")
    d.mode_buttons[Mode.AUTO].click()
    d.mode_buttons[Mode.CHOSEN].click()
    assert scanner.calls == 1, "picked again: the list is there already"
    d.search_button.click()
    assert scanner.calls == 2 and d.search_button.isEnabled()


def test_unusable_runtimes_cannot_be_picked(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog(state(LauncherSettings(game_build=Build.WINDOWS), build=Build.WINDOWS),
               scan=Scanner([LUTRIS]))
    d.search_button.click()
    item = d.found.item(0)
    assert not item.flags() & Qt.ItemFlag.ItemIsSelectable
    assert LUTRIS.problem in item.toolTip()


def test_picking_a_runtime_chooses_it(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog(state(LauncherSettings(game_build=Build.WINDOWS), build=Build.WINDOWS),
               scan=Scanner([WINEHQ, SYSTEM]))
    d.search_button.click()
    d.found.setCurrentRow(0)
    assert d.mode_buttons[Mode.CHOSEN].isChecked()
    d.ok_button.click()
    assert d.chosen is not None
    assert (d.chosen.runtime_mode, d.chosen.runtime_wine) == (
        Mode.CHOSEN, "/opt/wine-staging/bin/wine")


def test_a_saved_runtime_stays_picked_after_a_search(qapp) -> None:  # type: ignore[no-untyped-def]
    staging = "/opt/wine-staging/bin/wine"
    saved = LauncherSettings(game_build=Build.WINDOWS, runtime_mode=Mode.CHOSEN,
                             runtime_wine=staging)
    d = dialog(state(saved, build=Build.WINDOWS), scan=Scanner([WINEHQ, SYSTEM]))
    assert d.found.currentItem().data(Qt.ItemDataRole.UserRole) == staging
    d.search_button.click()
    assert d.found.currentItem().data(Qt.ItemDataRole.UserRole) == staging
    d.ok_button.click()
    assert d.chosen == saved


def test_a_saved_pick_of_the_system_wine_shows_as_system(qapp) -> None:  # type: ignore[no-untyped-def]
    # Picked from the list, /usr/bin/wine ran as "chosen".
    saved = LauncherSettings(game_build=Build.WINDOWS, runtime_mode=Mode.CHOSEN,
                             runtime_wine="/usr/bin/wine")
    d = dialog(state(saved, build=Build.WINDOWS))
    assert d.mode_buttons[Mode.SYSTEM].isChecked() and d.found.count() == 0
    d.ok_button.click()
    assert d.chosen is not None
    assert (d.chosen.runtime_mode, d.chosen.runtime_wine) == (Mode.SYSTEM, None)


def test_the_radios_name_what_they_run(qapp) -> None:  # type: ignore[no-untyped-def]
    bundled = wine(Source.BUNDLED, "/srv/launcher-appdir/opt/wine", (10, 20), "wine-10.20")
    d = dialog(windows_state(system=SYSTEM, bundled=bundled))
    assert d.runtime_box.isEnabled()
    assert d.mode_buttons[Mode.SYSTEM].text() == "System Wine 10.0"
    assert d.mode_buttons[Mode.BUNDLED].text() == "Bundled runtime 10.20"
    assert d.mode_buttons[Mode.SYSTEM].isEnabled() and d.mode_buttons[Mode.BUNDLED].isEnabled()


@pytest.mark.parametrize("system, reason", [
    (None, "No Wine is installed on this system."),
    (wine(Source.SYSTEM, "/usr", (6, 0), "wine-6.0.3",
          "Wine 6.0 is older than 10.0, the oldest this launcher supports"),
     "Wine 6.0 is older than 10.0, the oldest this launcher supports")])
def test_a_system_wine_that_cannot_run_is_greyed(qapp, system: Checked | None,  # type: ignore[no-untyped-def]
                                                 reason: str) -> None:
    d = dialog(windows_state(system=system))
    assert d.runtime_box.isEnabled()
    radio = d.mode_buttons[Mode.SYSTEM]
    assert not radio.isEnabled() and radio.toolTip() == reason
    assert radio.text() == "System Wine"


def test_no_bundled_runtime_outside_the_appimage(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog(windows_state(bundled=None))
    assert d.runtime_box.isEnabled()
    radio = d.mode_buttons[Mode.BUNDLED]
    assert not radio.isEnabled()
    assert radio.toolTip() == "Only the launcher's AppImage brings a bundled runtime."


def test_the_list_never_repeats_the_system_or_bundled_wine(qapp) -> None:  # type: ignore[no-untyped-def]
    bundled = wine(Source.BUNDLED, "/srv/launcher-appdir/opt/wine", (10, 20), "wine-10.20")
    # A WineHQ tree that is the system's own under another path, seen through a link.
    same_as_system = wine(Source.WINEHQ, "/usr", (10, 0), "wine-10.0")
    d = dialog(state(LauncherSettings(game_build=Build.WINDOWS), build=Build.WINDOWS,
                     bundled=bundled), scan=Scanner([SYSTEM, bundled, same_as_system, WINEHQ]))
    d.mode_buttons[Mode.CHOSEN].click()
    assert [d.found.item(i).text() for i in range(d.found.count())] == [
        "Wine 10.20 (Staging) - WineHQ"]


def test_another_wine_without_a_pick_keeps_automatic(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog(state(LauncherSettings(game_build=Build.WINDOWS), build=Build.WINDOWS),
               scan=Scanner([]))
    d.mode_buttons[Mode.CHOSEN].click()
    assert d.runtime_hint.text() == "No other Wine builds found on this system."
    d.ok_button.click()
    assert d.chosen is not None and d.chosen.runtime_mode is Mode.AUTO


def test_install_icon_is_greyed_without_the_appimage(qapp) -> None:  # type: ignore[no-untyped-def]
    reason = "Start the launcher from its AppImage to install it."
    d = dialog(state(icon_installed=False, icon_problem=reason))
    assert not d.icon_button.isEnabled() and d.icon_button.toolTip() == reason
    removable = dialog(state(icon_installed=True, icon_problem=reason))
    assert removable.icon_button.isEnabled() and removable.icon_button.text() == "Remove"


def test_the_search_ending_after_the_dialog_closed_is_ignored(qapp) -> None:  # type: ignore[no-untyped-def]
    scanner = Scanner([SYSTEM], hold=True)
    d = dialog(state(LauncherSettings(game_build=Build.WINDOWS), build=Build.WINDOWS),
               scan=scanner)
    d.search_button.click()
    assert not d.search_button.isEnabled()
    d.reject()
    assert scanner.pending is not None
    scanner.pending([SYSTEM])
    assert d.found.count() == 0
    scanner.pending = None  # the dialog holds the scanner: its kept method would close a cycle


def test_the_icon_button_acts_at_once_and_flips(qapp) -> None:  # type: ignore[no-untyped-def]
    icons = Icons()
    d = dialog(state(icon_installed=False), icons=icons)
    assert d.icon_button.text() == "Install"
    d.icon_button.click()
    assert icons.calls == [True] and d.icon_button.text() == "Remove"
    d.icon_button.click()
    assert icons.calls == [True, False] and d.icon_button.text() == "Install"
    d.ok_button.click()
    assert d.chosen is not None and d.chosen.desktop is DesktopChoice.DECLINED


def test_a_failed_icon_change_says_why_and_does_not_flip(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog(state(icon_installed=False), icons=Icons("Start the launcher from its AppImage."))
    told: list[str] = []
    d.warn = told.append
    d.icon_button.click()
    assert told == ["Start the launcher from its AppImage."]
    assert d.icon_button.text() == "Install"
    d.ok_button.click()
    assert d.chosen is not None and d.chosen.desktop is DesktopChoice.ASK


@pytest.mark.parametrize("checked, text", [
    (SYSTEM, "Wine 10.0 (Debian 10.0~repack-6) - system"),
    (LUTRIS, "wine-ge-8-26 - Lutris - too old, needs 10.0"),
    (BROKEN, "soda-9.0-1 - Bottles - not usable"),
    (wine(Source.CHOSEN, "/srv/w", None, "", "/srv/w/bin/wine is missing or cannot be run"),
     "/srv/w/bin/wine - chosen - not usable"),
])
def test_runtime_labels(checked: Checked, text: str) -> None:
    assert runtime_label(checked) == text


def runtime_hint(resolved: Resolved) -> str:
    d = dialog(state(resolved=resolved))
    text = d.runtime_hint.text()
    d.close()  # several dialogs in one test: none may stay shown as garbage
    return text


def test_the_runtime_hint_says_what_runs(qapp) -> None:  # type: ignore[no-untyped-def]
    assert runtime_hint(Resolved(SYSTEM)) == "Runs now: Wine 10.0, the system's."
    fallback = Resolved(WINEHQ, note="System Wine not used (too old); the bundled runtime runs.")
    assert runtime_hint(fallback) == fallback.note
    broken = Resolved(None, problem="No usable Wine: none installed.")
    assert runtime_hint(broken) == broken.problem


def test_a_build_not_installed_says_so(qapp) -> None:  # type: ignore[no-untyped-def]
    d = dialog(state(game_installed=False, game_version=None))
    assert d.build_hint.text() == "Runs now: the Linux AppImage, not installed yet."


def test_on_an_old_system_the_build_that_runs_is_checked(qapp) -> None:  # type: ignore[no-untyped-def]
    saved = LauncherSettings(game_build=Build.LINUX_APPIMAGE)
    d = dialog(state(saved, native=OLD, build=Build.WINDOWS))
    assert d.build_buttons[Build.WINDOWS].isChecked()
    assert not d.build_buttons[Build.LINUX_APPIMAGE].isEnabled()
    assert d.runtime_box.isEnabled()
    d.ok_button.click()
    assert d.chosen == saved, "untouched: the choice stays for a system that runs it"
