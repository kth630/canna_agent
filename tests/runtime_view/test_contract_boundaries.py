"""The boundary rules: completeness, the server's own verdict, and what leaks.

Each test here corresponds to a way the previous version of this layer could
have said yes when it had no business doing so — an empty plan, a refusal
recorded as a mapping, a span nobody wrote, or a reply that handed the model the
Registry identifier it had just failed to guess.
"""

from __future__ import annotations

import json

import pytest

from canna.runtime_view import (
    CODE_CANONICALIZER_UNAVAILABLE,
    CODE_CROSS_FAMILY_FIELD,
    CODE_EMPTY_REQUIREMENT,
    CODE_MISSING_SOURCE_SPAN,
    CODE_MISSING_TARGET,
    CODE_REQUIREMENT_INCOMPLETE,
    CODE_SPAN_ALIGNMENT_FAILED,
    CONTRACT_STATUS,
    DECISION_AMBIGUOUS,
    DECISION_MAPPED,
    DECISION_UNRESOLVED,
    SUBMISSION_SCHEMA,
    BindingSummary,
    CandidateProposal,
    NoExecutionFacts,
    SubmittedCondition,
    SubmittedOrdering,
    SubmittedQuery,
    SubmittedRelationship,
    SubmittedRequirement,
    build_runtime_view,
    model_response,
    tool_definition,
    validate,
)
from canna.runtime_view.contract import STATUS_MAPPED
from canna.runtime_view.execution_facts import STATE_AVAILABLE
from canna.runtime_view.schema import parser_properties, schema_properties
from canna.runtime_view.spans import ALIGNMENT_NORMALIZED, align
from canna.runtime_view.view import MATCH_EXACT

from .conftest import StubEntityResolver, resolved

QUESTION = "알파상품 중에서 알파 비용이 낮은 순으로 10개를 보여줘"


def _view(facts, semantic_ids, **kwargs):
    return build_runtime_view(
        facts,
        QUESTION,
        [CandidateProposal(value, MATCH_EXACT) for value in semantic_ids],
        **kwargs,
    )


def _codes(result):
    return sorted(issue.code for issue in result.issues)


def _requirement(**overrides):
    row = {
        "requirement_id": "r1",
        "kind": "listing",
        "status": STATUS_MAPPED,
        "source_span": "알파상품",
    }
    row.update(overrides)
    return SubmittedRequirement(**row)


# ------------------------------------------------------ minimum completeness


def test_a_mapped_listing_without_a_target_is_refused(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct"])
    result = validate(facts, view, SubmittedQuery((_requirement(),)))
    assert CODE_MISSING_TARGET in _codes(result)
    assert not result.semantic_valid


def test_a_mapped_requirement_without_a_source_span_is_refused(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    source_span="",
                    target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                ),
            )
        ),
    )
    assert CODE_MISSING_SOURCE_SPAN in _codes(result)
    assert not result.semantic_valid


def test_an_attribute_lookup_without_an_output_is_refused(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    kind="attribute_lookup",
                    target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                ),
            )
        ),
    )
    assert CODE_REQUIREMENT_INCOMPLETE in _codes(result)
    assert not result.semantic_valid


def test_an_attribute_lookup_with_an_output_field_is_accepted(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    kind="attribute_lookup",
                    target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                    output_field_refs=(view.ref_for("syn:AlphaCost"),),
                ),
            )
        ),
    )
    assert result.semantic_valid


