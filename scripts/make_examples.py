"""Regenerate the synthetic predictions in examples/claims-fraud/.

Run from the project root:  python scripts/make_examples.py

Every row is made up: a seeded random generator draws a fraud label and a model
score for each synthetic motor claim. The 70+ age band is drawn with weaker
separation between fraud and genuine claims, so the card has a real gap to find,
and the Islands region is kept small.
"""

from __future__ import annotations

import csv
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "examples" / "claims-fraud" / "predictions.csv"

AGE_BANDS = [("18-29", 0.22), ("30-49", 0.38), ("50-69", 0.28), ("70+", 0.12)]
REGIONS = [("North", 0.36), ("South", 0.34), ("Midlands", 0.27), ("Islands", 0.03)]
CHANNELS = [("broker", 0.4), ("direct", 0.35), ("aggregator", 0.25)]


def pick(rng: random.Random, options: list[tuple[str, float]]) -> str:
    r = rng.random()
    acc = 0.0
    for value, weight in options:
        acc += weight
        if r < acc:
            return value
    return options[-1][0]


def main(rows: int = 2400, seed: int = 20261127) -> None:
    rng = random.Random(seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["claim_id", "fraud", "score", "age_band", "region", "channel"])
        for i in range(rows):
            age = pick(rng, AGE_BANDS)
            region = pick(rng, REGIONS)
            channel = pick(rng, CHANNELS)
            p_fraud = 0.10 + (0.04 if channel == "aggregator" else 0.0)
            fraud = 1 if rng.random() < p_fraud else 0
            separation = 1.6 if age == "70+" else 2.9
            z = -2.0 + separation * fraud + rng.gauss(0, 1.0)
            score = 1 / (1 + math.exp(-z))
            w.writerow([f"CLM-{100000 + i}", fraud, f"{score:.4f}", age, region, channel])
    print(f"wrote {OUT.relative_to(ROOT)} ({rows} rows)")


if __name__ == "__main__":
    main()
