"""The composite evaluator scores candidate kinds separately and fails loudly.

Every case here is built from a synthetic registry, so what is under test is the
scoring rule itself rather than any approved question or any current Registry
term. The approved proposal is never imported by these tests.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from canna.retrieval.composite import (
    CompositeError,
    candidate_kind,
    evaluate_composite,
    load_composite_proposal,
)
from canna.retrieval.index import RetrievalIndex, build_index
from canna.retrieval.settings import RuleSettings

from .conftest import StubEmbeddings, synthetic_registry, term

BUDGETS = ({"dataset": 1, "field": 2, "predicate": 1},)


def _vocabulary():
    return synthetic_registry(
        [
            term("syn:Family", label="합성상품군", kind="class"),
            term("syn:OtherFamily", label="타상품군", kind="class"),
            term("syn:MetricA", label="합성지표가", kind="metric"),
            term("syn:MetricB", label="합성지표나", kind="metric"),
            term("syn:MetricNeighbour", label="합성지표다", kind="metric"),
            term("syn:holdsThing", label="합성관계", kind="predicate"),
            term("syn:isHeldByThing", label="합성역관계", kind="predicate"),
        ]
    )


def _case(**overrides):
    row = {
        "record_type": "evaluation_case",
        "case_id": "case-1",
        "section": "clear",
        "question": "합성상품군의 합성지표가와 합성지표나를 합성관계로 보여줘",
        "test_purpose": "scoring rule",
        "capability_under_test": "synthetic.composite",
        "question_structure": {"targets": ["synthetic"]},
        "explicit_requirements": ["합성상품군", "합성지표가"],
        "semantic_clarity": "explicit",
        "required_candidates": {
            "dataset": ["syn:Family"],
            "field": ["syn:MetricA", "syn:MetricB"],
            "predicate": ["syn:holdsThing"],
        },
        "equivalent_alternatives": {},
        "entity_mentions": [],
        "confusion_sets": {},
        "confusable_candidates_allowed": [],
        "coverage_notes": [],
        "expected_invariant": "all kinds recovered",
        "falsifies_if": "a kind is dropped",
        "execution_expectation": "executable",
        "natural_question_rationale": "synthetic",
    }
    row.update(overrides)
    return row


def _write(tmp_path, vocabulary, cases, **metadata_overrides):
    pairs = [[row["case_id"], row["question"]] for row in cases]
    payload = json.dumps(pairs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    metadata = {
        "record_type": "proposal_metadata",
        "proposal_id": "composite-test",
        "approval_status": "test",
        "registry_content_hash": vocabulary.content_hash,
        "questions_sha256": hashlib.sha256(payload).hexdigest(),
    }
    metadata.update(metadata_overrides)
    path = tmp_path / "composite.jsonl"
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in [metadata, *cases]) + "\n",
        encoding="utf-8",
    )
    return path


def test_approval_reference_is_required(tmp_path) -> None:
    vocabulary = _vocabulary()
    path = _write(tmp_path, vocabulary, [_case()])
    with pytest.raises(CompositeError, match="approval-reference"):
        load_composite_proposal(path, vocabulary, approval_reference="   ")
    _metadata, cases = load_composite_proposal(path, vocabulary, approval_reference="ok")
    assert cases[0].required["field"] == ("syn:MetricA", "syn:MetricB")


def test_question_hash_and_registry_hash_are_both_enforced(tmp_path) -> None:
    vocabulary = _vocabulary()
    tampered = _write(tmp_path, vocabulary, [_case()], questions_sha256="0" * 64)
    with pytest.raises(CompositeError, match="question text/order hash"):
        load_composite_proposal(tampered, vocabulary, approval_reference="ok")
    wrong_registry = _write(tmp_path, vocabulary, [_case()], registry_content_hash="1" * 64)
    with pytest.raises(CompositeError, match="another Registry hash"):
        load_composite_proposal(wrong_registry, vocabulary, approval_reference="ok")


def test_required_kind_must_match_the_registry_classification(tmp_path) -> None:
    vocabulary = _vocabulary()
    case = _case(
        required_candidates={"dataset": ["syn:MetricA"], "field": [], "predicate": []}
    )
    path = _write(tmp_path, vocabulary, [case])
    with pytest.raises(CompositeError, match="classifies it as 'field'"):
        load_composite_proposal(path, vocabulary, approval_reference="ok")


def test_entity_expectations_cannot_be_smuggled_in_as_semantic_ids(tmp_path) -> None:
    vocabulary = _vocabulary()
    case = _case(
        required_candidates={"dataset": ["syn:Family"], "entity": ["syn:MetricA"]},
    )
    path = _write(tmp_path, vocabulary, [case])
    with pytest.raises(CompositeError, match="entity_mentions"):
        load_composite_proposal(path, vocabulary, approval_reference="ok")


def test_a_term_cannot_be_required_and_confusable_at_once(tmp_path) -> None:
    vocabulary = _vocabulary()
    case = _case(confusion_sets={"period": ["syn:MetricA"]})
    path = _write(tmp_path, vocabulary, [case])
    with pytest.raises(CompositeError, match="both required and confusable"):
        load_composite_proposal(path, vocabulary, approval_reference="ok")


def test_unknown_semantic_ids_and_categories_are_rejected(tmp_path) -> None:
    vocabulary = _vocabulary()
    unknown_id = _case(confusion_sets={"period": ["syn:Missing"]})
    with pytest.raises(CompositeError, match="unknown semantic IDs"):
        load_composite_proposal(
            _write(tmp_path, vocabulary, [unknown_id]), vocabulary, approval_reference="ok"
        )
    unknown_category = _case(confusion_sets={"vibes": ["syn:MetricNeighbour"]})
    with pytest.raises(CompositeError, match="unknown confusion categories"):
        load_composite_proposal(
            _write(tmp_path, vocabulary, [unknown_category]), vocabulary, approval_reference="ok"
        )


def test_candidate_kind_follows_the_registry_not_a_hardcoded_list() -> None:
    vocabulary = _vocabulary()
    assert candidate_kind(vocabulary, "syn:Family") == "dataset"
    assert candidate_kind(vocabulary, "syn:MetricA") == "field"
    assert candidate_kind(vocabulary, "syn:holdsThing") == "predicate"
    assert candidate_kind(vocabulary, "syn:NotPresent") == "other"


def _report(tmp_path, vocabulary, cases, top_ks=(20,), budgets=BUDGETS):
    provider = StubEmbeddings()
    index = RetrievalIndex(*build_index(vocabulary, provider))
    path = _write(tmp_path, vocabulary, cases)
    _metadata, loaded = load_composite_proposal(path, vocabulary, approval_reference="ok")
    return evaluate_composite(
        vocabulary,
        index,
        provider,
        loaded,
        rule_settings=RuleSettings(),
        top_ks=top_ks,
        budget_grid=budgets,
    )


def test_per_kind_recall_is_reported_separately_from_joint_recall(tmp_path) -> None:
    vocabulary = _vocabulary()
    report = _report(tmp_path, vocabulary, [_case()])
    merged = report["path_recall_by_kind"][0]["merged"]
    kinds = {row["kind"]: row for row in merged["by_kind"]}
    assert set(kinds) == {"dataset", "field", "predicate"}
    assert kinds["dataset"]["cases_requiring_kind"] == 1
    assert merged["all_required_recall"] == 1.0
    assert report["question_text_in_report"] is False


def test_a_dropped_kind_is_visible_instead_of_averaged_away(tmp_path) -> None:
    vocabulary = _vocabulary()
    case = _case(
        question="합성상품군의 합성지표가를 보여줘",
        required_candidates={
            "dataset": ["syn:Family"],
            "field": ["syn:MetricA"],
            "predicate": ["syn:holdsThing"],
        },
    )
    report = _report(tmp_path, vocabulary, [case], top_ks=(2,))
    merged = report["path_recall_by_kind"][0]["merged"]
    kinds = {row["kind"]: row for row in merged["by_kind"]}
    assert kinds["dataset"]["all_required_of_kind_recall"] == 1.0
    assert kinds["predicate"]["all_required_of_kind_recall"] == 0.0
    assert kinds["predicate"]["missing"] == [
        {"case_id": "case-1", "semantic_id": "syn:holdsThing"}
    ]
    assert merged["all_required_recall"] == 0.0


def test_equivalent_alternatives_satisfy_a_required_id(tmp_path) -> None:
    vocabulary = _vocabulary()
    case = _case(
        question="타상품군의 합성지표가와 합성지표나를 합성관계로 보여줘",
        equivalent_alternatives={"syn:Family": ["syn:OtherFamily"]},
    )
    report = _report(tmp_path, vocabulary, [case])
    row = next(
        item
        for item in report["case_results"][0]["required_rank_in_merged"]
        if item["semantic_id"] == "syn:Family"
    )
    assert row["satisfied_by"] == "syn:OtherFamily"


def test_confusion_is_counted_at_both_levels_and_never_scored_as_failure(
    tmp_path,
) -> None:
    vocabulary = _vocabulary()
    case = _case(
        question="합성상품군의 합성지표가와 합성지표나를 합성관계로, 합성지표다도 보여줘",
        confusion_sets={"period": ["syn:MetricNeighbour"]},
    )
    report = _report(tmp_path, vocabulary, [case])
    aggregate = report["global_top_k"][0]["aggregate"]
    period = aggregate["confusion_totals"]["period"]
    assert period["as_candidate"] == 1
    assert period["as_grounding"] == 1
    # the neighbour is confusable, not required, so joint recall is untouched
    assert aggregate["all_required_recall"] == 1.0


def test_rule_candidates_are_never_displaced_by_embedding_neighbours(tmp_path) -> None:
    vocabulary = _vocabulary()
    case = _case(question="합성관계")
    report = _report(tmp_path, vocabulary, [case], top_ks=(1,))
    case_result = report["case_results"][0]
    assert case_result["merged_ids"][0] == "syn:holdsThing"
    assert "syn:holdsThing" in case_result["rule_grounding_ids"]


def test_budget_simulation_reports_its_own_truncation_per_kind(tmp_path) -> None:
    vocabulary = _vocabulary()
    report = _report(tmp_path, vocabulary, [_case()])
    row = report["budget_simulation"][0]
    assert row["budget_total"] == 4
    case_row = row["cases"][0]
    assert sum(case_row["kind_mix"].values()) <= row["budget_total"]
    assert case_row["kind_mix"].get("dataset", 0) <= 1
    assert case_row["kind_mix"].get("field", 0) <= 2
    assert case_row["budget_truncated_by_kind"]


def test_precision_counts_only_the_required_terms_as_relevant(tmp_path) -> None:
    vocabulary = _vocabulary()
    report = _report(tmp_path, vocabulary, [_case()])
    case_row = report["global_top_k"][0]["cases"][0]
    assert case_row["relevant_candidate_count"] == 4
    assert (
        case_row["irrelevant_candidate_count"]
        == case_row["candidate_count"] - case_row["relevant_candidate_count"]
    )
    assert 0.0 < case_row["candidate_precision"] <= 1.0


def test_entity_mentions_are_reported_as_a_structural_gap(tmp_path) -> None:
    vocabulary = _vocabulary()
    case = _case(
        entity_mentions=[
            {"mention_role": "security", "expected_resolution": "entity_resolution_not_implemented"}
        ]
    )
    report = _report(tmp_path, vocabulary, [case])
    gap = report["entity_gap"]
    assert gap["entity_candidate_recall"] == 0.0
    assert gap["excluded_from_all_required_recall"] is True
    assert gap["mentions"][0]["mention_role"] == "security"
    # the gap must not depress the retrieval score it is excluded from
    assert report["path_recall_by_kind"][0]["merged"]["all_required_recall"] == 1.0


def test_coverage_boundary_cases_may_require_no_field(tmp_path) -> None:
    vocabulary = _vocabulary()
    case = _case(
        case_id="boundary-1",
        section="coverage_boundary",
        question="합성상품군의 없는지표를 보여줘",
        required_candidates={"dataset": ["syn:Family"]},
        execution_expectation="unresolved_absent_field",
    )
    report = _report(tmp_path, vocabulary, [case])
    assert report["case_counts"]["coverage_boundary"] == 1
    assert report["global_top_k"][0]["cases"][0]["execution_expectation"] == (
        "unresolved_absent_field"
    )


def test_unknown_execution_expectation_is_rejected(tmp_path) -> None:
    vocabulary = _vocabulary()
    case = _case(execution_expectation="probably_fine")
    with pytest.raises(CompositeError, match="unknown execution expectation"):
        load_composite_proposal(
            _write(tmp_path, vocabulary, [case]), vocabulary, approval_reference="ok"
        )
