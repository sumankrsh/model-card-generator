from __future__ import annotations

from pathlib import Path

from model_card_generator.fairness import FairnessConfig, analyse
from model_card_generator.manifest import load_predictions

from .conftest import write_predictions


def make(tmp_path: Path, rows) -> object:
    p = tmp_path / "p.csv"
    write_predictions(p, rows)
    return load_predictions(p, {"label_column": "label", "score_column": "score", "groups": ["group"]})


def balanced(group: str, n: int, tpr: float) -> list[tuple[int, float, str]]:
    """n positives with the given true positive rate, plus n negatives all scored low."""
    hits = round(n * tpr)
    rows = [(1, 0.9, group)] * hits + [(1, 0.1, group)] * (n - hits)
    return rows + [(0, 0.1, group)] * n


def test_clear_true_positive_rate_gap_is_high_severity(tmp_path):
    pred = make(tmp_path, balanced("A", 300, 0.8) + balanced("B", 300, 0.4))
    slices, gaps = analyse(pred, {"group": "A"}, FairnessConfig())
    tpr_gaps = [g for g in gaps if g.metric == "tpr"]
    assert len(tpr_gaps) == 1
    g = tpr_gaps[0]
    assert g.value == "B" and g.reference == "A"
    assert g.measure < -0.35 and g.clear and g.severity == "high"
    # Selection rate is halved too, so the four-fifths rule flags it as well.
    assert any(x.metric == "selection_rate" for x in gaps)


def test_small_slice_gap_is_flagged_but_marked_noise(tmp_path):
    pred = make(tmp_path, balanced("A", 300, 0.8) + balanced("B", 6, 0.5))
    _, gaps = analyse(pred, {"group": "A"}, FairnessConfig())
    g = next(x for x in gaps if x.metric == "tpr")
    assert g.small and not g.clear and g.severity == "medium"
    assert "may be noise" in g.describe() and "small slice" in g.describe()


def test_no_gap_when_slices_match(tmp_path):
    pred = make(tmp_path, balanced("A", 200, 0.7) + balanced("B", 200, 0.7))
    _, gaps = analyse(pred, None, FairnessConfig())
    assert gaps == []


def test_reference_defaults_to_largest_slice(tmp_path):
    pred = make(tmp_path, balanced("small", 50, 0.7) + balanced("big", 400, 0.7))
    slices, _ = analyse(pred, None, FairnessConfig())
    ref = [s.value for s in slices["group"] if s.is_reference]
    assert ref == ["big"]


def test_higher_tpr_than_reference_is_not_flagged(tmp_path):
    pred = make(tmp_path, balanced("A", 300, 0.5) + balanced("B", 300, 0.9))
    _, gaps = analyse(pred, {"group": "A"}, FairnessConfig())
    assert not [g for g in gaps if g.metric == "tpr"]