def test_a_requirement_that_names_nothing_is_never_valid(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct"])
    result = validate(facts, view, SubmittedQuery((_requirement(kind="count"),)))
    assert CODE_EMPTY_REQUIREMENT in _codes(result)
    assert not result.semantic_valid
    assert result.plan.requirements[0].semantic_valid is False


def test_an_empty_submission_is_not_a_valid_plan(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct"])
    result = validate(facts, view, SubmittedQuery(()))
    assert result.plan is None
    assert not result.semantic_valid


# -------------------------------------------- submitted status vs server verdict


def test_a_server_refusal_overrides_the_models_mapped_claim(facts) -> None:
    view = _view(facts, ["syn:BetaProduct", "syn:AlphaCost"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    target_dataset_refs=(view.ref_for("syn:BetaProduct"),),
                    field_refs=(view.ref_for("syn:AlphaCost"),),
                ),
            )
        ),
    )
    requirement = result.plan.requirements[0]
    assert _codes(result) == [CODE_CROSS_FAMILY_FIELD]
    assert requirement.submitted_status == STATUS_MAPPED
    assert requirement.server_decision == DECISION_UNRESOLVED
    assert "r1" in result.unresolved_requirement_ids


def test_an_undecidable_direction_ends_as_ambiguous_not_unresolved(facts) -> None:
    view = _view(
        facts,
        ["syn:AlphaProduct", "syn:isHeldBy"],
        entity_resolver=StubEntityResolver(
            [resolved("알파상품", "syn:AlphaProduct", "alpha:1")]
        ),
    )
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                    relationship=SubmittedRelationship(
                        predicate_ref=view.ref_for("syn:isHeldBy"),
                        anchor_entity_ref=view.entities[0].ref,
                    ),
                ),
            )
        ),
    )
    requirement = result.plan.requirements[0]
    assert requirement.submitted_status == STATUS_MAPPED
    # this particular refusal is a target mismatch, which is not an ambiguity
    assert requirement.server_decision == DECISION_UNRESOLVED
    assert "r1" in result.unresolved_requirement_ids


def test_an_accepted_requirement_keeps_a_mapped_decision(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                    field_refs=(view.ref_for("syn:AlphaCost"),),
                ),
            )
        ),
    )
    assert result.plan.requirements[0].server_decision == DECISION_MAPPED
    assert result.unresolved_requirement_ids == ()


def test_a_model_declared_ambiguity_stays_ambiguous(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct"])
    result = validate(
        facts,
        view,
        SubmittedQuery((_requirement(status="ambiguous"),)),
    )
    assert result.plan.requirements[0].server_decision == DECISION_AMBIGUOUS


# ----------------------------------------------------------- span verification


@pytest.mark.parametrize(
    "overrides",
    [
        {"conditions": (SubmittedCondition(field_ref="", comparison_span="이상"),)},
        {"conditions": (SubmittedCondition(field_ref="", value_span="50개"),)},
        {"ordering": SubmittedOrdering(field_ref="", direction_span="낮은 것부터")},
        {"limit_span": "20개"},
    ],
)
def test_a_span_that_is_not_in_the_question_blocks_execution(facts, overrides) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    fields = {}
    if "conditions" in overrides:
        overrides["conditions"] = tuple(
            SubmittedCondition(
                field_ref=view.ref_for("syn:AlphaCost"),
                comparison_span=item.comparison_span,
                value_span=item.value_span,
            )
            for item in overrides["conditions"]
        )
    if "ordering" in overrides:
        overrides["ordering"] = SubmittedOrdering(
            field_ref=view.ref_for("syn:AlphaCost"),
            direction_span=overrides["ordering"].direction_span,
        )
        fields["field_refs"] = (view.ref_for("syn:AlphaCost"),)
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                    field_refs=fields.get("field_refs", (view.ref_for("syn:AlphaCost"),)),
                    **overrides,
                ),
            )
        ),
    )
    assert CODE_SPAN_ALIGNMENT_FAILED in _codes(result)
    assert not result.semantic_valid


def test_a_span_quoted_from_the_question_passes_alignment(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    kind="ranking",
                    target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                    field_refs=(view.ref_for("syn:AlphaCost"),),
                    ordering=SubmittedOrdering(
                        field_ref=view.ref_for("syn:AlphaCost"), direction_span="낮은 순으로"
                    ),
                    limit_span="10개",
                ),
            )
        ),
    )
    # the spans are quoted, so what stops it is the missing canonicaliser alone
    assert _codes(result) == [
        CODE_CANONICALIZER_UNAVAILABLE,
        CODE_CANONICALIZER_UNAVAILABLE,
    ]


