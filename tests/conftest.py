# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import os
import socket
from pathlib import Path

import pytest


@pytest.fixture
def xdg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every XDG base directory into tmp_path so no test touches the real home."""
    for var, sub in (
        ("XDG_DATA_HOME", "data"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_STATE_HOME", "state"),
    ):
        target = tmp_path / sub
        target.mkdir()
        monkeypatch.setenv(var, str(target))
    return tmp_path


@pytest.fixture(autouse=True)
def no_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs offline unless it is marked network; net.py is tested with fakes."""
    if request.node.get_closest_marker("network") is not None:
        return

    def refuse(*args: object, **kwargs: object) -> None:
        raise RuntimeError("a test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# Qt draws into memory in tests; no display needed.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
