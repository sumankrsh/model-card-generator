"""A draft model risk tier and the list of findings a reviewer should look at.

The tier is a transparent points score, not a judgement:

    score = 2 x decision impact + autonomy + complexity + 1 if it affects individuals

with impact, autonomy and complexity each scored 1-3. A score of 10 or more is
Tier 1 (highest), 7-9 is Tier 2, and anything lower is Tier 3. Every point is
listed in the card so a reviewer can disagree with a specific input.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from .fairness import Gap, Slice
from .manifest import Manifest, parse_date, sha256_file
from .metrics import METRIC_LABELS, check_threshold, describe_rule

IMPACT = {"low": 1, "medium": 2, "high": 3}
AUTONOMY = {"advisory": 1, "human-in-the-loop": 2, "automated": 3}
COMPLEXITY = {"low": 1, "medium": 2, "high": 3}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
STALE_MONTHS = 18
VALIDATION_MAX_MONTHS = 12


@dataclass
class Tier:
    tier: int | None
    score: int | None
    reasons: list[tuple[str, str, int]] = field(default_factory=list)  # (factor, value, points)
    missing: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"Tier {self.tier}" if self.tier else "Not rated"


@dataclass
class Finding:
    severity: str
    area: str
    text: str


def months_between(a: dt.date, b: dt.date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)


def tier_for(m: Manifest) -> Tier:
    risk = m.get("risk") or {}
    t = Tier(None, None)
    factors = [
        ("Decision impact", "decision_impact", IMPACT, 2),
        ("Autonomy", "autonomy", AUTONOMY, 1),
        ("Complexity", "complexity", COMPLEXITY, 1),
    ]
    score = 0
    for label, key, table, weight in factors:
        raw = str(risk.get(key, "")).strip().lower()
        if raw not in table:
            t.missing.append(f"risk.{key} ({' / '.join(table)})")
            continue
        pts = table[raw] * weight
        score += pts
        t.reasons.append((label, raw, pts))
    if "affects_individuals" not in risk:
        t.missing.append("risk.affects_individuals (true / false)")
    else:
        yes = bool(risk["affects_individuals"])
        pts = 1 if yes else 0
        score += pts
        t.reasons.append(("Affects individuals", "yes" if yes else "no", pts))
    if t.missing:
        return t
    t.score = score
    t.tier = 1 if score >= 10 else 2 if score >= 7 else 3
    return t


def metric_results(m: Manifest, metrics: dict) -> list[tuple[str, float | None, dict | None, bool | None]]:
    """(metric, value, rule, passed) for every metric with a value or a threshold."""
    rules = m.get("evaluation.metric_thresholds") or {}
    out = []
    for key in METRIC_LABELS:
        value = metrics.get(key)
        rule = rules.get(key)
        if value is None and rule is None:
            continue
        out.append((key, value, rule, check_threshold(value, rule) if rule else None))
    for key in rules:
        if key not in METRIC_LABELS:
            out.append((key, metrics.get(key), rules[key], check_threshold(metrics.get(key), rules[key])))
    return out


def findings_for(
    m: Manifest,
    metrics: dict,
    slices: dict[str, list[Slice]],
    gaps: list[Gap],
    tier: Tier,
    as_of: dt.date,
) -> list[Finding]:
    f: list[Finding] = []
    add = lambda sev, area, text: f.append(Finding(sev, area, text))  # noqa: E731

    for key, value, rule, passed in metric_results(m, metrics):
        name = METRIC_LABELS.get(key, key)
        if rule and value is None:
            add("medium", "Metrics", f"{name} has a threshold ({describe_rule(rule)}) but no value to check")
        elif passed is False:
            add("high", "Metrics", f"{name} is {value:.3f}, which fails its threshold ({describe_rule(rule)})")

    for g in gaps:
        add(g.severity, "Performance by group", g.describe())
    for group, sl in slices.items():
        for s in sl:
            if s.small:
                add("low", "Performance by group", f"{group}={s.value} has {s.rows} rows, too few to trust its rates")

    if tier.missing:
        add("medium", "Risk tier", "Can't rate the model: missing " + ", ".join(tier.missing))

    if not m.get("intended_use.out_of_scope"):
        add("medium", "Use", "No out-of-scope uses are listed")
    if not m.get("limitations"):
        add("medium", "Limitations", "No limitations are listed")

    for role in ("training", "evaluation"):
        ds = m.get(f"data.{role}") or {}
        if not ds:
            add("medium", "Data", f"No {role} data is described")
            continue
        if not ds.get("owner"):
            add("low", "Data", f"The {role} data has no named owner")
        end = parse_date(ds.get("period"))
        if role == "training" and end and months_between(end, as_of) > STALE_MONTHS:
            add(
                "medium",
                "Data",
                f"Training data ends {end.isoformat()}, more than {STALE_MONTHS} months before {as_of.isoformat()}",
            )
        if ds.get("path"):
            p = m.base / str(ds["path"])
            if not p.exists():
                add("high", "Data", f"The {role} data file {ds['path']} doesn't exist")
            elif ds.get("sha256") and sha256_file(p) != str(ds["sha256"]).lower():
                add("high", "Data", f"The {role} data file {ds['path']} has changed since its hash was recorded")
    if not m.get("lineage"):
        add("medium", "Data", "No data lineage is recorded")

    if m.predictions is None:
        add("medium", "Metrics", "Metrics are reported in the manifest, not recomputed from predictions")
    elif not m.predictions.groups:
        add("medium", "Performance by group", "No group columns are set, so performance by group isn't measured")

    val = m.get("validation") or {}
    if not val:
        add("high" if tier.tier == 1 else "medium", "Validation", "No validation is recorded")
    else:
        if not val.get("independent"):
            sev = "high" if tier.tier == 1 else "medium"
            add(sev, "Validation", "Validation is not marked as independent of the developers")
        vdate = parse_date(val.get("date"))
        if vdate and months_between(vdate, as_of) >= VALIDATION_MAX_MONTHS:
            add("medium", "Validation", f"Last validated {vdate.isoformat()}, {VALIDATION_MAX_MONTHS}+ months ago")
        nxt = parse_date(val.get("next_review"))
        if nxt and nxt < as_of:
            add("high", "Validation", f"The review due {nxt.isoformat()} is overdue")
        for cond in val.get("conditions") or []:
            add("medium", "Validation", f"Open validation condition: {cond}")

    if not m.get("monitoring"):
        add("medium", "Monitoring", "No monitoring plan is recorded")
    if tier.tier == 1 and not m.get("human_oversight"):
        add("high", "Oversight", "A Tier 1 model has no human oversight described")
    if not m.get("approvals"):
        add("medium", "Ownership", "No approvals are recorded")
    if not m.get("model.owner"):
        add("medium", "Ownership", "The model has no named owner")

    f.sort(key=lambda x: SEVERITY_ORDER[x.severity])
    return f


def relpath(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
