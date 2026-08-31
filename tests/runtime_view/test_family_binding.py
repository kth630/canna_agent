"""A wrong product family must fail loudly, and never be corrected in silence."""

from __future__ import annotations

import json

import pytest

from canna.runtime_view import (
    CODE_CANONICALIZER_UNAVAILABLE,
    CODE_CROSS_FAMILY_FIELD,
    CODE_DIRECTION_UNDECIDABLE,
    CODE_ENTITY_UNRESOLVED,
    CODE_FIELD_SCOPE_UNPROVEN,
    CODE_GRAIN_MISMATCH,
    CODE_REF_KIND_MISMATCH,
    CODE_RELATION_TARGET_MISMATCH,
    CODE_REQUIREMENT_INCOMPLETE,
    CODE_SPAN_ALIGNMENT_FAILED,
    CODE_UNACCOUNTED_SPAN,
    CODE_UNKNOWN_REF,
    CONTRACT_STATUS,
    REQUIREMENT_KINDS,
    BudgetError,
    CandidateBudget,
    CandidateProposal,
    EntityMention,
    RefMinter,
    SubmittedCondition,
    SubmittedOrdering,
    SubmittedQuery,
    SubmittedRelationship,
    SubmittedRequirement,
    build_runtime_view,
    parse_submission,
    validate,
)
from canna.runtime_view.query import STATUS_MAPPED, STATUS_UNRESOLVED
from canna.runtime_view.view import (
    MATCH_EXACT,
    MEANING_UNNAMED,
    SCOPE_UNPROVEN,
    candidate_kind,
)

from .conftest import FAMILY_A, StubEntityResolver, registry, resolved, term

QUESTION = "질문 원문 조각을 포함한 전체 질문"


def _proposals(*semantic_ids: str) -> list[CandidateProposal]:
    return [CandidateProposal(value, MATCH_EXACT) for value in semantic_ids]


def _view(facts, semantic_ids, **kwargs):
    return build_runtime_view(facts, QUESTION, _proposals(*semantic_ids), **kwargs)


def _requirement(view, *, targets, fields=(), relationship=None, kind="listing", **extra):
    return SubmittedRequirement(
        requirement_id="r1",
        kind=kind,
        status=STATUS_MAPPED,
        source_span="질문 원문 조각",
        target_dataset_refs=tuple(view.ref_for(value) for value in targets),
        field_refs=tuple(view.ref_for(value) for value in fields),
        relationship=relationship,
        **extra,
    )


def _codes(result):
    return sorted(issue.code for issue in result.issues)


def _thing_anchor():
    return StubEntityResolver([resolved("어떤구성요소", "syn:Thing", "thing:verified:1")])


# ---------------------------------------------------------------- family rules


def test_a_field_from_another_family_is_refused_without_a_substitute(facts) -> None:
    view = _view(facts, ["syn:BetaProduct", "syn:AlphaCost", "syn:BetaCost"])
    submission = SubmittedQuery(
        (_requirement(view, targets=["syn:BetaProduct"], fields=["syn:AlphaCost"]),)
    )
    result = validate(facts, view, submission)
    assert not result.semantic_valid
    assert _codes(result) == [CODE_CROSS_FAMILY_FIELD]
    assert result.issues[0].substitute_offered is False
    # the correctly-familied twin is right there and is still not swapped in
    assert view.ref_for("syn:BetaCost") is not None
    assert result.plan.requirements[0].field_bindings == ()


def test_the_rule_is_symmetric_across_families(facts) -> None:
    good = _view(facts, ["syn:AlphaProduct", "syn:AlphaSize"])
    bad = _view(facts, ["syn:BetaProduct", "syn:AlphaSize"])
    assert validate(
        facts,
        good,
        SubmittedQuery((_requirement(good, targets=["syn:AlphaProduct"], fields=["syn:AlphaSize"]),)),
    ).semantic_valid
    assert _codes(
        validate(
            facts,
            bad,
            SubmittedQuery((_requirement(bad, targets=["syn:BetaProduct"], fields=["syn:AlphaSize"]),)),
        )
    ) == [CODE_CROSS_FAMILY_FIELD]


