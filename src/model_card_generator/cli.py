"""Command-line interface: ``model-card build | check | init | profiles``."""

from __future__ import annotations

import datetime as dt
from importlib import resources
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .card import Card, build, fmt, to_json
from .check import CheckResult, check_markdown
from .html import markdown_to_html
from .manifest import ManifestError, load
from .metrics import METRIC_LABELS, describe_rule
from .profiles import PROFILES, SECTIONS, get_profile
from .risk import metric_results

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Audit-ready model cards and model-risk summaries, offline.",
)
console = Console(highlight=False)

SEV_STYLE = {"high": "bold red", "medium": "yellow", "low": "dim"}
STATUS_TEXT = {
    "missing": "missing",
    "empty": "heading only, no content",
    "placeholder": "placeholder text",
}


def _date(value: str | None) -> dt.date | None:
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter(f"{value!r} is not a YYYY-MM-DD date") from None


def _profile(name: str):
    try:
        return get_profile(name)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from None


def print_card(card: Card) -> None:
    m = card.manifest
    head = f"[bold]{m.name}[/bold]" + (f" v{m.version}" if m.version else "")
    console.print(f"{head} · owner {m.get('model.owner') or 'not named'} · as of {card.as_of.isoformat()}")
    if card.metrics_source == "computed" and m.predictions:
        p = m.predictions
        console.print(
            f"Computed from {p.path.name}: {p.rows:,} rows, {card.metrics['positives']:,} positives, "
            f"{len(p.groups)} group column{'s' if len(p.groups) != 1 else ''}"
        )
    else:
        console.print("Metrics as reported in the manifest (no predictions file, nothing recomputed)")

    t = Table(title="Metrics", title_justify="left", show_edge=False, pad_edge=False)
    t.add_column("Metric")
    t.add_column("Value", justify="right")
    t.add_column("Threshold")
    t.add_column("Result")
    for key, value, rule, passed in metric_results(m, card.metrics):
        result = "" if passed is None else ("pass" if passed else "[bold red]FAIL[/bold red]")
        t.add_row(METRIC_LABELS.get(key, key), fmt(value), describe_rule(rule) if rule else "", result)
    console.print()
    console.print(t)

    if card.slices:
        console.print()
        n_slices = sum(len(s) for s in card.slices.values())
        console.print(f"[bold]Performance by group[/bold]: {n_slices} slices, {len(card.gaps)} gaps flagged")
        for g in card.gaps:
            style = SEV_STYLE[g.severity]
            console.print(f"  [{style}]{g.severity:<6}[/{style}] {g.describe()}")

    tier = card.tier
    console.print()
    if tier.tier:
        why = ", ".join(f"{a.lower()} {b}" for a, b, _ in tier.reasons)
        console.print(f"[bold]Risk tier: {tier.label}[/bold] (score {tier.score} of 13: {why})")
    else:
        console.print(f"[bold]Risk tier: not rated[/bold] (missing {', '.join(tier.missing)})")

    c = card.counts()
    console.print(f"[bold]Findings[/bold]: {c['high']} high, {c['medium']} medium, {c['low']} low")
    for f in card.findings:
        if f.severity == "low" or f.area == "Performance by group":
            continue  # gaps are listed above; low findings are in the card
        style = SEV_STYLE[f.severity]
        console.print(f"  [{style}]{f.severity:<6}[/{style}] {f.area}: {f.text}")
    if c["low"]:
        console.print(f"  [dim]{c['low']} low findings are listed in the card[/dim]")

    chk = card.check
    if chk:
        done = sum(r.ok for r in chk.results)
        style = "green" if chk.passed else "yellow"
        console.print()
        console.print(
            f"[{style}]Profile {chk.profile}: {done} of {len(chk.results)} required sections complete[/{style}]"
        )
        if chk.failures:
            console.print("  needs content: " + ", ".join(r.title for r in chk.failures))


