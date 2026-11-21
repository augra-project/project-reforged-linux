# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import json
import logging
import os

# Only passed on to wineprefix as the default runner.
import subprocess  # nosec B404
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from kista.fileops import write_atomic

from project_reforged_linux import GAME_NAME
from project_reforged_linux.artseed import seed_art
from project_reforged_linux.builds import Build
from project_reforged_linux.download import Expected, download
from project_reforged_linux.gamefiles import (
    find_6r51_below,
    missing_level_files,
    validate,
    write_game_folder_txt,
)
from project_reforged_linux.gamesettings import write_first_settings
from project_reforged_linux.gameversion import read_installed_version
from project_reforged_linux.install import (
    InstallError,
    executable,
    install_appimage,
    install_card_zip,
    install_tarball,
    install_zip,
)
from project_reforged_linux.logsetup import home_as_tilde
from project_reforged_linux.manifest import Manifest, fetch_manifest, version_key
from project_reforged_linux.net import Transport
from project_reforged_linux.paths import AppPaths, ensure_dirs, native_port_dir
from project_reforged_linux.runner import LOG_NAME
from project_reforged_linux.runtimes import PREFIX_STAMP, Checked, Resolved, mark_prefix
from project_reforged_linux.settings import LauncherSettings
from project_reforged_linux.wineprefix import (
    PrefixError,
    Run,
    adopt_finished_prefix,
    create_prefix,
    find_wine_user,
    prefix_ready,
)

__all__ = ["LAST_NATIVE", "OLD_STAMP_NAME", "Progress", "Status", "Step", "apply_game_files",
           "install_requirements", "installed_version", "latest_game_version",
           "record_native_run", "stamp_path", "status", "write_native_game_folder",
           "write_windows_settings"]

# Both Linux builds write one shadowkey.log; this names the one that ran last.
LAST_NATIVE = "last-native-build.txt"

logger = logging.getLogger(__name__)


class Step(Enum):
    MANIFEST = "Checking the current version on his site"
    DOWNLOAD = f"Downloading {GAME_NAME}"
    INSTALL = f"Installing {GAME_NAME}"
    PREFIX = "Setting up Wine"
    CONFIGURE = "Writing the game's settings"


# What the launcher installed last, one file per build: his log names a version only after
# the first start, and his own updater may move it on from there.
OLD_STAMP_NAME = "installed.json"  # the first launchers' only stamp, always Windows
_STAMP_MAX = 4096


Progress = Callable[[Step, int | None, int | None], None]


def _quiet(step: Step, done: int | None, total: int | None) -> None:
    pass


@dataclass(frozen=True, slots=True)
class Status:
    game_installed: bool
    game_version: str | None  # from his log; None before his first start
    prefix_ready: bool
    game_files: Path | None  # the checked 6R51 folder
    game_files_problem: str | None
    runtime: Checked | None  # the Wine that runs the game, when one is usable
    runtime_note: str | None  # Automatic fell back to the bundled runtime
    runtime_problem: str | None  # nothing usable; the window shows the install help
    build: Build | None = None  # None while nothing is installed


def stamp_path(paths: AppPaths, build: Build) -> Path:
    return paths.data / f"installed-{build.key}.json"


def _write_stamp(paths: AppPaths, build: Build, version: str) -> None:
    version_key(version)  # refuses anything that is not a version
    record = {"format": 1, "build": build.key, "version": version}
    write_atomic(stamp_path(paths, build), json.dumps(record).encode("utf-8"))


def _adopt_old_stamp(paths: AppPaths) -> None:
    old, new = paths.data / OLD_STAMP_NAME, stamp_path(paths, Build.WINDOWS)
    if old.is_file() and not new.exists():
        try:
            os.replace(old, new)
        except OSError as error:
            logger.warning("could not take over %s: %s", home_as_tilde(old), error)
            return
        logger.info("took over %s as %s", home_as_tilde(old), new.name)


def installed_version(paths: AppPaths, build: Build) -> str | None:
    """The launcher's record of the build's installed version (None if unknown)."""
    if build is Build.WINDOWS:
        _adopt_old_stamp(paths)
    path = stamp_path(paths, build)
    try:
        with path.open("rb") as stamp:
            raw = stamp.read(_STAMP_MAX + 1)
    except FileNotFoundError:
        return None
    except OSError as error:
        logger.warning("cannot read %s: %s", path, error)
        return None
    try:
        if len(raw) > _STAMP_MAX:
            raise ValueError("too large")
        record = json.loads(raw.decode("utf-8"))
        if not isinstance(record, dict) or record.get("format") != 1:
            raise ValueError("unknown format")
        if Build.from_key(str(record.get("build", ""))) is not build:
            raise ValueError(f"a stamp of another build: {record.get('build')!r}")
        version = record.get("version")
        if not isinstance(version, str):
            raise ValueError("no version")
        version_key(version)
    except (ValueError, RecursionError) as error:
        logger.warning("ignoring a broken %s: %s", path, error)
        return None
    return version


