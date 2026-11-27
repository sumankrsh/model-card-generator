"""Binary classification metrics computed from labels and scores, in plain Python.

Every number in a card comes from here, so the functions are small and exact:
no sampling, no randomness, the same input always gives the same output.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Confusion:
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def positives(self) -> int:
        return self.tp + self.fn

    @property
    def negatives(self) -> int:
        return self.tn + self.fp

    @property
    def predicted_positive(self) -> int:
        return self.tp + self.fp


def confusion(labels: Sequence[int], preds: Sequence[int]) -> Confusion:
    if len(labels) != len(preds):
        raise ValueError("labels and predictions must be the same length")
    tp = fp = tn = fn = 0
    for y, p in zip(labels, preds, strict=True):
        if y and p:
            tp += 1
        elif p:
            fp += 1
        elif y:
            fn += 1
        else:
            tn += 1
    return Confusion(tp, fp, tn, fn)


def ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion k/n. None when n is 0."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def auc(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    """Area under the ROC curve via the rank-sum (Mann-Whitney U), ties averaged."""
    pos = sum(1 for y in labels if y)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    rank_sum = sum(r for r, y in zip(ranks, labels, strict=True) if y)
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def brier(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    if not labels:
        return None
    return sum((s - y) ** 2 for y, s in zip(labels, scores, strict=True)) / len(labels)


def ece(labels: Sequence[int], scores: Sequence[float], bins: int = 10) -> float | None:
    """Expected calibration error with equal-width bins over [0, 1]."""
    if not labels:
        return None
    totals = [0] * bins
    conf = [0.0] * bins
    hits = [0] * bins
    for y, s in zip(labels, scores, strict=True):
        b = min(int(s * bins), bins - 1)
        totals[b] += 1
        conf[b] += s
        hits[b] += y
    n = len(labels)
    return sum(abs(hits[b] / totals[b] - conf[b] / totals[b]) * totals[b] / n for b in range(bins) if totals[b])


METRIC_LABELS = {
    "auc": "AUC (ROC)",
    "accuracy": "Accuracy",
    "precision": "Precision",
    "recall": "Recall (true positive rate)",
    "specificity": "Specificity",
    "f1": "F1",
    "fpr": "False positive rate",
    "selection_rate": "Selection rate",
    "brier": "Brier score",
    "ece": "Calibration error (ECE)",
}


def binary_metrics(labels: Sequence[int], preds: Sequence[int], scores: Sequence[float] | None = None) -> dict:
    """All headline metrics. Score-based metrics are None when there are no scores."""
    c = confusion(labels, preds)
    precision = ratio(c.tp, c.predicted_positive)
    recall = ratio(c.tp, c.positives)
    f1 = None
    if precision is not None and recall is not None and precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    out = {
        "rows": c.n,
        "positives": c.positives,
        "prevalence": ratio(c.positives, c.n),
        "confusion": {"tp": c.tp, "fp": c.fp, "tn": c.tn, "fn": c.fn},
        "accuracy": ratio(c.tp + c.tn, c.n),
        "precision": precision,
        "recall": recall,
        "specificity": ratio(c.tn, c.negatives),
        "f1": f1,
        "fpr": ratio(c.fp, c.negatives),
        "selection_rate": ratio(c.predicted_positive, c.n),
        "auc": None,
        "brier": None,
        "ece": None,
    }
    if scores is not None:
        out["auc"] = auc(labels, scores)
        out["brier"] = brier(labels, scores)
        out["ece"] = ece(labels, scores)
    return out


def check_threshold(value: float | None, rule: dict) -> bool | None:
    """True if value meets {min: x} and/or {max: y}; None if value is missing."""
    if value is None:
        return None
    if "min" in rule and value < float(rule["min"]):
        return False
    if "max" in rule and value > float(rule["max"]):
        return False
    return True


def describe_rule(rule: dict) -> str:
    parts = []
    if "min" in rule:
        parts.append(f"≥ {float(rule['min']):.3f}")
    if "max" in rule:
        parts.append(f"≤ {float(rule['max']):.3f}")
    return " and ".join(parts)
