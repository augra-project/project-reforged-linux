# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Where the launcher keeps its data, settings and downloads."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from project_reforged_linux import APP_NAME
from project_reforged_linux.builds import Build

__all__ = ["AppPaths", "ensure_dirs", "native_data_dir", "native_port_dir", "resolve"]


@dataclass(frozen=True, slots=True)
class AppPaths:
    data: Path
    config: Path
    cache: Path
    state: Path

    @property
    def game(self) -> Path:
        return self.data / "game"

    def build_dir(self, build: Build) -> Path:
        """Where the launcher installs the build; Windows keeps its first folder, game/."""
        return self.game if build is Build.WINDOWS else self.data / _BUILD_DIRS[build]

    @property
    def card(self) -> Path:
        """The player's N-Gage card, unpacked from the zip they chose."""
        return self.data / "ngage"

    @property
    def runtime(self) -> Path:
        return self.data / "runtime"

    @property
    def prefix(self) -> Path:
        return self.data / "prefix"

    def port_dir(self, wine_user: str) -> Path:
        """His settings, log and art inside the prefix."""
        if not wine_user or wine_user in (".", "..") or "/" in wine_user or "\\" in wine_user:
            raise ValueError(f"invalid Wine user name: {wine_user!r}")
        return (self.prefix / "drive_c" / "users" / wine_user / "AppData" / "Roaming"
                / "Shadowkey" / "ShadowkeyPort")


_BUILD_DIRS = {Build.LINUX_TARBALL: "linux", Build.LINUX_APPIMAGE: "appimage"}


def native_data_dir(env: Mapping[str, str], home: Path) -> Path:
    """His native build's folder; a relative XDG_DATA_HOME he would take below the current one."""
    value = env.get("XDG_DATA_HOME", "")
    base = Path(value) if value.startswith("/") else home / ".local" / "share"
    return base / "Shadowkey"


def native_port_dir(env: Mapping[str, str], home: Path) -> Path:
    """His native build's settings, log, art and game_folder.txt."""
    return native_data_dir(env, home) / "ShadowkeyPort"


def resolve() -> AppPaths:
    """Compute the paths from the environment without creating anything."""
    # platformdirs (4.14) already ignores relative XDG values, as the XDG spec asks.
    return AppPaths(
        data=platformdirs.user_data_path(APP_NAME),
        config=platformdirs.user_config_path(APP_NAME),
        cache=platformdirs.user_cache_path(APP_NAME),
        state=platformdirs.user_state_path(APP_NAME),
    )


def ensure_dirs(paths: AppPaths) -> None:
    """Create the launcher's folders as 0700; folders that already exist keep their mode."""
    for directory in (paths.data, paths.config, paths.cache, paths.state, paths.game,
                      paths.prefix):
        if directory.is_dir():
            continue
        directory.mkdir(parents=True, mode=0o700)
        # mkdir's mode is masked by the umask
        directory.chmod(0o700)
