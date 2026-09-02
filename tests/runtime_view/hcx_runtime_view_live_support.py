"""Offline construction and assessment for the one approved HCX live case.

The approved question is test material, never a production routing key.  This
module performs no network access: it uses the rule path only, reads both
registries, and derives the expected dataset/field pair from Registry metadata
rather than naming a semantic ID.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from canna.retrieval import build_retriever
from canna.runtime_view import (
    CandidateProposal,
    ExecutionRegistryFacts,
    RegistryFacts,
    RuntimeView,
    build_runtime_view,
    one_line_submission_guidance,
)
from canna.runtime_view.view import MATCH_EXACT, MATCH_PARTIAL, is_dataset, is_field

ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_REGISTRY = ROOT / "data" / "processed" / "semantic_registry.json"
EXECUTION_REGISTRY = ROOT / "data" / "processed" / "execution_registry.json"

APPROVED_QUESTION = "국내 ETF 중 1년 수익률이 높은 10개를 보여줘."
EXPECTED_PERIOD = "P1Y"
EXPECTED_OPERATION = "order"

TEST_METADATA = {
    "test_purpose": "신규 submit_semantic_query Schema의 HCX provider 수용성 확인",
    "capability_under_test": (
        "actual Runtime View dataset/field opaque ref 선택, ranking requirement 회계, "
        "source/order/limit 원문 span 보존"
    ),
    "question_structure": {
        "target": "국내 ETF",
        "requirement": "ranking",
        "metric": "1년 수익률",
        "direction": "높은 순",
        "limit": 10,
    },
    "semantic_clarity": "explicit",
}


@dataclass(frozen=True)
class ApprovedLiveCase:
    facts: RegistryFacts
    view: RuntimeView
    expected_dataset_ref: str
    expected_field_ref: str
    model_payload: dict[str, Any]
    retrieval_paths: tuple[str, ...]


def _sequence(value: Any) -> tuple[str, ...]:
    if not value or isinstance(value, str | bytes | dict):
        return ()
    return tuple(str(item) for item in value)


def _families(facts: RegistryFacts, semantic_id: str) -> set[str]:
    return set(_sequence(facts.term(semantic_id).evidence.get("families")))


def _grains(facts: RegistryFacts, semantic_id: str) -> set[str]:
    return set(_sequence(facts.term(semantic_id).evidence.get("grains")))


def property_names(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, Mapping):
        names.update(str(key).lower() for key in value)
        for child in value.values():
            names.update(property_names(child))
    elif isinstance(value, list | tuple):
        for child in value:
            names.update(property_names(child))
    return names


def build_approved_live_case() -> ApprovedLiveCase:
    """Build the actual rule-only Runtime View or fail before any HCX call."""
    if not SEMANTIC_REGISTRY.is_file() or not EXECUTION_REGISTRY.is_file():
        raise AssertionError("actual Semantic and Execution Registry files are required")

    facts = RegistryFacts.load(SEMANTIC_REGISTRY)
    retriever = build_retriever(
        registry_path=SEMANTIC_REGISTRY,
        with_embedding=False,
    )
    retrieval = retriever.retrieve(APPROVED_QUESTION)
    if retriever.embedding_enabled:
        raise AssertionError("the approved live case must use rule-only retrieval")
    if tuple(path.source for path in retrieval.paths) != ("rule",):
        raise AssertionError("an unexpected retrieval path was used")

    grounded = {
        candidate.semantic_id
        for candidate in retrieval.candidates
        if candidate.grounding_eligible
    }
    datasets = sorted(
        semantic_id for semantic_id in grounded if is_dataset(facts, semantic_id)
    )
    fields = sorted(
        semantic_id
        for semantic_id in grounded
        if is_field(facts, semantic_id)
        and str(facts.term(semantic_id).evidence.get("period_code", "")) == EXPECTED_PERIOD
        and EXPECTED_OPERATION
        in _sequence(facts.term(semantic_id).evidence.get("allowed_operations"))
    )
    pairs = [
        (dataset_id, field_id)
        for dataset_id in datasets
        for field_id in fields
        if _families(facts, dataset_id) & _families(facts, field_id)
        and _grains(facts, dataset_id) & _grains(facts, field_id)
    ]
    if len(pairs) != 1:
        raise AssertionError(
            "the actual rule-only candidates do not uniquely identify the approved "
            f"dataset/period/operation pair: pair_count={len(pairs)}"
        )
    expected_dataset_id, expected_field_id = pairs[0]

    execution_payload = json.loads(EXECUTION_REGISTRY.read_text(encoding="utf-8"))
    all_datasets = [
        term.semantic_id for term in facts.terms if is_dataset(facts, term.semantic_id)
    ]
    execution = ExecutionRegistryFacts.from_payload(
        execution_payload,
        target_families={
            semantic_id: _sequence(facts.term(semantic_id).evidence.get("families"))
            for semantic_id in all_datasets
        },
        target_grains={
            semantic_id: _sequence(facts.term(semantic_id).evidence.get("grains"))
            for semantic_id in all_datasets
        },
        semantic_operations={
            term.semantic_id: _sequence(term.evidence.get("allowed_operations"))
            for term in facts.terms
        },
    )
    proposals = [
        CandidateProposal(
            candidate.semantic_id,
            MATCH_EXACT if candidate.grounding_eligible else MATCH_PARTIAL,
        )
        for candidate in retrieval.candidates
    ]
    view = build_runtime_view(
        facts,
        APPROVED_QUESTION,
        proposals,
        execution_facts=execution,
    )
    dataset_ref = view.ref_for(expected_dataset_id)
    field_ref = view.ref_for(expected_field_id)
    if not dataset_ref or not field_ref:
        raise AssertionError("the actual Runtime View omitted a required opaque reference")
    field = view.field(field_ref)
    if field is None or dataset_ref not in field.belongs_to_dataset_refs:
        raise AssertionError("the actual Runtime View did not bind the field to the target")

    model_payload = view.to_model_payload()
    serialized = json.dumps(model_payload, ensure_ascii=False).lower()
    for term in facts.terms:
        if term.semantic_id.lower() in serialized:
            raise AssertionError("the model payload leaked a stable semantic ID")
    forbidden_properties = {
        "sql",
        "table",
        "column",
        "join",
        "source_table",
        "source_column",
        "physical_table",
        "physical_column",
    }
    leaked_properties = property_names(model_payload) & forbidden_properties
    if leaked_properties or '"src_' in serialized or "select " in serialized:
        raise AssertionError(
            f"the model payload leaked physical detail: {sorted(leaked_properties)}"
        )
    return ApprovedLiveCase(
        facts=facts,
        view=view,
        expected_dataset_ref=dataset_ref,
        expected_field_ref=field_ref,
        model_payload=model_payload,
        retrieval_paths=tuple(path.source for path in retrieval.paths),
    )


def model_messages(case: ApprovedLiveCase) -> tuple[str, str]:
    system = (
        # The grouped-flat structure no longer travels as JSON Schema: the
        # provider refused every declaration that carried it. Nor does it
        # travel as JSON inside the string any more — writing JSON there cost
        # quote escaping, non-ASCII escaping and brace balance at once, and one
        # of the three failed every time. It travels as record lines, whose
        # fields and enums are stated here, rendered from the same tables the
        # server routes by. Since 2026-09-01 a record is one line, which is
        # the shape the provider wrote on both calls that reached the reader.
        "You account for every explicit requirement in the user's question. "
        "Call submit_semantic_query exactly once. "
        + one_line_submission_guidance()
        + " Represent this request as one REQ line whose kind is ranking and "
        "which carries a limit_span, one REF line whose role is target_dataset, "
        "and one DETAIL line whose detail_kind is ordering carrying the field "
        "reference and the direction words."
    )
    human = json.dumps(
        {
            "question": APPROVED_QUESTION,
            "runtime_view": case.model_payload,
            "test_metadata": TEST_METADATA,
        },
        ensure_ascii=False,
    )
    return system, human
