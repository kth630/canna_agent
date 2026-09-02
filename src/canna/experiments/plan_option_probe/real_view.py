"""The same questions, against the real Registry rather than a fixture.

The synthetic sources make the option generator measurable, because the gold is
written in their key namespace. They cannot tell us whether the *actual*
Semantic and Execution Registry would supply the same anchors, and a
pre-generation contract that only works against a fixture is not a contract.

So this module asks a narrower question that needs no key mapping and no
hand-written table: for each anchor the gold requires, take the words the
approved source says name it, and ask whether the production Runtime View --
built from the real registries with rule-only retrieval and no network -- offers
a candidate the real Registry names with those same words.

That is a meaning-level join through two data files. No stable semantic
identifier is written in this module, and none is reported.

This module is experiment-only. It is not imported by any serving path,
it calls no provider, index or database, and nothing it produces is a
product contract.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from canna.retrieval import build_retriever
from canna.runtime_view import (
    CandidateProposal,
    ExecutionRegistryFacts,
    RegistryFacts,
    build_runtime_view,
)
from canna.runtime_view.view import MATCH_EXACT, MATCH_PARTIAL, is_dataset

from .corpus import Case
from .sources import KIND_DATASET, KIND_ENTITY, KIND_FIELD, KIND_PREDICATE, ViewSource

SEMANTIC_REGISTRY = Path("data") / "processed" / "semantic_registry.json"
EXECUTION_REGISTRY = Path("data") / "processed" / "execution_registry.json"


@dataclass(frozen=True)
class RealAnchorResult:
    test_id: str
    split: str
    required_by_kind: dict[str, int]
    recalled_by_kind: dict[str, int]
    candidates_offered: int


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip().lower()


def _sequence(value: object) -> tuple[str, ...]:
    if not value or isinstance(value, str | bytes | dict):
        return ()
    return tuple(str(item) for item in value)  # type: ignore[union-attr]


def _registry_forms(facts: RegistryFacts, semantic_id: str) -> set[str]:
    term = facts.term(semantic_id)
    return {_normalise(form.text) for form in term.forms if form.text}


def load_real(root: Path) -> tuple[RegistryFacts, ExecutionRegistryFacts]:
    semantic_path = Path(root) / SEMANTIC_REGISTRY
    execution_path = Path(root) / EXECUTION_REGISTRY
    facts = RegistryFacts.load(semantic_path)
    payload = json.loads(execution_path.read_text(encoding="utf-8"))
    datasets = [
        term.semantic_id for term in facts.terms if is_dataset(facts, term.semantic_id)
    ]
    execution = ExecutionRegistryFacts.from_payload(
        payload,
        target_families={
            semantic_id: _sequence(facts.term(semantic_id).evidence.get("families"))
            for semantic_id in datasets
        },
        target_grains={
            semantic_id: _sequence(facts.term(semantic_id).evidence.get("grains"))
            for semantic_id in datasets
        },
        semantic_operations={
            term.semantic_id: _sequence(term.evidence.get("allowed_operations"))
            for term in facts.terms
        },
    )
    return facts, execution


def run_case(
    case: Case,
    source: ViewSource,
    facts: RegistryFacts,
    execution: ExecutionRegistryFacts,
) -> RealAnchorResult:
    retriever = build_retriever(with_embedding=False)
    retrieval = retriever.retrieve(case.question)
    if retriever.embedding_enabled:  # pragma: no cover - guarded by construction
        raise AssertionError("this experiment must not use the embedding path")
    proposals = [
        CandidateProposal(
            item.semantic_id,
            MATCH_EXACT if item.grounding_eligible else MATCH_PARTIAL,
        )
        for item in retrieval.candidates
    ]
    view = build_runtime_view(facts, case.question, proposals, execution_facts=execution)

    offered: set[str] = set()
    for group in (view.datasets, view.fields, view.predicates):
        for item in group:
            offered |= _registry_forms(facts, item.semantic_id)

    required: dict[str, int] = {}
    recalled: dict[str, int] = {}
    for key in case.required_keys:
        candidate = source.get(key)
        if candidate is None or candidate.kind == KIND_ENTITY:
            continue
        kind = candidate.kind
        required[kind] = required.get(kind, 0) + 1
        wanted = {_normalise(form) for form in candidate.surface_forms}
        if wanted & offered:
            recalled[kind] = recalled.get(kind, 0) + 1
    for kind in (KIND_DATASET, KIND_FIELD, KIND_PREDICATE):
        required.setdefault(kind, 0)
        recalled.setdefault(kind, 0)
    return RealAnchorResult(
        test_id=case.test_id,
        split=case.split,
        required_by_kind=required,
        recalled_by_kind=recalled,
        candidates_offered=len(view.datasets) + len(view.fields) + len(view.predicates),
    )


def run(
    root: Path, cases: Sequence[Case], sources: dict[str, ViewSource]
) -> tuple[RealAnchorResult, ...]:
    facts, execution = load_real(root)
    return tuple(
        run_case(case, sources[case.view_source], facts, execution) for case in cases
    )
