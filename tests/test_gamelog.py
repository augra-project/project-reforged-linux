# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import pytest

from project_reforged_linux.gamelog import Art, progress_text, read_log

# The first run of 0.2.31 in an empty prefix, 2026-11-15, as his build wrote it.
FRESH = ("Shadowkey 0.2.31, Windows, 2026-11-15 13:25:54\r\n"
         "00:00.184 Start: finding the game files\r\n"
         "00:00.280 No game files found: the setup page\r\n"
         "00:00.577 Art: 805 of 805 pictures to download (632.6 MB), 4 at a time\r\n"
         "00:00.744 Start: the setup page: looking for Morrowind\r\n")
HEAD = "Shadowkey 0.2.31, Windows, 2026-11-15 13:25:54\r\n"


def test_empty_log() -> None:
    state = read_log("")
    assert state.art is Art.UNKNOWN and not state.gave_up and state.problem == ""


def test_download_running_shows_the_plan() -> None:
    state = read_log(FRESH)
    assert state.art is Art.FETCHING
    assert (state.to_fetch, state.pictures, state.megabytes) == (805, 805, 632.6)


def test_download_finished() -> None:
    state = read_log(FRESH + "00:55.970 Art: downloaded 805 of 805 pictures\r\n")
    assert state.art is Art.DONE and state.pictures == 805


def test_delta_download_finished() -> None:
    log = HEAD + ("00:00.650 Art: 8 of 805 pictures to download (0.6 MB), 4 at a time\r\n"
                  "00:01.029 Art: downloaded 8 of 8 pictures\r\n")
    state = read_log(log)
    assert state.art is Art.DONE and state.pictures == 805


def test_short_download_is_a_failure() -> None:
    log = HEAD + ("00:00.650 Art: 8 of 805 pictures to download (0.6 MB), 4 at a time\r\n"
                  "00:01.029 Art: downloaded 6 of 8 pictures\r\n")
    state = read_log(log)
    assert state.art is Art.FAILED and "6 of 8" in state.problem


def test_up_to_date() -> None:
    state = read_log(HEAD + "00:00.640 Art: all 805 pictures up to date in C:\\users\\x\\art\r\n")
    assert state.art is Art.DONE and state.pictures == 805


@pytest.mark.parametrize("line", [
    "Art: can't fetch sprite/1.png: HTTP 503",
    "Art: can't keep sprite/1.png: disk full",
    "Art: can't put sprite/1.png in place: access denied",
    "Art: texture/x tex_01.png didn't download right (size); next time",
    "Art: the list at https://x/art/index.txt isn't trusted: bad signature; nothing changed",
])
def test_art_failures(line: str) -> None:
    state = read_log(FRESH + f"00:01.000 {line}\r\n")
    assert state.art is Art.FAILED and state.problem == line


@pytest.mark.parametrize("line", [
    "Shadowkey couldn't start SDL, its window and sound system; giving up",
    "Shadowkey couldn't start its window system; giving up",
    "Shadowkey couldn't start its graphics; giving up",
])
def test_start_failures(line: str) -> None:
    state = read_log(HEAD + f"00:00.275 {line}\r\n")
    assert state.gave_up and state.problem == line


def test_gpu_fallback_is_not_a_start_failure() -> None:
    line = "GPU: direct3d12 couldn't start (no device); using the automatic choice instead"
    state = read_log(HEAD + f"00:00.400 {line}\r\n")
    assert not state.gave_up and state.problem == ""


def test_art_keeps_running_after_a_start_failure() -> None:
    log = (HEAD
           + "00:00.275 Shadowkey couldn't start SDL, its window and sound system; giving up\r\n"
           + "00:00.650 Art: 8 of 805 pictures to download (0.6 MB), 4 at a time\r\n")
    state = read_log(log)
    assert state.gave_up and state.art is Art.FETCHING


def test_progress_line_while_fetching() -> None:
    assert progress_text(read_log(FRESH)) == (
        "Downloading the game's art: 805 of 805 pictures (632.6 MB)")


def test_progress_line_when_done() -> None:
    log = HEAD + "00:00.606 Art: all 805 pictures up to date in C:\\x\\art\r\n"
    assert progress_text(read_log(log)) == "Art ready: 805 pictures"


def test_progress_line_shows_his_problem() -> None:
    log = HEAD + ("00:00.500 Shadowkey couldn't start SDL, its window and sound system; "
                  "giving up\r\n")
    assert progress_text(read_log(log)) == (
        "Shadowkey couldn't start SDL, its window and sound system; giving up")


def test_progress_line_empty_before_anything() -> None:
    assert progress_text(read_log(HEAD)) == ""