def test_two_families_in_one_requirement_keep_separate_bindings(facts) -> None:
    view = _view(
        facts, ["syn:AlphaProduct", "syn:BetaProduct", "syn:AlphaCost", "syn:BetaCost"]
    )
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    view,
                    targets=["syn:AlphaProduct", "syn:BetaProduct"],
                    fields=["syn:AlphaCost", "syn:BetaCost"],
                ),
            )
        ),
    )
    assert result.semantic_valid
    assert {
        (binding.target_dataset_id, binding.field_id)
        for binding in result.plan.requirements[0].field_bindings
    } == {("syn:AlphaProduct", "syn:AlphaCost"), ("syn:BetaProduct", "syn:BetaCost")}


def test_binding_follows_the_selected_target_not_the_first_of_the_family(facts) -> None:
    """One family, two datasets: the field binds to the target actually chosen."""
    view = _view(
        facts,
        ["syn:AlphaProduct", "syn:AlphaClass", "syn:AlphaCost", "syn:AlphaClassFee"],
    )
    assert {item.semantic_id for item in view.datasets} == {"syn:AlphaProduct", "syn:AlphaClass"}

    to_class = validate(
        facts,
        view,
        SubmittedQuery(
            (_requirement(view, targets=["syn:AlphaClass"], fields=["syn:AlphaClassFee"]),)
        ),
    )
    assert to_class.semantic_valid
    assert to_class.plan.requirements[0].field_bindings[0].target_dataset_id == "syn:AlphaClass"

    to_product = validate(
        facts,
        view,
        SubmittedQuery(
            (_requirement(view, targets=["syn:AlphaProduct"], fields=["syn:AlphaCost"]),)
        ),
    )
    assert to_product.semantic_valid
    assert (
        to_product.plan.requirements[0].field_bindings[0].target_dataset_id == "syn:AlphaProduct"
    )


def test_the_same_family_at_the_wrong_grain_is_refused(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaClass", "syn:AlphaClassFee"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (_requirement(view, targets=["syn:AlphaProduct"], fields=["syn:AlphaClassFee"]),)
        ),
    )
    assert _codes(result) == [CODE_GRAIN_MISMATCH]


def test_a_field_with_no_declared_family_is_unresolved_not_universal(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:BetaProduct", "syn:SharedName"])
    candidate = view.field(view.ref_for("syn:SharedName"))
    assert candidate.dataset_scope == SCOPE_UNPROVEN
    assert candidate.belongs_to_dataset_refs == ()
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (_requirement(view, targets=["syn:AlphaProduct"], fields=["syn:SharedName"]),)
        ),
    )
    assert _codes(result) == [CODE_FIELD_SCOPE_UNPROVEN]


# ------------------------------------------------------------- dataset candidacy


def test_only_family_classes_at_a_result_grain_become_datasets(facts) -> None:
    view = _view(facts, ["syn:Product", "syn:Thing", "syn:Book", "syn:AlphaProduct"])
    assert {item.semantic_id for item in view.datasets} == {"syn:AlphaProduct"}
    assert {item.semantic_id for item in view.excluded} == {
        "syn:Product",
        "syn:Thing",
        "syn:Book",
    }
    assert candidate_kind(facts, "syn:Thing") == ""
    assert candidate_kind(facts, "syn:AlphaProduct") == "dataset"
    assert candidate_kind(facts, "syn:holds") == "predicate"
    assert candidate_kind(facts, "syn:AlphaCost") == "field"


def test_a_security_class_cannot_be_used_as_a_target(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:Thing", "syn:AlphaCost"])
    # there is no reference to hand the model, because it is not a candidate
    assert view.ref_for("syn:Thing") is None


def test_family_closure_covers_predicates_as_well_as_fields(facts) -> None:
    """A question with no field candidate still gets the family's dataset."""
    view = _view(facts, ["syn:betaHolds"])
    assert [item.semantic_id for item in view.datasets] == ["syn:BetaProduct"]
    assert view.datasets[0].introduced_by == "family_closure"
    families = {
        family
        for candidate in (*view.fields, *view.predicates)
        for family in candidate.families
    }
    covered = {family for item in view.datasets for family in item.families}
    assert families <= covered


def test_a_predicate_with_no_family_introduces_no_dataset(facts) -> None:
    """The claim is about declared families, and this predicate declares none."""
    view = _view(facts, ["syn:holds"])
    assert view.datasets == ()
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                SubmittedRequirement(
                    requirement_id="r1",
                    kind="listing",
                    status=STATUS_MAPPED,
                    relationship=SubmittedRelationship(
                        predicate_ref=view.ref_for("syn:holds"), anchor_entity_ref="en_missing"
                    ),
                ),
            )
        ),
    )
    assert "missing_target_dataset" in _codes(result)


