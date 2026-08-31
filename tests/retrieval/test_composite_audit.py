"""A gold audit corrects a published measurement without re-running it."""

from __future__ import annotations

import json

import pytest

from canna.retrieval.composite import (
    CompositeError,
    evaluate_composite,
    load_composite_proposal,
    registry_inverse_alternatives,
)
from canna.retrieval.composite_audit import (
    apply_audit,
    entity_mention_counts,
    load_audit,
    rescore,
    restore_prepared,
)
from canna.retrieval.index import RetrievalIndex, build_index
from canna.retrieval.settings import RuleSettings

from .conftest import StubEmbeddings, synthetic_registry, term
from .test_composite import _case, _vocabulary, _write


def _inverse_vocabulary():
    terms = [
        term("syn:Family", label="합성상품군", kind="class"),
        term("syn:MetricA", label="합성지표가", kind="metric"),
        term("syn:holdsThing", label="합성관계", kind="predicate"),
        term("syn:isHeldByThing", label="합성역관계", kind="predicate"),
    ]
    for row in terms:
        if row["semantic_id"] == "syn:holdsThing":
            row["inverse_of"] = "syn:isHeldByThing"
    return synthetic_registry(terms)


def _run(tmp_path, vocabulary, cases, top_ks=(20,)):
    provider = StubEmbeddings()
    index = RetrievalIndex(*build_index(vocabulary, provider))
    path = _write(tmp_path, vocabulary, cases)
    _metadata, loaded = load_composite_proposal(path, vocabulary, approval_reference="ok")
    report = evaluate_composite(
        vocabulary, index, provider, loaded, rule_settings=RuleSettings(), top_ks=top_ks
    )
    return report, loaded


def test_registry_inverse_is_read_from_the_registry_in_both_directions() -> None:
    vocabulary = _inverse_vocabulary()
    assert registry_inverse_alternatives(vocabulary, "syn:holdsThing") == ("syn:isHeldByThing",)
    assert registry_inverse_alternatives(vocabulary, "syn:isHeldByThing") == ("syn:holdsThing",)
    assert registry_inverse_alternatives(vocabulary, "syn:MetricA") == ()


def test_restored_state_reproduces_the_published_numbers(tmp_path) -> None:
    vocabulary = _vocabulary()
    report, cases = _run(tmp_path, vocabulary, [_case()])
    restored = restore_prepared(vocabulary, report, cases)
    again = rescore(vocabulary, restored, top_ks=(20,))
    assert (
        again["path_recall_by_kind"][0]["merged"]["all_required_recall"]
        == report["path_recall_by_kind"][0]["merged"]["all_required_recall"]
    )


def test_an_invalid_gold_case_is_excluded_and_recorded(tmp_path) -> None:
    vocabulary = _vocabulary()
    report, cases = _run(tmp_path, vocabulary, [_case(), _case(case_id="case-2")])
    restored = restore_prepared(vocabulary, report, cases)
    audit = {
        "case_audits": [
            {"case_id": "case-2", "verdict": "invalid_gold_diagnostic", "reason": "ambiguous"}
        ]
    }
    kept, ledger = apply_audit(vocabulary, restored, audit)
    assert [item.case.case_id for item in kept] == ["case-1"]
    excluded = next(row for row in ledger if row["case_id"] == "case-2")
    assert excluded["scored"] is False
    assert excluded["reason"] == "ambiguous"


def test_a_partial_audit_removes_one_slot_and_keeps_the_rest(tmp_path) -> None:
    vocabulary = _vocabulary()
    report, cases = _run(tmp_path, vocabulary, [_case()])
    restored = restore_prepared(vocabulary, report, cases)
    audit = {
        "case_audits": [
            {
                "case_id": "case-1",
                "verdict": "invalid_gold_partial",
                "reason": "relation kind not stated",
                "required_overrides": {"predicate": []},
            }
        ]
    }
    kept, ledger = apply_audit(vocabulary, restored, audit)
    assert kept[0].case.required["predicate"] == ()
    assert kept[0].case.required["field"] == ("syn:MetricA", "syn:MetricB")
    assert ledger[0]["removed_required_ids"] == ["syn:holdsThing"]
    by_kind = {
        row["kind"]: row
        for row in rescore(vocabulary, kept, top_ks=(20,))["path_recall_by_kind"][0]["merged"][
            "by_kind"
        ]
    }
    assert "predicate" not in by_kind


def test_inverse_predicates_satisfy_each_other_and_stop_counting_as_confusion(
    tmp_path,
) -> None:
    vocabulary = _inverse_vocabulary()
    # The question names one end of the pair; the gold demanded the other end.
    # A single-seat merge isolates the substitution from any incidental recall.
    case = _case(
        question="합성관계",
        required_candidates={"dataset": [], "field": [], "predicate": ["syn:isHeldByThing"]},
        confusion_sets={"relation_direction": ["syn:holdsThing"]},
    )
    report, cases = _run(tmp_path, vocabulary, [case], top_ks=(1,))
    restored = restore_prepared(vocabulary, report, cases)
    before = rescore(vocabulary, restored, top_ks=(1,))
    kept, ledger = apply_audit(vocabulary, restored, {"case_audits": []})
    after = rescore(vocabulary, kept, top_ks=(1,))

    def predicate_recall(payload):
        rows = payload["path_recall_by_kind"][0]["merged"]["by_kind"]
        return next(row["all_required_of_kind_recall"] for row in rows if row["kind"] == "predicate")

    assert predicate_recall(before) == 0.0
    assert predicate_recall(after) == 1.0
    assert kept[0].case.accepted_for("syn:isHeldByThing") == (
        "syn:isHeldByThing",
        "syn:holdsThing",
    )
    assert ledger[0]["confusable_ids_reclassified_as_equivalent"] == ["syn:holdsThing"]
    totals = after["global_top_k"][0]["aggregate"]["confusion_totals"]
    assert totals["relation_direction"]["declared"] == 0


def test_audit_file_requires_a_reason_and_a_known_verdict(tmp_path) -> None:
    path = tmp_path / "audit.json"
    path.write_text(
        json.dumps({"case_audits": [{"case_id": "c", "verdict": "valid"}]}), encoding="utf-8"
    )
    with pytest.raises(CompositeError, match="must record a reason"):
        load_audit(path)
    path.write_text(
        json.dumps({"case_audits": [{"case_id": "c", "verdict": "meh", "reason": "x"}]}),
        encoding="utf-8",
    )
    with pytest.raises(CompositeError, match="unknown audit verdict"):
        load_audit(path)


def test_entity_mention_counts_are_reported_per_scored_scope(tmp_path) -> None:
    vocabulary = _vocabulary()
    mention = {
        "mention_role": "security",
        "expected_resolution": "entity_resolution_not_implemented",
    }
    report, cases = _run(
        tmp_path,
        vocabulary,
        [_case(entity_mentions=[mention]), _case(case_id="case-2", entity_mentions=[mention])],
    )
    restored = restore_prepared(vocabulary, report, cases)
    assert entity_mention_counts(restored) == {
        "cases_with_entity_mention": 2,
        "entity_mention_count": 2,
    }
    kept, _ledger = apply_audit(
        vocabulary,
        restored,
        {
            "case_audits": [
                {"case_id": "case-2", "verdict": "invalid_gold_diagnostic", "reason": "ambiguous"}
            ]
        },
    )
    assert entity_mention_counts(kept)["entity_mention_count"] == 1
