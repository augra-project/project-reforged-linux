# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
from pathlib import Path

import pytest

from project_reforged_linux.gamesettings import SETTINGS_CFG, write_first_settings


def test_writes_the_one_line(tmp_path: Path) -> None:
    assert write_first_settings(tmp_path) is True
    assert (tmp_path / SETTINGS_CFG).read_bytes() == b"graphics_driver = vulkan\r\n"


def test_never_touches_an_existing_file(tmp_path: Path) -> None:
    his = b"graphics_driver = direct3d12    # the player's choice\r\n"
    (tmp_path / SETTINGS_CFG).write_bytes(his)
    assert write_first_settings(tmp_path) is False
    assert (tmp_path / SETTINGS_CFG).read_bytes() == his


def test_never_touches_an_empty_file(tmp_path: Path) -> None:
    (tmp_path / SETTINGS_CFG).write_bytes(b"")
    assert write_first_settings(tmp_path) is False
    assert (tmp_path / SETTINGS_CFG).read_bytes() == b""


def test_missing_port_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        write_first_settings(tmp_path / "missing")