# ------------------------------------------------------------------- relations


def test_the_server_decides_relation_direction_from_the_anchor_type(facts) -> None:
    view = _view(
        facts,
        ["syn:AlphaProduct", "syn:holds", "syn:isHeldBy"],
        entity_resolver=_thing_anchor(),
    )
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    view,
                    targets=["syn:AlphaProduct"],
                    relationship=SubmittedRelationship(
                        predicate_ref=view.ref_for("syn:holds"),
                        anchor_entity_ref=view.entities[0].ref,
                    ),
                ),
            )
        ),
    )
    assert result.semantic_valid
    relation = result.plan.requirements[0].relation
    assert relation.submitted_predicate_id == "syn:holds"
    assert relation.predicate_id == "syn:isHeldBy"
    assert relation.subject_class_id == "syn:Thing"
    assert relation.traversal == "anchor_is_subject"


def test_the_plan_carries_the_verified_key_not_the_mention_text(facts) -> None:
    view = _view(
        facts,
        ["syn:AlphaProduct", "syn:holds", "syn:isHeldBy"],
        entity_resolver=_thing_anchor(),
    )
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    view,
                    targets=["syn:AlphaProduct"],
                    relationship=SubmittedRelationship(
                        predicate_ref=view.ref_for("syn:holds"),
                        anchor_entity_ref=view.entities[0].ref,
                    ),
                ),
            )
        ),
    )
    relation = result.plan.requirements[0].relation
    assert relation.anchor_entity_key == "thing:verified:1"
    assert relation.anchor_entity_key != "어떤구성요소"
    assert relation.anchor_class_id == "syn:Thing"
    # and the verified key never reaches the model
    payload = json.dumps(view.to_model_payload(), ensure_ascii=False)
    assert "thing:verified:1" not in payload
    assert "어떤구성요소" in payload


def test_an_indirect_relation_is_not_interchangeable_with_a_direct_one(facts) -> None:
    view = _view(
        facts,
        [
            "syn:AlphaProduct",
            "syn:holds",
            "syn:isHeldBy",
            "syn:hasIndirectExposureTo",
            "syn:isIndirectExposureOf",
        ],
        entity_resolver=_thing_anchor(),
    )
    indirect = view.predicate(view.ref_for("syn:hasIndirectExposureTo"))
    assert set(indirect.distinct_from_refs) == {
        view.ref_for("syn:holds"),
        view.ref_for("syn:isHeldBy"),
    }
    assert indirect.inverse_ref == view.ref_for("syn:isIndirectExposureOf")

    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    view,
                    targets=["syn:AlphaProduct"],
                    relationship=SubmittedRelationship(
                        predicate_ref=view.ref_for("syn:hasIndirectExposureTo"),
                        anchor_entity_ref=view.entities[0].ref,
                    ),
                ),
            )
        ),
    )
    assert result.semantic_valid
    relation = result.plan.requirements[0].relation
    assert relation.predicate_id == "syn:isIndirectExposureOf"
    assert relation.predicate_id not in {"syn:holds", "syn:isHeldBy"}


def test_an_unresolved_anchor_refuses_the_relation_instead_of_guessing(facts) -> None:
    resolver = StubEntityResolver([EntityMention(mention_text="어떤것")])
    view = _view(facts, ["syn:AlphaProduct", "syn:holds"], entity_resolver=resolver)
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    view,
                    targets=["syn:AlphaProduct"],
                    relationship=SubmittedRelationship(
                        predicate_ref=view.ref_for("syn:holds"),
                        anchor_entity_ref=view.entities[0].ref,
                    ),
                ),
            )
        ),
    )
    assert _codes(result) == [CODE_ENTITY_UNRESOLVED]