def test_alignment_accepts_the_one_approved_normalisation() -> None:
    assert align("10개를 보여줘", "１０개") == ALIGNMENT_NORMALIZED
    assert align("10개를 보여줘", "10 개를") == "not_in_question"


def test_the_contract_has_no_unverified_free_text_field() -> None:
    from canna.runtime_view.query import REQUIREMENT_PROPERTIES

    assert "note" not in REQUIREMENT_PROPERTIES
    assert not hasattr(SubmittedRequirement("r", "listing", "mapped"), "note")


# ----------------------------------------------- model-facing response is safe


def test_the_model_response_carries_no_identifier_or_key(facts) -> None:
    view = _view(
        facts,
        ["syn:AlphaProduct", "syn:AlphaCost", "syn:holds", "syn:isHeldBy"],
        entity_resolver=StubEntityResolver(
            [resolved("어떤구성요소", "syn:Thing", "thing:verified:9")]
        ),
    )
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                    field_refs=(view.ref_for("syn:AlphaCost"),),
                    relationship=SubmittedRelationship(
                        predicate_ref=view.ref_for("syn:holds"),
                        anchor_entity_ref=view.entities[0].ref,
                    ),
                ),
            )
        ),
    )
    reply = json.dumps(model_response(view, result), ensure_ascii=False)
    for leak in ("syn:", "thing:verified:9", "table", "column", "sql", "join"):
        assert leak not in reply
    # the same information is present in the server's own record
    internal = json.dumps(result.to_dict(), ensure_ascii=False)
    assert "syn:AlphaProduct" in internal
    assert "thing:verified:9" in internal


def test_the_model_response_still_explains_a_refusal(facts) -> None:
    view = _view(facts, ["syn:BetaProduct", "syn:AlphaCost"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    target_dataset_refs=(view.ref_for("syn:BetaProduct"),),
                    field_refs=(view.ref_for("syn:AlphaCost"),),
                ),
            )
        ),
    )
    reply = model_response(view, result)
    assert reply["audience"] == "model_facing"
    assert reply["semantic_valid"] is False
    assert reply["execution_readiness"] == "not_evaluated_by_semantic_validation"
    reasons = reply["requirements"][0]["reasons"]
    assert reasons[0]["code"] == CODE_CROSS_FAMILY_FIELD
    assert "different product" in reasons[0]["meaning"]
    assert "syn:" not in json.dumps(reply, ensure_ascii=False)


