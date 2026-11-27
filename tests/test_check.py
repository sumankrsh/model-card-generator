from __future__ import annotations

import pytest

from model_card_generator.check import body_status, check_markdown, classify
from model_card_generator.profiles import PROFILES, get_profile


def test_headings_map_to_the_most_specific_section():
    assert classify("Validation data") == "evaluation_data"
    assert classify("Model validation") == "validation"
    assert classify("Performance by group") == "groups"
    assert classify("3.2 Performance metrics") == "metrics"
    assert classify("Caveats and Recommendations") == "limitations"
    assert classify("Out-of-scope use") == "out_of_scope"
    assert classify("Lunch menu") is None


@pytest.mark.parametrize(
    "body,status",
    [
        ("TBD", "placeholder"),
        ("_Not provided._ Ask the model owner before this card is approved.", "placeholder"),
        ("", "empty"),
        ("Yes.", "empty"),
        ("Trained on three years of synthetic claims.", "ok"),
    ],
)
def test_body_status(body, status):
    assert body_status(body) == status


def test_subsections_count_as_content():
    md = "# Card\n\n## Fairness\n\n### By age\n\n| a | b |\n|---|---|\n| 18-29 | 0.71 recall overall |\n"
    res = check_markdown(md, get_profile("core"))
    groups = next(r for r in res.results if r.key == "groups")
    assert groups.ok and groups.heading == "Fairness"


def test_headings_inside_code_fences_are_ignored():
    md = "# Card\n\n## Intended use\n\n```\n## Limitations\n```\n"
    res = check_markdown(md, get_profile("core"))
    lim = next(r for r in res.results if r.key == "limitations")
    assert lim.status == "missing"


def test_hand_written_example_fails_model_risk_but_lists_what_it_found(examples):
    text = (examples / "hand-written-card.md").read_text()
    res = check_markdown(text, get_profile("model-risk"), path="hand-written-card.md")
    assert not res.passed
    by_key = {r.key: r for r in res.results}
    assert by_key["evaluation_data"].ok and by_key["evaluation_data"].heading == "Validation data"
    assert by_key["limitations"].status == "placeholder" and by_key["limitations"].line == 30
    assert by_key["changes"].status == "missing"
    assert sum(r.ok for r in res.results) == 7


def test_profiles_extend_core():
    core = {r.section for r in PROFILES["core"].requirements}
    for name in ("model-risk", "eu-ai-act"):
        secs = {r.section for r in PROFILES[name].requirements}
        assert core < secs
    with pytest.raises(ValueError):
        get_profile("nope")
