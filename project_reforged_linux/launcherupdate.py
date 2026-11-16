# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""The opt-in check for a newer launcher on GitHub (off by default)."""

import json
import re

from project_reforged_linux import __version__
from project_reforged_linux.manifest import version_key
from project_reforged_linux.net import Transport

__all__ = ["RELEASES_URL", "UpdateCheckError", "latest_release", "newer_launcher"]

RELEASES_URL = ("https://api.github.com/repos/augra-project/project-reforged-linux/"
                "releases/latest")
_MAX_BYTES = 256 * 1024
_TAG = re.compile(r"^v?(\d+(?:\.\d+){1,3})$")


class UpdateCheckError(Exception):
    """GitHub's answer could not be read."""


def latest_release(transport: Transport, *, timeout: float = 15.0) -> str | None:
    """The newest release's version, or None while there is no release."""
    response = transport.get(RELEASES_URL, {"Accept": "application/vnd.github+json"}, timeout)
    try:
        if response.status == 404:
            return None
        if response.status != 200:
            raise UpdateCheckError(f"HTTP {response.status} from GitHub")
        raw = response.body.read(_MAX_BYTES + 1)
    finally:
        response.close()
    if len(raw) > _MAX_BYTES:
        raise UpdateCheckError("GitHub's answer is larger than expected")
    try:
        data = json.loads(raw)
    except ValueError as error:
        raise UpdateCheckError("GitHub sent something that is not JSON") from error
    tag = data.get("tag_name") if isinstance(data, dict) else None
    match = _TAG.match(tag) if isinstance(tag, str) else None
    if match is None:
        raise UpdateCheckError(f"unexpected release tag: {tag!r}")
    return match.group(1)


def newer_launcher(transport: Transport, current: str = __version__) -> str | None:
    latest = latest_release(transport)
    if latest is None or version_key(latest) <= version_key(current):
        return None
    return latest
