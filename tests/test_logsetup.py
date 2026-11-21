# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import logging
import re
import stat
import sys
from collections.abc import Iterator
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

import pytest

from project_reforged_linux import __version__, logsetup
from project_reforged_linux.app import main
from project_reforged_linux.logsetup import (
    CRASH_NAME,
    KEEP_DAYS,
    LOG_NAME,
    home_as_tilde,
    log_dir,
    setup_logging,
)

# augra-log's default "{timestamp} [{level}] {component}: {message}", seconds only as luducat.
LINE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \[(INFO|DEBUG|WARNING|ERROR)\] [\w.]+: .+$")


@pytest.fixture
def root_restored() -> Iterator[None]:
    """setup_logging adds handlers to the root logger; take them off and close them again."""
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)


def lines(path: Path) -> list[str]:
    for handler in logging.getLogger().handlers:
        handler.flush()
    return path.read_text(encoding="utf-8").splitlines()


def test_log_file_in_the_state_folder(tmp_path: Path, root_restored: None) -> None:
    path = setup_logging(tmp_path / "state", crash_trace=False)
    assert path == log_dir(tmp_path / "state") / LOG_NAME
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    logging.getLogger("project_reforged_linux.download").info("fetched %d bytes", 5)
    written = lines(path)
    assert __version__ in written[0]
    assert all(LINE.match(line) for line in written), written
    assert written[-1].endswith("[INFO] project_reforged_linux.download: fetched 5 bytes")


def test_the_file_rotates_at_midnight_and_keeps_a_week(tmp_path: Path,
                                                      root_restored: None) -> None:
    setup_logging(tmp_path, crash_trace=False)
    files = [h for h in logging.getLogger().handlers if isinstance(h, TimedRotatingFileHandler)]
    assert len(files) == 1
    assert files[0].when == "MIDNIGHT" and files[0].backupCount == KEEP_DAYS == 7


@pytest.mark.parametrize(("debug", "kept"), [(False, False), (True, True)])
def test_debug_lines_only_with_debug(tmp_path: Path, root_restored: None, debug: bool,
                                     kept: bool) -> None:
    path = setup_logging(tmp_path, debug=debug, crash_trace=False)
    logging.getLogger("project_reforged_linux.net").debug("redirect seen")
    assert any("redirect seen" in line for line in lines(path)) is kept


