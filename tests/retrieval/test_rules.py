"""Rule retrieval: tier order, and the line partial matches may not cross.

The load-bearing claim is negative. A partial match must never be groundable —
not because a threshold happens to keep it out, but because the tier itself
carries no grounding. These tests try to get a substring coincidence promoted
and fail to.
"""

from __future__ import annotations

import pytest

from canna.retrieval.rules import grounding_matches, search
from canna.retrieval.settings import RuleSettings
from canna.retrieval.vocabulary import (
    ROLE_ALIAS,
    ROLE_DEFINITION,
    ROLE_LABEL,
    ROLE_SEMANTIC_ID,
    TIER_EXACT,
    TIER_NORMALIZED,
    TIER_PHRASE,
    TIER_SUBSTRING,
)

from .conftest import synthetic_registry, term

RULES = RuleSettings()


def only(matches, semantic_id):
    found = [match for match in matches if match.semantic_id == semantic_id]
    assert len(found) == 1, f"expected exactly one match for {semantic_id}, got {len(found)}"
    return found[0]


def test_exact_match_requires_the_whole_question() -> None:
    vocabulary = synthetic_registry([term("syn:A", label="가나다라")])
    matches, _ = search(vocabulary, "가나다라", RULES)
    match = only(matches, "syn:A")
    assert match.tier == TIER_EXACT
    assert match.grounding_eligible
    assert match.score == 1.0


def test_normalized_match_is_whole_question_after_safe_folding() -> None:
    vocabulary = synthetic_registry([term("syn:A", label="가나다라")])
    matches, _ = search(vocabulary, "가 나 다 라", RULES)
    match = only(matches, "syn:A")
    assert match.tier == TIER_NORMALIZED
    assert match.grounding_eligible


@pytest.mark.parametrize(
    "question",
    [
        "가 나 다 라를 알려줘",  # spacing and an attached particle
        "가나다라!!! 알려줘",  # sentence punctuation around the expression
        "ＡＢＣ가나다라",  # full-width neighbours
    ],
)
def test_phrase_match_finds_the_whole_form_inside_a_sentence(question: str) -> None:
    vocabulary = synthetic_registry([term("syn:A", label="가나다라")])
    match = only(search(vocabulary, question, RULES)[0], "syn:A")
    assert match.tier == TIER_PHRASE
    assert match.grounding_eligible


def test_case_and_width_folding_is_symmetric() -> None:
    vocabulary = synthetic_registry([term("syn:A", label="Net Asset Value")])
    matches, _ = search(vocabulary, "ＮＥＴ　ａｓｓｅｔ　ｖａｌｕｅ 를 보여줘", RULES)
    assert only(matches, "syn:A").grounding_eligible


def test_partial_match_is_a_proposal_and_never_grounding() -> None:
    vocabulary = synthetic_registry([term("syn:A", label="가나다라마바사")])
    matches, _ = search(vocabulary, "가나다라마 무엇", RULES)
    match = only(matches, "syn:A")
    assert match.tier == TIER_SUBSTRING
    assert not match.grounding_eligible
    assert match.score < 1.0
    assert grounding_matches(matches) == ()


def test_substring_coincidence_cannot_reach_grounding() -> None:
    """A short registered form swallowed by a longer one is proposal-only."""
    vocabulary = synthetic_registry(
        [term("syn:Short", label="가나다"), term("syn:Long", label="가나다라")]
    )
    matches, _ = search(vocabulary, "가나다라를 알려줘", RULES)
    short = only(matches, "syn:Short")
    assert short.tier == TIER_SUBSTRING
    assert not short.grounding_eligible
    assert only(matches, "syn:Long").grounding_eligible


def test_a_fragment_of_a_semantic_id_never_matches() -> None:
    vocabulary = synthetic_registry([term("syn:LongOpaqueIdentifier", label="라벨")])
    matches, _ = search(vocabulary, "syn:LongOpaque 를 찾아줘", RULES)
    assert [match.semantic_id for match in matches] == []


def test_a_whole_semantic_id_matches_and_grounds() -> None:
    vocabulary = synthetic_registry([term("syn:Identifier", label="라벨")])
    matches, _ = search(vocabulary, "syn:Identifier 를 찾아줘", RULES)
    match = only(matches, "syn:Identifier")
    assert match.form.role == ROLE_SEMANTIC_ID
    assert match.grounding_eligible


def test_a_fragment_of_a_definition_never_matches() -> None:
    vocabulary = synthetic_registry(
        [term("syn:A", label="라벨", definition="이 지표는 아주 특별한 방식으로 계산된다")]
    )
    matches, _ = search(vocabulary, "아주 특별한 방식으로", RULES)
    assert [match.semantic_id for match in matches] == []


