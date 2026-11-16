# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
import subprocess
from pathlib import Path
from typing import Any

import pytest

from project_reforged_linux.paths import AppPaths, ensure_dirs, resolve
from project_reforged_linux.runtimes import (
    MIN_VERSION,
    Candidate,
    Mode,
    Source,
    check,
    mark_prefix,
    prefix_downgrade,
    resolve_runtime,
    scan,
)


def wine_tree(root: Path, layout: str = "lib/wine", *, executable: bool = True,
              server: bool = True) -> Path:
    """A Wine tree on disk; nothing in it is ever run, FakeRun answers instead."""
    (root / "bin").mkdir(parents=True)
    names = ["wine", "wineserver"] if server else ["wine"]
    for name in names:
        tool = root / "bin" / name
        tool.write_text("#!/bin/sh\n", encoding="utf-8")
        tool.chmod(0o755 if executable else 0o644)
    if layout:
        dlls = root / layout / "x86_64-windows"
        dlls.mkdir(parents=True)
        (dlls / "ntdll.dll").write_bytes(b"MZ")
    return root / "bin" / "wine"


class FakeRun:
    """Answers wine --version per binary; None means the call times out."""

    def __init__(self, answers: dict[Path, str | None]) -> None:
        self.answers = answers
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        answer = self.answers.get(Path(command[0]), "")
        if answer is None:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        code = 0 if answer.startswith("wine-") else 1
        return subprocess.CompletedProcess(command, code, answer + "\n", "")


def candidate(wine: Path, source: Source = Source.SYSTEM) -> Candidate:
    return Candidate(source, wine, wine.with_name("wineserver"))


def test_usable_wine(tmp_path: Path) -> None:
    wine = wine_tree(tmp_path / "w")
    run = FakeRun({wine: "wine-10.0 (Debian 10.0~repack-6)"})
    checked = check(candidate(wine), {"LD_PRELOAD": "/opt/remote/lib/libpreload.so", "HOME": "/h"},
                    run=run)
    assert checked.usable and checked.version == (10, 0)
    assert checked.version_text == "wine-10.0 (Debian 10.0~repack-6)"
    (command, kwargs), = run.calls
    assert command == [str(wine), "--version"]
    assert "LD_PRELOAD" not in kwargs["env"]


@pytest.mark.parametrize("layout", ["lib/wine", "lib64/wine", "lib/x86_64-linux-gnu/wine"])
def test_64bit_layouts(tmp_path: Path, layout: str) -> None:
    wine = wine_tree(tmp_path / "w", layout)
    assert check(candidate(wine), {}, run=FakeRun({wine: "wine-10.0"})).usable


def test_32bit_only_wine_is_refused(tmp_path: Path) -> None:
    wine = wine_tree(tmp_path / "w", layout="")
    checked = check(candidate(wine), {}, run=FakeRun({wine: "wine-10.0"}))
    assert not checked.usable and "64-bit" in str(checked.problem)


def test_too_old(tmp_path: Path) -> None:
    wine = wine_tree(tmp_path / "w")
    checked = check(candidate(wine), {}, run=FakeRun({wine: "wine-9.0"}))
    assert not checked.usable and checked.version == (9, 0)
    assert "9.0" in str(checked.problem) and f"{MIN_VERSION[0]}.{MIN_VERSION[1]}" in str(
        checked.problem)


@pytest.mark.parametrize("answer", ["", "not wine", None])
def test_no_proper_answer(tmp_path: Path, answer: str | None) -> None:
    wine = wine_tree(tmp_path / "w")
    assert not check(candidate(wine), {}, run=FakeRun({wine: answer})).usable


def test_missing_wineserver(tmp_path: Path) -> None:
    wine = wine_tree(tmp_path / "w", server=False)
    checked = check(candidate(wine), {}, run=FakeRun({wine: "wine-10.0"}))
    assert not checked.usable and "wineserver" in str(checked.problem)


def test_not_executable(tmp_path: Path) -> None:
    wine = wine_tree(tmp_path / "w", executable=False)
    assert not check(candidate(wine), {}, run=FakeRun({wine: "wine-10.0"})).usable


def test_scan_finds_the_sane_places_only(tmp_path: Path) -> None:
    home, opt = tmp_path / "home", tmp_path / "opt"
    system = wine_tree(tmp_path / "usr")
    staging = wine_tree(opt / "wine-staging")
    lutris = wine_tree(home / ".local/share/lutris/runners/wine/wine-ge-8-26")
    bottles = wine_tree(home / ".local/share/bottles/runners/soda-9.0-1")
    proton = wine_tree(home / ".local/share/Steam/compatibilitytools.d/GE-Proton9-20/files")
    flatpak = wine_tree(home / ".var/app/net.lutris.Lutris/data/lutris/runners/wine/x")
    run = FakeRun({system: "wine-10.0", staging: "wine-10.19 (Staging)",
                   lutris: "wine-8.26", bottles: "wine-9.0"})
    which = {"wine": str(system), "wineserver": str(system.with_name("wineserver"))}.get
    found = scan({}, home=home, opt=opt, which=which, run=run)
    assert [c.candidate.wine for c in found] == [staging, system, bottles, lutris]
    assert [c.usable for c in found] == [True, True, False, False]
    assert {c.candidate.source for c in found} == {Source.SYSTEM, Source.WINEHQ,
                                                   Source.LUTRIS, Source.BOTTLES}
    assert proton not in [c.candidate.wine for c in found]
    assert flatpak not in [c.candidate.wine for c in found]


