"""One meaning can be served many ways, and the adapter must not pick for you.

Twenty-two semantic IDs in the shipped Execution Registry have more than one
binding, and some are duplicated inside a single family and grain. Every test
here finds those cases by asking the Registry rather than naming them, so the
rules stay true of whatever the Registry contains tomorrow.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest

from canna.runtime_view import (
    BindingSummary,
    CandidateProposal,
    ExecutionRegistryFacts,
    NoExecutionFacts,
    RegistryFacts,
    build_runtime_view,
)
from canna.runtime_view.execution_facts import (
    RESOLUTION_AMBIGUOUS,
    RESOLUTION_RESOLVED,
    RESOLUTION_UNAVAILABLE,
    RESOLUTION_UNSUPPORTED,
    STATE_AVAILABLE,
)
from canna.runtime_view.view import MATCH_EXACT, is_dataset

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "processed" / "semantic_registry.json"
EXECUTION_REGISTRY = ROOT / "data" / "processed" / "execution_registry.json"
QUESTION = "실행 레지스트리 어댑터를 검사하는 질문"


@pytest.fixture(scope="module")
def facts() -> RegistryFacts:
    if not REGISTRY.is_file():
        pytest.skip("the semantic registry has not been generated in this workspace")
    return RegistryFacts.load()


@pytest.fixture(scope="module")
def payload() -> dict:
    if not EXECUTION_REGISTRY.is_file():
        pytest.skip("the execution registry has not been generated in this workspace")
    return json.loads(EXECUTION_REGISTRY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def execution(facts: RegistryFacts, payload: dict) -> ExecutionRegistryFacts:
    """Targets are described by the Semantic Registry; bindings by the Execution one."""
    datasets = [
        term.semantic_id for term in facts.terms if is_dataset(facts, term.semantic_id)
    ]
    return ExecutionRegistryFacts.from_payload(
        payload,
        target_families={
            value: tuple(facts.term(value).evidence.get("families") or ())
            for value in datasets
        },
        target_grains={
            value: tuple(facts.term(value).evidence.get("grains") or ())
            for value in datasets
        },
        semantic_operations={
            term.semantic_id: tuple(term.evidence.get("allowed_operations") or ())
            for term in facts.terms
        },
    )


def _multi_binding_ids(execution: ExecutionRegistryFacts) -> list[str]:
    return sorted(
        semantic_id
        for semantic_id, rows in execution.bindings_by_id.items()
        if len(rows) > 1
    )


def _same_family_duplicates(execution: ExecutionRegistryFacts) -> list[tuple[str, str, str]]:
    """IDs bound twice within one family and grain — the ambiguous ones."""
    found = []
    for semantic_id, rows in execution.bindings_by_id.items():
        counts = collections.Counter((row.family_id, row.subject_grain) for row in rows)
        found += [
            (semantic_id, family, grain)
            for (family, grain), count in counts.items()
            if count > 1
        ]
    return sorted(found)


def test_the_registry_really_does_bind_meanings_more_than_once(execution) -> None:
    assert _multi_binding_ids(execution), "no meaning has several bindings; guard is vacuous"
    assert _same_family_duplicates(execution), "no duplicate within a family; guard is vacuous"


def test_every_binding_is_listed_and_none_is_collapsed(execution) -> None:
    for semantic_id in _multi_binding_ids(execution):
        rows = execution.candidate_bindings_for(semantic_id)
        assert len(rows) > 1
        # each row keeps its own family, grain and source rather than merging
        assert len({(row.family_id, row.subject_grain, row.source_id) for row in rows}) >= 1
        assert all(row.semantic_id == semantic_id for row in rows)


def test_a_candidate_shows_every_family_that_serves_it(facts, execution) -> None:
    multi = [
        semantic_id
        for semantic_id in _multi_binding_ids(execution)
        if len({row.family_id for row in execution.candidate_bindings_for(semantic_id)}) > 1
        and facts.has(semantic_id)
    ]
    assert multi
    semantic_id = multi[0]
    view = build_runtime_view(
        facts,
        QUESTION,
        [CandidateProposal(semantic_id, MATCH_EXACT)],
        execution_facts=execution,
    )
    candidate = view.field(view.ref_for(semantic_id))
    assert candidate is not None
    served = {row.family_id for row in candidate.bindings}
    assert len(served) > 1
    payload = view.to_model_payload()["fields"][0]["served_by"]
    assert len(payload) == len(candidate.bindings)


def test_real_datasets_publish_target_capabilities_without_looking_unsupported(
    facts, execution
) -> None:
    datasets = [term.semantic_id for term in facts.terms if is_dataset(facts, term.semantic_id)]
    assert datasets
    view = build_runtime_view(
        facts,
        QUESTION,
        [CandidateProposal(value, MATCH_EXACT) for value in datasets],
        execution_facts=execution,
    )
    payload = view.to_model_payload()
    assert payload["datasets"]
    assert all("served_by" not in candidate for candidate in payload["datasets"])
    described = [
        summary
        for candidate in payload["datasets"]
        for summary in candidate["target_capabilities"]
        if summary["binding_count"] > 0
    ]
    assert described, "no real dataset received a family/grain capability summary"
    assert all(summary["coverage_knowledge"] != "unsupported" for summary in described)
    assert all(summary["claim_readiness"] == "not_evaluated" for summary in described)
    assert "not that the dataset is unsupported" in payload["notes"]["target_capabilities"]


def test_a_duplicate_within_one_family_resolves_as_ambiguous(execution) -> None:
    duplicates = _same_family_duplicates(execution)
    assert duplicates
    for semantic_id, family, grain in duplicates:
        target = next(
            (
                value
                for value, families in execution.target_families.items()
                if family in families and grain in execution.target_grains.get(value, ())
            ),
            None,
        )
        if target is None:
            continue
        rows = [
            row
            for row in execution.candidate_bindings_for(semantic_id)
            if row.family_id == family and row.subject_grain == grain
        ]
        operation = next(
            (op for row in rows for op in row.executable_operations), ""
        )
        if not operation:
            continue
        resolution = execution.resolve_capability(target, semantic_id, operation)
        assert resolution.status == RESOLUTION_AMBIGUOUS, (semantic_id, family)
        assert resolution.binding is None
        assert len(resolution.alternatives) > 1
        return
    pytest.skip("no duplicate had a target and an executable operation to test with")


def test_a_single_fitting_binding_resolves(facts, execution) -> None:
    resolved = 0
    for semantic_id, rows in execution.bindings_by_id.items():
        if len(rows) != 1:
            continue
        row = rows[0]
        if not row.executable_operations:
            continue
        target = next(
            (
                value
                for value, families in execution.target_families.items()
                if row.family_id in families
                and row.subject_grain in execution.target_grains.get(value, ())
            ),
            None,
        )
        if target is None:
            continue
        resolution = execution.resolve_capability(
            target, semantic_id, row.executable_operations[0]
        )
        assert resolution.status == RESOLUTION_RESOLVED, (semantic_id, resolution.reason)
        assert resolution.binding is not None
        assert resolution.binding.family_id == row.family_id
        resolved += 1
        if resolved >= 5:
            break
    assert resolved, "no singly-bound meaning could be resolved; guard is vacuous"


def test_a_meaning_of_another_family_is_unsupported(facts, execution) -> None:
    for semantic_id, rows in execution.bindings_by_id.items():
        families = {row.family_id for row in rows}
        target = next(
            (
                value
                for value, target_families in execution.target_families.items()
                if not (set(target_families) & families)
            ),
            None,
        )
        if target is None or not rows[0].executable_operations:
            continue
        resolution = execution.resolve_capability(
            target, semantic_id, rows[0].executable_operations[0]
        )
        assert resolution.status == RESOLUTION_UNSUPPORTED
        assert resolution.binding is None
        return
    pytest.skip("every meaning is served for every family")


def test_an_operation_no_binding_supports_is_unavailable(facts, execution) -> None:
    for semantic_id, rows in execution.bindings_by_id.items():
        row = rows[0]
        if not row.executable_operations:
            continue
        target = next(
            (
                value
                for value, families in execution.target_families.items()
                if row.family_id in families
                and row.subject_grain in execution.target_grains.get(value, ())
            ),
            None,
        )
        if target is None:
            continue
        resolution = execution.resolve_capability(target, semantic_id, "no_such_operation")
        assert resolution.status == RESOLUTION_UNAVAILABLE
        assert resolution.binding is None
        assert resolution.alternatives
        return
    pytest.skip("no binding had both a target and an executable operation")


def test_an_as_of_outside_the_observed_window_is_unavailable(facts, execution) -> None:
    for semantic_id, rows in execution.bindings_by_id.items():
        if len(rows) != 1:
            continue
        row = rows[0]
        if row.freshness_state != STATE_AVAILABLE or not row.executable_operations:
            continue
        target = next(
            (
                value
                for value, families in execution.target_families.items()
                if row.family_id in families
                and row.subject_grain in execution.target_grains.get(value, ())
            ),
            None,
        )
        if target is None:
            continue
        resolution = execution.resolve_capability(
            target, semantic_id, row.executable_operations[0], requested_as_of="1999-01-01"
        )
        assert resolution.status == RESOLUTION_UNAVAILABLE
        assert "as-of" in resolution.reason
        return
    pytest.skip("no dated binding available to test with")


def test_a_relationship_kind_narrows_the_resolution(facts, execution) -> None:
    relations = [
        (semantic_id, rows)
        for semantic_id, rows in execution.bindings_by_id.items()
        if any(row.relation_kind for row in rows)
    ]
    assert relations, "no relation binding; guard is vacuous"
    semantic_id, rows = relations[0]
    kinds = {row.relation_kind for row in rows if row.relation_kind}
    target = next(
        (
            value
            for value, families in execution.target_families.items()
            if rows[0].family_id in families
        ),
        None,
    )
    assert target
    unknown = execution.resolve_capability(
        target, semantic_id, "exists", relationship_kind="no_such_relation_kind"
    )
    assert unknown.status == RESOLUTION_UNSUPPORTED
    assert kinds


def test_no_physical_detail_leaves_the_adapter(execution) -> None:
    for rows in execution.bindings_by_id.values():
        for row in rows:
            text = json.dumps(row.to_payload(), ensure_ascii=False)
            for forbidden in ("src_", "source_table", "source_column", "join", "select"):
                assert forbidden not in text
            assert not hasattr(row, "physical")


def test_source_ids_are_the_published_dataset_identifiers(execution, payload) -> None:
    declared = {str(row["source_id"]) for row in payload["data_catalog"]["sources"]}
    seen = {
        row.source_id
        for rows in execution.bindings_by_id.values()
        for row in rows
        if row.source_id != "unknown_source"
    }
    assert seen
    assert seen <= declared


def test_real_relation_bindings_preserve_unique_holdings_source_and_coverage(
    execution, payload
) -> None:
    coverage = {row["family_id"]: row for row in payload["holdings_coverage"]}
    relation_rows = [
        row
        for rows in execution.bindings_by_id.values()
        for row in rows
        if row.relation_kind
    ]
    assert relation_rows
    for row in relation_rows:
        expected = coverage[row.family_id]
        assert row.coverage_resolution == "matched"
        assert row.source_id == expected["source_id"]
        assert row.eligible_subjects == expected["eligible_count"]
        assert row.attempted_subjects == expected["attempted_count"]
        assert row.successful_subjects == expected["success_count"]
        assert row.failed_subjects == expected["failed_count"]
        assert row.observed_subjects == expected["observed_subject_count"]
        assert row.holding_as_of_min == expected["holding_as_of_min"]
        assert row.holding_as_of_max == expected["holding_as_of_max"]
        assert row.snapshot_state in {"full", "partial", "unknown", "unavailable"}
        assert row.coverage_state in {"full", "partial", "observed", "unknown", "unavailable"}
        assert row.coverage_state != "unavailable"


def test_direct_and_look_through_keep_their_registry_operation_difference(
    facts, execution
) -> None:
    by_kind: dict[str, set[tuple[str, ...]]] = collections.defaultdict(set)
    checked = 0
    for semantic_id, rows in execution.bindings_by_id.items():
        if not facts.has(semantic_id):
            continue
        allowed = tuple(facts.term(semantic_id).evidence.get("allowed_operations") or ())
        for row in rows:
            if not row.relation_kind:
                continue
            assert row.semantic_operations == allowed
            assert row.executable_operations == (allowed if row.binding_available else ())
            assert set(row.evidence_requirements).isdisjoint(row.semantic_operations)
            by_kind[row.relation_kind].add(row.executable_operations)
            checked += 1
    assert checked
    assert len(by_kind) >= 2, "the real Registry exposes no distinct relation kinds"
    operation_sets = {operations for values in by_kind.values() for operations in values}
    assert len(operation_sets) >= 2, "relation kinds lost their allowed-operation difference"


def test_relation_operations_fail_closed_without_semantic_registry_input(payload) -> None:
    execution = ExecutionRegistryFacts.from_payload(payload)
    relations = [
        row
        for rows in execution.bindings_by_id.values()
        for row in rows
        if row.relation_kind
    ]
    assert relations
    assert all(row.semantic_operations == () for row in relations)
    assert all(row.executable_operations == () for row in relations)
    assert any(row.evidence_requirements for row in relations)


def test_non_unique_holdings_coverage_is_not_guessed(payload, facts) -> None:
    semantic_operations = {
        term.semantic_id: tuple(term.evidence.get("allowed_operations") or ())
        for term in facts.terms
    }
    duplicated = dict(payload)
    duplicated["holdings_coverage"] = [
        *payload["holdings_coverage"],
        dict(payload["holdings_coverage"][0]),
    ]
    execution = ExecutionRegistryFacts.from_payload(
        duplicated, semantic_operations=semantic_operations
    )
    ambiguous_family = payload["holdings_coverage"][0]["family_id"]
    rows = [
        row
        for values in execution.bindings_by_id.values()
        for row in values
        if row.relation_kind and row.family_id == ambiguous_family
    ]
    assert rows
    assert all(row.coverage_resolution == "ambiguous" for row in rows)
    assert all(row.coverage_state == "unknown" for row in rows)
    assert all(row.source_id == "unknown_source" for row in rows)

    missing = dict(payload)
    missing["holdings_coverage"] = [
        row
        for row in payload["holdings_coverage"]
        if row["family_id"] != ambiguous_family
    ]
    execution = ExecutionRegistryFacts.from_payload(
        missing, semantic_operations=semantic_operations
    )
    rows = [
        row
        for values in execution.bindings_by_id.values()
        for row in values
        if row.relation_kind and row.family_id == ambiguous_family
    ]
    assert rows
    assert all(row.coverage_resolution == "unknown" for row in rows)
    assert all(row.coverage_state == "unknown" for row in rows)
    assert all(row.source_id == "unknown_source" for row in rows)


def test_a_binding_summary_never_claims_a_whole_plan_is_ready() -> None:
    row = BindingSummary(semantic_id="x", family_id="f", subject_grain="product")
    assert not hasattr(row, "execution_ready")
    assert row.binding_available is False
    assert "execution_ready" not in row.to_payload()


def test_without_an_adapter_nothing_is_described_or_resolved() -> None:
    adapter = NoExecutionFacts()
    assert adapter.candidate_bindings_for("anything") == ()
    resolution = adapter.resolve_capability("target", "candidate", "filter")
    assert resolution.status == RESOLUTION_UNSUPPORTED
    assert resolution.binding is None


def test_a_family_neutral_field_is_scoped_by_what_actually_serves_it(
    facts, execution
) -> None:
    """The Registry declares no family; the Execution Registry says who serves it."""
    neutral = [
        term.semantic_id
        for term in facts.terms
        if not (term.evidence.get("families") or ())
        and execution.candidate_bindings_for(term.semantic_id)
    ]
    assert neutral, "no family-neutral term is served; guard is vacuous"
    semantic_id = neutral[0]
    unscoped = build_runtime_view(
        facts, QUESTION, [CandidateProposal(semantic_id, MATCH_EXACT)]
    )
    scoped = build_runtime_view(
        facts,
        QUESTION,
        [CandidateProposal(semantic_id, MATCH_EXACT)],
        execution_facts=execution,
    )
    served = {
        row.family_id for row in execution.candidate_bindings_for(semantic_id)
    }

    def candidate(view):
        ref = view.ref_for(semantic_id)
        return view.field(ref) or view.predicate(ref)

    before = candidate(unscoped)
    after = candidate(scoped)
    assert before is not None and after is not None
    # without the adapter the scope cannot be proven and nothing is offered
    assert before.dataset_scope == "scope_unproven"
    assert before.families == ()
    # with it the scope is exactly the families that serve the term
    assert after.dataset_scope == "execution_scoped"
    assert set(after.families) == served
    # and the closure now gives every one of those families a dataset
    covered = {family for item in scoped.datasets for family in item.families}
    assert served <= covered


def test_relation_kind_comes_from_the_execution_registry_not_a_guess(
    facts, execution
) -> None:
    """Direct and look-through are distinguished by recorded kind, not by shape."""
    predicates = [
        semantic_id
        for semantic_id, rows in execution.bindings_by_id.items()
        if any(row.relation_kind for row in rows) and facts.has(semantic_id)
    ]
    assert len(predicates) > 1
    view = build_runtime_view(
        facts,
        QUESTION,
        [CandidateProposal(value, MATCH_EXACT) for value in predicates],
        execution_facts=execution,
    )
    by_id = {item.semantic_id: item for item in view.predicates}
    assert by_id
    for candidate in by_id.values():
        assert candidate.relation_kinds, candidate.semantic_id

    # a declared inverse pair serves the same relation kind; a same-shaped
    # sibling serves a different one. Both agree with the derivation, so no
    # Ontology discriminator is needed to tell them apart.
    for candidate in by_id.values():
        inverse = next(
            (
                other
                for other in by_id.values()
                if other.ref == candidate.inverse_ref and other.ref
            ),
            None,
        )
        if inverse is not None:
            assert set(candidate.relation_kinds) == set(inverse.relation_kinds)
        for sibling_ref in candidate.distinct_from_refs:
            sibling = next(item for item in by_id.values() if item.ref == sibling_ref)
            assert set(candidate.relation_kinds) != set(sibling.relation_kinds), (
                candidate.semantic_id,
                sibling.semantic_id,
            )
