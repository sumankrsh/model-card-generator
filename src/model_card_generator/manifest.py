"""Load a model manifest (YAML) and the predictions file it points to."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ManifestError(ValueError):
    """The manifest or a file it references can't be used."""


@dataclass
class Predictions:
    path: Path
    sha256: str
    labels: list[int]
    preds: list[int]
    scores: list[float] | None
    groups: dict[str, list[str]] = field(default_factory=dict)

    @property
    def rows(self) -> int:
        return len(self.labels)


@dataclass
class Manifest:
    path: Path
    data: dict[str, Any]
    predictions: Predictions | None = None

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def base(self) -> Path:
        return self.path.parent

    @property
    def name(self) -> str:
        return str(self.get("model.name") or self.path.stem)

    @property
    def version(self) -> str:
        return str(self.get("model.version") or "")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date(value: Any) -> dt.date | None:
    """Accept a YAML date, an ISO string, or the end of an 'A to B' period."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if " to " in text:
        text = text.rsplit(" to ", 1)[1].strip()
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _truthy(value: str, positive: str) -> int:
    v = value.strip().lower()
    if v == positive.lower():
        return 1
    if v in {"1", "true", "yes", "y"} and positive.lower() in {"1", "true", "yes", "y"}:
        return 1
    return 0


def load_predictions(path: Path, cfg: dict) -> Predictions:
    label_col = cfg.get("label_column", "label")
    score_col = cfg.get("score_column")
    pred_col = cfg.get("prediction_column")
    threshold = float(cfg.get("threshold", 0.5))
    positive = str(cfg.get("positive_label", 1))
    group_cols = list(cfg.get("groups") or [])
    if not score_col and not pred_col:
        raise ManifestError("evaluation needs score_column or prediction_column")
    try:
        fh = path.open(newline="", encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"can't read predictions file {path}: {exc.strerror}") from exc
    with fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        wanted = [label_col] + [c for c in (score_col, pred_col) if c] + group_cols
        missing = [c for c in wanted if c not in header]
        if missing:
            raise ManifestError(f"{path.name} has no column(s): {', '.join(missing)}")
        labels: list[int] = []
        preds: list[int] = []
        scores: list[float] = []
        groups: dict[str, list[str]] = {g: [] for g in group_cols}
        for lineno, row in enumerate(reader, start=2):
            labels.append(_truthy(row[label_col], positive))
            if score_col:
                try:
                    s = float(row[score_col])
                except ValueError as exc:
                    raise ManifestError(f"{path.name} line {lineno}: score {row[score_col]!r} is not a number") from exc
                if not 0.0 <= s <= 1.0:
                    raise ManifestError(f"{path.name} line {lineno}: score {s} is outside 0-1")
                scores.append(s)
            if pred_col:
                preds.append(_truthy(row[pred_col], positive))
            else:
                preds.append(1 if scores[-1] >= threshold else 0)
            for g in group_cols:
                groups[g].append((row[g] or "").strip() or "(blank)")
    if not labels:
        raise ManifestError(f"{path.name} has no rows")
    return Predictions(path, sha256_file(path), labels, preds, scores if score_col else None, groups)


def load(path: str | Path) -> Manifest:
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestError(f"can't read {p}: {exc.strerror}") from exc
    except yaml.YAMLError as exc:
        raise ManifestError(f"{p} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{p} must be a YAML mapping")
    m = Manifest(p, raw)
    ev = m.get("evaluation") or {}
    if not isinstance(ev, dict):
        raise ManifestError("evaluation must be a mapping")
    if ev.get("predictions"):
        m.predictions = load_predictions(m.base / str(ev["predictions"]), ev)
    return m