@app.command("build")
def build_cmd(
    manifest: Path = typer.Argument(..., help="Model manifest (YAML)."),
    markdown: Path | None = typer.Option(None, "--markdown", "-o", help="Write the card as Markdown."),
    html: Path | None = typer.Option(None, "--html", help="Write the card as a single-file HTML page."),
    json_out: Path | None = typer.Option(None, "--json", help="Write metrics, gaps, tier and findings as JSON."),
    profile: str = typer.Option(
        "model-risk", "--profile", "-p", help="Section profile: core, model-risk or eu-ai-act."
    ),
    as_of: str | None = typer.Option(
        None, "--as-of", help="Date to judge staleness and overdue reviews (YYYY-MM-DD). Default: today."
    ),
    strict: bool = typer.Option(False, "--strict", help="Exit 1 on any high finding or missing required section."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Only print the files written."),
) -> None:
    """Build a model card and model-risk summary from a manifest."""
    _profile(profile)
    try:
        m = load(manifest)
        card = build(m, profile=profile, as_of=_date(as_of))
    except (ManifestError, ValueError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(2) from None
    if not quiet:
        print_card(card)
    written = []
    if markdown:
        markdown.write_text(card.markdown, encoding="utf-8")
        written.append(markdown)
    if html:
        title = f"Model card: {m.name}" + (f" v{m.version}" if m.version else "")
        html.write_text(markdown_to_html(card.markdown, title), encoding="utf-8")
        written.append(html)
    if json_out:
        json_out.write_text(to_json(card) + "\n", encoding="utf-8")
        written.append(json_out)
    if written:
        if not quiet:
            console.print()
        for p in written:
            console.print(f"wrote {p}")
    if strict and (card.counts()["high"] or (card.check and not card.check.passed)):
        if not quiet:
            console.print("[red]--strict: high findings or missing sections[/red]")
        raise typer.Exit(1)


def print_check(result: CheckResult, github: bool) -> None:
    done = sum(r.ok for r in result.results)
    t = Table(show_edge=False, pad_edge=False)
    t.add_column("Section")
    t.add_column("Status")
    t.add_column("Found as, or why it's required")
    for r in result.results:
        status = "[green]ok[/green]" if r.ok else f"[red]{STATUS_TEXT[r.status]}[/red]"
        if r.ok:
            found = f"{r.heading} (line {r.line})"
        else:
            found = (f"line {r.line}: " if r.line else "") + f"[dim]{r.reference}[/dim]"
        t.add_row(r.title, status, found)
    console.print(f"[bold]{result.path}[/bold] against profile [bold]{result.profile}[/bold]")
    console.print(t)
    style = "green" if result.passed else "red"
    console.print(f"[{style}]{done} of {len(result.results)} required sections complete[/{style}]")
    if github:
        for r in result.failures:
            line = f",line={r.line}" if r.line else ""
            print(f"::error file={result.path}{line}::{r.title}: {STATUS_TEXT[r.status]} ({r.reference})")


@app.command("check")
def check_cmd(
    cards: list[Path] = typer.Argument(..., help="Markdown model card(s) to check."),
    profile: str = typer.Option(
        "model-risk", "--profile", "-p", help="Section profile: core, model-risk or eu-ai-act."
    ),
    github: bool = typer.Option(False, "--github", help="Also print GitHub Actions error annotations."),
) -> None:
    """Fail (exit 1) when a model card is missing required sections. Works on hand-written cards too."""
    prof = _profile(profile)
    failed = False
    for i, path in enumerate(cards):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            console.print(f"[red]error:[/red] can't read {path}: {exc.strerror}")
            raise typer.Exit(2) from None
        result = check_markdown(text, prof, path=str(path))
        if i:
            console.print()
        print_check(result, github)
        failed = failed or not result.passed
    if failed:
        raise typer.Exit(1)


@app.command("init")
def init_cmd(
    path: Path = typer.Argument(Path("model.yaml"), help="Where to write the starter manifest."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file."),
) -> None:
    """Write a starter manifest with every field the card uses."""
    if path.exists() and not force:
        console.print(f"[red]error:[/red] {path} exists; use --force to overwrite")
        raise typer.Exit(2)
    text = resources.files("model_card_generator").joinpath("template.yaml").read_text(encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    console.print(f"wrote {path}. Fill it in, then: model-card build {path} --markdown MODEL_CARD.md")


@app.command("profiles")
def profiles_cmd(name: str | None = typer.Argument(None, help="Show one profile's sections.")) -> None:
    """List the section profiles and what each one requires."""
    names = [name] if name else list(PROFILES)
    for i, n in enumerate(names):
        p = _profile(n)
        if i:
            console.print()
        console.print(f"[bold]{p.name}[/bold]: {p.summary} ({len(p.requirements)} sections)")
        for r in p.requirements:
            console.print(f"  {SECTIONS[r.section].title:<28} {r.reference}")


def _version(value: bool) -> None:
    if value:
        console.print(f"model-card-generator {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Show the version."),
) -> None:
    pass


def main() -> None:
    app()
