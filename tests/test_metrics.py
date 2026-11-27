from __future__ import annotations

import pytest

from model_card_generator.metrics import auc, binary_metrics, check_threshold, confusion, ece, wilson


def test_confusion_counts_each_cell():
    c = confusion([1, 1, 0, 0, 1], [1, 0, 1, 0, 1])
    assert (c.tp, c.fn, c.fp, c.tn) == (2, 1, 1, 1)
    assert c.positives == 3 and c.predicted_positive == 3


def test_auc_perfect_random_and_ties():
    assert auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0
    # Every score tied: no ranking information at all.
    assert auc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]) == 0.5
    # Hand-computed: pairs (pos, neg) correctly ordered = 3 of 4.
    assert auc([1, 0, 1, 0], [0.9, 0.3, 0.4, 0.6]) == pytest.approx(0.75)


def test_auc_needs_both_classes():
    assert auc([1, 1], [0.2, 0.3]) is None


def test_wilson_interval_matches_known_values():
    lo, hi = wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-4)
    assert hi == pytest.approx(0.5962, abs=1e-4)
    assert wilson(0, 0) is None
    lo, hi = wilson(0, 10)
    assert lo == 0.0 and hi > 0.2


def test_ece_is_zero_for_perfect_calibration_and_large_when_wrong():
    labels = [1, 0] * 50
    assert ece(labels, [0.5] * 100) == pytest.approx(0.0)
    assert ece([1, 1, 1, 1], [0.05, 0.05, 0.05, 0.05]) == pytest.approx(0.95)


def test_binary_metrics_without_scores_leaves_score_metrics_empty():
    m = binary_metrics([1, 0, 1, 0], [1, 0, 0, 0])
    assert m["precision"] == 1.0 and m["recall"] == 0.5 and m["selection_rate"] == 0.25
    assert m["f1"] == pytest.approx(2 / 3)
    assert m["auc"] is None and m["brier"] is None


def test_threshold_rules():
    assert check_threshold(0.8, {"min": 0.75}) is True
    assert check_threshold(0.7, {"min": 0.75}) is False
    assert check_threshold(0.2, {"max": 0.1}) is False
    assert check_threshold(0.5, {"min": 0.4, "max": 0.6}) is True
    assert check_threshold(None, {"min": 0.1}) is None
