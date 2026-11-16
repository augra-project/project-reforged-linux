# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The game version his own updater installed, read from his log."""

import re
from pathlib import Path

__all__ = ["parse_log_version", "read_installed_version"]

_FIRST_LINE = re.compile(r"Shadowkey (?P<version>\d+(?:\.\d+)+), [^,]+, ")


def parse_log_version(line: str) -> str:
    match = _FIRST_LINE.match(line.strip("\r\n"))
    if match is None:
        raise ValueError(f"not a Shadowkey log header: {line!r}")
    return match.group("version")


def read_installed_version(log_path: Path) -> str | None:
    """None before the game has run once; ValueError if the log does not look like his."""
    try:
        with log_path.open(encoding="utf-8-sig", errors="replace") as log:
            first = log.readline()
    except FileNotFoundError:
        return None
    return parse_log_version(first)