def test_a_relation_that_cannot_reach_the_target_is_refused(facts) -> None:
    resolver = StubEntityResolver([resolved("어떤상품", "syn:AlphaProduct", "alpha:1")])
    view = _view(facts, ["syn:AlphaProduct", "syn:isHeldBy"], entity_resolver=resolver)
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    view,
                    targets=["syn:AlphaProduct"],
                    relationship=SubmittedRelationship(
                        predicate_ref=view.ref_for("syn:isHeldBy"),
                        anchor_entity_ref=view.entities[0].ref,
                    ),
                ),
            )
        ),
    )
    assert _codes(result) == [CODE_RELATION_TARGET_MISMATCH]


def test_a_symmetric_relation_leaves_the_direction_undecidable() -> None:
    symmetric = registry(
        [
            term("syn:Product", label="상품", operations=(), grains=["product"]),
            term(
                "syn:AlphaProduct",
                label="알파상품",
                families=[FAMILY_A],
                grains=["product"],
                operations=(),
                subclass_of=["syn:Product"],
            ),
            term(
                "syn:tracks",
                label="추종한다",
                domain=["syn:Product"],
                range_=["syn:Product"],
                inverse_of="syn:isTrackedBy",
                grains=["product"],
                operations=["exists"],
            ),
            term(
                "syn:isTrackedBy",
                label="추종된다",
                domain=["syn:Product"],
                range_=["syn:Product"],
                grains=["product"],
                operations=["exists"],
            ),
        ]
    )
    resolver = StubEntityResolver([resolved("어떤상품", "syn:AlphaProduct", "alpha:1")])
    view = _view(symmetric, ["syn:AlphaProduct", "syn:tracks"], entity_resolver=resolver)
    result = validate(
        symmetric,
        view,
        SubmittedQuery(
            (
                _requirement(
                    view,
                    targets=["syn:AlphaProduct"],
                    relationship=SubmittedRelationship(
                        predicate_ref=view.ref_for("syn:tracks"),
                        anchor_entity_ref=view.entities[0].ref,
                    ),
                ),
            )
        ),
    )
    assert _codes(result) == [CODE_DIRECTION_UNDECIDABLE]


# ----------------------------------------------------------------- references


