"""Record real CLI output into docs/demo.svg.

Run from the project root:  python scripts/make_demo.py

It builds the card for the synthetic claims-fraud model, then checks the
hand-written example card, and saves what the terminal showed.
"""

from __future__ import annotations

import io
import os
import shlex
from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from model_card_generator import cli

ROOT = Path(__file__).resolve().parents[1]


def run(console: Console, command: str) -> None:
    console.print(f"[bold green]$[/bold green] [bold]{command}[/bold]")
    result = CliRunner().invoke(cli.app, shlex.split(command)[1:])
    if result.exception and not isinstance(result.exception, SystemExit):
        raise result.exception
    console.print()


def main() -> None:
    console = Console(record=True, width=118, file=io.StringIO(), force_terminal=True, highlight=False)
    cli.console = console
    os.chdir(ROOT)
    try:
        run(console, "model-card build examples/claims-fraud/model.yaml --markdown MODEL_CARD.md --html card.html")
        run(console, "model-card check examples/hand-written-card.md")
    finally:
        for name in ("MODEL_CARD.md", "card.html"):
            (ROOT / name).unlink(missing_ok=True)
    (ROOT / "docs").mkdir(exist_ok=True)
    console.save_svg(str(ROOT / "docs" / "demo.svg"), title="model-card-generator")
    print("wrote docs/demo.svg")


if __name__ == "__main__":
    main()
