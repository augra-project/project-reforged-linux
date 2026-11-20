# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Starting the launcher: the command line first, the window after."""

import argparse
import logging
import sys

from project_reforged_linux import GAME_NAME, PART_NUMBER, RELEASE_DATE, __version__
from project_reforged_linux.logsetup import setup_logging
from project_reforged_linux.paths import resolve

__all__ = ["main"]

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="project-reforged-linux",
        description=f"Launcher for {GAME_NAME}, Dan Whelan's free fan port of "
                    "The Elder Scrolls Travels: Shadowkey.")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__} ({PART_NUMBER}-{RELEASE_DATE})")
    parser.add_argument("--debug", action="store_true",
                        help="write debug lines to the console and the log file")
    args = parser.parse_args(argv)
    try:
        setup_logging(resolve().state, debug=args.debug)
    except OSError as error:
        print(f"{parser.prog}: cannot write its log: {error}", file=sys.stderr)
        return 1
    # Qt only after the arguments: --help and --version must work without a display.
    from project_reforged_linux.ui.window import run_window

    return run_window()
