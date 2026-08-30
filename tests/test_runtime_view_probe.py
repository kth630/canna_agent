"""Offline tests for the stage 1-A Runtime View retrieval probe.

Every test here runs without a network call, a model or source data. Fixture
questions are data: they are parameterised over, never branched on, and no test
looks at a ``test_id`` to decide what to assert.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from pathlib import Path

import pytest

from canna.experiments.runtime_view_probe.diagnostics import (
    FAILURE_BUDGET_TRUNCATED,
    FAILURE_CAPABILITY_UNSUPPORTED,
    FAILURE_KINDS,
    FAILURE_NO_DATASET_MATCH,
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    assess,
)
from canna.experiments.runtime_view_probe.measurement import (
    MISS_BUDGET_TRUNCATED,
    MISS_NOT_MATCHED,
    aggregate_recall,
    required_candidate_recall,
)
from canna.experiments.runtime_view_probe.probe import ProbeCase, run_case, summarise
from canna.experiments.runtime_view_probe.registry import (
    NEIGHBOR_RULES,
    Registry,
    RegistryError,
    load_registry,
)
from canna.experiments.runtime_view_probe.retrieval import (
    REASON_CROSS_FAMILY_HOMONYM,
    REASON_DATASET_OWNERSHIP,
    REASON_SAME_NEIGHBOR_GROUP,
    REASON_SURFACE_MATCH,
    retrieve,
)
from canna.experiments.runtime_view_probe.view import RefMinter, build_view

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
REGISTRY_PATH = FIXTURES / "runtime_view_registry.json"
FIXTURE_PATHS = (
    FIXTURES / "runtime_view_probe.jsonl",
    FIXTURES / "runtime_view_probe_unseen.jsonl",
)


def read_registry_payload() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry() -> Registry:
    return load_registry(read_registry_payload())


def load_cases() -> list[Mapping[str, object]]:
    cases: list[Mapping[str, object]] = []
    for path in FIXTURE_PATHS:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cases.append(json.loads(line))
    return cases


def case_of(record: Mapping[str, object]) -> ProbeCase:
    expected = record["expected_decision"]
    assert isinstance(expected, Mapping)
    budget = record.get("candidate_budget")
    return ProbeCase(
        case_key=str(record["test_id"]),
        question=str(record["question"]),
        required_candidate_ids=tuple(expected.get("required_candidate_ids", ())),  # type: ignore[arg-type]
        required_neighbor_ids=tuple(expected.get("required_neighbor_ids", ())),  # type: ignore[arg-type]
        candidate_budget=None if budget is None else int(budget),  # type: ignore[arg-type]
    )


CASES = load_cases()
CASE_IDS = [str(record["test_id"]) for record in CASES]


def case_with_capability(capability: str) -> Mapping[str, object]:
    """Pick a fixture by the capability it exercises, never by its identity."""
    return next(record for record in CASES if record["capability_under_test"] == capability)


# --- registry validation -------------------------------------------------


def test_registry_loads_and_declares_synthetic_authority(registry: Registry) -> None:
    assert registry.authority == "non_authoritative_synthetic"
    assert registry.entries
    assert set(registry.policy.neighbor_rules) <= set(NEIGHBOR_RULES)


def test_every_family_classifies_every_capability(registry: Registry) -> None:
    """Coverage is a partition, so an unsupported capability is never implicit."""
    capability_ids = {capability.capability_id for capability in registry.capabilities}
    for dataset in registry.entries_of_kind("dataset"):
        coverage = dataset.capability_coverage
        assert coverage is not None
        assert set(coverage.supported) | set(coverage.unsupported) == capability_ids
        assert not set(coverage.supported) & set(coverage.unsupported)


def test_registry_rejects_unknown_neighbor_rule() -> None:
    payload = read_registry_payload()
    policy = dict(payload["retrieval_policy"])  # type: ignore[arg-type]
    policy["neighbor_rules"] = ["a_rule_retrieval_does_not_implement"]
    payload["retrieval_policy"] = policy
    with pytest.raises(RegistryError, match="unknown neighbor rule"):
        load_registry(payload)


def test_registry_rejects_unclassified_capability() -> None:
    payload = read_registry_payload()
    datasets = [dict(item) for item in payload["datasets"]]  # type: ignore[arg-type]
    coverage = dict(datasets[0]["capability_coverage"])  # type: ignore[arg-type]
    coverage["supported"] = list(coverage["supported"])[:-1]  # type: ignore[arg-type]
    datasets[0]["capability_coverage"] = coverage
    payload["datasets"] = datasets
    with pytest.raises(RegistryError, match="unclassified"):
        load_registry(payload)


def test_registry_rejects_field_bound_to_unknown_family() -> None:
    payload = read_registry_payload()
    fields = [dict(item) for item in payload["fields"]]  # type: ignore[arg-type]
    fields[0]["dataset_id"] = "ds.not_a_family"
    payload["fields"] = fields
    with pytest.raises(RegistryError, match="unknown dataset"):
        load_registry(payload)


# --- fixture-driven retrieval behaviour ----------------------------------


@pytest.mark.parametrize("record", CASES, ids=CASE_IDS)
def test_required_candidates_are_retrieved(registry: Registry, record: Mapping[str, object]) -> None:
    expected = record["expected_decision"]
    assert isinstance(expected, Mapping)
    result = run_case(registry, case_of(record))

    missing = sorted(item.semantic_id for item in result.recall.missing)
    assert missing == sorted(expected.get("expected_missing_required_ids", ()))  # type: ignore[arg-type]
    assert sorted(result.recall.neighbors_missing) == sorted(
        expected.get("expected_missing_neighbor_ids", ())  # type: ignore[arg-type]
    )
    for semantic_id in result.recall.retrieved:
        assert result.bundle.view.contains(semantic_id)


@pytest.mark.parametrize("record", CASES, ids=CASE_IDS)
def test_retrieval_outcome_matches_expectation(
    registry: Registry, record: Mapping[str, object]
) -> None:
    expected = record["expected_decision"]
    assert isinstance(expected, Mapping)
    result = run_case(registry, case_of(record))

    assert result.outcome.status == expected["retrieval_status"]
    assert result.outcome.executable is expected["executable"]
    assert list(result.outcome.failure_kinds()) == sorted(
        expected.get("expected_failure_kinds", ())  # type: ignore[arg-type]
    )
    unsupported = sorted(
        request.capability_id
        for request in result.outcome.capability_requests
        if request.unsupported_everywhere()
    )
    assert unsupported == sorted(expected.get("expected_unsupported_capability_ids", ()))  # type: ignore[arg-type]


@pytest.mark.parametrize("record", CASES, ids=CASE_IDS)
def test_candidate_order_is_stable_across_runs(
    registry: Registry, record: Mapping[str, object]
) -> None:
    case = case_of(record)
    orders = {run_case(registry, case).bundle.view.presentation_order() for _ in range(3)}
    assert len(orders) == 1


@pytest.mark.parametrize("record", CASES, ids=CASE_IDS)
def test_refs_are_request_scoped_and_opaque(
    registry: Registry, record: Mapping[str, object]
) -> None:
    case = case_of(record)
    first = run_case(registry, case)
    second = run_case(registry, case)

    assert set(first.bundle.view.refs()).isdisjoint(second.bundle.view.refs())
    serialized = json.dumps(first.bundle.view.as_prompt_payload(), ensure_ascii=False)
    for entry in registry.entries:
        assert entry.semantic_id not in serialized
    for capability in registry.capabilities:
        assert capability.capability_id not in serialized
    for candidate in first.bundle.view.all_candidates():
        assert candidate.ref not in candidate.semantic_id
        assert first.bundle.semantic_id_by_ref[candidate.ref] == candidate.semantic_id


@pytest.mark.parametrize("record", CASES, ids=CASE_IDS)
def test_view_records_size_and_latency(registry: Registry, record: Mapping[str, object]) -> None:
    result = run_case(registry, case_of(record))
    metrics = result.bundle.metrics
    assert metrics.candidate_count == len(result.bundle.view.all_candidates())
    assert metrics.serialized_bytes > 0
    assert sum(metrics.candidate_count_by_kind.values()) == metrics.candidate_count
    assert result.retrieval_latency_ms >= 0.0
    assert result.view_latency_ms >= 0.0


@pytest.mark.parametrize("record", CASES, ids=CASE_IDS)
def test_every_candidate_carries_its_discriminators(
    registry: Registry, record: Mapping[str, object]
) -> None:
    """A candidate the reader cannot tell apart from its neighbour is useless."""
    result = run_case(registry, case_of(record))
    view = result.bundle.view
    dataset_refs = {candidate.ref for candidate in view.datasets}

    for candidate in view.all_candidates():
        payload = candidate.payload
        assert payload["ref"] == candidate.ref
        assert payload["label"]
        assert payload["meaning"]
        if candidate.kind == "dataset":
            coverage = payload["capability_coverage"]
            assert isinstance(coverage, Mapping)
            assert coverage["supported_capabilities"] or coverage["unsupported_capabilities"]
            assert coverage["coverage_grain"]
            assert coverage["freshness"]
            assert coverage["observed_universe"]
        if candidate.kind == "field":
            assert payload["belongs_to_dataset_ref"] in dataset_refs
            assert payload["grain"]
            assert payload["source"]
            assert payload["allowed_operations"]
        if candidate.kind == "predicate":
            assert payload["subject_role"] and payload["object_role"]
            assert payload["relation_mode"]
            assert payload["grain"]
            assert payload["evidence_requirements"]
            scope = payload["applies_to_dataset_refs"]
            assert isinstance(scope, list) and scope
            assert set(scope) <= dataset_refs
        if candidate.kind == "entity":
            assert payload["identifier_scheme"]
            assert payload["entity_type"]
            assert payload["grain"]


# --- retrieval mechanics --------------------------------------------------


def test_confusion_neighbors_are_labelled_by_why_they_were_retrieved(
    registry: Registry,
) -> None:
    """Period neighbours, homonyms and ownership must be distinguishable."""
    record = case_with_capability("field_retrieval_neighbor")
    result = retrieve(registry, str(record["question"]))
    reasons = {candidate.semantic_id: candidate.reasons for candidate in result.admitted}

    period_neighbors = [
        semantic_id
        for semantic_id, why in reasons.items()
        if REASON_SAME_NEIGHBOR_GROUP in why
    ]
    homonyms = [
        semantic_id
        for semantic_id, why in reasons.items()
        if REASON_CROSS_FAMILY_HOMONYM in why
    ]
    owned = [
        semantic_id
        for semantic_id, why in reasons.items()
        if why == (REASON_DATASET_OWNERSHIP,)
    ]
    assert period_neighbors and homonyms and owned


def test_a_candidate_is_never_offered_without_its_family(registry: Registry) -> None:
    for record in CASES:
        result = retrieve(
            registry,
            str(record["question"]),
            None if record.get("candidate_budget") is None else int(record["candidate_budget"]),  # type: ignore[arg-type]
        )
        admitted = set(result.admitted_ids())
        for semantic_id in admitted:
            entry = registry.entry(semantic_id)
            if entry.kind == "predicate":
                assert set(entry.dataset_scope) & admitted
            elif entry.dataset_id:
                assert entry.dataset_id in admitted


def test_order_does_not_depend_on_registry_declaration_order(registry: Registry) -> None:
    """Reordering the registry file must not reorder the view."""
    payload = read_registry_payload()
    payload["fields"] = list(reversed(payload["fields"]))  # type: ignore[arg-type]
    payload["datasets"] = list(reversed(payload["datasets"]))  # type: ignore[arg-type]
    shuffled = load_registry(payload)

    question = str(CASES[0]["question"])
    assert retrieve(registry, question).admitted_ids() == retrieve(shuffled, question).admitted_ids()


def test_budget_truncation_is_reported_before_it_reaches_a_view(registry: Registry) -> None:
    question = str(CASES[0]["question"])
    full = retrieve(registry, question)
    tight = retrieve(registry, question, candidate_budget=4)

    assert len(tight.admitted) == 4
    assert len(tight.admitted) < len(full.admitted)
    assert tight.truncated
    assert any(candidate.directly_matched for candidate in tight.truncated)
    outcome = assess(registry, tight)
    assert outcome.status == STATUS_INCOMPLETE
    assert outcome.executable is False
    assert FAILURE_BUDGET_TRUNCATED in outcome.failure_kinds()


def test_unmatched_question_yields_a_structured_failure_not_an_empty_success(
    registry: Registry,
) -> None:
    result = retrieve(registry, "이 저장소에 등록되지 않은 의미만 담긴 문장")
    outcome = assess(registry, result)

    assert not result.admitted
    assert outcome.status == STATUS_INCOMPLETE
    assert outcome.executable is False
    assert outcome.failure_kinds() == (FAILURE_NO_DATASET_MATCH,)


def test_failure_kinds_are_all_reachable_vocabulary() -> None:
    assert set(FAILURE_KINDS) == {
        FAILURE_NO_DATASET_MATCH,
        FAILURE_BUDGET_TRUNCATED,
        FAILURE_CAPABILITY_UNSUPPORTED,
    }


def test_capability_support_is_read_per_family(registry: Registry) -> None:
    """The same capability can be supported by one family and not another."""
    record = case_with_capability("relationship_mode_retrieval")
    outcome = assess(registry, retrieve(registry, str(record["question"])))
    request = next(
        item
        for item in outcome.capability_requests
        if item.supported_by or item.unsupported_by
    )
    assert request.supported_by
    assert request.unsupported_by
    assert outcome.status == STATUS_COMPLETE


# --- measurement ----------------------------------------------------------


def test_recall_reports_family_level_loss(registry: Registry) -> None:
    result = retrieve(registry, str(CASES[0]["question"]), candidate_budget=4)
    report = required_candidate_recall(
        registry,
        result,
        ["ds.domestic_etf", "f.etf_kr.return_1y"],
    )
    assert report.recall == pytest.approx(0.5)
    assert report.per_family_recall() == {"ds.domestic_etf": pytest.approx(0.5)}
    assert [item.reason for item in report.missing] == [MISS_BUDGET_TRUNCATED]


def test_recall_distinguishes_a_never_matched_candidate(registry: Registry) -> None:
    result = retrieve(registry, "국내 ETF의 상장상태를 알려줘")
    report = required_candidate_recall(
        registry,
        result,
        ["ds.domestic_etf", "f.bond_kr.credit_rating"],
    )
    assert [item.reason for item in report.missing] == [MISS_NOT_MATCHED]
    assert report.per_family_recall()["ds.domestic_bond"] == pytest.approx(0.0)


def test_recall_rejects_gold_that_names_an_unknown_candidate(registry: Registry) -> None:
    result = retrieve(registry, str(CASES[0]["question"]))
    with pytest.raises(KeyError, match="absent from the registry"):
        required_candidate_recall(registry, result, ["f.not_a_field"])


def test_aggregate_recall_reports_per_family(registry: Registry) -> None:
    reports = [
        run_case(registry, case_of(record)).recall
        for record in CASES
    ]
    aggregate = aggregate_recall(reports)
    assert aggregate["questions"] == len(CASES)
    per_family = aggregate["per_family_recall"]
    assert isinstance(per_family, Mapping)
    assert per_family


def test_summary_reports_size_latency_and_failure_mix(registry: Registry) -> None:
    records = [run_case(registry, case_of(record)) for record in CASES]
    summary = summarise(records)

    assert summary["cases"] == len(CASES)
    for key in ("candidate_count", "serialized_bytes", "total_latency_ms"):
        distribution = summary[key]
        assert isinstance(distribution, Mapping)
        assert distribution["min"] <= distribution["max"]
    assert summary["failure_kind_counts"]


def test_transcript_record_round_trips_as_json(registry: Registry) -> None:
    record = run_case(registry, case_of(CASES[0])).as_transcript_record()
    restored = json.loads(json.dumps(record, ensure_ascii=False))
    assert restored["presentation_order"] == record["presentation_order"]
    assert restored["semantic_id_by_ref"]


def test_a_seeded_minter_reproduces_a_recorded_run(registry: Registry) -> None:
    """Refs are random per request, but a recorded seed can replay a run."""
    result = retrieve(registry, str(CASES[0]["question"]))
    first = build_view(registry, result, RefMinter(random.Random(20260830)))
    second = build_view(registry, result, RefMinter(random.Random(20260830)))
    assert first.view.refs() == second.view.refs()
    assert first.semantic_id_by_ref == second.semantic_id_by_ref


def test_neighbor_rules_can_be_switched_off_by_the_registry(registry: Registry) -> None:
    """Expansion is registry policy, not a behaviour baked into retrieval."""
    payload = read_registry_payload()
    policy = dict(payload["retrieval_policy"])  # type: ignore[arg-type]
    policy["neighbor_rules"] = []
    payload["retrieval_policy"] = policy
    without_neighbors = load_registry(payload)

    question = str(CASES[0]["question"])
    with_rules = retrieve(registry, question)
    without_rules = retrieve(without_neighbors, question)

    assert len(without_rules.admitted) < len(with_rules.admitted)
    assert all(
        candidate.reasons != (REASON_SAME_NEIGHBOR_GROUP,)
        for candidate in without_rules.admitted
    )
    assert any(
        REASON_SURFACE_MATCH in candidate.reasons for candidate in without_rules.admitted
    )
