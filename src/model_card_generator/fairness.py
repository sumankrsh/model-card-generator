"""Performance by group: per-slice rates and the gaps against a reference slice.

Three comparisons are made for every slice against its group's reference slice:

- selection rate ratio (slice / reference), flagged below ``min_ratio`` (the
  "four-fifths" rule of thumb when min_ratio is 0.8);
- true positive rate difference (equal opportunity), flagged above ``max_gap``;
- false positive rate difference, flagged above ``max_gap``.

A flagged gap is "clear" when the 95% Wilson intervals of the two rates don't
overlap, and "may be noise" when they do. Slices under ``min_slice_rows`` are
reported but marked small.
"""

from __future__ import annotations

from dataclasses import dataclass

from .manifest import Predictions
from .metrics import confusion, ratio, wilson


@dataclass
class Slice:
    group: str
    value: str
    rows: int
    positives: int
    selected: int
    selection_rate: float | None
    selection_ci: tuple[float, float] | None
    tpr: float | None
    tpr_ci: tuple[float, float] | None
    fpr: float | None
    fpr_ci: tuple[float, float] | None
    precision: float | None
    is_reference: bool = False
    small: bool = False


@dataclass
class Gap:
    group: str
    value: str
    reference: str
    metric: str  # "selection_rate", "tpr" or "fpr"
    slice_value: float
    reference_value: float
    measure: float  # ratio for selection_rate, difference for tpr/fpr
    clear: bool
    small: bool

    @property
    def label(self) -> str:
        return {
            "selection_rate": "selection rate ratio",
            "tpr": "true positive rate gap",
            "fpr": "false positive rate gap",
        }[self.metric]

    @property
    def severity(self) -> str:
        return "high" if self.clear and not self.small else "medium"

    def describe(self) -> str:
        if self.metric == "selection_rate":
            shown = f"{self.measure:.2f}"
        else:
            shown = f"{self.measure:+.3f}"
        verdict = "clear" if self.clear else "may be noise"
        size = ", small slice" if self.small else ""
        return (
            f"{self.group}={self.value}: {self.label} {shown} vs {self.reference} "
            f"({self.slice_value:.3f} vs {self.reference_value:.3f}; {verdict}{size})"
        )


@dataclass
class FairnessConfig:
    max_gap: float = 0.05
    min_ratio: float = 0.8
    min_slice_rows: int = 100

    @classmethod
    def from_dict(cls, d: dict | None) -> FairnessConfig:
        d = d or {}
        return cls(
            max_gap=float(d.get("max_gap", cls.max_gap)),
            min_ratio=float(d.get("min_ratio", cls.min_ratio)),
            min_slice_rows=int(d.get("min_slice_rows", cls.min_slice_rows)),
        )


def _overlap(a: tuple[float, float] | None, b: tuple[float, float] | None) -> bool:
    if a is None or b is None:
        return True
    return a[0] <= b[1] and b[0] <= a[1]


def slices_for(pred: Predictions, group: str, reference: str | None, cfg: FairnessConfig) -> list[Slice]:
    values = pred.groups[group]
    buckets: dict[str, list[int]] = {}
    for i, v in enumerate(values):
        buckets.setdefault(v, []).append(i)
    if reference is None:
        # Largest slice; ties broken by name so the choice is stable.
        reference = sorted(buckets, key=lambda v: (-len(buckets[v]), v))[0]
    elif reference not in buckets:
        raise ValueError(f"reference slice {reference!r} not found in column {group!r}")
    out = []
    for value in sorted(buckets):
        idx = buckets[value]
        c = confusion([pred.labels[i] for i in idx], [pred.preds[i] for i in idx])
        out.append(
            Slice(
                group=group,
                value=value,
                rows=c.n,
                positives=c.positives,
                selected=c.predicted_positive,
                selection_rate=ratio(c.predicted_positive, c.n),
                selection_ci=wilson(c.predicted_positive, c.n),
                tpr=ratio(c.tp, c.positives),
                tpr_ci=wilson(c.tp, c.positives),
                fpr=ratio(c.fp, c.negatives),
                fpr_ci=wilson(c.fp, c.negatives),
                precision=ratio(c.tp, c.predicted_positive),
                is_reference=value == reference,
                small=c.n < cfg.min_slice_rows,
            )
        )
    return out


def gaps_for(slices: list[Slice], cfg: FairnessConfig) -> list[Gap]:
    ref = next(s for s in slices if s.is_reference)
    gaps: list[Gap] = []
    for s in slices:
        if s.is_reference:
            continue
        if s.selection_rate is not None and ref.selection_rate:
            r = s.selection_rate / ref.selection_rate
            if r < cfg.min_ratio:
                gaps.append(
                    Gap(
                        s.group,
                        s.value,
                        ref.value,
                        "selection_rate",
                        s.selection_rate,
                        ref.selection_rate,
                        r,
                        not _overlap(s.selection_ci, ref.selection_ci),
                        s.small,
                    )
                )
        for metric, ci in (("tpr", "tpr_ci"), ("fpr", "fpr_ci")):
            a, b = getattr(s, metric), getattr(ref, metric)
            if a is None or b is None:
                continue
            diff = a - b
            # A lower TPR or a higher FPR than the reference is the harmful direction.
            harmful = -diff if metric == "tpr" else diff
            if harmful > cfg.max_gap:
                gaps.append(
                    Gap(
                        s.group,
                        s.value,
                        ref.value,
                        metric,
                        a,
                        b,
                        diff,
                        not _overlap(getattr(s, ci), getattr(ref, ci)),
                        s.small,
                    )
                )
    return gaps


def analyse(
    pred: Predictions, references: dict | None, cfg: FairnessConfig
) -> tuple[dict[str, list[Slice]], list[Gap]]:
    references = references or {}
    all_slices: dict[str, list[Slice]] = {}
    all_gaps: list[Gap] = []
    for group in pred.groups:
        ref = references.get(group)
        sl = slices_for(pred, group, None if ref is None else str(ref), cfg)
        all_slices[group] = sl
        all_gaps.extend(gaps_for(sl, cfg))
    return all_slices, all_gaps
