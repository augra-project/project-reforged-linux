# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""His settings.cfg: the launcher's one setting before his first start."""

from pathlib import Path

from kista.fileops import write_atomic

__all__ = ["FIRST_SETTINGS", "SETTINGS_CFG", "write_first_settings"]

SETTINGS_CFG = "settings.cfg"
# His own setting since 0.2.31; Wine's Direct3D 12 has no DXIL, so his auto ends on Vulkan anyway.
FIRST_SETTINGS = b"graphics_driver = vulkan\r\n"


def write_first_settings(port_dir: Path) -> bool:
    """True when the file was written; a file that exists is left as it is."""
    target = port_dir / SETTINGS_CFG
    if target.exists():
        return False
    write_atomic(target, FIRST_SETTINGS)
    return True
