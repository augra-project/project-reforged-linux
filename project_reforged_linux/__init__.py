# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
APP_NAME = "project-reforged-linux"
# His game's name, spelled only here: he renamed it once already.
GAME_NAME = "Project Reforged"
# The name people see: title bar, menu entry, log, About.
LAUNCHER_NAME = f"{GAME_NAME} Linux Launcher"
APP_ID = "io.github.augra_project.ProjectReforgedLinux"
# Sjáandi part number; a release appends its date, -YYYYMMDD.
PART_NUMBER = "SJ-PRG-2004"
# The release appends its day to the part number (the scheme); set when a release is cut.
RELEASE_DATE = "20261121"
__version__ = "1.0.0"

__all__ = ["APP_ID", "APP_NAME", "GAME_NAME", "LAUNCHER_NAME", "PART_NUMBER", "RELEASE_DATE",
           "__version__"]
