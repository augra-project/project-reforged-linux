# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""What the window shows and does, kept apart from how it looks."""

import logging
import os
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from project_reforged_linux import GAME_NAME, desktop
from project_reforged_linux.builds import Build, effective_build
from project_reforged_linux.gamelog import Art, progress_text
from project_reforged_linux.installhelp import Family, family, hint
from project_reforged_linux.launcherupdate import UpdateCheckError, newer_launcher
from project_reforged_linux.logsetup import home_as_tilde
from project_reforged_linux.manifest import Manifest, ManifestError, version_key
from project_reforged_linux.nativecheck import NativeCheck, check_native
from project_reforged_linux.nativerun import NativeSession
from project_reforged_linux.net import HostRefused, Transport, for_launcher
from project_reforged_linux.paths import AppPaths, native_data_dir
from project_reforged_linux.prepare import (
    Status,
    apply_game_files,
    install_requirements,
    latest_game_version,
    record_native_run,
    status,
    write_native_game_folder,
    write_windows_settings,
)
from project_reforged_linux.runner import GameSession
from project_reforged_linux.runtimes import (
    Checked,
    Resolved,
    bundled_candidate,
    check,
    mark_prefix,
    prefix_downgrade,
    resolve_runtime,
    scan,
    system_candidate,
)
from project_reforged_linux.savesync import sync_saves
from project_reforged_linux.settings import DesktopChoice, LauncherSettings, load, save
from project_reforged_linux.ui.firststart import FirstStart, IconChoice
from project_reforged_linux.ui.options import OptionsState
from project_reforged_linux.wineprefix import PrefixError, find_wine_user

__all__ = ["GameUpdate", "Job", "JobStopped", "LauncherController", "Report"]

logger = logging.getLogger(__name__)

POLL_MS = 500
RUN_TITLE = "Run game"
FILES_TITLE = "Original game files"
ICON_NEEDS_APPIMAGE = ("The desktop icon starts the launcher's AppImage. Start the launcher from "
                       "its AppImage to install it.")
INSTALL_TITLE = "Update Reforged"
SETTINGS_TITLE = "Launcher settings"

# A fraction of a known end, or None while the step's end is unknown, and the step's words.
Report = Callable[[float | None, str], None]


class JobStopped(BaseException):
    """A stopped job's next report raises it; no step's own except clause takes it for a failure."""