def _newer(first: str | None, second: str | None) -> str | None:
    if first is None or second is None:
        return first or second
    return first if version_key(first) >= version_key(second) else second


def _port_dir(paths: AppPaths) -> Path:
    return paths.port_dir(find_wine_user(paths.prefix))


def record_native_run(paths: AppPaths, build: Build) -> None:
    write_atomic(paths.data / LAST_NATIVE, f"{build.key}\n".encode())


def _last_native(paths: AppPaths) -> Build | None:
    try:
        return Build.from_key((paths.data / LAST_NATIVE).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _logged_version(paths: AppPaths, build: Build, env: Mapping[str, str],
                   home: Path) -> str | None:
    """The version in his log's first line, for the build's own log; None if unusable."""
    try:
        if build is Build.WINDOWS:
            if not prefix_ready(paths.prefix):
                return None
            logged = read_installed_version(_port_dir(paths) / LOG_NAME)
        else:
            if _last_native(paths) not in (None, build):
                return None
            logged = read_installed_version(native_port_dir(env, home) / LOG_NAME)
        if logged is not None:
            version_key(logged)  # one the launcher cannot compare would break every status
    # A log that cannot be read leaves the version to the stamp; it must not stop the status.
    except (PrefixError, ValueError, OSError) as error:
        logger.warning("cannot read the installed version: %s", error)
        return None
    return logged


def status(paths: AppPaths, settings: LauncherSettings, resolved: Resolved,
           build: Build = Build.WINDOWS, *, env: Mapping[str, str] = os.environ,
           home: Path | None = None) -> Status:
    home = home or Path.home()
    try:
        adopt_finished_prefix(paths.prefix, paths.data / PREFIX_STAMP)
    except OSError as error:
        logger.warning("could not mark the old prefix as finished: %s", error)
    files, problem = None, None
    if settings.game_files:
        try:
            files = validate(Path(settings.game_files))
        except (OSError, ValueError) as error:
            problem = str(error)
    installed = executable(paths, build).is_file()
    version = None
    if installed:
        version = _newer(installed_version(paths, build),
                         _logged_version(paths, build, env, home))
    return Status(game_installed=installed, game_version=version,
                  prefix_ready=prefix_ready(paths.prefix),
                  game_files=files, game_files_problem=problem,
                  runtime=resolved.checked, runtime_note=resolved.note,
                  runtime_problem=resolved.problem, build=build if installed else None)


def _checked_card(root: Path) -> Path | None:
    """The card's 6R51 folder, complete; raising inside the swap keeps the old card."""
    folder = find_6r51_below(root)
    if folder is not None:
        missing = missing_level_files(folder)
        if missing:
            raise ValueError(f"{folder.relative_to(root).as_posix()} is missing level files: "
                             f"{', '.join(missing)}")
    return folder


def apply_game_files(paths: AppPaths, chosen: Path) -> Path:
    """Check the chosen folder, file or card zip; write game_folder.txt if the prefix exists.

    A zip is unpacked into the launcher's own card folder, every date kept.
    """
    if chosen.is_file() and zipfile.is_zipfile(chosen):
        ensure_dirs(paths)
        try:
            unpacked = install_card_zip(chosen, paths, _checked_card)
        except InstallError as error:
            raise ValueError(str(error)) from error
        except ValueError as error:
            raise ValueError(f"{chosen.name}: {error}") from error
        logger.info("card unpacked from %s", home_as_tilde(chosen))
        chosen = unpacked
    folder = validate(chosen)
    if prefix_ready(paths.prefix):
        port = _port_dir(paths)
        port.mkdir(parents=True, exist_ok=True)
        write_game_folder_txt(port, folder, Build.WINDOWS)
    return folder


def _fetch_build(paths: AppPaths, transport: Transport, build: Build,
                 progress: Progress) -> Manifest:
    progress(Step.MANIFEST, None, None)
    manifest = fetch_manifest(transport, paths.cache, build)
    logger.info("%s: v%s from %s, %d bytes", build.value, manifest.version,
                manifest.url, manifest.size)
    progress(Step.DOWNLOAD, 0, manifest.size)
    archive = download(transport, manifest.url, paths.cache / manifest.filename,
                       Expected(manifest.size, manifest.sha256),
                       progress=lambda done, total: progress(Step.DOWNLOAD, done, total))
    logger.info("downloaded %s, size and sha256 checked", home_as_tilde(archive))
    progress(Step.INSTALL, None, None)
    if build is Build.WINDOWS:
        install_zip(archive, paths)
    elif build is Build.LINUX_TARBALL:
        install_tarball(archive, paths)
    else:
        install_appimage(archive, paths)
    archive.unlink(missing_ok=True)
    _write_stamp(paths, build, manifest.version)
    logger.info("installed v%s into %s", manifest.version,
                home_as_tilde(paths.build_dir(build)))
    return manifest


def install_requirements(paths: AppPaths, settings: LauncherSettings, transport: Transport,
                         runtime: Checked | None, *, build: Build = Build.WINDOWS,
                         base_env: Mapping[str, str], progress: Progress = _quiet,
                         update_game: bool = False, run: Run = subprocess.run,
                         home: Path | None = None) -> Manifest | None:
    """Returns his manifest when a build was installed, else None."""
    home = home or Path.home()
    # The runtime is checked first: a missing Wine must not cost his site a download.
    if build is Build.WINDOWS and (runtime is None or not runtime.usable):
        raise ValueError(f"no usable runtime: {runtime.problem if runtime else 'none'}")
    ensure_dirs(paths)
    manifest = None
    if update_game or not executable(paths, build).is_file():
        manifest = _fetch_build(paths, transport, build, progress)
    else:
        logger.info("his build stays as it is: installed, and nothing newer asked for")
    if build is not Build.WINDOWS:
        _configure_native(paths, settings, build, base_env, home, progress)
        return manifest
    if not prefix_ready(paths.prefix):
        progress(Step.PREFIX, None, None)
        logger.info("creating the Wine prefix %s with %s", home_as_tilde(paths.prefix),
                    runtime.version_text)
        (paths.data / PREFIX_STAMP).unlink(missing_ok=True)
        create_prefix(runtime.runtime, paths.prefix, base_env, run=run)
        mark_prefix(paths, runtime)
    progress(Step.CONFIGURE, None, None)
    port = _port_dir(paths)
    write_windows_settings(port, settings)
    _seed(native_port_dir(base_env, home), port)
    if settings.game_files:
        logger.info("game settings written, game files %s", home_as_tilde(settings.game_files))
    else:
        logger.info("game settings written; no game files chosen yet")
    return manifest


def write_windows_settings(port: Path, settings: LauncherSettings) -> None:
    """The install's last step, written again before each start of his Windows build.

    A launcher stopped or killed between the Wine setup and that step would start him unset.
    """
    port.mkdir(parents=True, exist_ok=True)
    write_first_settings(port)
    if settings.game_files:
        write_game_folder_txt(port, validate(Path(settings.game_files)), Build.WINDOWS)


def _seed(source: Path, target: Path) -> None:
    # Only a shortcut: his build fetches what is missing itself.
    try:
        seed_art(source, target)
    except OSError as error:
        logger.warning("the art could not be copied over, his build fetches it: %s", error)


def write_native_game_folder(paths: AppPaths, settings: LauncherSettings, build: Build,
                             env: Mapping[str, str], home: Path) -> None:
    """Tell his Linux build where the game files are, before each start."""
    if not settings.game_files:
        return
    port = native_port_dir(env, home)
    port.mkdir(parents=True, exist_ok=True)
    write_game_folder_txt(port, validate(Path(settings.game_files)), build)


def _configure_native(paths: AppPaths, settings: LauncherSettings, build: Build,
                      env: Mapping[str, str], home: Path, progress: Progress) -> None:
    """His Linux build keeps its own settings and updater; the launcher adds the game files."""
    progress(Step.CONFIGURE, None, None)
    port = native_port_dir(env, home)
    port.mkdir(parents=True, exist_ok=True)
    if prefix_ready(paths.prefix):
        try:
            _seed(_port_dir(paths), port)
        except PrefixError as error:
            logger.warning("no art to seed from the Windows build: %s", error)
    if settings.game_files:
        folder = validate(Path(settings.game_files))
        write_game_folder_txt(port, folder, build)
        logger.info("game files %s for %s", home_as_tilde(folder), build.value)


def latest_game_version(paths: AppPaths, transport: Transport, build: Build) -> str:
    """The version his manifest names now for the build."""
    ensure_dirs(paths)
    return fetch_manifest(transport, paths.cache, build).version
