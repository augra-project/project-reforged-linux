# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Starting the launcher: the command line first, the window after."""

import argparse
import logging

from project_reforged_linux import PART_NUMBER, RELEASE_DATE, __version__

__all__ = ["main"]

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="project-reforged-linux",
        description="Linux launcher for Project Reforged, Dan Whelan's free fan port of "
                    "The Elder Scrolls Travels: Shadowkey.")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__} ({PART_NUMBER}-{RELEASE_DATE})")
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    # Qt only after the arguments: --help and --version must work without a display.
    from project_reforged_linux.ui.window import run_window

    return run_window()
