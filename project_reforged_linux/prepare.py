# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Install / Update Requirements: everything RUN GAME needs, and the state the window shows."""

import logging

# Only passed on to wineprefix as the default runner.
import subprocess  # nosec B404
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from project_reforged_linux.download import Expected, download
from project_reforged_linux.gamefiles import validate, write_game_folder_txt
from project_reforged_linux.gamesettings import write_first_settings
from project_reforged_linux.gameversion import read_installed_version
from project_reforged_linux.install import game_exe, install_zip
from project_reforged_linux.manifest import Manifest, fetch_manifest, version_key
from project_reforged_linux.net import Transport
from project_reforged_linux.paths import AppPaths, ensure_dirs
from project_reforged_linux.runner import LOG_NAME
from project_reforged_linux.runtimes import Checked, Resolved, mark_prefix
from project_reforged_linux.settings import LauncherSettings
from project_reforged_linux.wineprefix import (
    PrefixError,
    Run,
    create_prefix,
    find_wine_user,
    prefix_ready,
)

__all__ = ["Progress", "Status", "Step", "apply_game_files", "game_update_available",
           "install_requirements", "status"]

logger = logging.getLogger(__name__)


class Step(Enum):
    MANIFEST = "Checking the current version on his site"
    DOWNLOAD = "Downloading Project Reforged"
    INSTALL = "Installing Project Reforged"
    PREFIX = "Setting up Wine"
    CONFIGURE = "Writing the game's settings"


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


def _port_dir(paths: AppPaths) -> Path:
    return paths.port_dir(find_wine_user(paths.prefix))


def _installed_version(paths: AppPaths) -> str | None:
    if not prefix_ready(paths.prefix):
        return None
    try:
        return read_installed_version(_port_dir(paths) / LOG_NAME)
    except (PrefixError, ValueError) as error:
        logger.warning("cannot read the installed version: %s", error)
        return None


def status(paths: AppPaths, settings: LauncherSettings, resolved: Resolved) -> Status:
    files, problem = None, None
    if settings.game_files:
        try:
            files = validate(Path(settings.game_files))
        except (OSError, ValueError) as error:
            problem = str(error)
    return Status(game_installed=game_exe(paths).is_file(),
                  game_version=_installed_version(paths),
                  prefix_ready=prefix_ready(paths.prefix),
                  game_files=files, game_files_problem=problem,
                  runtime=resolved.checked, runtime_note=resolved.note,
                  runtime_problem=resolved.problem)


def apply_game_files(paths: AppPaths, chosen: Path) -> Path:
    """Check the chosen folder; write game_folder.txt now if the prefix exists."""
    folder = validate(chosen)
    if prefix_ready(paths.prefix):
        port = _port_dir(paths)
        port.mkdir(parents=True, exist_ok=True)
        write_game_folder_txt(port, folder)
    return folder


def install_requirements(paths: AppPaths, settings: LauncherSettings, transport: Transport,
                         runtime: Checked, *, base_env: Mapping[str, str],
                         progress: Progress = _quiet, update_game: bool = False,
                         run: Run = subprocess.run) -> Manifest | None:
    """Returns his manifest when a build was installed, else None."""
    # The runtime is checked first: a missing Wine must not cost his site a download.
    if not runtime.usable:
        raise ValueError(f"no usable runtime: {runtime.problem}")
    ensure_dirs(paths)
    manifest = None
    if update_game or not game_exe(paths).is_file():
        progress(Step.MANIFEST, None, None)
        manifest = fetch_manifest(transport, paths.cache)
        progress(Step.DOWNLOAD, 0, manifest.size)
        archive = download(transport, manifest.url, paths.cache / manifest.filename,
                           Expected(manifest.size, manifest.sha256),
                           progress=lambda done, total: progress(Step.DOWNLOAD, done, total))
        progress(Step.INSTALL, None, None)
        install_zip(archive, paths)
        archive.unlink()
    if not prefix_ready(paths.prefix):
        progress(Step.PREFIX, None, None)
        create_prefix(runtime.runtime, paths.prefix, base_env, run=run)
        mark_prefix(paths, runtime)
    progress(Step.CONFIGURE, None, None)
    port = _port_dir(paths)
    port.mkdir(parents=True, exist_ok=True)
    write_first_settings(port)
    if settings.game_files:
        write_game_folder_txt(port, validate(Path(settings.game_files)))
    return manifest


def game_update_available(paths: AppPaths, transport: Transport) -> Manifest | None:
    """His manifest when it names a newer build than his log; the startup check (opt-in)."""
    installed = _installed_version(paths)
    if installed is None:
        return None
    manifest = fetch_manifest(transport, paths.cache)
    return manifest if version_key(manifest.version) > version_key(installed) else None
