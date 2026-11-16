# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The launcher's own settings (settings.json in the config folder)."""

import json
import logging
import os
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from kista.fileops import write_atomic

from project_reforged_linux.runtimes import Mode

__all__ = ["SETTINGS_JSON", "DesktopChoice", "LauncherSettings", "Loaded", "load", "save"]

logger = logging.getLogger(__name__)

SETTINGS_JSON = "settings.json"
FORMAT = 1
_FLAGS = ("check_game_updates", "check_launcher_updates", "first_run_done")


class DesktopChoice(StrEnum):
    ASK = "ask"
    INSTALLED = "installed"
    DECLINED = "declined"


@dataclass(frozen=True, slots=True)
class LauncherSettings:
    game_files: str | None = None
    # Both startup checks stay off until the player turns them on.
    check_game_updates: bool = False
    check_launcher_updates: bool = False
    desktop: DesktopChoice = DesktopChoice.ASK
    first_run_done: bool = False
    # Automatic unless the player picked a runtime on purpose.
    runtime_mode: Mode = Mode.AUTO
    runtime_wine: str | None = None  # the picked wine binary, for Mode.CHOSEN only

    def __post_init__(self) -> None:
        for name in ("game_files", "runtime_wine"):
            value = getattr(self, name)
            if value is not None and not value.startswith("/"):
                raise ValueError(f"{name} must be an absolute path")
        if (self.runtime_mode is Mode.CHOSEN) != (self.runtime_wine is not None):
            raise ValueError("runtime_wine belongs to the chosen runtime mode, and only to it")


@dataclass(frozen=True, slots=True)
class Loaded:
    settings: LauncherSettings
    problem: str | None = None


def _from_dict(data: Any) -> LauncherSettings:
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("unknown settings format")
    game_files = data.get("game_files")
    if game_files is not None and (not isinstance(game_files, str)
                                   or not game_files.startswith("/")):
        raise ValueError("game_files must be an absolute path")
    flags = {}
    for name in _FLAGS:
        value = data.get(name, False)
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be true or false")
        flags[name] = value
    desktop = data.get("desktop", DesktopChoice.ASK.value)
    mode = data.get("runtime_mode", Mode.AUTO.value)
    if not isinstance(desktop, str) or not isinstance(mode, str):
        raise ValueError("desktop and runtime_mode must be words")
    runtime_mode = Mode(mode)
    runtime_wine = data.get("runtime_wine")
    if runtime_wine is not None and not isinstance(runtime_wine, str):
        raise ValueError("runtime_wine must be a path")
    # LauncherSettings checks the rest: absolute paths, and the path only with Mode.CHOSEN.
    return LauncherSettings(game_files=game_files, desktop=DesktopChoice(desktop),
                            runtime_mode=runtime_mode, runtime_wine=runtime_wine, **flags)


def load(config_dir: Path) -> Loaded:
    path = config_dir / SETTINGS_JSON
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return Loaded(LauncherSettings())
    try:
        return Loaded(_from_dict(json.loads(raw.decode("utf-8"))))
    except ValueError as error:  # JSONDecodeError and UnicodeDecodeError are ValueErrors
        aside = path.with_name(SETTINGS_JSON + ".bad")
        os.replace(path, aside)
        logger.warning("could not read %s (%s); kept as %s", path, error, aside)
        return Loaded(LauncherSettings(),
                      problem=f"{path} could not be read ({error}). It was kept as "
                              f"{aside.name} and the defaults are in use.")


def save(config_dir: Path, settings: LauncherSettings) -> None:
    data = {"format": FORMAT, **asdict(settings)}
    data["desktop"] = settings.desktop.value
    data["runtime_mode"] = settings.runtime_mode.value
    text = json.dumps(data, indent=2) + "\n"
    write_atomic(config_dir / SETTINGS_JSON, text.encode("utf-8"), mode=0o600)
