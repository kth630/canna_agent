"""The wired path, end to end and offline: submission to execution values, or refusal.

Two things are asserted here that no single-layer test can assert. The first is
that the whole path holds together: a Runtime View built from the real Semantic
and Execution Registries, a submission written in the notation HCX is actually
sent, read back by the line parser, validated against the Registry, canonicalised
into execution values, and carried into the executor's own request type. The
second is that a refusal anywhere on that path stops it — not by convention but
because a requirement that refused anything releases no execution values at all.

Nothing here reaches the network or a model. The one place a database is touched,
the assertion is that execution does *not* succeed: the Registry extension the
Execution workstream specified does not exist yet, so a plan whose meaning is
entirely in order still has to come back unexecuted rather than answered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from canna.runtime_view import (
    CODE_CANONICALIZATION_REFUSED,
    CODE_CANONICALIZER_UNAVAILABLE,
    CODE_REQUIREMENT_INCOMPLETE,
    DATASET_GRAINS,
    DECISION_MAPPED,
    ENVELOPE_PROPERTY,
    STATUS_MAPPED,
    CandidateProposal,
    SubmittedAggregation,
    SubmittedOrdering,
    SubmittedQuery,
    SubmittedRequirement,
    build_runtime_view,
    parse_tool_arguments,
    render_one_line_records,
    validate,
)
from canna.runtime_view.view import MATCH_EXACT

from .hcx_runtime_view_live_support import APPROVED_QUESTION, build_approved_live_case

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "data" / "processed" / "query_store.duckdb"
EXECUTION_REGISTRY = ROOT / "data" / "processed" / "execution_registry.json"

SYNTHETIC_QUESTION = "알파상품 중에서 알파 비용이 낮은 순으로 10개를 보여줘"


@pytest.fixture
def view(facts):
    """A per-request view over the synthetic registry, as any request builds one."""
    return build_runtime_view(
        facts,
        SYNTHETIC_QUESTION,
        [
            CandidateProposal("syn:AlphaProduct", MATCH_EXACT),
            CandidateProposal("syn:AlphaCost", MATCH_EXACT),
        ],
    )


def _ranking_wire(case, *, direction_span: str, limit_span: str) -> dict:
    """One ranking requirement over references this request actually minted."""
    return {
        "requirement_records": [
            {
                "requirement_id": "v1",
                "kind": "ranking",
                "status": STATUS_MAPPED,
                "source_span": APPROVED_QUESTION,
                "limit_span": limit_span,
            }
        ],
        "ref_records": [
            {
                "requirement_id": "v1",
                "role": "target_dataset",
                "ref": case.expected_dataset_ref,
            }
        ],
        "detail_records": [
            {
                "requirement_id": "v1",
                "detail_kind": "ordering",
                "ref": case.expected_field_ref,
                "span": direction_span,
            }
        ],
    }


def _through_the_wire(case, wire):
    """Render, read and validate: the path a real call takes, without the call."""
    parsed = parse_tool_arguments(
        {ENVELOPE_PROPERTY: render_one_line_records(wire)}
    )
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None
    return parsed, validate(case.facts, case.view, parsed.query)


# --------------------------------------------------------------- the vertical


@pytest.mark.real_data
def test_a_submission_travels_from_the_runtime_view_to_a_blocked_execution() -> None:
    """Runtime View to line parser to validation to canonicalisation to no execution.

    The one vertical test. Every stage is the production one, and the last
    stage's answer is that it will not run: the Execution Registry carries no
    row-level provenance or selection policy, so a semantically perfect plan is
    refused rather than answered out of the store.
    """
    case = build_approved_live_case()

    # 1. the Runtime View published per-request references and nothing stable
    dataset = case.view.dataset(case.expected_dataset_ref)
    field = case.view.field(case.expected_field_ref)
    assert dataset is not None and field is not None

    # 2-3. the notation HCX is actually sent, read back by the line parser
    parsed, result = _through_the_wire(
        case, _ranking_wire(case, direction_span="높은", limit_span="10개")
    )
    requirement = parsed.query.requirements[0]
    assert requirement.ordering is not None
    assert requirement.ordering.direction_span == "높은"
    assert requirement.limit_span == "10개"

    # 4. semantic validation: the references bind and the spans are quotations
    assert result.issues == ()
    assert result.semantic_valid
    built = result.plan.requirements[0]
    assert built.server_decision == DECISION_MAPPED

    # 5. canonicalisation turned those two spans into execution values
    values = built.execution_values
    assert values is not None
    assert values.ordering.direction == "desc"
    assert values.limit.limit == 10

    # 6. and this layer still refuses to say the plan can run
    assert result.execution_readiness == "not_evaluated_by_semantic_validation"

    # 7. the executor's request type takes those values unchanged, and the
    #    execution comes back unexecuted because the Registry cannot yet prove
    #    row provenance. A correct plan is not by itself an answer.
    if not (STORE.is_file() and EXECUTION_REGISTRY.is_file()):
        pytest.skip("the query store and Execution Registry are required for this stage")
    from canna.execution import (
        ExecutionStatus,
        FieldOperation,
        Grain,
        OrderDirection,
        ProductQueryExecutor,
        ResolvedProductQuery,
    )

    grains = [grain for grain in dataset.grains if grain in DATASET_GRAINS]
    assert grains
    query = ResolvedProductQuery(
        dataset_family=field.families[0],
        result_grain=Grain(grains[0]),
        display_field_id=field.semantic_id,
        order_field_id=field.semantic_id,
        field_operation=FieldOperation.ORDER,
        # the canonicalised values, carried across the interface unchanged
        direction=OrderDirection(values.ordering.direction),
        limit=values.limit.limit,
    )
    assert query.direction.value == values.ordering.direction
    assert query.limit == values.limit.limit

    executed = ProductQueryExecutor(EXECUTION_REGISTRY, STORE).execute(query)
    assert executed.status is not ExecutionStatus.EXECUTED
    assert executed.binding_failures
    assert not executed.rows


# ------------------------------------------------------ refusals stop the path


@pytest.mark.real_data
def test_an_unreadable_direction_stops_the_path_before_any_execution_value() -> None:
    """The same submission with one word the direction grammar cannot read."""
    case = build_approved_live_case()
    _parsed, result = _through_the_wire(
        case, _ranking_wire(case, direction_span="1년", limit_span="10개")
    )
    assert not result.semantic_valid
    assert CODE_CANONICALIZATION_REFUSED in {issue.code for issue in result.issues}
    built = result.plan.requirements[0]
    assert built.server_decision != DECISION_MAPPED
    # the limit did canonicalise, and it is still not released
    assert built.canonical is not None
    assert built.canonical.limit.limit == 10
    assert built.execution_values is None


@pytest.mark.real_data
def test_a_limit_that_is_not_a_row_count_stops_the_path() -> None:
    case = build_approved_live_case()
    _parsed, result = _through_the_wire(
        case, _ranking_wire(case, direction_span="높은", limit_span="1년")
    )
    assert not result.semantic_valid
    assert CODE_CANONICALIZATION_REFUSED in {issue.code for issue in result.issues}
    assert result.plan.requirements[0].execution_values is None


def test_a_refused_requirement_releases_no_execution_values(facts, view) -> None:
    """The gate itself, on synthetic material: refused means nothing comes out."""
    requirement = SubmittedRequirement(
        requirement_id="r1",
        kind="ranking",
        status=STATUS_MAPPED,
        source_span="알파 비용이 낮은 순으로 10개",
        target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
        field_refs=(view.ref_for("syn:AlphaCost"),),
        ordering=SubmittedOrdering(
            field_ref=view.ref_for("syn:AlphaCost"), direction_span="낮은 순으로"
        ),
        limit_span="10개",
    )
    result = validate(facts, view, SubmittedQuery((requirement,)))
    assert not result.semantic_valid
    assert not result.plan.semantic_valid
    built = result.plan.requirements[0]
    assert built.semantic_valid is False
    assert built.execution_values is None
    # the record survives the refusal, so the reason stays readable afterwards
    assert built.canonical is not None
    assert [failure.slot for failure in built.canonical.failures] == [
        "ordering.direction_span"
    ]
    assert "r1" in result.unresolved_requirement_ids
    assert built.to_dict()["execution_values_released"] is False


# ------------------------------------------------- aggregation completeness


def test_an_aggregation_without_its_detail_is_incomplete(facts, view) -> None:
    """A requirement that says it aggregates has to say what, and which way."""
    requirement = SubmittedRequirement(
        requirement_id="r1",
        kind="aggregation",
        status=STATUS_MAPPED,
        source_span="알파 비용이 낮은 순으로 10개",
        target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
        field_refs=(view.ref_for("syn:AlphaCost"),),
    )
    result = validate(facts, view, SubmittedQuery((requirement,)))
    assert not result.semantic_valid
    codes = {issue.code for issue in result.issues}
    assert CODE_REQUIREMENT_INCOMPLETE in codes
    # the canonicaliser exists, so absence is what is refused, not availability
    assert CODE_CANONICALIZER_UNAVAILABLE not in codes
    assert result.plan.requirements[0].execution_values is None


def test_an_aggregation_naming_a_field_but_not_a_function_is_incomplete(
    facts, view
) -> None:
    requirement = SubmittedRequirement(
        requirement_id="r1",
        kind="aggregation",
        status=STATUS_MAPPED,
        source_span="알파 비용이 낮은 순으로 10개",
        target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
        field_refs=(view.ref_for("syn:AlphaCost"),),
        aggregation=SubmittedAggregation(
            field_ref=view.ref_for("syn:AlphaCost"), function_span=""
        ),
    )
    result = validate(facts, view, SubmittedQuery((requirement,)))
    assert CODE_REQUIREMENT_INCOMPLETE in {issue.code for issue in result.issues}
    assert result.plan.requirements[0].execution_values is None


def test_an_aggregation_with_its_detail_reaches_the_canonicaliser(facts) -> None:
    """The control: completeness refuses absence, not aggregation itself.

    This one needs a question that actually contains an aggregation word, since
    a span is read only after it is found in the question.
    """
    view = build_runtime_view(
        facts,
        "알파상품의 알파 비용 평균은 얼마인가",
        [
            CandidateProposal("syn:AlphaProduct", MATCH_EXACT),
            CandidateProposal("syn:AlphaCost", MATCH_EXACT),
        ],
    )
    requirement = SubmittedRequirement(
        requirement_id="r1",
        kind="aggregation",
        status=STATUS_MAPPED,
        source_span="알파 비용 평균",
        target_dataset_refs=(view.ref_for("syn:AlphaProduct"),),
        field_refs=(view.ref_for("syn:AlphaCost"),),
        aggregation=SubmittedAggregation(
            field_ref=view.ref_for("syn:AlphaCost"), function_span="평균"
        ),
    )
    result = validate(facts, view, SubmittedQuery((requirement,)))
    codes = {issue.code for issue in result.issues}
    assert CODE_REQUIREMENT_INCOMPLETE not in codes
    # It got as far as being asked, and the answer came from the Registry: this
    # synthetic field is declared filterable and orderable, not aggregatable, so
    # the word was read and the permission was missing.
    built = result.plan.requirements[0]
    assert built.canonical is not None
    assert built.canonical.aggregation is not None
    assert built.canonical.aggregation.failure.code == "operation_not_allowed_by_registry"
    assert built.execution_values is None


# ------------------------------------------------- what a refusal may remember


@pytest.mark.real_data
def test_the_wired_diagnostics_remember_shape_and_nothing_from_the_submission() -> None:
    """The record kept about a live call, taken over a real submission.

    ``one_line_records`` already holds its diagnostics to the approved list.
    This asserts the same thing about the values the wired path actually
    produces: the references this request minted and the spans quoted from
    the question are in the submission, and none of them survives into the
    record.
    """
    from canna.runtime_view import (
        ONE_LINE_DIAGNOSTIC_FIELDS,
        one_line_envelope_diagnostics,
    )

    case = build_approved_live_case()
    wire = _ranking_wire(case, direction_span="높은", limit_span="10개")
    text = render_one_line_records(wire)
    arguments = {ENVELOPE_PROPERTY: text}
    diagnostics = one_line_envelope_diagnostics(
        arguments,
        parse_tool_arguments(arguments),
        finish_reason="tool_calls",
        output_tokens=269,
    )

    assert set(diagnostics) <= set(ONE_LINE_DIAGNOSTIC_FIELDS)
    serialized = json.dumps(diagnostics, ensure_ascii=False)
    for reference in (case.expected_dataset_ref, case.expected_field_ref):
        assert reference not in serialized
    for span in (APPROVED_QUESTION, "높은", "10개"):
        assert span not in serialized
    for term in case.facts.terms:
        assert term.semantic_id not in serialized
    # and the shape it does keep is enough to tell what arrived
    assert diagnostics["record_line_counts"]["REQ"] == 1
    assert diagnostics["record_line_counts"]["REF"] == 1
    assert diagnostics["record_line_counts"]["DETAIL"] == 1
    assert diagnostics["record_line_counts"]["UNACCOUNTED"] == 0
    assert diagnostics["end_count"] == 0
    assert diagnostics["end_position_valid"] is True
    assert diagnostics["parser_problem_codes"] == []
