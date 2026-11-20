# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""His game's name is spelled in one place."""

import ast
from pathlib import Path

import project_reforged_linux
from project_reforged_linux import GAME_NAME, LAUNCHER_NAME

PACKAGE = Path(project_reforged_linux.__file__).parent


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


def spellings(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstrings(tree)
    return [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in skip and GAME_NAME in node.value]


def test_the_names() -> None:
    assert GAME_NAME == "Project Reforged"
    assert LAUNCHER_NAME == f"{GAME_NAME} Linux Launcher"


def test_no_module_spells_the_game_name_itself() -> None:
    found = {str(path.relative_to(PACKAGE)): lines
             for path in sorted(PACKAGE.rglob("*.py"))
             if (lines := spellings(path)) and path.name != "__init__.py"}
    assert found == {}


def test_the_scan_sees_a_spelling_and_skips_a_docstring(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text('"""About Project Reforged."""\n'
                     'x = "Install Project Reforged first"\n'
                     'y = f"Start {name}."\n', encoding="utf-8")
    assert spellings(probe) == [2]
