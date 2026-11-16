# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import pytest

from project_reforged_linux import PART_NUMBER, RELEASE_DATE, __version__
from project_reforged_linux.app import main


def test_version_needs_no_display(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.strip() == (
        f"project-reforged-linux {__version__} ({PART_NUMBER}-{RELEASE_DATE})")


def test_help_needs_no_display(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0
    assert "Project Reforged" in capsys.readouterr().out


def test_unknown_option_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--no-such-option"])
    assert stop.value.code == 2


def test_release_date_is_a_real_day() -> None:
    from datetime import datetime

    assert len(RELEASE_DATE) == 8 and RELEASE_DATE.isdigit()
    datetime.strptime(RELEASE_DATE, "%Y%m%d")