def test_invented_and_cross_request_references_are_refused(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    other = build_runtime_view(
        facts,
        "다른 질문",
        _proposals("syn:AlphaProduct", "syn:AlphaCost"),
        minter=RefMinter(salt=b"another-request-salt"),
    )
    for bad_ref in ("fd_" + "d" * 32, other.ref_for("syn:AlphaCost")):
        submission = SubmittedQuery(
            (
                SubmittedRequirement(
                    requirement_id="r1",
                    kind="listing",
                    status=STATUS_MAPPED,
                    source_span="질문 원문 조각",
                    target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                    field_refs=(bad_ref,),
                ),
            )
        )
        assert _codes(validate(facts, view, submission)) == [CODE_UNKNOWN_REF]


def test_a_reference_used_in_the_wrong_slot_is_refused(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    submission = SubmittedQuery(
        (
            SubmittedRequirement(
                requirement_id="r1",
                kind="listing",
                status=STATUS_MAPPED,
                source_span="질문 원문 조각",
                target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                field_refs=(view.ref_for("syn:AlphaProduct"),),
            ),
        )
    )
    assert _codes(validate(facts, view, submission)) == [CODE_REF_KIND_MISMATCH]


def test_references_are_wide_and_collision_checked(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost", "syn:holds"])
    for candidate in (*view.datasets, *view.fields, *view.predicates):
        prefix, _, digest = candidate.ref.partition("_")
        assert len(prefix) == 2
        assert len(digest) == 32
    minter = RefMinter(salt=b"fixed")
    first = minter.mint("field", "syn:A")
    assert minter.mint("field", "syn:A") == first
    assert minter.mint("field", "syn:B") != first


def test_canonical_plan_is_invariant_to_order_and_reference_values(facts) -> None:
    forward = ["syn:AlphaProduct", "syn:BetaProduct", "syn:AlphaCost", "syn:BetaCost"]
    plans = []
    for salt, ordering in ((b"salt-one", forward), (b"salt-two", list(reversed(forward)))):
        view = build_runtime_view(
            facts, QUESTION, _proposals(*ordering), minter=RefMinter(salt=salt)
        )
        result = validate(
            facts,
            view,
            SubmittedQuery(
                (
                    _requirement(
                        view,
                        targets=["syn:BetaProduct", "syn:AlphaProduct"],
                        fields=["syn:BetaCost", "syn:AlphaCost"],
                    ),
                )
            ),
        )
        assert result.semantic_valid
        payload = result.plan.to_dict()
        for row in payload["requirements"]:
            row["preserved"]["submitted_refs"] = "<per-request>"
        plans.append(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    assert plans[0] == plans[1]


# -------------------------------------------------------------------- payload


def test_the_model_payload_hides_ids_scores_and_physical_bindings(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost", "syn:holds"])
    payload = json.dumps(view.to_model_payload(), ensure_ascii=False)
    for semantic_id in ("syn:AlphaProduct", "syn:AlphaCost", "syn:holds"):
        assert semantic_id not in payload
    for forbidden in ("score", "rank", "table", "column", "sql", "join", "semantic_id"):
        assert forbidden not in payload
    assert CONTRACT_STATUS in payload


def test_an_unnamed_candidate_does_not_fall_back_to_its_semantic_id(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:Unnamed"])
    candidate = view.field(view.ref_for("syn:Unnamed"))
    assert candidate.meaning == ""
    assert candidate.meaning_status == MEANING_UNNAMED
    assert "syn:Unnamed" not in json.dumps(view.to_model_payload(), ensure_ascii=False)


def test_surface_form_match_is_published_as_a_lexical_signal_only(facts) -> None:
    view = _view(facts, ["syn:BetaProduct", "syn:AlphaCost"])
    payload = view.to_model_payload()
    assert payload["fields"][0]["surface_form_match"] == MATCH_EXACT
    assert "does not decide the product family" in payload["notes"]["surface_form_match"]
    assert not validate(
        facts,
        view,
        SubmittedQuery(
            (_requirement(view, targets=["syn:BetaProduct"], fields=["syn:AlphaCost"]),)
        ),
    ).semantic_valid


# --------------------------------------------------------------------- budgets


def test_without_a_budget_candidates_are_kept_and_still_grouped(facts) -> None:
    view = _view(
        facts,
        [
            "syn:AlphaProduct",
            "syn:BetaProduct",
            "syn:AlphaCost",
            "syn:BetaCost",
            "syn:AlphaSize",
            "syn:holds",
            "syn:isHeldBy",
        ],
    )
    assert view.budget_applied is False
    assert view.truncated_by_kind == {}
    # alpha is queryable at two grains, so its closure contributes both
    assert {item.semantic_id for item in view.datasets} == {
        "syn:AlphaProduct",
        "syn:AlphaClass",
        "syn:BetaProduct",
    }
    assert len(view.fields) == 3
    assert len(view.predicates) == 2
    assert set(view.to_model_payload()) >= {"datasets", "fields", "predicates", "entities"}


def test_a_budget_truncates_only_what_retrieval_proposed(facts) -> None:
    view = _view(
        facts,
        ["syn:AlphaProduct", "syn:AlphaCost", "syn:AlphaSize", "syn:holds"],
        budget=CandidateBudget({"field": 1}),
    )
    assert view.budget_applied is True
    assert view.truncated_by_kind == {"field": 1}
    assert len(view.fields) == 1


def test_family_closure_datasets_are_exempt_from_the_dataset_budget(facts) -> None:
    """Truncating a closure dataset would delete the evidence of a wrong family."""
    view = _view(
        facts,
        ["syn:AlphaProduct", "syn:AlphaCost", "syn:BetaCost"],
        budget=CandidateBudget({"dataset": 1}),
    )
    assert view.truncated_by_kind == {}
    assert view.budget_exempt_datasets == 2
    assert {item.semantic_id for item in view.datasets} == {
        "syn:AlphaProduct",
        "syn:AlphaClass",
        "syn:BetaProduct",
    }
    beta = view.field(view.ref_for("syn:BetaCost"))
    assert beta.belongs_to_dataset_refs


def test_a_budget_rejects_negative_seats_and_unknown_kinds() -> None:
    with pytest.raises(BudgetError, match="do not exist"):
        CandidateBudget({"entity": 3})
    with pytest.raises(BudgetError, match="must not be negative"):
        CandidateBudget({"field": -1})


# -------------------------------------------------- requirement kinds and spans


def test_requirement_kinds_are_the_canonical_eight() -> None:
    assert set(REQUIREMENT_KINDS) == {
        "listing",
        "attribute_lookup",
        "count",
        "aggregation",
        "ranking",
        "grouping",
        "comparison",
        "explanation",
    }


def test_a_ranking_without_a_direction_or_a_limit_is_not_given_defaults(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    view, targets=["syn:AlphaProduct"], fields=["syn:AlphaCost"], kind="ranking"
                ),
            )
        ),
    )
    assert CODE_REQUIREMENT_INCOMPLETE in _codes(result)
    assert not result.semantic_valid
    assert result.plan.requirements[0].semantic_valid is False


def test_an_operation_with_no_canonicalizer_is_returned_non_executable(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    view,
                    targets=["syn:AlphaProduct"],
                    fields=["syn:AlphaCost"],
                    kind="ranking",
                    ordering=SubmittedOrdering(
                        field_ref=view.ref_for("syn:AlphaCost"), direction_span="높은 순"
                    ),
                    limit_span="10개",
                ),
            )
        ),
    )
    assert not result.semantic_valid
    assert CODE_CANONICALIZER_UNAVAILABLE in _codes(result)
    blocking = result.plan.requirements[0].blocking_codes
    assert CODE_CANONICALIZER_UNAVAILABLE in blocking


