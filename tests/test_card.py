from __future__ import annotations

import datetime as dt
import json

import pytest
import yaml

from model_card_generator.card import build, to_json
from model_card_generator.check import check_markdown
from model_card_generator.html import markdown_to_html
from model_card_generator.manifest import ManifestError, load
from model_card_generator.profiles import PROFILES, get_profile
from model_card_generator.risk import tier_for

AS_OF = dt.date(2026, 11, 27)


def test_claims_example_numbers_come_from_the_predictions_file(examples):
    card = build(load(examples / "claims-fraud" / "model.yaml"), as_of=AS_OF)
    assert card.metrics_source == "computed"
    assert card.metrics["rows"] == 2400
    assert card.metrics["positives"] == 279
    cm = card.metrics["confusion"]
    assert cm["tp"] + cm["fn"] == 279 and sum(cm.values()) == 2400
    assert card.tier.tier == 1 and card.tier.score == 11
    high = [f.text for f in card.findings if f.severity == "high"]
    assert any("70+" in t and "true positive rate" in t for t in high)
    assert any("Calibration error" in t for t in high)
    assert card.check.passed


@pytest.mark.parametrize("profile", list(PROFILES))
def test_full_manifest_passes_every_profile(examples, profile):
    card = build(load(examples / "claims-fraud" / "model.yaml"), profile=profile, as_of=AS_OF)
    assert card.check.passed, [r.title for r in card.check.failures]


def test_generated_card_passes_its_own_check(examples):
    """The card writer and the checker agree: check on the written Markdown gives the same answer."""
    card = build(load(examples / "policy-lapse" / "model.yaml"), as_of=AS_OF)
    again = check_markdown(card.markdown, get_profile("model-risk"))
    assert [r.status for r in again.results] == [r.status for r in card.check.results]
    assert not again.passed


def test_incomplete_manifest_produces_findings(examples):
    card = build(load(examples / "policy-lapse" / "model.yaml"), as_of=AS_OF)
    texts = " | ".join(f.text for f in card.findings)
    assert card.metrics_source == "reported"
    assert "overdue" in texts
    assert "not marked as independent" in texts
    assert "more than 18 months" in texts
    assert "AUC (ROC) is 0.710" in texts
    assert "Not provided" in card.markdown


def test_changed_data_file_is_caught_by_its_hash(examples):
    pred = examples / "claims-fraud" / "predictions.csv"
    pred.write_text(pred.read_text() + "CLM-999999,0,0.0100,30-49,North,broker\n")
    card = build(load(examples / "claims-fraud" / "model.yaml"), as_of=AS_OF)
    assert any("has changed since its hash was recorded" in f.text and f.severity == "high" for f in card.findings)


def test_tier_needs_every_factor(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump({"model": {"name": "x"}, "risk": {"decision_impact": "high"}}))
    t = tier_for(load(p))
    assert t.tier is None and any("autonomy" in x for x in t.missing)
    p.write_text(
        yaml.safe_dump(
            {
                "risk": {
                    "decision_impact": "low",
                    "autonomy": "advisory",
                    "complexity": "low",
                    "affects_individuals": False,
                }
            }
        )
    )
    t = tier_for(load(p))
    assert (t.tier, t.score) == (3, 4)


def test_bad_inputs_raise_clear_errors(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("evaluation:\n  predictions: missing.csv\n  score_column: s\n")
    with pytest.raises(ManifestError, match="can't read predictions"):
        load(p)
    (tmp_path / "bad.csv").write_text("label,score\n1,1.7\n")
    p.write_text("evaluation:\n  predictions: bad.csv\n  score_column: score\n")
    with pytest.raises(ManifestError, match="outside 0-1"):
        load(p)
    p.write_text("- just\n- a list\n")
    with pytest.raises(ManifestError, match="mapping"):
        load(p)


def test_json_and_html_outputs(examples):
    card = build(load(examples / "claims-fraud" / "model.yaml"), as_of=AS_OF)
    doc = json.loads(to_json(card))
    assert doc["risk_tier"]["tier"] == 1 and doc["metrics"]["rows"] == 2400
    assert doc["evidence"][0]["file"] == "predictions.csv" and len(doc["evidence"][0]["sha256"]) == 64
    page = markdown_to_html(card.markdown, "Model card")
    assert page.startswith("<!doctype html>")
    assert "<script" not in page and "http://" not in page and "https://" not in page
    assert '<span class="sev sev-high">high</span>' in page
    assert "<table>" in page
