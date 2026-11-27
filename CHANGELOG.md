# Changelog

## 0.1.0 (2026-11-27)

First release.

- `build`: a model card in Markdown, single-file HTML and JSON from a YAML manifest. Metrics, threshold checks and performance by group are computed from a predictions CSV, with the file's SHA-256 recorded. A suggested risk tier with its points, and findings for review. `--strict` exits 1 on high findings or missing sections.
- Performance by group: selection rate ratio, true positive rate gap and false positive rate gap against a reference slice, with 95% Wilson intervals and small-slice flags.
- `check`: required sections for the `core`, `model-risk` and `eu-ai-act` profiles in any Markdown card, with GitHub annotations.
- `profiles` and `init`.
- Synthetic examples: a complete claims-fraud manifest with 2,400 scored claims, an incomplete policy-lapse manifest, and a hand-written card.