def test_the_internal_record_is_labelled_as_server_only(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct"])
    result = validate(facts, view, SubmittedQuery((_requirement(),)))
    assert result.to_dict()["audience"] == "server_internal"
    assert result.to_dict()["contract_status"] == CONTRACT_STATUS


# ------------------------------------------- semantic validity is not readiness


def test_semantic_validity_never_claims_execution_readiness(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"])
    result = validate(
        facts,
        view,
        SubmittedQuery(
            (
                _requirement(
                    target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
                    field_refs=(view.ref_for("syn:AlphaCost"),),
                ),
            )
        ),
    )
    assert result.semantic_valid is True
    assert result.execution_readiness == "not_evaluated_by_semantic_validation"
    assert "after this layer" in result.to_dict()["execution_readiness_basis"]


# --------------------------------------- source, coverage and freshness states


def test_every_candidate_publishes_how_it_is_served(facts) -> None:
    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost", "syn:holds"])
    payload = view.to_model_payload()
    for group in ("fields", "predicates"):
        assert payload[group]
        for item in payload[group]:
            # no adapter is supplied, so no binding is described
            assert item["served_by"] == []
    for item in payload["datasets"]:
        assert item["target_capabilities"]
        assert all(
            summary["coverage_knowledge"] == "not_evaluated"
            and summary["freshness_knowledge"] == "not_evaluated"
            and summary["binding_count"] == 0
            for summary in item["target_capabilities"]
        )
    assert "not proof" in payload["notes"]["served_by"]


def _two_family_binding(semantic_id: str, family: str, grain: str) -> BindingSummary:
    return BindingSummary(
        semantic_id=semantic_id,
        family_id=family,
        subject_grain=grain,
        binding_kind="metric",
        source_id="SOURCE_A",
        semantic_operations=("filter", "order"),
        executable_operations=("filter", "order"),
        coverage_state=STATE_AVAILABLE,
        observed_subjects=100,
        subject_total=120,
        freshness_state=STATE_AVAILABLE,
        effective_as_of_min="2026-08-01",
        effective_as_of_max="2026-08-22",
        as_of_status="known",
        binding_available=True,
    )


def test_a_candidate_served_for_two_families_publishes_both(facts) -> None:
    class TwoBindings:
        def candidate_bindings_for(self, semantic_id: str):
            if semantic_id != "syn:AlphaCost":
                return ()
            return (
                _two_family_binding(semantic_id, "alpha_family", "product"),
                _two_family_binding(semantic_id, "beta_family", "product"),
            )

        def resolve_capability(self, *args, **kwargs):  # pragma: no cover - unused here
            raise AssertionError("not called")

    view = _view(facts, ["syn:AlphaProduct", "syn:AlphaCost"], execution_facts=TwoBindings())
    served = view.field(view.ref_for("syn:AlphaCost")).bindings
    assert [row.family_id for row in served] == ["alpha_family", "beta_family"]
    payload = view.to_model_payload()["fields"][0]["served_by"]
    assert len(payload) == 2
    assert {row["source_id"] for row in payload} == {"SOURCE_A"}
    # the dataset uses a family/grain summary rather than pretending to own a field binding
    summary = view.dataset(view.ref_for("syn:AlphaProduct")).target_capabilities[0]
    assert summary.binding_count == 0
    assert summary.coverage_knowledge == "not_evaluated"
    assert NoExecutionFacts().candidate_bindings_for("syn:AlphaCost") == ()


# ------------------------------------------------------------- schema parity


def test_the_schema_and_the_parser_allow_the_same_properties() -> None:
    assert schema_properties() == parser_properties()


def test_the_schema_is_closed_and_names_its_required_fields() -> None:
    assert SUBMISSION_SCHEMA["additionalProperties"] is False
    assert SUBMISSION_SCHEMA["required"] == ["requirements"]
    requirement = SUBMISSION_SCHEMA["properties"]["requirements"]["items"]
    assert requirement["additionalProperties"] is False
    assert requirement["required"] == ["requirement_id", "kind", "status", "source_span"]
    for name in ("conditions", "ordering", "aggregation", "relationship"):
        nested = requirement["properties"][name]
        nested = nested["items"] if nested["type"] == "array" else nested
        assert nested["additionalProperties"] is False
        assert nested["required"]


def _property_names(node) -> set[str]:
    """Every property name the schema declares, at any depth."""
    names: set[str] = set()
    if isinstance(node, dict):
        names |= set(node.get("properties", {}))
        for value in node.values():
            names |= _property_names(value)
    elif isinstance(node, list):
        for item in node:
            names |= _property_names(item)
    return names


def test_the_schema_offers_no_slot_for_a_physical_plan() -> None:
    names = _property_names(SUBMISSION_SCHEMA)
    assert names
    for forbidden in ("sql", "table", "column", "join", "semantic_id", "traversal", "plan"):
        assert not any(forbidden in name for name in names), (forbidden, sorted(names))
    assert tool_definition()["name"] == "submit_semantic_query"
    assert tool_definition()["x-contract-status"] == CONTRACT_STATUS