class Job(QThread):
    """One slow call off the window's thread; reports progress, a result or an error.

    Its signals reach named controller slots: Qt queues those onto the window's thread, while a
    bare lambda would be a direct call by Qt's own rule.
    """

    progress = Signal(object, str)
    succeeded = Signal(object, object)  # job, result
    failed = Signal(object, str)  # job, message
    over = Signal(object)  # job; after finished, on the thread the job object lives on

    def __init__(self, work: Callable[[Report], Any], done: Callable[[Any], None],
                 title: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._work = work
        self.done = done
        self.title = title
        self._stop = threading.Event()
        self.finished.connect(self._over)

    def stop(self) -> None:
        """Ask the work to end at its next report; a download keeps its part for the resume."""
        self._stop.set()

    def _report(self, fraction: float | None, text: str) -> None:
        if self._stop.is_set():
            raise JobStopped
        self.progress.emit(fraction, text)

    @Slot()
    def _over(self) -> None:
        self.over.emit(self)

    def run(self) -> None:
        try:
            result = self._work(self._report)
        except JobStopped:
            logger.info("job %r stopped", self.title)
            return
        # A worker shell: whatever the step raised becomes a message for the player.
        except Exception as error:  # noqa: BLE001
            logger.exception("job %r failed", self.title)
            self.failed.emit(self, str(error) or type(error).__name__)
            return
        self.succeeded.emit(self, result)


@dataclass(frozen=True, slots=True)
class GameUpdate:
    """What the check at start found: his current version, or why there is none."""

    latest: str | None
    problem: str | None = None
    build: Build | None = None  # the build whose manifest gave the answer


def _resolve(settings: LauncherSettings) -> Resolved:
    chosen = Path(settings.runtime_wine) if settings.runtime_wine else None
    return resolve_runtime(settings.runtime_mode, chosen, os.environ)


def _probe_runtimes() -> tuple[Checked | None, Checked | None]:
    """The system's and the bundled Wine as Options names them; None where there is none."""
    system, bundled = system_candidate(), bundled_candidate()
    return (None if system is None else check(system, os.environ),
            None if bundled is None else check(bundled, os.environ))


def _scan() -> list[Checked]:
    return scan(os.environ, home=Path.home())


def _fraction(done: int | None, total: int | None) -> float | None:
    if done is None or not total or total < 0:
        return None
    return min(1.0, max(0.0, done / total))


def _log_status(s: Status) -> None:
    game = (f"{(s.build or Build.WINDOWS).value} v{s.game_version or '?'}"
            if s.game_installed else "not installed")
    files = home_as_tilde(s.game_files) if s.game_files else (s.game_files_problem or "not chosen")
    runtime = (f"{s.runtime.candidate.source.value} {s.runtime.version_text}" if s.runtime
               else s.runtime_problem or "none")
    logger.info("status: game %s; prefix %s; game files %s; runtime %s%s", game,
                "ready" if s.prefix_ready else "missing", home_as_tilde(files), runtime,
                f"; {s.runtime_note}" if s.runtime_note else "")


def _fetch_wanted(before: Status | None, answer: GameUpdate | None) -> bool:
    """Fetch his build when his site names a newer one, or ours has no readable version."""
    latest = answer.latest if answer else None
    if before is None or not before.game_installed or latest is None:
        return False
    installed = before.game_version
    return installed is None or version_key(latest) > version_key(installed)


def _install_note(installed: Any, before: Status | None, latest: str | None) -> str:
    """What Update Reforged did, for the progress line: a blip alone said nothing."""
    if isinstance(installed, Manifest):
        if before is not None and before.game_installed:
            return f"Updated {GAME_NAME} to v{installed.version}."
        return f"Installed {GAME_NAME} v{installed.version}."
    if latest is None:
        return "Everything is in place. The check for a newer build did not get through."
    return f"{GAME_NAME} is up to date (v{latest})."


class LauncherController(QObject):
    status_changed = Signal(object)  # Status
    progress = Signal(object, str)  # fraction or None (busy), the step's words
    note = Signal(str)  # a line that stands still: the art is ready, or what went wrong
    message = Signal(str, str)  # title, text
    busy_changed = Signal(bool)
    game_running = Signal(bool)
    launcher_checked = Signal(object, object)  # newer version or None, problem or None

    def __init__(self, paths: AppPaths, *,
                 resolve: Callable[[LauncherSettings], Resolved] = _resolve,
                 status: Callable[..., Status] = status,
                 apply_files: Callable[[AppPaths, Path], Path] = apply_game_files,
                 install: Callable[..., Any] = install_requirements,
                 latest: Callable[[AppPaths, Transport, Build], str] = latest_game_version,
                 start_game: Callable[..., Any] = GameSession.start,
                 start_native: Callable[..., Any] = NativeSession.start,
                 sync: Callable[[Path, Path, Path], list[str]] = sync_saves,
                 wine_user: Callable[[AppPaths], str] = lambda p: find_wine_user(p.prefix),
                 mark: Callable[..., None] = mark_prefix,
                 downgrade: Callable[..., str | None] = prefix_downgrade,
                 native: Callable[[], NativeCheck] = check_native,
                 family: Callable[[], Family] = family,
                 find_runtimes: Callable[[], list[Checked]] = _scan,
                 probe_runtimes: Callable[[], tuple[Checked | None, Checked | None]] = (
                     _probe_runtimes),
                 newer: Callable[[Transport], str | None] = newer_launcher,
                 desktop_targets: Callable[[], desktop.DesktopTargets] = desktop.targets,
                 env: Mapping[str, str] = os.environ,
                 synchronous: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.paths = paths
        loaded = load(paths.config)
        self.settings = loaded.settings
        self.settings_problem = loaded.problem
        self.resolved: Resolved | None = None
        self.status: Status | None = None
        self.game_update: GameUpdate | None = None
        self._resolve, self._status, self._apply_files = resolve, status, apply_files
        self._install, self._start_game, self._wine_user = install, start_game, wine_user
        self._latest = latest
        self._mark, self._downgrade, self._env = mark, downgrade, env
        self._native, self._family = native, family
        self.native_check: NativeCheck | None = None
        self._start_native, self._sync = start_native, sync
        self._find_runtimes, self._desktop_targets = find_runtimes, desktop_targets
        self._probe_runtimes = probe_runtimes
        self._probed: tuple[Checked | None, Checked | None] | None = None
        self._newer = newer
        # Until the first refresh has asked the host: the chosen build, else Windows.
        self._build = self.settings.game_build or Build.WINDOWS
        self.build_note: str | None = None  # the chosen build gave way to this one
        self._synchronous = synchronous
        self._jobs: list[Job] = []
        self._depth = 0  # synchronous jobs started from inside another one
        self._closing_note: str | None = None  # said once the last job has ended
        self._closing = False  # the window is closing: no job starts any more
        self._install_pending = False
        self._session: Any = None
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.poll_game)

    def _start(self, work: Callable[[Report], Any], done: Callable[[Any], None],
               title: str) -> None:
        if self._closing:
            # A done callback delivered during the close; a thread started now outlives exec().
            logger.info("not started, the launcher is closing: %s", title)
            return
        job = Job(work, done, title)
        job.progress.connect(self.progress)
        job.succeeded.connect(self._succeeded)
        job.failed.connect(self._failed)
        self.busy_changed.emit(True)
        if self._synchronous:
            self._depth += 1
            try:
                job.run()
            finally:
                self._depth -= 1
            job.deleteLater()
            if self._depth == 0:
                self._went_idle()
            return
        self._jobs.append(job)
        job.over.connect(self._finished)
        job.start()

    @Slot(object, object)
    def _succeeded(self, job: Job, result: Any) -> None:
        job.done(result)

    @Slot(object, str)
    def _failed(self, job: Job, text: str) -> None:
        self._tell(job.title, text)

    def _tell(self, title: str, text: str) -> None:
        if self._closing:
            return  # the log has it; a box would open over a window that is going
        self.message.emit(title, text)

    def _save(self, new: LauncherSettings) -> None:
        """Take on the player's settings; if the disk refuses them, they hold for this run."""
        self.settings = new
        try:
            save(self.paths.config, new)
        except OSError as error:
            logger.warning("the settings could not be saved: %s", error)
            self._tell(SETTINGS_TITLE, "The settings could not be saved, so they hold only "
                       f"until the launcher closes: {error}")
            return
        logger.info("settings saved")

    @Slot(object)
    def _finished(self, job: Job) -> None:
        if job in self._jobs:
            self._jobs.remove(job)
        job.deleteLater()
        if self._jobs:
            self.busy_changed.emit(True)
        else:
            self._went_idle()

    def install_when_idle(self) -> None:
        """Install now, or as soon as the jobs still running are done."""
        if self._jobs:
            self._install_pending = True
            return
        self.install()

    def _went_idle(self) -> None:
        # After busy_changed: going idle clears the progress line, the note then stands on it.
        self.busy_changed.emit(False)
        if self._install_pending:
            self._install_pending = False
            if not self.is_running():
                self.install()
                return
        if self._closing_note is not None:
            note, self._closing_note = self._closing_note, None
            self.note.emit(note)

    def jobs(self) -> int:
        return len(self._jobs)

    def stop_jobs(self) -> None:
        """For the close: nothing new starts, and the running jobs stop at their next report."""
        self._closing = True
        self._install_pending = False
        self._timer.stop()
        for job in self._jobs:
            job.stop()

    def shutdown(self) -> None:
        self.stop_jobs()
        for job in list(self._jobs):
            job.wait()

    def refresh(self, after: Callable[[], None] | None = None) -> None:
        def work(report: Report) -> tuple[NativeCheck, Build, str | None, Resolved, Status,
                                          tuple[Checked | None, Checked | None]]:
            check = self._native()
            build, problem = effective_build(self.settings.game_build, check)
            resolved = self._resolve(self.settings)
            found = self._status(self.paths, self.settings, resolved, build, env=self._env,
                                 home=Path.home())
            # Asked here for Options: a Wine wrapper that waits would hold the window there.
            return check, build, problem, resolved, found, self._probe_runtimes()

        def done(result: tuple[NativeCheck, Build, str | None, Resolved, Status,
                               tuple[Checked | None, Checked | None]]) -> None:
            (self.native_check, self._build, self.build_note, self.resolved,
             self.status, self._probed) = result
            logger.info("his %s build%s", self._build.value,
                        f" ({self.build_note})" if self.build_note else "")
            if self.build_note and self._closing_note is None:
                self._closing_note = self.build_note
            _log_status(self.status)
            self.status_changed.emit(self.status)
            if after is not None:
                after()

        self._start(work, done, "Checking the requirements")

    @property
    def build(self) -> Build:
        """The build the launcher installs and runs: chosen, or the best that runs here."""
        return self._build

    def install_hint(self) -> str:
        """What the player can install so the build runs; "" when nothing is missing."""
        if self.native_check is None:
            return ""
        wine_missing = self.status is not None and self.status.runtime is None
        return hint(self._build, self.native_check, wine_missing=wine_missing,
                    family=self._family())

    def fallback_note(self) -> str:
        """Why the chosen build gave way, and what to install to have it back; "" otherwise."""
        chosen = self.settings.game_build
        if not self.build_note or chosen is None or self.native_check is None:
            return ""
        back = hint(chosen, self.native_check, wine_missing=False, family=self._family())
        return "\n".join(part for part in (self.build_note, back) if part)

    def start_checks(self) -> None:
        """At start: the requirements always; his manifest and GitHub only as the player chose.

        Nothing goes online before the first start's questions are answered.
        """
        self.refresh_desktop_entry()

        def online() -> None:
            # His manifest belongs to the build, so it is asked once the build is known.
            if self.settings.check_game_updates:
                self.check_game_update()
            if self.settings.check_launcher_updates:
                self.check_launcher_update()

        self.refresh(after=online)

    def check_launcher_update(self) -> None:
        """GitHub's newest release; never a box, never in the way."""
        transport = for_launcher(True)

        def work(report: Report) -> tuple[str | None, str | None]:
            try:
                return self._newer(transport), None
            except (UpdateCheckError, HostRefused, OSError, ValueError) as error:
                logger.warning("could not check for a newer launcher: %s", error)
                return None, str(error) or type(error).__name__

        def done(result: tuple[str | None, str | None]) -> None:
            newer, problem = result
            if newer is None and problem is None:
                logger.info("the launcher is the newest on GitHub")
            if newer is not None:
                logger.info("a newer launcher is out: v%s", newer)
                self._closing_note = (f"Launcher v{newer} is out: the Launcher Homepage "
                                      "has it.")
            self.launcher_checked.emit(newer, problem)

        self._start(work, done, "Checking for a newer launcher")

    def refresh_desktop_entry(self) -> None:
        """Point an installed entry at the AppImage where it is now (it may have moved)."""
        appimage = desktop.current_appimage(self._env)
        if appimage is None:
            return
        try:
            if desktop.refresh_exec(self._desktop_targets(), appimage):
                logger.info("desktop entry now starts %s", home_as_tilde(appimage))
        except (OSError, ValueError) as error:
            logger.warning("could not update the desktop entry: %s", error)

    def offers_icon(self) -> bool:
        """GNOME, started from the AppImage, and no entry yet: the icon is worth offering."""
        return (desktop.is_gnome(self._env) and desktop.current_appimage(self._env) is not None
                and desktop.installed_exec(self._desktop_targets()) is None)

    def icon_question_due(self) -> bool:
        """On later starts: asked again only while the player has not decided."""
        return self.settings.desktop is DesktopChoice.ASK and self.offers_icon()

    def answer_icon(self, choice: IconChoice) -> str | None:
        """Act on the icon question; the problem in words when the install failed."""
        if choice is IconChoice.INSTALL:
            problem = self.set_desktop_icon(True)
            if problem is None:
                # Said once the start's checks are through, so it is not wiped by them.
                self._closing_note = "Desktop icon installed. Options can remove it again."
            return problem
        if choice is IconChoice.NEVER:
            self._save(replace(self.settings, desktop=DesktopChoice.DECLINED))
            logger.info("desktop icon: not to be asked again")
        return None

    def finish_first_start(self, answer: FirstStart) -> str | None:
        """The first start's answers, saved once; it is never shown again."""
        self._save(replace(self.settings, first_run_done=True,
                           check_launcher_updates=answer.launcher_updates))
        logger.info("first start done; launcher updates %s", answer.launcher_updates)
        return None if answer.icon is None else self.answer_icon(answer.icon)

    def _ask_latest(self, build: Build) -> GameUpdate:
        try:
            transport = for_launcher(self.settings.check_launcher_updates)
            return GameUpdate(self._latest(self.paths, transport, build), build=build)
        except (ManifestError, HostRefused, OSError, ValueError) as error:
            logger.warning("could not check for a newer build: %s", error)
            return GameUpdate(None, str(error) or type(error).__name__, build=build)

    def _current_update(self) -> GameUpdate | None:
        """The last answer from his site, if it was given for the build that runs now."""
        u = self.game_update
        return u if u is not None and u.build is self._build else None

    def check_game_update(self) -> None:
        """Ask his site for the current version; a failure is shown on the row, not in a box."""
        build = self.build

        def work(report: Report) -> GameUpdate:
            return self._ask_latest(build)

        def done(result: GameUpdate) -> None:
            self.game_update = result
            if result.latest is not None:
                logger.info("his current build: v%s", result.latest)
            if self.status is not None:
                self.status_changed.emit(self.status)

        self._start(work, done, "Checking for a newer build")

    def update_available(self) -> bool:
        installed = self.status.game_version if self.status else None
        current = self._current_update()
        latest = current.latest if current else None
        if installed is None or latest is None:
            return False
        return version_key(latest) > version_key(installed)

    def can_run(self) -> bool:
        s = self.status
        if s is None or not s.game_installed or s.game_files is None or self._session is not None:
            return False
        if self._build is not Build.WINDOWS:
            return True  # the build that runs here; it needs neither Wine nor a prefix
        return s.prefix_ready and s.runtime is not None

    def is_running(self) -> bool:
        return self._session is not None

    def choose_game_files(self, chosen: Path) -> None:
        """Take the chosen zip, file or folder; a zip is unpacked in a job, off the window."""
        def work(report: Report) -> Path:
            report(None, "Checking the original game files")
            return self._apply_files(self.paths, chosen)

        def done(folder: Path) -> None:
            logger.info("original game files: %s", home_as_tilde(folder))
            self._save(replace(self.settings, game_files=str(folder)))
            self.refresh()

        self._start(work, done, FILES_TITLE)

    def options_state(self) -> OptionsState:
        """What the Options dialog shows; asks the host first when no refresh has run yet."""
        native = self.native_check or self._native()
        s = self.status
        installed = s is not None and s.game_installed and s.build is self._build
        system, bundled = self._probed if self._probed is not None else self._probe_runtimes()
        return OptionsState(
            settings=self.settings, native=native, build=self._build,
            game_version=s.game_version if installed and s is not None else None,
            game_installed=installed, resolved=self.resolved,
            icon_installed=desktop.installed_exec(self._desktop_targets()) is not None,
            system=system, bundled=bundled,
            icon_problem=(None if desktop.current_appimage(self._env) is not None
                          else ICON_NEEDS_APPIMAGE))

    def apply_settings(self, new: LauncherSettings,
                       after: Callable[[], None] | None = None) -> None:
        """Save what Options returned and look at the system again under it."""
        if new == self.settings:
            if after is not None:
                after()
            return
        old = self.settings
        self._save(new)
        if new.game_build != old.game_build:
            self.game_update = None  # his manifest belongs to the build

        def then() -> None:
            if new.check_game_updates and self.game_update is None:
                self.check_game_update()
            if after is not None:
                after()

        self.refresh(after=then)

    def find_runtimes(self, done: Callable[[list[Checked]], None]) -> None:
        """The search behind Search again; each Wine answers within seconds, so it is a job."""
        def work(report: Report) -> list[Checked]:
            report(None, "Searching for Wine builds")
            try:
                return self._find_runtimes()
            except OSError as error:
                logger.warning("the search for Wine builds stopped: %s", error)
                return []

        self._start(work, done, "Searching for Wine builds")

    def set_desktop_icon(self, install: bool) -> str | None:
        """Install or remove the desktop entry now; the problem in words, or None."""
        where = self._desktop_targets()
        try:
            if install:
                appimage = desktop.current_appimage(self._env)
                if appimage is None:
                    return ICON_NEEDS_APPIMAGE
                desktop.install(where, appimage)
            else:
                desktop.remove(where)
        except (OSError, ValueError) as error:
            logger.warning("desktop icon %s failed: %s", "install" if install else "removal",
                           error)
            return f"The desktop icon could not be {'installed' if install else 'removed'}: {error}"
        choice = DesktopChoice.INSTALLED if install else DesktopChoice.DECLINED
        self._save(replace(self.settings, desktop=choice))
        logger.info("desktop icon %s", "installed" if install else "removed")
        return None

    def install(self, update_game: bool | None = None) -> None:
        """Brings everything up to date; fetches his build when it is missing or newer."""
        before = self.status
        build = self._build
        installed = before is not None and before.game_installed
        # The start check may be off, for another build, or failed; the press asks his site then.
        current = self._current_update()
        ask = update_game is None and installed and (current is None or current.latest is None)
        runtime = self.resolved.checked if self.resolved else None
        if build is Build.WINDOWS and runtime is None:
            problem = self.resolved.problem if self.resolved else None
            self.message.emit(INSTALL_TITLE, problem or "The runtime has not been checked yet.")
            return

        def work(report: Report) -> tuple[Any, GameUpdate | None]:
            answer = self._current_update()
            if ask:
                report(None, "Checking for a newer build")
                answer = self._ask_latest(build)
            fetch = update_game if update_game is not None else _fetch_wanted(before, answer)
            result = self._install(self.paths, self.settings,
                                   for_launcher(self.settings.check_launcher_updates), runtime,
                                   build=build, base_env=self._env, update_game=fetch,
                                   progress=lambda step, done, total: report(
                                       _fraction(done, total), step.value))
            return result, answer

        def done(outcome: tuple[Any, GameUpdate | None]) -> None:
            result, answer = outcome
            if answer is not None:
                self.game_update = answer
            self._closing_note = _install_note(result, before, answer.latest if answer else None)
            logger.info("Update Reforged: %s", self._closing_note)
            self.refresh()

        logger.info("Update Reforged pressed: %s", "fetching his build" if not installed
                    or update_game else "asking his site first" if ask
                    else "his build stays, checking the rest")
        self._start(work, done, INSTALL_TITLE)

    def _sync_saves(self, build: Build) -> None:
        """Before a start: the build about to run takes the other build's newer saves."""
        if not self.settings.sync_saves:
            return
        try:
            windows = self.paths.port_dir(self._wine_user(self.paths)).parent
        except (PrefixError, OSError, ValueError) as error:
            logger.info("no Windows saves to sync: %s", error)
            return
        linux = native_data_dir(self._env, Path.home())
        other, mine = (linux, windows) if build is Build.WINDOWS else (windows, linux)
        try:
            self._sync(other, mine, self.paths.data / "save-backups")
        except OSError as error:
            # The game still starts with the saves it has; the player hears why.
            logger.warning("the save sync failed: %s", error)
            self.message.emit(RUN_TITLE, f"The saves could not be synced: {error}")

    def run_game(self, confirmed: bool = False) -> str | None:
        """Starts the game; returns a warning instead when the player must confirm first."""
        if not self.can_run():
            return "The requirements are not complete yet."
        if self._build is not Build.WINDOWS:
            return self._run_native(self._build)
        checked = self.resolved.checked if self.resolved else None
        if checked is None:
            return "The requirements are not complete yet."
        warning = self._downgrade(self.paths, checked)
        if warning is not None and not confirmed:
            logger.info("asking before the start: %s", warning)
            return warning
        logger.info("starting the game with %s %s", checked.candidate.source.value,
                    checked.version_text)
        self._sync_saves(Build.WINDOWS)
        try:
            user = self._wine_user(self.paths)
            write_windows_settings(self.paths.port_dir(user), self.settings)
            self._session = self._start_game(checked.runtime, self.paths, user, self._env)
        except (OSError, ValueError, PrefixError) as error:
            logger.warning("the game did not start: %s", error)
            self.message.emit(RUN_TITLE, str(error))
            return None
        try:
            self._mark(self.paths, checked)
        except OSError as error:
            # The game runs either way; without the stamp only the downgrade warning is lost.
            logger.warning("could not note which Wine set up the prefix: %s", error)
        self.game_running.emit(True)
        if not self._synchronous:
            self._timer.start()
        return None

    def _run_native(self, build: Build) -> str | None:
        logger.info("starting his %s build", build.value)
        self._sync_saves(build)
        try:
            write_native_game_folder(self.paths, self.settings, build, self._env, Path.home())
            self._session = self._start_native(build, self.paths, self._env)
        except (OSError, ValueError) as error:
            logger.warning("the game did not start: %s", error)
            self.message.emit(RUN_TITLE, str(error))
            return None
        try:
            record_native_run(self.paths, build)
        except OSError as error:
            logger.warning("could not note which Linux build ran: %s", error)
        self.game_running.emit(True)
        if not self._synchronous:
            self._timer.start()
        return None

    @Slot()
    def poll_game(self) -> None:
        if self._session is None:
            return
        state = self._session.poll()
        line = progress_text(state.log)
        if line and state.log.art is Art.FETCHING and not state.log.problem:
            self.progress.emit(None, line)
        elif line:
            self.note.emit(line)
        if not state.running:
            logger.info("the game ended, exit code %s%s", state.exit_code,
                        ", ended by the launcher" if state.stopped else "")
            self._timer.stop()
            self._session = None
            self.game_running.emit(False)
            self.refresh()
