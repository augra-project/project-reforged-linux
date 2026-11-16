# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
"""No module but net.py reaches for the network."""

import ast
from collections.abc import Iterator
from pathlib import Path

import project_reforged_linux

PACKAGE = Path(project_reforged_linux.__file__).parent
NETWORK_MODULES = ("socket", "ssl", "http", "urllib.request", "urllib.error", "urllib3",
                   "requests", "httpx", "aiohttp", "asyncio", "ftplib", "smtplib",
                   "kista.http")


def _imports(tree: ast.AST) -> Iterator[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


def _is_network(name: str) -> bool:
    return name == "urllib" or any(name == m or name.startswith(m + ".") for m in NETWORK_MODULES)


def test_only_net_imports_network_modules() -> None:
    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name == "net.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders += [f"{path.name}: {name}" for name in _imports(tree) if _is_network(name)]
    assert offenders == []


def test_the_check_sees_a_violation() -> None:
    tree = ast.parse("from urllib import request\nimport http.client\n"
                     "from kista.http import session_for\nfrom kista.fileops import write_atomic\n")
    assert [n for n in _imports(tree) if _is_network(n)] == [
        "urllib", "urllib.request", "http.client", "kista.http", "kista.http.session_for"]
