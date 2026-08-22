"""Static-analysis helpers for the constitution tests.

These tests assert architectural facts, so they read the source rather than
running it. The checks are direct-import checks, not full transitive reachability
analysis — that is a deliberate trade. A direct-import check is fast, has no
false positives, and catches the realistic failure: somebody adds `import httpx`
to a strategy module because it was convenient at the time.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "goldbot"
REPO = Path(__file__).resolve().parents[2]


def modules_in(package: str) -> list[Path]:
    """Every .py file in a package under src/goldbot."""
    root = SRC / package if package else SRC
    return sorted(p for p in root.rglob("*.py") if p.name != "__init__.py")


def imported_names(path: Path) -> set[str]:
    """Top-level module names imported by a file, plus dotted `from` targets."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
                found.add(node.module.split(".")[0])
                for alias in node.names:
                    found.add(f"{node.module}.{alias.name}")
    return found


def attribute_chains(path: Path) -> set[str]:
    """Dotted attribute expressions such as `datetime.now` or `time.time`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            parts: list[str] = [node.attr]
            current: ast.expr = node.value
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                found.add(".".join(reversed(parts)))
    return found


def called_names(path: Path) -> set[str]:
    """Bare function names that get called, e.g. `open(...)`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            found.add(node.func.id)
    return found


def rel(path: Path) -> str:
    return str(path.relative_to(REPO)).replace("\\", "/")
