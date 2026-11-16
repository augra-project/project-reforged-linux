# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Real Wine on the desktop.

Run: tools/mypython -m pytest -m integration tests/test_integration_wine.py
"""

import os
import pwd
from pathlib import Path

import pytest

from project_reforged_linux.runtimes import check, system_candidate
from project_reforged_linux.wineprefix import (
    create_prefix,
    find_wine_user,
    prefix_ready,
)

pytestmark = pytest.mark.integration


def test_system_wine_creates_a_prefix(tmp_path: Path) -> None:
    found = system_candidate()
    assert found is not None
    prefix = tmp_path / "prefix"
    prefix.mkdir(mode=0o700)
    create_prefix(check(found, os.environ).runtime, prefix, os.environ)
    assert prefix_ready(prefix)
    assert find_wine_user(prefix) == pwd.getpwuid(os.getuid()).pw_name


def test_the_desktops_wine_is_usable() -> None:
    found = system_candidate()
    assert found is not None
    checked = check(found, os.environ)
    assert checked.usable, checked.problem
    assert checked.version is not None and checked.version >= (10, 0)
