from __future__ import annotations

from typer.testing import CliRunner

from model_card_generator.cli import app

runner = CliRunner()


def test_build_writes_all_outputs(examples, tmp_path):
    md, html, js = tmp_path / "card.md", tmp_path / "card.html", tmp_path / "card.json"
    r = runner.invoke(
        app,
        [
            "build",
            str(examples / "claims-fraud" / "model.yaml"),
            "--markdown",
            str(md),
            "--html",
            str(html),
            "--json",
            str(js),
            "--as-of",
            "2026-11-27",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "Risk tier: Tier 1" in r.output
    assert "17 of 17 required sections complete" in r.output
    assert md.read_text().startswith("# Model card: Motor claims fraud triage v2.3.0")
    assert html.exists() and js.exists()


def test_build_strict_fails_on_high_findings(examples):
    r = runner.invoke(
        app, ["build", str(examples / "policy-lapse" / "model.yaml"), "--strict", "--as-of", "2026-11-27"]
    )
    assert r.exit_code == 1
    assert "overdue" in r.output


def test_check_exit_codes_and_github_annotations(examples, tmp_path):
    md = tmp_path / "card.md"
    assert (
        runner.invoke(
            app, ["build", str(examples / "claims-fraud" / "model.yaml"), "-q", "--markdown", str(md)]
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["check", str(md)]).exit_code == 0
    r = runner.invoke(app, ["check", str(examples / "hand-written-card.md"), "--github"])
    assert r.exit_code == 1
    assert "::error file=" in r.output and "line=30::Limitations: placeholder text" in r.output
    r = runner.invoke(app, ["check", str(examples / "hand-written-card.md"), "--profile", "nope"])
    assert r.exit_code == 2


def test_init_then_build(tmp_path):
    path = tmp_path / "model.yaml"
    assert runner.invoke(app, ["init", str(path)]).exit_code == 0
    assert runner.invoke(app, ["init", str(path)]).exit_code == 2  # no overwrite without --force
    r = runner.invoke(app, ["build", str(path), "--profile", "eu-ai-act"])
    assert r.exit_code == 0, r.output
    # The starter manifest has no predictions file or slices, so only performance by group is still empty.
    assert "Profile eu-ai-act: 15 of 16 required sections complete" in r.output
    assert "needs content: Performance by group" in r.output


def test_missing_manifest_is_a_usage_error(tmp_path):
    r = runner.invoke(app, ["build", str(tmp_path / "nope.yaml")])
    assert r.exit_code == 2 and "can't read" in r.output
