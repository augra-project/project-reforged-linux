# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
from collections.abc import Mapping

from project_reforged_linux.hostenv import host_env

__all__ = ["native_env"]

# With APPIMAGE set, his tarball takes itself for an AppImage and his updater would replace
# the file it names, which is ours: host_env takes it out with the rest
# of our AppImage. The NX client's LD_PRELOAD has no business in his process either.
_CLEARED = frozenset({"LD_PRELOAD", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"})


def native_env(base: Mapping[str, str]) -> dict[str, str]:
    env = {k: v for k, v in host_env(base).items() if k not in _CLEARED}
    # His build reads an empty or relative value as a folder below the current one.
    if not env.get("XDG_DATA_HOME", "/").startswith("/"):
        del env["XDG_DATA_HOME"]
    return env
