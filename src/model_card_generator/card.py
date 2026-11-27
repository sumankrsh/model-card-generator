"""Build a model card from a manifest and render it as Markdown and JSON."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

from . import __version__
from .check import CheckResult, check_markdown
from .fairness import FairnessConfig, Gap, Slice, analyse
from .manifest import Manifest
from .metrics import METRIC_LABELS, binary_metrics, describe_rule
from .profiles import SECTIONS, get_profile
from .risk import Finding, Tier, findings_for, metric_results, relpath, tier_for

NOT_PROVIDED = "_Not provided._ Ask the model owner before this card is approved."


@dataclass
class Card:
    manifest: Manifest
    as_of: dt.date
    metrics: dict
    metrics_source: str  # "computed" or "reported"
    slices: dict[str, list[Slice]]
    gaps: list[Gap]
    tier: Tier
    findings: list[Finding]
    markdown: str = ""
    check: CheckResult | None = None
    evidence: list[tuple[str, str]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {"high": 0, "medium": 0, "low": 0}
        for f in self.findings:
            out[f.severity] += 1
        return out


def build(manifest: Manifest, profile: str = "model-risk", as_of: dt.date | None = None) -> Card:
    as_of = as_of or dt.date.today()
    prof = get_profile(profile)
    pred = manifest.predictions
    cfg = FairnessConfig.from_dict(manifest.get("fairness"))
    if pred is not None:
        metrics = binary_metrics(pred.labels, pred.preds, pred.scores)
        source = "computed"
        slices, gaps = analyse(pred, manifest.get("evaluation.reference_groups"), cfg)
    else:
        reported = manifest.get("evaluation.metrics") or {}
        metrics = {k: (float(v) if v is not None else None) for k, v in reported.items()}
        source = "reported"
        slices, gaps = {}, []
    tier = tier_for(manifest)
    findings = findings_for(manifest, metrics, slices, gaps, tier, as_of)
    card = Card(manifest, as_of, metrics, source, slices, gaps, tier, findings)
    if pred is not None:
        card.evidence.append((relpath(pred.path, manifest.base), pred.sha256))
    card.markdown = render_markdown(card)
    card.check = check_markdown(card.markdown, prof, path="(generated card)")
    return card


# ---------------------------------------------------------------- formatting


def fmt(v: Any, digits: int = 3) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def esc(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return out


def bullets(items: Any) -> list[str]:
    if not items:
        return [NOT_PROVIDED]
    if isinstance(items, str):
        return [items.strip()]
    return [f"- {str(i).strip()}" for i in items]


def kv(d: Any, labels: dict[str, str] | None = None) -> list[str]:
    if not d:
        return [NOT_PROVIDED]
    if not isinstance(d, dict):
        return [str(d)]
    labels = {"sha256": "SHA-256", **(labels or {})}
    rows = []
    for k, v in d.items():
        if k == "sha256":
            v = f"`{str(v)[:12]}…`"
        elif isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        rows.append([labels.get(k, k.replace("_", " ").capitalize()), fmt(v)])
    return table(["Field", "Value"], rows)


def ci(c: tuple[float, float] | None) -> str:
    return f"{c[0]:.2f}–{c[1]:.2f}" if c else ""


# ---------------------------------------------------------------- markdown


def render_markdown(card: Card) -> str:
    m = card.manifest
    lines: list[str] = []
    w = lines.append

    def section(key: str) -> None:
        w("")
        w(f"## {SECTIONS[key].title}")
        w("")

    title = m.name + (f" v{m.version}" if m.version else "")
    counts = card.counts()
    w(f"# Model card: {title}")
    w("")
    w(
        "> **Draft for human review.** Built with model-card-generator "
        f"{__version__} on {card.as_of.isoformat()}. Metrics and group results are "
        f"{'computed from the predictions file listed under Evidence' if card.metrics_source == 'computed' else 'as reported in the manifest, not recomputed'}. "
        "The risk tier and findings are rule-based suggestions, not a validation opinion."
    )
    w("")
    w(
        f"**{card.tier.label}** · {counts['high']} high, {counts['medium']} medium and "
        f"{counts['low']} low findings · owner: {m.get('model.owner') or 'not named'}"
    )

    section("details")
    details = {k: v for k, v in (m.get("model") or {}).items() if k != "description"}
    if m.get("model.description"):
        w(str(m.get("model.description")).strip())
        w("")
    lines.extend(kv(details) if details else [NOT_PROVIDED])

    section("intended_use")
    iu = m.get("intended_use") or {}
    if iu.get("primary"):
        w(str(iu["primary"]).strip())
    else:
        w(NOT_PROVIDED)
    if iu.get("users"):
        w("")
        w("Intended users:")
        w("")
        lines.extend(bullets(iu["users"]))

    section("out_of_scope")
    lines.extend(bullets(iu.get("out_of_scope")))

    section("risk_tier")
    t = card.tier
    if t.tier:
        w(
            f"Suggested **{t.label}** (score {t.score} of 13). Score = 2 × decision impact + autonomy + "
            "complexity + 1 if the model affects individuals. 10 or more is Tier 1, 7 to 9 is Tier 2, "
            "lower is Tier 3."
        )
        w("")
        lines.extend(table(["Factor", "Value", "Points"], [[a, b, c] for a, b, c in t.reasons]))
    else:
        w(f"{NOT_PROVIDED} The tier needs: {', '.join(t.missing)}.")
    reg = m.get("risk.regulatory_context")
    if reg:
        w("")
        w("Regulatory context given by the owner:")
        w("")
        lines.extend(bullets(reg))

    section("findings")
    if card.findings:
        w("Rule-based findings, most severe first. Each one needs a response from the owner or validator.")
        w("")
        lines.extend(
            table(
                ["#", "Severity", "Area", "Finding"],
                [[i, f.severity, f.area, f.text] for i, f in enumerate(card.findings, 1)],
            )
        )
    else:
        w("No findings at the thresholds set in the manifest.")

    section("methodology")
    meth = m.get("methodology") or {}
    if not meth:
        w(NOT_PROVIDED)
    else:
        if meth.get("approach"):
            w(str(meth["approach"]).strip())
        for key, label in (
            ("features", "Features"),
            ("assumptions", "Assumptions"),
            ("alternatives", "Alternatives considered"),
        ):
            if meth.get(key):
                w("")
                w(f"{label}:")
                w("")
                lines.extend(bullets(meth[key]))

    section("training_data")
    lines.extend(kv(m.get("data.training")))
    section("evaluation_data")
    lines.extend(kv(m.get("data.evaluation")))

    section("lineage")
    lin = m.get("lineage") or []
    if lin and isinstance(lin, list) and all(isinstance(x, dict) for x in lin):
        lines.extend(
            table(
                ["Step", "From", "To", "Owner"],
                [[x.get("step", ""), x.get("from", ""), x.get("to", ""), x.get("owner", "")] for x in lin],
            )
        )
    else:
        lines.extend(bullets(lin))

    section("metrics")
    results = metric_results(m, card.metrics)
    if card.metrics_source == "computed":
        pred = m.predictions
        pcol = m.get("evaluation.prediction_column")
        how = (
            f"Predictions are read from the `{pcol}` column."
            if pcol
            else f"A positive prediction is a score at or above {m.get('evaluation.threshold', 0.5)}."
        )
        w(
            f"Computed from {fmt(card.metrics['rows'])} rows of `{relpath(pred.path, m.base)}` with "
            f"{fmt(card.metrics['positives'])} positives (prevalence {fmt(card.metrics['prevalence'])}). {how}"
        )
        w("")
    if results:
        rows = []
        for key, value, rule, passed in results:
            verdict = "" if passed is None else ("pass" if passed else "**fail**")
            rows.append([METRIC_LABELS.get(key, key), fmt(value), describe_rule(rule) if rule else "", verdict])
        lines.extend(table(["Metric", "Value", "Threshold", "Result"], rows))
    else:
        w(NOT_PROVIDED)
    if card.metrics_source == "computed":
        cm = card.metrics["confusion"]
        w("")
        w(
            f"Confusion matrix: {cm['tp']:,} true positives, {cm['fp']:,} false positives, {cm['tn']:,} true negatives, {cm['fn']:,} false negatives."
        )

    section("groups")
    if card.slices:
        cfg = FairnessConfig.from_dict(m.get("fairness"))
        w(
            f"Each slice is compared with its group's reference slice (marked ★). Flagged: selection rate ratio "
            f"below {cfg.min_ratio:.2f}, a true positive rate more than {cfg.max_gap:.2f} lower, or a false positive "
            f"rate more than {cfg.max_gap:.2f} higher. A gap is *clear* when the 95% Wilson intervals don't overlap. "
            f"Slices under {cfg.min_slice_rows} rows are marked small."
        )
        for group, sl in card.slices.items():
            w("")
            w(f"### {group}")
            w("")
            rows = []
            for s in sl:
                name = s.value + (" ★" if s.is_reference else "") + (" (small)" if s.small else "")
                rows.append(
                    [
                        name,
                        fmt(s.rows),
                        fmt(s.positives),
                        f"{fmt(s.selection_rate)} ({ci(s.selection_ci)})",
                        f"{fmt(s.tpr)} ({ci(s.tpr_ci)})" if s.tpr is not None else "n/a",
                        f"{fmt(s.fpr)} ({ci(s.fpr_ci)})" if s.fpr is not None else "n/a",
                        fmt(s.precision),
                    ]
                )
            lines.extend(
                table(
                    [
                        "Slice",
                        "Rows",
                        "Positives",
                        "Selection rate (95% CI)",
                        "TPR (95% CI)",
                        "FPR (95% CI)",
                        "Precision",
                    ],
                    rows,
                )
            )
        w("")
        if card.gaps:
            w("Gaps flagged:")
            w("")
            lines.extend(f"- {g.describe()}" for g in card.gaps)
        else:
            w("No gaps were flagged at these thresholds.")
    elif m.get("evaluation.slices"):
        lines.extend(
            table(
                ["Slice", "Rows", "Metrics (reported)"],
                [
                    [
                        s.get("name", ""),
                        fmt(s.get("rows")),
                        ", ".join(f"{k} {fmt(v)}" for k, v in (s.get("metrics") or {}).items()),
                    ]
                    for s in m.get("evaluation.slices")
                ],
            )
        )
    else:
        w(NOT_PROVIDED)

    section("oversight")
    lines.extend(bullets(m.get("human_oversight")))
    section("robustness")
    lines.extend(bullets(m.get("robustness")))
    section("ethics")
    lines.extend(bullets(m.get("ethical_considerations")))
    section("limitations")
    lines.extend(bullets(m.get("limitations")))

    section("monitoring")
    mon = m.get("monitoring")
    if isinstance(mon, dict):
        lines.extend(kv(mon))
    else:
        lines.extend(bullets(mon))

    section("validation")
    val = dict(m.get("validation") or {})
    conditions = val.pop("conditions", None)
    lines.extend(kv(val))
    if conditions:
        w("")
        w("Conditions:")
        w("")
        lines.extend(bullets(conditions))

    section("ownership")
    owner = m.get("model.owner")
    w(f"Model owner: {owner}." if owner else NOT_PROVIDED)
    appr = m.get("approvals") or []
    if appr:
        w("")
        lines.extend(
            table(
                ["Role", "Name", "Date", "Decision"],
                [[a.get("role", ""), a.get("name", ""), fmt(a.get("date")), a.get("decision", "")] for a in appr],
            )
        )

    section("changes")
    ch = m.get("changes") or []
    if ch:
        lines.extend(
            table(
                ["Version", "Date", "Change"],
                [[c.get("version", ""), fmt(c.get("date")), c.get("summary", "")] for c in ch],
            )
        )
    else:
        w(NOT_PROVIDED)

    w("")
    w("## Evidence")
    w("")
    w(f"Card built with model-card-generator {__version__}, as of {card.as_of.isoformat()}, from `{m.path.name}`.")
    if card.evidence:
        w("")
        lines.extend(table(["File", "SHA-256"], [[f"`{p}`", f"`{h}`"] for p, h in card.evidence]))
    w("")
    return "\n".join(lines)


# ---------------------------------------------------------------- json


def to_json(card: Card) -> str:
    m = card.manifest

    def slice_dict(s: Slice) -> dict:
        return {
            "value": s.value,
            "rows": s.rows,
            "positives": s.positives,
            "selection_rate": s.selection_rate,
            "selection_rate_ci": s.selection_ci,
            "tpr": s.tpr,
            "tpr_ci": s.tpr_ci,
            "fpr": s.fpr,
            "fpr_ci": s.fpr_ci,
            "precision": s.precision,
            "reference": s.is_reference,
            "small": s.small,
        }

    doc = {
        "model": m.name,
        "version": m.version,
        "as_of": card.as_of.isoformat(),
        "generator": f"model-card-generator {__version__}",
        "metrics_source": card.metrics_source,
        "metrics": {k: v for k, v in card.metrics.items()},
        "thresholds": [
            {"metric": k, "value": v, "rule": r, "passed": p} for k, v, r, p in metric_results(m, card.metrics) if r
        ],
        "groups": {g: [slice_dict(s) for s in sl] for g, sl in card.slices.items()},
        "gaps": [
            {
                "group": g.group,
                "value": g.value,
                "reference": g.reference,
                "metric": g.metric,
                "slice_value": g.slice_value,
                "reference_value": g.reference_value,
                "measure": g.measure,
                "clear": g.clear,
                "small": g.small,
                "severity": g.severity,
            }
            for g in card.gaps
        ],
        "risk_tier": {
            "tier": card.tier.tier,
            "score": card.tier.score,
            "reasons": card.tier.reasons,
            "missing": card.tier.missing,
        },
        "findings": [{"severity": f.severity, "area": f.area, "text": f.text} for f in card.findings],
        "profile": {
            "name": card.check.profile if card.check else None,
            "passed": card.check.passed if card.check else None,
            "sections": [
                {"section": r.title, "status": r.status, "reference": r.reference}
                for r in (card.check.results if card.check else [])
            ],
        },
        "evidence": [{"file": p, "sha256": h} for p, h in card.evidence],
    }
    return json.dumps(doc, indent=2, default=str)
