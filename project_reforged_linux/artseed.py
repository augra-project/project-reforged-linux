# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""Seeding one build's art from the other's, so his site serves only what differs.

The art is the same for his Windows and Linux builds: the Linux 0.2.48 took the Windows
0.2.46 set as "all up to date".
"""

import logging
import os
import shutil
import tempfile
from pathlib import Path

from project_reforged_linux.logsetup import home_as_tilde

__all__ = ["ART", "INDEX", "seed_art"]

logger = logging.getLogger(__name__)

ART = "art"
INDEX = "index.txt"  # his list of every picture; a set without it is not complete


def _has_links(folder: Path) -> bool:
    return any(Path(root, name).is_symlink()
               for root, dirs, files in os.walk(folder) for name in (*dirs, *files))


def seed_art(source_port: Path, target_port: Path) -> bool:
    source, target = source_port / ART, target_port / ART
    if target.is_dir() and any(target.iterdir()):
        return False
    if not (source / INDEX).is_file():
        return False
    if _has_links(source):
        logger.warning("not seeding art from %s: it holds links", home_as_tilde(source))
        return False
    target_port.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".art-seed-", dir=target_port))
    try:
        copied = staging / ART
        # copytree keeps file dates through copy2 and folder dates through copystat.
        shutil.copytree(source, copied, copy_function=shutil.copy2)
        if target.is_dir():
            target.rmdir()  # empty, checked above
        os.rename(copied, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    logger.info("seeded the art from %s into %s", home_as_tilde(source), home_as_tilde(target))
    return True
