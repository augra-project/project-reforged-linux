# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import gc
import os
import socket
import sys
from pathlib import Path

import pytest


@pytest.fixture
def xdg_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME and every XDG base directory into tmp_path: no test touches the real home."""
    for var, sub in (
        ("XDG_DATA_HOME", "data"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_STATE_HOME", "state"),
    ):
        target = tmp_path / sub
        target.mkdir()
        monkeypatch.setenv(var, str(target))
    # His native build lives in ~/.local/share/Shadowkey; no test may reach the real one.
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return tmp_path


@pytest.fixture(autouse=True)
def excepthook_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    """setup_logging sets sys.excepthook; each test gets the one it started with back."""
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)


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


@pytest.fixture(autouse=True)
def no_modal_dialogs(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """A modal dialog in a test waits for a click that never comes; fail with its text instead."""
    if request.node.get_closest_marker("modal") is not None:
        return
    from PySide6.QtWidgets import QDialog, QMessageBox

    def refuse(dialog: QDialog) -> int:
        text = dialog.text() if isinstance(dialog, QMessageBox) else dialog.windowTitle()
        raise AssertionError(f"a modal dialog opened in a test: {text!r}")

    monkeypatch.setattr(QDialog, "exec", refuse)


@pytest.fixture(autouse=True)
def no_window_left_open() -> object:
    """Close every window a test left visible: later tests would paint it while it is garbage."""
    yield
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    for widget in app.topLevelWidgets():
        if widget.isVisible():
            widget.close()


# Kept alive for good: freeing them is what crashes.
_CYCLIC_QT: list[object] = []


@pytest.fixture(autouse=True)
def no_qt_object_in_a_cycle(request: pytest.FixtureRequest) -> object:
    """PySide 6.11 can crash freeing Qt objects in a reference cycle, at exit and some runs only.

    Deferred deletes go first: until then Qt still holds the object, and the cycle would
    surface under a later test.
    """
    yield
    if "qapp" not in request.fixturenames:
        return
    from PySide6.QtCore import QCoreApplication, QEvent, QObject

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.set_debug(gc.DEBUG_SAVEALL)
    try:
        gc.collect()
    finally:
        gc.set_debug(0)
    found = sorted({type(o).__name__ for o in gc.garbage if isinstance(o, QObject)})
    _CYCLIC_QT.extend(gc.garbage)
    gc.garbage.clear()
    if found:
        pytest.fail(f"Qt objects left in a reference cycle: {', '.join(found)}")


# Qt draws into memory in tests; no display needed.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():  # type: ignore[no-untyped-def]
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
