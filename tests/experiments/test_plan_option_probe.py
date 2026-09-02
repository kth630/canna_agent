"""Structural tests for the offline plan-option falsification probe.

Every test here states what it is for, which capability it exercises, what it
would take to be wrong, and what its failure would falsify. None of them names
a question string, a stable semantic identifier or a fixture's expected answer:
the inputs are either the approved fixtures read as data or synthetic view
sources built inside the test, and the assertions are about invariants.

The probe is an experiment. Passing here does not approve the contract it
measures; it only means the measurement itself holds up.
"""

from __future__ import annotations

import json
import random
import unicodedata
from pathlib import Path

import pytest

from canna.experiments.plan_option_probe import (
    capprobe,
    presentation,
    selection,
)
from canna.experiments.plan_option_probe import options as opt
from canna.experiments.plan_option_probe.corpus import SPLIT_PRIMARY, load_cases
from canna.experiments.plan_option_probe.ledger import (
    PROPOSAL_ALLOWED_REASONS,
    build_ledger,
)
from canna.experiments.plan_option_probe.sources import (
    KIND_DATASET,
    KIND_FIELD,
    ViewCandidate,
    ViewSource,
    load_view_source,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"

TEST_METADATA = {
    "test_purpose": (
        "서버가 Runtime View와 승인된 질문 metadata만으로 만드는 SpanLedger·"
        "RequirementOption·PlanOption의 불변식을 반증한다"
    ),
    "capability_under_test": (
        "deterministic_span_ledger, bounded_option_generation, "
        "atomic_plan_materialization, stable_plan_identity"
    ),
    "semantic_clarity": "explicit",
    "provenance": "experiment_only_not_a_product_contract",
}


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


@pytest.fixture(scope="module")
def sources() -> dict[str, ViewSource]:
    return {
        path.name: load_view_source(path)
        for path in (
            FIXTURES / "runtime_view_registry.json",
            FIXTURES / "semantic_probe_catalog.json",
        )
    }


@pytest.fixture(scope="module")
def primary_cases():
    return load_cases(ROOT, split=SPLIT_PRIMARY)


def _generate(case, source, seed: int | None = None):
    candidates = list(source.candidates)
    if seed is not None:
        random.Random(seed).shuffle(candidates)
        source = ViewSource(
            source_id=source.source_id,
            authority=source.authority,
            candidates=tuple(candidates),
        )
    question = _normalise(case.question)
    ledger = build_ledger(case.question, source)
    return ledger, opt.generate(question, ledger, source), source


def _synthetic_source(field_count: int) -> ViewSource:
    """A view source built here, so no Registry identifier is written in code."""
    dataset = ViewCandidate(
        key="probe.dataset",
        kind=KIND_DATASET,
        meaning="probe dataset",
        surface_forms=("표적집합",),
        dataset_keys=(),
        grains=("product",),
        period="",
        unit="",
        currency="",
        allowed_operations=(),
        subject_class="",
        object_class="",
        relation_mode="",
        entity_class="",
        role_nouns=(),
        declared_axes=frozenset({"type", "family", "grain"}),
    )
    fields = tuple(
        ViewCandidate(
            key=f"probe.field.{index}",
            kind=KIND_FIELD,
            meaning=f"probe measure {index}",
            surface_forms=("측정값",),
            dataset_keys=("probe.dataset",),
            grains=("product",),
            period=f"{index + 1}Y",
            unit="percent",
            currency="",
            allowed_operations=("filter", "sort", "aggregate", "output"),
            subject_class="",
            object_class="",
            relation_mode="",
            entity_class="",
            role_nouns=(),
            declared_axes=frozenset(
                {"type", "family", "grain", "operation", "period", "unit"}
            ),
        )
        for index in range(field_count)
    )
    return ViewSource(
        source_id="probe_synthetic",
        authority="experiment_only",
        candidates=(dataset, *fields),
    )


# ---------------------------------------------------------------------------
# 1. Span ledger
# ---------------------------------------------------------------------------


def test_every_approved_question_is_split_into_the_expected_number_of_requirements(
    primary_cases, sources
):
    """falsifies_if: a frame count differs from every declared alternative.

    If the server cannot recover the requirement frame, the role-reduction
    contract has no unit to attach a RequirementOption to.
    """
    for case in primary_cases:
        ledger = build_ledger(case.question, sources[case.view_source])
        assert len(ledger.frames) in case.requirement_counts, case.test_id


def test_no_approved_question_leaves_an_unclassified_content_span(
    primary_cases, sources
):
    """falsifies_if: residue survives both classification and promotion.

    Leftover content is what section 5.1 blocks the whole option set on, so a
    ledger that leaves any is not usable as a production input.
    """
    for case in primary_cases:
        ledger = build_ledger(case.question, sources[case.view_source])
        assert ledger.unclassified == (), case.test_id


def test_the_residue_needs_reasons_the_proposal_does_not_allow(
    primary_cases, sources
):
    """falsifies_if: the four allowed reasons turn out to be sufficient.

    This test asserts a *finding*: the approved corpus cannot be accounted for
    with connective, politeness, discourse and punctuation alone. If it ever
    passes with only those, the added reasons should be removed rather than
    approved.
    """
    used: set[str] = set()
    for case in primary_cases:
        ledger = build_ledger(case.question, sources[case.view_source])
        used.update(item.reason for item in ledger.non_requirement)
    assert used - set(PROPOSAL_ALLOWED_REASONS)


def test_a_named_candidate_is_never_classified_as_a_function_word(
    primary_cases, sources
):
    """falsifies_if: a surface form the view declares is swallowed as residue.

    Discarding a named candidate as a particle is the specific misclassification
    the task forbids, and it would be invisible downstream.
    """
    for case in primary_cases:
        source = sources[case.view_source]
        ledger = build_ledger(case.question, source)
        named = {
            (span.start, span.end)
            for span in ledger.spans
            if span.candidate_keys
        }
        for item in ledger.non_requirement:
            for start, end in named:
                assert not (item.start < end and start < item.end), case.test_id


# ---------------------------------------------------------------------------
# 2. Option generation
# ---------------------------------------------------------------------------


def test_no_option_uses_a_candidate_the_view_did_not_bind_to_its_target(
    primary_cases, sources
):
    """falsifies_if: an option names a field outside its target's family.

    Generating a combination the Runtime View never offered is the failure the
    whole opaque-reference design exists to make impossible.
    """
    for case in primary_cases:
        source = sources[case.view_source]
        _ledger, result, _ = _generate(case, source)
        for options in result.requirement_options.values():
            for option in options:
                for key in option.output_field_keys:
                    candidate = source.get(key)
                    assert candidate is not None, case.test_id
                    assert set(candidate.dataset_keys) & set(option.target_keys)


def test_the_three_states_are_recorded_independently(primary_cases, sources):
    """falsifies_if: a ready canonicalisation carries failures, or a mapped
    option claims execution readiness.

    Collapsing semantic mapping, canonicalisation and execution readiness into
    one verdict is what lets an unservable plan look answerable.
    """
    for case in primary_cases:
        _ledger, result, _ = _generate(case, sources[case.view_source])
        for options in result.requirement_options.values():
            for option in options:
                if option.canonicalization_status == opt.CANONICALIZATION_READY:
                    assert not option.canonicalization_failures, case.test_id
                assert option.execution_readiness in (
                    opt.READINESS_BLOCKED,
                    opt.READINESS_NOT_EVALUATED,
                ), case.test_id


def test_coverage_and_freshness_are_carried_rather_than_used_to_delete_a_meaning(
    primary_cases, sources
):
    """falsifies_if: an option with a mapped meaning carries no constraint note.

    ARCHITECTURE.md section 6 requires incomplete coverage to change the claim,
    not the candidate set.
    """
    for case in primary_cases:
        _ledger, result, _ = _generate(case, sources[case.view_source])
        for options in result.requirement_options.values():
            for option in options:
                if option.target_keys:
                    assert option.execution_constraints, case.test_id
                    assert (
                        opt.REASON_PROVENANCE_UNAVAILABLE
                        in option.execution_constraints
                    )


def test_choice_required_and_materially_ambiguous_are_different_outcomes():
    """falsifies_if: two candidates named by the same words are offered as a
    free choice.

    A choice the question does not discriminate is not a choice a model may
    make, and merging the two states would let it.
    """
    source = _synthetic_source(2)
    question = "표적집합 중 측정값이 높은 3개를 보여줘"
    ledger = build_ledger(question, source)
    result = opt.generate(question, ledger, source)
    assert result.generation_status == opt.GENERATION_MATERIALLY_AMBIGUOUS
    assert not result.selectable_plans


# ---------------------------------------------------------------------------
# 3. Caps and truncation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("offset", (-1, 0, 1))
def test_the_option_cap_blocks_only_when_it_actually_discards_a_meaning(offset):
    """falsifies_if: a run over the cap still offers a selectable plan.

    Section 7's caps are safe only under the rule that one lossy discard blocks
    everything; a cap that quietly returns the first N is a wrong answer with a
    budget.
    """
    policy = opt.OptionGenerationPolicy()
    count = policy.max_options_per_requirement + offset
    source = _synthetic_source(count)
    question = "표적집합 중 측정값이 높은 3개를 보여줘"
    ledger = build_ledger(question, source)
    result = opt.generate(question, ledger, source, policy)
    # Same-span homonyms are refused before any cap can bind, which is itself
    # the finding: the cap is not what protects this corpus.
    assert not result.selectable_plans
    if result.lossy_discards:
        assert result.generation_status == opt.GENERATION_TRUNCATED
        assert opt.REASON_TRUNCATED in result.generation_reasons


def test_every_cap_is_a_refusal_above_it_and_a_pass_at_it():
    """falsifies_if: a cap trims silently, or refuses before it is reached.

    Runs each provisional cap at one below, exactly on and one above. The row
    above a cap has to be truncated *and* unselectable; the rows at and below it
    have to still offer plans, or the cap would be refusing work it can do.
    """
    rows = capprobe.to_rows(capprobe.observations())
    assert rows
    for row in rows:
        if row["position"] == "above":
            assert row["truncated"], row
            assert row["blocked"], row
            assert row["lossy_discards"] >= 0
        else:
            assert not row["truncated"], row
            assert not row["blocked"], row
            assert row["lossy_discards"] == 0, row


def test_a_lossy_discard_is_never_reported_as_a_success(primary_cases, sources):
    """falsifies_if: a case with a discarded meaning still has a selectable plan."""
    for case in primary_cases:
        _ledger, result, _ = _generate(case, sources[case.view_source])
        if result.lossy_discards:
            assert not result.selectable_plans, case.test_id


def test_too_many_requirements_is_a_structural_refusal_not_a_trim():
    """falsifies_if: a question over the requirement cap returns a partial plan."""
    policy = opt.OptionGenerationPolicy(max_requirements=1)
    source = _synthetic_source(1)
    question = "표적집합의 측정값 목록과 평균 측정값을 알려줘"
    ledger = build_ledger(question, source)
    result = opt.generate(question, ledger, source, policy)
    if len(ledger.frames) > policy.max_requirements:
        assert result.generation_status == opt.GENERATION_TRUNCATED
        assert result.plan_options == ()


# ---------------------------------------------------------------------------
# 4. Identity and invariance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", (1, 7, 42))
def test_the_same_meaning_survives_a_different_candidate_order(
    primary_cases, sources, seed
):
    """falsifies_if: shuffling the candidate pool changes an equivalence key.

    A plan identity that depends on retrieval order cannot be re-validated after
    selection, which is the check the whole selection step rests on.
    """
    for case in primary_cases:
        source = sources[case.view_source]
        _ledger, baseline, _ = _generate(case, source)
        _ledger, shuffled, _ = _generate(case, source, seed=seed)
        assert sorted(item.equivalence_key for item in baseline.plan_options) == sorted(
            item.equivalence_key for item in shuffled.plan_options
        ), case.test_id


def test_a_new_request_salt_does_not_change_the_plan_preview(primary_cases, sources):
    """falsifies_if: two requests for one question disagree on the preview.

    References are per request by design, so the preview has to be computed from
    meaning alone or nothing minted twice could ever be compared.
    """
    for case in primary_cases:
        source = sources[case.view_source]
        _ledger, result, _ = _generate(case, source)
        first = selection.PlanOptionStore.for_request(result)
        second = selection.PlanOptionStore.for_request(result)
        assert sorted(first.previews.values()) == sorted(second.previews.values())
        assert set(first.by_ref) & set(second.by_ref) == set()


# ---------------------------------------------------------------------------
# 5. Reference authority
# ---------------------------------------------------------------------------


def test_only_a_reference_this_request_minted_can_be_selected(primary_cases, sources):
    """falsifies_if: an arbitrary or foreign reference reaches a plan.

    Membership, not shape, is the permission; a store that accepts a well-formed
    stranger has no authority model at all.
    """
    case = primary_cases[0]
    source = sources[case.view_source]
    _ledger, result, _ = _generate(case, source)
    store = selection.PlanOptionStore.for_request(result)
    other = selection.PlanOptionStore.for_request(result)

    with pytest.raises(selection.SelectionRejected) as arbitrary:
        store.select("not-a-reference")
    assert arbitrary.value.reason == selection.REJECT_SHAPE

    foreign = next(iter(other.by_ref))
    with pytest.raises(selection.SelectionRejected) as cross:
        store.select(foreign)
    assert cross.value.reason == selection.REJECT_NOT_IN_REQUEST


def test_a_reference_is_single_use_and_dies_with_its_request(primary_cases, sources):
    """falsifies_if: a reference can be replayed, or survives its request."""
    case = primary_cases[0]
    source = sources[case.view_source]
    _ledger, result, _ = _generate(case, source)
    store = selection.PlanOptionStore.for_request(result)
    ref = next(iter(store.by_ref))
    try:
        store.select(ref)
    except selection.SelectionRejected as refused:
        assert refused.reason == selection.REJECT_NOT_SELECTABLE
    with pytest.raises(selection.SelectionRejected) as replay:
        store.select(ref)
    assert replay.value.reason == selection.REJECT_CONSUMED

    fresh = selection.PlanOptionStore.for_request(result)
    other = next(iter(fresh.by_ref))
    fresh.expire()
    with pytest.raises(selection.SelectionRejected) as expired:
        fresh.select(other)
    assert expired.value.reason == selection.REJECT_EXPIRED


def test_a_blocked_plan_cannot_be_selected(primary_cases, sources):
    """falsifies_if: a plan with a blocking reason is executable anyway."""
    for case in primary_cases:
        source = sources[case.view_source]
        _ledger, result, _ = _generate(case, source)
        store = selection.PlanOptionStore.for_request(result)
        for ref, plan in store.by_ref.items():
            if plan.selectable:
                continue
            with pytest.raises(selection.SelectionRejected) as refused:
                store.select(ref)
            assert refused.value.reason == selection.REJECT_NOT_SELECTABLE


# ---------------------------------------------------------------------------
# 6. Presentation
# ---------------------------------------------------------------------------


def test_the_offered_payload_carries_no_identifier_and_no_physical_name(
    primary_cases, sources
):
    """falsifies_if: a stable identifier, a table, a column or SQL is visible.

    The model is meant to see meanings and one opaque reference; anything else
    hands it the vocabulary to invent a plan the server never issued.
    """
    for case in primary_cases:
        source = sources[case.view_source]
        _ledger, result, _ = _generate(case, source)
        store = selection.PlanOptionStore.for_request(result)
        payload = presentation.payload_for(store.offered, source)
        assert presentation.leaked_values(payload, source) == (), case.test_id
        for plan in store.offered:
            for summary in presentation.plan_summary(plan, source)["requirements"]:
                assert presentation.unexpected_fields(summary) == ()


def test_the_payload_is_serialisable_and_bounded(primary_cases, sources):
    """falsifies_if: an option payload cannot be measured before it is sent."""
    for case in primary_cases:
        source = sources[case.view_source]
        _ledger, result, _ = _generate(case, source)
        payload = presentation.payload_for(result.plan_options, source)
        json.loads(payload)
        estimates = presentation.scale_estimates(result.plan_options, source)
        if result.plan_options:
            assert [item.option_count for item in estimates] == [2, 4, 8, 16]
            assert all(item.bytes_utf8 > 0 for item in estimates)
