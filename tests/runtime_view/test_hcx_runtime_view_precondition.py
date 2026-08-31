"""Offline precondition for the one user-approved HCX Runtime View call.

Everything here uses the actual Semantic and Execution Registries and the
rule-only Retriever, and none of it touches the network. Since 2026-08-31 the
wire is the grouped-flat encoding, so the submission this builds is written as
records — with references taken from the Runtime View the request actually
minted, never from a fixture — and it has to survive assembly, the canonical
parser and server validation exactly as the nested form did.
"""

from __future__ import annotations

import json

from canna.runtime_view import (
    CODE_CANONICALIZER_UNAVAILABLE,
    grouped_flat_schema,
    hcx_tool_definition,
    keyword_vocabulary,
    parse_grouped_flat,
    validate,
)
from canna.runtime_view.hcx_wire import HCX_WIRE_KEYWORDS
from canna.runtime_view.schema import FUNCTION_NAME

from .hcx_runtime_view_live_support import (
    APPROVED_QUESTION,
    EXPECTED_PERIOD,
    build_approved_live_case,
)


def _approved_wire_submission(case) -> dict:
    """One ranking requirement, as grouped-flat records."""
    return {
        "requirement_records": [
            {
                "requirement_id": "approved-live-r1",
                "kind": "ranking",
                "status": "mapped",
                "source_span": APPROVED_QUESTION,
                "limit_span": "10개",
            }
        ],
        "ref_records": [
            {
                "requirement_id": "approved-live-r1",
                "role": "target_dataset",
                "ref": case.expected_dataset_ref,
            }
        ],
        "detail_records": [
            {
                "requirement_id": "approved-live-r1",
                "detail_kind": "ordering",
                "ref": case.expected_field_ref,
                "span": "높은",
            }
        ],
    }


def test_approved_live_case_preconditions_hold_without_network() -> None:
    """Falsifies missing actual candidates or a broken local schema boundary."""
    case = build_approved_live_case()
    assert case.retrieval_paths == ("rule",)
    assert case.view.dataset(case.expected_dataset_ref) is not None
    field = case.view.field(case.expected_field_ref)
    assert field is not None
    assert field.period == EXPECTED_PERIOD
    assert case.expected_dataset_ref in field.belongs_to_dataset_refs

    tool = hcx_tool_definition()
    assert tool["function"]["name"] == FUNCTION_NAME == "submit_semantic_query"
    assert tool["function"]["parameters"]["additionalProperties"] is False

    parsed = parse_grouped_flat(_approved_wire_submission(case))
    assert parsed.well_formed, parsed.problems
    assert parsed.query is not None
    requirement = parsed.query.requirements[0]
    assert requirement.target_dataset_refs == (case.expected_dataset_ref,)
    assert requirement.ordering is not None
    assert requirement.ordering.field_ref == case.expected_field_ref
    assert requirement.ordering.direction_span == "높은"
    assert requirement.limit_span == "10개"

    result = validate(case.facts, case.view, parsed.query)
    assert not result.semantic_valid
    assert result.execution_readiness == "not_evaluated_by_semantic_validation"
    assert {issue.code for issue in result.issues} == {CODE_CANONICALIZER_UNAVAILABLE}

    serialized = json.dumps(case.model_payload, ensure_ascii=False).lower()
    assert "semantic_id" not in serialized


def test_the_actual_case_binds_the_grouped_flat_tool_without_a_call() -> None:
    """The declaration reaches the real client's bind_tools, unspent."""
    from canna.experiments.semantic_probe.provider import HcxSemanticProvider

    case = build_approved_live_case()
    seen: dict[str, object] = {}

    class StubChat:
        def bind_tools(self, tools, tool_choice):
            seen["tools"] = tools
            seen["tool_choice"] = tool_choice
            return self

    def factory(model, timeout, tool_schema):
        seen["model"] = model
        return StubChat().bind_tools(
            tools=[dict(tool_schema)],
            tool_choice={"type": "function", "function": {"name": FUNCTION_NAME}},
        )

    HcxSemanticProvider(chat_factory=factory)._build_chat(hcx_tool_definition())

    bound = seen["tools"][0]
    assert bound["function"]["name"] == FUNCTION_NAME
    assert seen["tool_choice"]["function"]["name"] == FUNCTION_NAME
    parameters = bound["function"]["parameters"]
    assert parameters == grouped_flat_schema()
    assert keyword_vocabulary(parameters) <= HCX_WIRE_KEYWORDS

    # what would actually be sent: the declaration and this request's view,
    # neither carrying a stable identifier or any physical detail
    payload = json.dumps(
        {"tool": bound, "runtime_view": case.model_payload}, ensure_ascii=False
    )
    assert json.loads(payload)
    lowered = payload.lower()
    for term in case.facts.terms:
        assert term.semantic_id.lower() not in lowered
    for forbidden in ('"sql"', '"table"', '"column"', '"join"', '"src_', "select "):
        assert forbidden not in lowered
