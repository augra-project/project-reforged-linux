# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""What his build reports in shadowkey.log: the art download and start failures."""

import re
from dataclasses import dataclass, replace
from enum import Enum

__all__ = ["Art", "LogState", "progress_text", "read_log"]

# Message formats from the 0.2.31 binary.
_PLAN = re.compile(r"Art: (\d+) of (\d+) pictures to download \(([\d.]+) MB\)")
_DOWNLOADED = re.compile(r"Art: downloaded (\d+) of (\d+) pictures")
_UP_TO_DATE = re.compile(r"Art: all (\d+) pictures up to date")
_ART_FAILURE = re.compile(r"Art: (?:can't fetch |can't keep |can't put "
                          r"|the list at .* isn't trusted|.+ didn't download right)")
# "GPU: x couldn't start (...); using the automatic choice instead" is his fallback, not this.
_GAVE_UP = re.compile(r"couldn't start.*; giving up$")
_TIMESTAMP = re.compile(r"^\d+:\d+\.\d+ ")


class Art(Enum):
    UNKNOWN = "unknown"
    FETCHING = "fetching"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class LogState:
    art: Art = Art.UNKNOWN
    pictures: int | None = None   # pictures in his index, once he names them
    to_fetch: int | None = None
    megabytes: float | None = None
    gave_up: bool = False         # he could not start; the process stays alive anyway
    problem: str = ""             # the line to show the player


def read_log(text: str) -> LogState:
    state = LogState()
    for raw in text.lstrip("\ufeff").splitlines():
        line = _TIMESTAMP.sub("", raw.strip())
        if _GAVE_UP.search(line):
            state = replace(state, gave_up=True, problem=line)
        elif state.art is Art.FAILED:
            continue
        elif _ART_FAILURE.search(line):
            state = replace(state, art=Art.FAILED, problem=line)
        elif m := _UP_TO_DATE.search(line):
            state = replace(state, art=Art.DONE, pictures=int(m.group(1)))
        elif m := _PLAN.search(line):
            state = replace(state, art=Art.FETCHING, to_fetch=int(m.group(1)),
                            pictures=int(m.group(2)), megabytes=float(m.group(3)))
        elif m := _DOWNLOADED.search(line):
            if state.to_fetch is not None and int(m.group(1)) == state.to_fetch:
                state = replace(state, art=Art.DONE)
            else:
                state = replace(state, art=Art.FAILED, problem=line)
    return state


def progress_text(state: LogState) -> str:
    """One line for the window's status row; empty while his log has said nothing yet."""
    if state.problem:
        return state.problem
    if state.art is Art.FETCHING:
        return (f"Downloading the game's art: {state.to_fetch} of {state.pictures} pictures "
                f"({state.megabytes:.1f} MB)")
    if state.art is Art.DONE:
        return f"Art ready: {state.pictures} pictures"
    return ""