def test_the_plan_preserves_every_span_and_reference_it_could_not_execute(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    view,
                    targets=["syn:AlphaProduct"],
                    fields=["syn:AlphaCost"],
                    kind="ranking",
                    conditions=(
                        SubmittedCondition(
                            field_ref=view.ref_for("syn:AlphaCost"),
                            comparison_span="이하",
                            value_span="0.3%",
                        ),
                    ),
                    ordering=SubmittedOrdering(
                        field_ref=view.ref_for("syn:AlphaCost"), direction_span="높은 순"
                    ),
                    limit_span="10개",
                ),
            )
        ),
    )
    preserved = result.plan.requirements[0].preserved
    assert preserved.source_span == "질문 원문 조각"
    assert preserved.condition_spans == (("syn:AlphaCost", "이하", "0.3%"),)
    assert preserved.ordering_span == ("syn:AlphaCost", "높은 순")
    assert preserved.limit_span == "10개"
    assert view.ref_for("syn:AlphaCost") in preserved.submitted_refs


def test_a_span_that_is_not_in_the_question_is_refused(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    submission = SubmittedQuery(
        (
            SubmittedRequirement(
                requirement_id="r1",
                kind="listing",
                status=STATUS_MAPPED,
                source_span="질문에 없는 문구",
                target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                field_refs=(view.ref_for("syn:AlphaCost"),),
            ),
        )
    )
    assert CODE_SPAN_ALIGNMENT_FAILED in _codes(validate(facts, view, submission))


def test_an_unaccounted_span_forbids_execution(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    submission = SubmittedQuery(
        requirements=(
            _requirement(view, targets=["syn:AlphaProduct"], fields=["syn:AlphaCost"]),
        ),
        unaccounted_spans=("남은 요구",),
    )
    result = validate(facts, view, submission)
    assert _codes(result) == [CODE_UNACCOUNTED_SPAN]
    assert not result.semantic_valid


def test_an_unresolved_requirement_is_preserved_and_not_executed(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                SubmittedRequirement(
                    requirement_id="r9",
                    kind="ranking",
                    status=STATUS_UNRESOLVED,
                    source_span="질문 원문 조각",
                ),
            )
        ),
    )
    assert result.unresolved_requirement_ids == ("r9",)
    assert not result.semantic_valid
    assert result.plan.requirements[0].preserved.source_span == "질문 원문 조각"