def test_without_a_console_only_the_file(tmp_path: Path, root_restored: None,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    # A start from the desktop menu may come without stderr; a stream handler would then
    # fail on every line.
    monkeypatch.setattr(sys, "stderr", None)
    before = len(logging.getLogger().handlers)
    path = setup_logging(tmp_path, crash_trace=False)
    added = logging.getLogger().handlers[before:]
    assert [type(h) for h in added] == [TimedRotatingFileHandler]
    assert lines(path)


def test_a_hard_crash_lands_in_crash_log(tmp_path: Path, root_restored: None,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    enabled: list[Any] = []
    monkeypatch.setattr(logsetup.faulthandler, "is_enabled", lambda: False)
    monkeypatch.setattr(logsetup.faulthandler, "enable", enabled.append)
    setup_logging(tmp_path, crash_trace=True)
    try:
        assert len(enabled) == 1 and enabled[0].name == str(log_dir(tmp_path) / CRASH_NAME)
    finally:
        enabled[0].close()
        monkeypatch.setattr(logsetup, "_crash_file", None)


@pytest.mark.parametrize(("given", "logged"), [
    (Path.home(), "~"),
    (Path.home() / "Projects" / "ngage-files", "~/Projects/ngage-files"),
    (f"{Path.home()}2/other", f"{Path.home()}2/other"),  # only the folder, not a prefix of it
    (Path("/media/card"), "/media/card"),
    ("no 6R51 folder in /srv/x", "no 6R51 folder in /srv/x"),
])
def test_the_home_folder_becomes_a_tilde(given: Path | str, logged: str) -> None:
    assert home_as_tilde(given) == logged


def test_a_log_that_cannot_be_written_stops_the_start(xdg_home: Path,
                                                      capsys: pytest.CaptureFixture[str],
                                                      root_restored: None) -> None:
    # The state folder's place is taken by a file.
    (xdg_home / "state" / "project-reforged-linux").write_text("x", encoding="utf-8")
    assert main([]) == 1
    assert "cannot write its log" in capsys.readouterr().err


def test_version_writes_no_log(xdg_home: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--version"])
    assert not (xdg_home / "state" / "project-reforged-linux").exists()


def test_the_state_folder_is_private_whatever_the_umask(tmp_path: Path,
                                                        root_restored: None) -> None:
    import os

    old = os.umask(0o002)
    try:
        setup_logging(tmp_path / "state", crash_trace=False)
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "state").stat().st_mode) == 0o700


def test_the_home_folder_never_reaches_the_log_file(tmp_path: Path, root_restored: None,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home" / "alice"
    monkeypatch.setenv("HOME", str(home))
    path = setup_logging(tmp_path / "state", crash_trace=False)
    log = logging.getLogger("project_reforged_linux.settings")
    log.warning("could not read %s; kept as %s", home / ".config" / "s.json", "s.json.bad")
    try:
        raise OSError(2, "No such file or directory", str(home / "data" / "x"))
    except OSError:
        log.exception("job failed")
    text = path.read_text(encoding="utf-8")
    assert str(home) not in text
    assert "~/.config/s.json" in text and "~/data/x" in text



def test_the_login_never_reaches_the_log_file(tmp_path: Path, root_restored: None,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home" / "alice"))
    for name in ("LOGNAME", "USER", "LNAME", "USERNAME"):
        monkeypatch.setenv(name, "alice")
    path = setup_logging(tmp_path / "state", crash_trace=False)
    log = logging.getLogger("project_reforged_linux.savesync")
    log.info("saves taken from %s: game1",
             tmp_path / "home" / "alice" / "prefix" / "drive_c" / "users" / "alice" / "Saves")
    log.info("in /srv/drive_c/users/bob, then (drive_c/users/bob) and drive_c/users/Public,")
    log.info("/mnt/alice/x and /mnt/alicea/x; alice and alice.cfg stay as they are")
    text = path.read_text(encoding="utf-8")
    assert "~/prefix/drive_c/users/<user>/Saves" in text
    assert "drive_c/users/<user>, then (drive_c/users/<user>) and drive_c/users/Public," in text
    assert "/mnt/<user>/x and /mnt/alicea/x; alice and alice.cfg stay as they are" in text



def test_paths_end_at_punctuation_and_in_windows_form(tmp_path: Path, root_restored: None,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home" / "a.smith"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(logsetup.getpass, "getuser", lambda: "asmith")
    path = setup_logging(tmp_path / "state", crash_trace=False)
    log = logging.getLogger("project_reforged_linux.runner")
    log.warning("could not read %s: denied (%s)", home, home)
    log.warning(r"couldn't start C:\users\asmith\AppData and Z:\home\asmith\games")
    log.info("files on /media/asmith/usb, Public in C:\\users\\Public\\x")
    text = path.read_text(encoding="utf-8")
    assert "a.smith" not in text and "asmith" not in text
    assert "could not read ~: denied (~)" in text
    assert r"C:\users\<user>\AppData and Z:\home\<user>\games" in text
    assert "/media/<user>/usb" in text and "C:\\users\\Public\\x" in text


@pytest.mark.parametrize("login", ["user", "build", "system"])
def test_a_common_word_as_login_leaves_the_words_alone(tmp_path: Path, root_restored: None,
                                                       monkeypatch: pytest.MonkeyPatch,
                                                       login: str) -> None:
    monkeypatch.setattr(logsetup.getpass, "getuser", lambda: login)
    path = setup_logging(tmp_path / "state", crash_trace=False)
    logging.getLogger("project_reforged_linux.x").info(
        "build: Windows build with system wine in /p/drive_c/users/%s/Saves", login)
    text = path.read_text(encoding="utf-8")
    assert "build: Windows build with system wine in /p/drive_c/users/<user>/Saves" in text


@pytest.mark.parametrize("error", [KeyError("uid"), OSError("no login"), ImportError("pwd")])
def test_no_login_to_find_still_writes_the_log(tmp_path: Path, root_restored: None,
                                               monkeypatch: pytest.MonkeyPatch,
                                               error: Exception) -> None:
    def no_login() -> str:
        raise error
    monkeypatch.setattr(logsetup.getpass, "getuser", no_login)
    path = setup_logging(tmp_path / "state", crash_trace=False)
    logging.getLogger("project_reforged_linux.x").info("still here in drive_c/users/bob/x")
    assert "still here in drive_c/users/<user>/x" in path.read_text(encoding="utf-8")


def test_an_exception_no_one_caught_lands_in_the_log(tmp_path: Path, root_restored: None) -> None:
    # A slot's exception reaches only sys.excepthook; from the desktop, nothing else sees it.
    path = setup_logging(tmp_path / "state", crash_trace=False)
    try:
        raise PermissionError("settings.json: permission denied")
    except PermissionError as error:
        sys.excepthook(type(error), error, error.__traceback__)
    text = "\n".join(lines(path))
    assert "[CRITICAL]" in text and "uncaught exception" in text
    assert "PermissionError: settings.json: permission denied" in text
    assert "Traceback" in text
