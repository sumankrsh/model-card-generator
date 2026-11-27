from __future__ import annotations

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


@pytest.fixture
def examples(tmp_path: Path) -> Path:
    """A private copy of examples/, so tests can change files freely."""
    dest = tmp_path / "examples"
    shutil.copytree(EXAMPLES, dest)
    return dest


def write_predictions(path: Path, rows: list[tuple[int, float, str]]) -> None:
    lines = ["label,score,group"] + [f"{y},{s},{g}" for y, s, g in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