def test_a_condition_field_is_family_checked_like_an_output_field(facts) -> None:
    view = _view(facts, ["syn:BetaProduct", "syn:AlphaCost"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    view,
                    targets=["syn:BetaProduct"],
                    conditions=(SubmittedCondition(field_ref=view.ref_for("syn:AlphaCost")),),
                ),
            )
        ),
    )
    assert CODE_CROSS_FAMILY_FIELD in _codes(result)


# ---------------------------------------------------------------- parse, closed


def test_parsing_refuses_a_string_where_a_list_belongs() -> None:
    parsed = parse_submission(
        {
            "requirements": [
                {
                    "requirement_id": "r1",
                    "kind": "listing",
                    "status": "mapped",
                    "source_span": "알파상품",
                    "target_dataset_refs": "ds_abc",
                }
            ]
        }
    )
    assert not parsed.well_formed
    assert "wrong_property_type" in {problem.code for problem in parsed.problems}
    assert parsed.query.requirements == ()


def test_parsing_refuses_unknown_properties_and_non_object_conditions() -> None:
    unknown = parse_submission(
        {
            "requirements": [
                {
                    "requirement_id": "r1",
                    "kind": "listing",
                    "status": "mapped",
                    "sql": "select 1",
                }
            ]
        }
    )
    assert unknown.problems[0].code == "unknown_property"
    bad_condition = parse_submission(
        {
            "requirements": [
                {
                    "requirement_id": "r1",
                    "kind": "listing",
                    "status": "mapped",
                    "source_span": "알파상품",
                    "conditions": ["fd_1"],
                }
            ]
        }
    )
    assert "wrong_property_type" in {problem.code for problem in bad_condition.problems}
    assert bad_condition.query.requirements == ()


def test_parsing_reports_shape_problems_and_accepts_a_valid_payload() -> None:
    assert parse_submission({}).problems[0].code == "malformed_submission"
    assert parse_submission({"requirements": []}).problems[0].code == "empty_submission"
    assert (
        parse_submission(
            {"requirements": [{"requirement_id": "r1", "kind": "sql", "status": "mapped"}]}
        ).problems[0].code
        == "unknown_requirement_kind"
    )
    good = parse_submission(
        {
            "requirements": [
                {
                    "requirement_id": "r1",
                    "kind": "ranking",
                    "status": "mapped",
                    "source_span": "국내 ETF",
                    "target_dataset_refs": ["ds_" + "0" * 32],
                    "field_refs": ["fd_" + "1" * 32],
                    "conditions": [
                        {
                            "field_ref": "fd_" + "2" * 32,
                            "comparison_span": "이하",
                            "value_span": "0.3%",
                        }
                    ],
                    "ordering": {"field_ref": "fd_" + "1" * 32, "direction_span": "높은 순"},
                    "limit_span": "10개",
                }
            ],
            "unaccounted_spans": [],
        }
    )
    assert good.well_formed
    requirement = good.query.requirements[0]
    assert requirement.conditions[0].value_span == "0.3%"
    assert requirement.ordering.direction_span == "높은 순"
    assert requirement.limit_span == "10개"


def test_the_rules_do_not_depend_on_any_particular_family_name(facts) -> None:
    families = {
        family
        for term_ in facts.terms
        for family in (term_.evidence.get("families") or ())
    }
    assert families == {FAMILY_A, "beta_family"}
    view = _view(facts, ["syn:BetaProduct", "syn:AlphaCost"])
    assert not validate(
        facts,
        view,
        SubmittedQuery(
            (_requirement(view, targets=["syn:BetaProduct"], fields=["syn:AlphaCost"]),)
        ),
    ).semantic_valid


@pytest.mark.parametrize("ref", ["", "ds_", "not-a-ref"])
def test_malformed_references_are_refused_rather_than_ignored(facts, ref) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    submission = SubmittedQuery(
        (
            SubmittedRequirement(
                requirement_id="r1",
                kind="listing",
                status=STATUS_MAPPED,
                source_span="질문 원문 조각",
                target_dataset_refs=(ref,),
                field_refs=(view.ref_for("syn:AlphaCost"),),
            ),
        )
    )
    result = validate(facts, view, submission)
    assert CODE_UNKNOWN_REF in _codes(result)
    assert not result.semantic_valid
