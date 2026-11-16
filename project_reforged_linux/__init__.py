# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Linux launcher for Project Reforged."""

APP_NAME = "project-reforged-linux"
APP_ID = "io.github.augra_project.ProjectReforgedLinux"
# Sjáandi part number (Stefan, 2026-11-15); a release appends its date, -YYYYMMDD.
PART_NUMBER = "SJ-PRG-2004"
# The release appends its day to the part number (the scheme); set when a release is cut.
RELEASE_DATE = "20261116"
__version__ = "1.0.0"

__all__ = ["APP_ID", "APP_NAME", "PART_NUMBER", "RELEASE_DATE", "__version__"]