def test_scan_drops_the_same_wine_twice(tmp_path: Path) -> None:
    opt = tmp_path / "opt"
    stable = wine_tree(opt / "wine-stable")
    (tmp_path / "usr" / "bin").mkdir(parents=True)
    link = tmp_path / "usr" / "bin" / "wine"
    link.symlink_to(stable)
    which = {"wine": str(link), "wineserver": str(stable.with_name("wineserver"))}.get
    found = scan({}, home=tmp_path / "home", opt=opt, which=which,
                 run=FakeRun({link: "wine-10.0", stable: "wine-10.0"}))
    assert [c.candidate.source for c in found] == [Source.SYSTEM]
    assert found[0].usable, found[0].problem


def bundled_env(root: Path) -> dict[str, str]:
    return {"APPDIR": str(root)}


def test_auto_takes_a_usable_system_wine(tmp_path: Path) -> None:
    system = wine_tree(tmp_path / "usr")
    bundled = wine_tree(tmp_path / "appdir" / "opt" / "wine")
    which = {"wine": str(system), "wineserver": str(system.with_name("wineserver"))}.get
    got = resolve_runtime(Mode.AUTO, None, {}, which=which, env=bundled_env(tmp_path / "appdir"),
                          run=FakeRun({system: "wine-10.0", bundled: "wine-10.0"}))
    assert got.checked is not None and got.checked.candidate.source is Source.SYSTEM
    assert got.note is None and got.problem is None


def test_auto_falls_back_to_bundled_and_says_why(tmp_path: Path) -> None:
    system = wine_tree(tmp_path / "usr")
    bundled = wine_tree(tmp_path / "appdir" / "opt" / "wine")
    which = {"wine": str(system), "wineserver": str(system.with_name("wineserver"))}.get
    got = resolve_runtime(Mode.AUTO, None, {}, which=which, env=bundled_env(tmp_path / "appdir"),
                          run=FakeRun({system: "wine-6.0.3", bundled: "wine-10.0"}))
    assert got.checked is not None and got.checked.candidate.source is Source.BUNDLED
    assert got.note is not None and "6.0" in got.note
    assert got.runtime is not None and got.runtime.wine == bundled


def test_auto_without_any_wine(tmp_path: Path) -> None:
    got = resolve_runtime(Mode.AUTO, None, {}, which=lambda name: None, env={},
                          run=FakeRun({}))
    assert got.checked is None and got.runtime is None and got.problem


def test_explicit_system_does_not_fall_back(tmp_path: Path) -> None:
    bundled = wine_tree(tmp_path / "appdir" / "opt" / "wine")
    got = resolve_runtime(Mode.SYSTEM, None, {}, which=lambda name: None,
                          env=bundled_env(tmp_path / "appdir"),
                          run=FakeRun({bundled: "wine-10.0"}))
    assert got.checked is None and got.problem and "system" in got.problem.lower()


def test_explicit_bundled(tmp_path: Path) -> None:
    bundled = wine_tree(tmp_path / "appdir" / "opt" / "wine")
    got = resolve_runtime(Mode.BUNDLED, None, {}, which=lambda name: None,
                          env=bundled_env(tmp_path / "appdir"),
                          run=FakeRun({bundled: "wine-10.0"}))
    assert got.checked is not None and got.checked.candidate.source is Source.BUNDLED


def test_no_bundled_runtime_outside_an_appimage() -> None:
    got = resolve_runtime(Mode.BUNDLED, None, {}, which=lambda name: None, env={},
                          run=FakeRun({}))
    assert got.checked is None and got.problem


def test_chosen_wine(tmp_path: Path) -> None:
    wine = wine_tree(tmp_path / "lutris" / "wine-ge")
    got = resolve_runtime(Mode.CHOSEN, wine, {}, which=lambda name: None, env={},
                          run=FakeRun({wine: "wine-10.4"}))
    assert got.checked is not None and got.checked.candidate.wine == wine


def test_chosen_wine_that_is_gone(tmp_path: Path) -> None:
    got = resolve_runtime(Mode.CHOSEN, tmp_path / "gone" / "bin" / "wine", {},
                          which=lambda name: None, env={}, run=FakeRun({}))
    assert got.checked is None and got.problem


def test_chosen_needs_a_path() -> None:
    with pytest.raises(ValueError):
        resolve_runtime(Mode.CHOSEN, None, {}, which=lambda name: None, env={},
                        run=FakeRun({}))


@pytest.fixture
def paths(xdg_home: Path) -> AppPaths:
    p = resolve()
    ensure_dirs(p)
    return p


def checked_at(tmp_path: Path, text: str) -> Any:
    wine = wine_tree(tmp_path / text.split()[0])
    return check(candidate(wine), {}, run=FakeRun({wine: text}))


def test_prefix_downgrade(paths: AppPaths, tmp_path: Path) -> None:
    newer, older = checked_at(tmp_path, "wine-10.19"), checked_at(tmp_path, "wine-10.0")
    assert prefix_downgrade(paths, older) is None
    mark_prefix(paths, newer)
    assert prefix_downgrade(paths, newer) is None
    warning = prefix_downgrade(paths, older)
    assert warning is not None and "wine-10.19" in warning and "wine-10.0" in warning


def test_mark_prefix_needs_a_usable_runtime(paths: AppPaths, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        mark_prefix(paths, checked_at(tmp_path, "wine-6.0.3"))
