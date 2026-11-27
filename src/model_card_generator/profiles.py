"""Required sections, grouped into profiles.

A profile is a list of sections a reviewer expects to find in a model card,
each tied to the guidance theme it comes from. The themes are paraphrased; a
profile is a checklist to start from, not a statement that a card complies
with any regulation.

Each section has the heading this tool writes and a set of alternative
headings, so ``check`` also works on cards written by hand.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    patterns: tuple[str, ...]


SECTIONS: dict[str, Section] = {
    s.key: s
    for s in [
        Section(
            "details",
            "Model details",
            (r"model details?", r"model overview", r"overview", r"model description", r"general description"),
        ),
        Section("intended_use", "Intended use", (r"intended uses?", r"purpose", r"use cases?", r"primary uses?")),
        Section(
            "out_of_scope",
            "Out-of-scope use",
            (r"out[ -]of[ -]scope", r"not intended", r"prohibited uses?", r"misuse", r"use restrictions?"),
        ),
        Section(
            "risk_tier",
            "Model risk tier",
            (r"(model )?risk (tier|classification|rating|materiality)", r"materiality", r"model tier"),
        ),
        Section(
            "findings",
            "Findings for review",
            (r"findings", r"risk summary", r"risk assessment", r"issues", r"risk management"),
        ),
        Section(
            "methodology",
            "Methodology and assumptions",
            (r"methodology", r"conceptual soundness", r"assumptions", r"model design", r"approach"),
        ),
        Section("training_data", "Training data", (r"training data(set)?s?", r"development data")),
        Section(
            "evaluation_data",
            "Evaluation data",
            (r"evaluation data(set)?s?", r"test data(set)?s?", r"validation data(set)?s?", r"holdout"),
        ),
        Section(
            "lineage", "Data lineage", (r"(data )?lineage", r"data provenance", r"data sources?", r"data pipeline")
        ),
        Section(
            "metrics", "Metrics", (r"(performance )?metrics", r"quantitative analys[ie]s", r"performance", r"results")
        ),
        Section(
            "groups",
            "Performance by group",
            (r"performance by (group|segment|slice)", r"fairness", r"bias", r"disaggregated", r"factors", r"subgroup"),
        ),
        Section("oversight", "Human oversight", (r"human oversight", r"human[ -]in[ -]the[ -]loop", r"human review")),
        Section(
            "robustness", "Robustness and security", (r"robustness", r"security", r"cyber ?security", r"resilience")
        ),
        Section(
            "ethics", "Ethical considerations", (r"ethic(s|al considerations?)", r"responsible ai", r"societal impact")
        ),
        Section(
            "limitations",
            "Limitations",
            (r"limitations?", r"caveats( and recommendations)?", r"known issues", r"weaknesses"),
        ),
        Section(
            "monitoring", "Ongoing monitoring", (r"(ongoing |post[ -]market )?monitoring", r"performance tracking")
        ),
        Section(
            "validation",
            "Independent validation",
            (r"(independent )?(model )?validation", r"model review", r"challenge"),
        ),
        Section(
            "ownership",
            "Ownership and approvals",
            (r"ownership", r"approvals?", r"sign[ -]?off", r"governance", r"accountability"),
        ),
        Section("changes", "Change log", (r"change ?log", r"version history", r"changes", r"revision history")),
    ]
}


@dataclass(frozen=True)
class Requirement:
    section: str
    reference: str


@dataclass(frozen=True)
class Profile:
    name: str
    summary: str
    requirements: tuple[Requirement, ...]


_CORE = (
    Requirement("details", "Model cards: model details"),
    Requirement("intended_use", "Model cards: intended use"),
    Requirement("out_of_scope", "Model cards: out-of-scope use cases"),
    Requirement("training_data", "Model cards: training data"),
    Requirement("evaluation_data", "Model cards: evaluation data"),
    Requirement("metrics", "Model cards: metrics and quantitative analyses"),
    Requirement("groups", "Model cards: factors and disaggregated results"),
    Requirement("ethics", "Model cards: ethical considerations"),
    Requirement("limitations", "Model cards: caveats and recommendations"),
)

PROFILES: dict[str, Profile] = {
    "core": Profile(
        "core",
        "The sections of the original model card proposal (Mitchell et al., 2019).",
        _CORE,
    ),
    "model-risk": Profile(
        "model-risk",
        "Core sections plus model risk management themes from US SR 11-7 and UK PRA SS1/23.",
        _CORE
        + (
            Requirement("risk_tier", "SS1/23 principle 1: model identification and risk classification"),
            Requirement("methodology", "SR 11-7: conceptual soundness; SS1/23 principle 3: development"),
            Requirement("lineage", "SR 11-7: data quality and relevance; SS1/23 principle 3"),
            Requirement("findings", "SR 11-7: outcomes analysis and limitations; SS1/23 principle 5: risk mitigants"),
            Requirement("validation", "SR 11-7: model validation; SS1/23 principle 4: independent validation"),
            Requirement("monitoring", "SR 11-7: ongoing monitoring"),
            Requirement("ownership", "SR 11-7: governance, policies and controls; SS1/23 principle 2: governance"),
            Requirement("changes", "SR 11-7: documentation of changes; SS1/23 principle 3"),
        ),
    ),
    "eu-ai-act": Profile(
        "eu-ai-act",
        "Core sections plus technical documentation themes from EU AI Act Annex IV (high-risk systems).",
        _CORE
        + (
            Requirement("methodology", "Annex IV point 2: development process and design choices"),
            Requirement("lineage", "Annex IV point 2: data requirements and provenance"),
            Requirement("oversight", "Annex IV point 2: human oversight measures"),
            Requirement("robustness", "Annex IV point 2: accuracy, robustness and cybersecurity"),
            Requirement("findings", "Annex IV point 5: risk management system"),
            Requirement("monitoring", "Annex IV points 3 and 9: monitoring and post-market monitoring plan"),
            Requirement("changes", "Annex IV point 6: changes through the lifecycle"),
        ),
    ),
}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown profile {name!r}; choose from {', '.join(PROFILES)}") from None