def test_a_whole_definition_matches_and_grounds() -> None:
    definition = "이 지표는 아주 특별한 방식으로 계산된다"
    vocabulary = synthetic_registry([term("syn:A", label="라벨", definition=definition)])
    matches, _ = search(vocabulary, f"설명이 '{definition}' 인 것", RULES)
    match = only(matches, "syn:A")
    assert match.form.role == ROLE_DEFINITION
    assert match.grounding_eligible


def test_alias_matches_are_grounding_and_report_the_alias() -> None:
    vocabulary = synthetic_registry([term("syn:A", label="정식명칭", aliases=["짧은별칭"])])
    matches, _ = search(vocabulary, "짧은별칭 알려줘", RULES)
    match = only(matches, "syn:A")
    assert match.form.role == ROLE_ALIAS
    assert match.form.text == "짧은별칭"
    assert match.grounding_eligible


def test_a_term_is_reported_once_at_its_strongest_tier() -> None:
    """A whole label and alias substring describe one meaning, not two candidates."""
    vocabulary = synthetic_registry([term("syn:A", label="가나다", aliases=["가나다라마바"])])
    matches, _ = search(vocabulary, "가나다 를 보여줘", RULES)
    match = only(matches, "syn:A")
    assert match.tier == TIER_PHRASE
    assert match.form.role == ROLE_LABEL


def test_longer_forms_outrank_shorter_ones_at_the_same_tier() -> None:
    vocabulary = synthetic_registry(
        [term("syn:Long", label="가나다라마바사"), term("syn:Short", label="가나다")]
    )
    matches, _ = search(vocabulary, "가나다라마바사 를 보여줘", RULES)
    assert matches[0].semantic_id == "syn:Long"


def test_ranking_is_total_and_stable_across_runs() -> None:
    vocabulary = synthetic_registry(
        [term(f"syn:T{index}", label=f"라벨{index}") for index in range(20)]
    )
    question = " ".join(f"라벨{index}" for index in range(20))
    first, _ = search(vocabulary, question, RULES)
    second, _ = search(vocabulary, question, RULES)
    assert [match.semantic_id for match in first] == [match.semantic_id for match in second]


def test_max_candidates_truncates_and_reports_how_many() -> None:
    vocabulary = synthetic_registry(
        [term(f"syn:T{index}", label=f"라벨{index:03d}") for index in range(30)]
    )
    question = " ".join(f"라벨{index:03d}" for index in range(30))
    matches, truncated = search(vocabulary, question, RuleSettings(max_candidates=10))
    assert len(matches) == 10
    assert truncated == 20


def test_a_question_naming_nothing_matches_nothing() -> None:
    vocabulary = synthetic_registry([term("syn:A", label="가나다라마바사")])
    matches, truncated = search(vocabulary, "완전히 다른 이야기", RULES)
    assert matches == []
    assert truncated == 0


def test_partial_bounds_are_configuration_not_a_promotion_switch() -> None:
    """Loosening the bound admits proposals; it cannot create grounding."""
    vocabulary = synthetic_registry([term("syn:A", label="가나다라마바사아자차")])
    loose = RuleSettings(min_substring_characters=2, substring_overlap_ratio=0.2)
    matches, _ = search(vocabulary, "가나 라고 했다", loose)
    if matches:
        assert not any(match.grounding_eligible for match in matches)

    strict = RuleSettings(min_substring_characters=8, substring_overlap_ratio=0.9)
    assert search(vocabulary, "가나 라고 했다", strict)[0] == []


def test_every_registry_term_is_found_by_its_own_label(vocabulary) -> None:
    """The general rule, applied to all 331 terms rather than a chosen few."""
    missed: list[str] = []
    for item in vocabulary.terms:
        label = item.preferred_label
        if not label:
            continue
        matches, _ = search(vocabulary, label, RuleSettings(max_candidates=500))
        grounded = {match.semantic_id for match in matches if match.grounding_eligible}
        if item.semantic_id not in grounded:
            missed.append(item.semantic_id)
    assert not missed, f"terms not retrievable by their own label: {missed[:10]}"


def test_every_approved_alias_retrieves_its_term(vocabulary) -> None:
    missed: list[str] = []
    for item in vocabulary.terms:
        for form in item.forms:
            if form.role != ROLE_ALIAS:
                continue
            matches, _ = search(vocabulary, form.text, RuleSettings(max_candidates=500))
            grounded = {match.semantic_id for match in matches if match.grounding_eligible}
            if item.semantic_id not in grounded:
                missed.append(f"{item.semantic_id}::{form.text}")
    assert not missed, f"aliases not retrievable: {missed[:10]}"
