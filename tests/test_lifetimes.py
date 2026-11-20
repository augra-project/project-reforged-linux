# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Every window and dialog dies with its last reference, never by Python's cycle collector.

PySide 6.11 crashes collecting widget graphs held by a lambda over self; bound methods
connected to signals do not hold the widget.
"""

import gc
import weakref
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget

from project_reforged_linux.builds import Build
from project_reforged_linux.nativecheck import NativeCheck
from project_reforged_linux.paths import ensure_dirs, resolve
from project_reforged_linux.settings import LauncherSettings
from project_reforged_linux.ui import theme
from project_reforged_linux.ui.about import AboutDialog
from project_reforged_linux.ui.controller import LauncherController
from project_reforged_linux.ui.firststart import FirstStartDialog
from project_reforged_linux.ui.options import OptionsDialog, OptionsState
from project_reforged_linux.ui.window import MainWindow

STATE = OptionsState(LauncherSettings(), NativeCheck((2, 41), True, True, True),
                     Build.LINUX_APPIMAGE, "0.2.48", True, None, False)


def makers(xdg_home: Path) -> dict[str, Callable[[], QWidget]]:
    fonts = theme.load_fonts()
    paths = resolve()
    ensure_dirs(paths)
    return {
        "options": lambda: OptionsDialog(fonts, STATE, scan=lambda done: done([]),
                                         set_icon=lambda install: None),
        "about": lambda: AboutDialog(fonts, open_url=lambda url: None),
        "first start": lambda: FirstStartDialog(fonts, offer_icon=True,
                                                open_url=lambda url: None),
        "window": lambda: MainWindow(None, fonts=fonts),
        "window with controller": lambda: MainWindow(
            LauncherController(paths, synchronous=True), fonts=fonts),
    }


@pytest.mark.parametrize("name", ["options", "about", "first start", "window",
                                  "window with controller"])
def test_dies_with_its_last_reference(qapp, xdg_home: Path, name: str) -> None:  # type: ignore[no-untyped-def]
    widget = makers(xdg_home)[name]()
    widget.show()
    ref = weakref.ref(widget)
    gc.disable()  # the collector must not be what frees it
    try:
        del widget
        assert ref() is None, f"{name} is held by a reference cycle"
    finally:
        gc.enable()
