"""Exactly one opt-in HCX call for the approved Runtime View schema probe.

Since 2026-08-31 the declaration sent is the grouped-flat encoding, so the
arguments that come back are records and are read by ``parse_grouped_flat``.
Everything the server decides afterwards is unchanged: assembly hands the
canonical shape to the same parser and the same validator.

This test asserts provider acceptance, so a refusal fails it. That is the point
of it; the three refusals recorded on 2026-08-31 are in the provenance
directory, not here.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping

import pytest

from canna.experiments.semantic_probe.provider import (
    API_KEY_ENV,
    DEFAULT_MODEL,
    classify_error,
)
from canna.runtime_view import (
    CODE_CANONICALIZER_UNAVAILABLE,
    align,
    hcx_tool_definition,
    parse_grouped_flat,
    validate,
)
from canna.runtime_view.query import SubmittedQuery
from canna.runtime_view.schema import FUNCTION_NAME

from .hcx_runtime_view_live_support import (
    APPROVED_QUESTION,
    ROOT,
    build_approved_live_case,
    model_messages,
    property_names,
)

pytestmark = pytest.mark.hcx_live


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    from dotenv import load_dotenv

    load_dotenv(env_path, override=False)


def _arguments(call: Mapping[str, object]) -> Mapping[str, object] | None:
    raw = call.get("args")
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, Mapping) else None
    return None


def _submitted_refs(query: SubmittedQuery) -> tuple[str, ...]:
    refs: list[str] = []
    for requirement in query.requirements:
        refs.extend(requirement.target_dataset_refs)
        refs.extend(ref for ref, _role in requirement.referenced_field_refs)
        if requirement.relationship is not None:
            refs.extend(
                (
                    requirement.relationship.predicate_ref,
                    requirement.relationship.anchor_entity_ref,
                )
            )
    return tuple(refs)


def _span_status(question: str, span: str) -> str:
    status = align(question, span)
    return status if status in {"exact", "normalized_exact"} else "failed"


def test_actual_runtime_view_schema_is_accepted_once() -> None:
    """One approved question, one provider invoke, zero retry and zero execution."""
    if os.environ.get("RUN_HCX_LIVE") != "1":
        pytest.skip("set RUN_HCX_LIVE=1 to permit the one approved external call")
    _load_env()
    if not os.environ.get(API_KEY_ENV, "").strip():
        pytest.skip("HyperCLOVA X credentials are not configured")

    case = build_approved_live_case()
    system_text, human_text = model_messages(case)
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_naver import ChatClovaX

    report: dict[str, object] = {
        "provider_schema_acceptance": "not_called",
        "tool_emitted": "no",
        "tool_name_exact": "no",
        "parser_well_formed": "no",
        "ref_validity": "not_evaluated",
        "source_span": "failed",
        "direction_span": "missing",
        "limit_span": "missing",
        "semantic_validation": "not_run",
        "execution_readiness": "not_evaluated/non-executable",
        "external_call_count": 0,
        "retry_count": 0,
    }
    llm = ChatClovaX(
        model=DEFAULT_MODEL,
        timeout=40,
        max_retries=0,
        reasoning_effort="none",
    )
    bound = llm.bind_tools(
        tools=[hcx_tool_definition()],
        tool_choice={"type": "function", "function": {"name": FUNCTION_NAME}},
    )
    try:
        report["external_call_count"] = 1
        response = bound.invoke(
            [SystemMessage(content=system_text), HumanMessage(content=human_text)]
        )
    except Exception as error:  # noqa: BLE001 - sanitized provider observation
        kind, code = classify_error(str(error))
        report["provider_schema_acceptance"] = "rejected"
        report["provider_error_kind"] = kind
        report["provider_error_code"] = code
        print("HCX_RUNTIME_VIEW_RESULT=" + json.dumps(report, ensure_ascii=False))
        pytest.fail(f"provider rejected the one approved call: kind={kind}, code={code}")

    report["provider_schema_acceptance"] = "accepted"
    calls = [
        call
        for call in (getattr(response, "tool_calls", None) or ())
        if isinstance(call, Mapping)
    ]
    report["tool_emitted"] = "yes" if calls else "no"
    if len(calls) != 1:
        print("HCX_RUNTIME_VIEW_RESULT=" + json.dumps(report, ensure_ascii=False))
        pytest.fail(f"expected exactly one tool call, received {len(calls)}")
    call = calls[0]
    report["tool_name_exact"] = "yes" if call.get("name") == FUNCTION_NAME else "no"
    arguments = _arguments(call)
    parsed = parse_grouped_flat(arguments) if arguments is not None else None
    report["parser_well_formed"] = (
        "yes" if parsed is not None and parsed.well_formed else "no"
    )

    if parsed is not None and parsed.well_formed and parsed.query is not None:
        allowed_refs = {
            *(candidate.ref for candidate in case.view.datasets),
            *(candidate.ref for candidate in case.view.fields),
            *(candidate.ref for candidate in case.view.predicates),
            *(candidate.ref for candidate in case.view.entities),
        }
        report["ref_validity"] = (
            "valid"
            if all(ref in allowed_refs for ref in _submitted_refs(parsed.query))
            else "invented_or_wrong_kind"
        )
        requirement = parsed.query.requirements[0] if parsed.query.requirements else None
        if requirement is not None:
            report["source_span"] = _span_status(
                APPROVED_QUESTION, requirement.source_span
            )
            if requirement.ordering is not None:
                report["direction_span"] = _span_status(
                    APPROVED_QUESTION, requirement.ordering.direction_span
                )
            if requirement.limit_span:
                report["limit_span"] = _span_status(
                    APPROVED_QUESTION, requirement.limit_span
                )
        validation = validate(case.facts, case.view, parsed.query)
        report["semantic_validation"] = {
            "semantic_valid": validation.semantic_valid,
            "issue_codes": sorted({issue.code for issue in validation.issues}),
            "server_decisions": [
                requirement.server_decision
                for requirement in (validation.plan.requirements if validation.plan else ())
            ],
        }
        report["execution_readiness"] = validation.execution_readiness

    serialized_arguments = json.dumps(arguments or {}, ensure_ascii=False).lower()
    leaked_stable_id = any(
        term.semantic_id.lower() in serialized_arguments for term in case.facts.terms
    )
    physical_leak = bool(
        property_names(arguments or {})
        & {
            "sql",
            "table",
            "column",
            "join",
            "source_table",
            "source_column",
            "physical_table",
            "physical_column",
        }
    ) or '"src_' in serialized_arguments or "select " in serialized_arguments
    print("HCX_RUNTIME_VIEW_RESULT=" + json.dumps(report, ensure_ascii=False))

    assert report["external_call_count"] == 1
    assert report["retry_count"] == 0
    assert report["tool_name_exact"] == "yes"
    assert report["parser_well_formed"] == "yes"
    assert report["ref_validity"] == "valid"
    assert report["source_span"] in {"exact", "normalized_exact"}
    assert report["direction_span"] in {"exact", "normalized_exact"}
    assert report["limit_span"] in {"exact", "normalized_exact"}
    assert not leaked_stable_id
    assert not physical_leak
    assert isinstance(report["semantic_validation"], dict)
    assert report["semantic_validation"]["semantic_valid"] is False
    assert set(report["semantic_validation"]["issue_codes"]) == {
        CODE_CANONICALIZER_UNAVAILABLE
    }
    assert report["execution_readiness"] == "not_evaluated_by_semantic_validation"
