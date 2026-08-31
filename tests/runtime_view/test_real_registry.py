"""The guard holds on the real Registry, discovered structurally rather than named.

These tests never spell out a product family, a measure or a relation. They ask
the Registry which of its own terms collide — every alias two families share,
every declared inverse pair — and then assert the rule on all of them. A test
written that way cannot pass by having memorised the four families that exist
today, and it will keep testing the same rule when a fifth is added.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from canna.runtime_view import (
    CODE_CROSS_FAMILY_FIELD,
    CandidateProposal,
    RegistryFacts,
    SubmittedQuery,
    SubmittedRelationship,
    SubmittedRequirement,
    build_runtime_view,
    validate,
)
from canna.runtime_view.contract import DATASET_GRAINS, REQUIREMENT_KIND_LISTING, STATUS_MAPPED
from canna.runtime_view.view import (
    MATCH_EXACT,
    dataset_terms_for_family,
    is_dataset,
    is_field,
    is_relation,
)

from .conftest import StubEntityResolver, resolved

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "processed" / "semantic_registry.json"
QUESTION = "실제 Registry 구조를 검사하는 질문"


@pytest.fixture(scope="module")
def facts() -> RegistryFacts:
    if not REGISTRY.is_file():
        pytest.skip("the semantic registry has not been generated in this workspace")
    return RegistryFacts.load()


def _surface_forms(term) -> set[str]:
    forms = {str(value) for value in term.evidence.get("aliases", ()) or ()}
    labels = term.evidence.get("labels", {}) or {}
    forms |= {str(value) for value in labels.values()}
    return {value for value in forms if value.strip()}


def _cross_family_homonyms(facts: RegistryFacts) -> list[tuple[str, str, str]]:
    """``(surface form, field in one family, field in another)`` for every collision."""
    by_form: dict[str, list[str]] = {}
    for term in facts.terms:
        if not is_field(facts, term.semantic_id):
            continue
        if not (term.evidence.get("families") or ()):
            continue
        for form in _surface_forms(term):
            by_form.setdefault(form, []).append(term.semantic_id)
    collisions = []
    for form, ids in sorted(by_form.items()):
        families = {
            semantic_id: set(facts.term(semantic_id).evidence.get("families", ()) or ())
            for semantic_id in ids
        }
        for first in sorted(ids):
            for second in sorted(ids):
                if first < second and not families[first] & families[second]:
                    collisions.append((form, first, second))
    return collisions


def _targets_sharing_grain(facts: RegistryFacts, field_id: str) -> tuple[str, ...]:
    """Datasets of the field's family that it can actually be measured at."""
    grains = set(facts.term(field_id).evidence.get("grains") or ())
    out: list[str] = []
    for family in sorted(facts.term(field_id).evidence.get("families") or ()):
        out += [
            dataset
            for dataset in dataset_terms_for_family(facts, family)
            if grains & set(facts.term(dataset).evidence.get("grains") or ())
        ]
    return tuple(out)


def _listing(view, target_id: str, field_id: str) -> SubmittedQuery:
    return SubmittedQuery(
        (
            SubmittedRequirement(
                requirement_id="r1",
                kind=REQUIREMENT_KIND_LISTING,
                status=STATUS_MAPPED,
                source_span=QUESTION,
                target_dataset_refs=(view.ref_for(target_id),),
                field_refs=(view.ref_for(field_id),),
            ),
        )
    )


def test_the_registry_really_does_contain_cross_family_homonyms(facts) -> None:
    """The failure this layer defends against is present in the shipped Registry."""
    assert _cross_family_homonyms(facts), "no cross-family homonym found; guard is vacuous"


def test_every_cross_family_homonym_is_refused_in_both_directions(facts) -> None:
    checked = 0
    for _form, first, second in _cross_family_homonyms(facts):
        for wrong_field, right_field in ((first, second), (second, first)):
            for target in _targets_sharing_grain(facts, right_field):
                view = build_runtime_view(
                    facts,
                    QUESTION,
                    [
                        CandidateProposal(target, MATCH_EXACT),
                        CandidateProposal(wrong_field, MATCH_EXACT),
                        CandidateProposal(right_field, MATCH_EXACT),
                    ],
                )
                result = validate(facts, view, _listing(view, target, wrong_field))
                assert not result.semantic_valid, (wrong_field, target)
                assert [issue.code for issue in result.issues] == [CODE_CROSS_FAMILY_FIELD]
                assert result.issues[0].substitute_offered is False
                checked += 1
    assert checked, "no homonym had a shared-grain target; guard is vacuous"


def test_the_right_family_field_of_the_same_homonym_is_accepted(facts) -> None:
    """The refusal is about the family, not about the name being ambiguous."""
    checked = 0
    for _form, first, second in _cross_family_homonyms(facts)[:20]:
        for field_id in (first, second):
            for target in _targets_sharing_grain(facts, field_id):
                view = build_runtime_view(
                    facts,
                    QUESTION,
                    [
                        CandidateProposal(target, MATCH_EXACT),
                        CandidateProposal(field_id, MATCH_EXACT),
                    ],
                )
                assert validate(facts, view, _listing(view, target, field_id)).semantic_valid, (
                    field_id,
                    target,
                )
                checked += 1
    assert checked


def test_a_field_whose_family_has_no_dataset_still_gets_a_visible_binding(facts) -> None:
    """Retrieval may omit the family's dataset; the binding must not disappear."""
    scoped = [
        term.semantic_id
        for term in facts.terms
        if is_field(facts, term.semantic_id) and (term.evidence.get("families") or ())
    ]
    assert scoped
    for semantic_id in scoped[:50]:
        view = build_runtime_view(
            facts, QUESTION, [CandidateProposal(semantic_id, MATCH_EXACT)]
        )
        candidate = view.field(view.ref_for(semantic_id))
        assert candidate.belongs_to_dataset_refs, semantic_id
        assert {view.dataset(ref).introduced_by for ref in candidate.belongs_to_dataset_refs} == {
            "family_closure"
        }


def test_no_non_queryable_class_is_offered_as_a_target(facts) -> None:
    """Security, portfolio and observation classes must not be query targets."""
    non_targets = [
        term.semantic_id
        for term in facts.terms
        if term.kind == "class" and not is_dataset(facts, term.semantic_id)
    ]
    assert non_targets, "every class is a dataset; guard is vacuous"
    view = build_runtime_view(
        facts, QUESTION, [CandidateProposal(value, MATCH_EXACT) for value in non_targets]
    )
    assert view.datasets == ()
    assert {item.semantic_id for item in view.excluded} == set(non_targets)
    for semantic_id in non_targets:
        assert view.ref_for(semantic_id) is None


def test_every_dataset_is_a_family_class_at_an_approved_result_grain(facts) -> None:
    datasets = [
        term.semantic_id for term in facts.terms if is_dataset(facts, term.semantic_id)
    ]
    assert datasets
    for semantic_id in datasets:
        evidence = facts.term(semantic_id).evidence
        assert evidence.get("families")
        assert set(evidence.get("grains") or ()) & set(DATASET_GRAINS)
        assert not evidence.get("allowed_operations")
        assert not is_relation(facts, semantic_id)


def _inverse_pairs(facts: RegistryFacts) -> list[tuple[str, str]]:
    pairs = []
    for term in facts.terms:
        if not is_relation(facts, term.semantic_id):
            continue
        partner = str(term.evidence.get("inverse_of", ""))
        if partner and facts.has(partner):
            pairs.append((term.semantic_id, partner))
    return sorted(pairs)


def test_every_declared_inverse_pair_resolves_from_the_anchor_type(facts) -> None:
    pairs = _inverse_pairs(facts)
    assert pairs, "no inverse pair declared; guard is vacuous"
    for forward, backward in pairs:
        object_class = str(facts.term(forward).evidence["range"][0])
        product_class = str(facts.term(forward).evidence["domain"][0])
        targets = [
            term.semantic_id
            for term in facts.terms
            if is_dataset(facts, term.semantic_id)
            and facts.is_kind_of(term.semantic_id, product_class)
        ]
        assert targets, forward
        view = build_runtime_view(
            facts,
            QUESTION,
            [
                CandidateProposal(targets[0], MATCH_EXACT),
                CandidateProposal(forward, MATCH_EXACT),
            ],
            entity_resolver=StubEntityResolver(
                [resolved("어떤대상", object_class, "verified:key:1")]
            ),
        )
        result = validate(
            facts,
            view,
            SubmittedQuery(
                (
                    SubmittedRequirement(
                        requirement_id="r1",
                        kind=REQUIREMENT_KIND_LISTING,
                        status=STATUS_MAPPED,
                        source_span=QUESTION,
                        target_dataset_refs=(view.ref_for(targets[0]),),
                        relationship=SubmittedRelationship(
                            predicate_ref=view.ref_for(forward),
                            anchor_entity_ref=view.entities[0].ref,
                        ),
                    ),
                )
            ),
        )
        assert result.semantic_valid, (forward, result.to_dict())
        relation = result.plan.requirements[0].relation
        assert relation.submitted_predicate_id == forward
        assert relation.predicate_id == backward
        assert relation.anchor_entity_key == "verified:key:1"


def test_same_shape_relations_are_published_as_different_meanings(facts) -> None:
    """Two relations sharing a domain and range must not look interchangeable."""
    predicates = [
        term.semantic_id for term in facts.terms if is_relation(facts, term.semantic_id)
    ]
    view = build_runtime_view(
        facts, QUESTION, [CandidateProposal(value, MATCH_EXACT) for value in predicates]
    )
    groups: dict[str, list] = {}
    for candidate in view.predicates:
        groups.setdefault(candidate.relation_mode_group, []).append(candidate)
    crowded = [items for items in groups.values() if len(items) > 2]
    assert crowded, "no relation shares a shape with a non-inverse; guard is vacuous"
    for items in crowded:
        for candidate in items:
            assert candidate.distinct_from_refs
            assert candidate.inverse_ref not in candidate.distinct_from_refs
            assert candidate.ref not in candidate.distinct_from_refs


def test_the_real_payload_never_leaks_a_semantic_id_or_a_score(facts) -> None:
    proposals = [
        CandidateProposal(term.semantic_id, MATCH_EXACT)
        for term in facts.terms
        if is_field(facts, term.semantic_id)
        or is_dataset(facts, term.semantic_id)
        or is_relation(facts, term.semantic_id)
    ][:160]
    view = build_runtime_view(facts, QUESTION, proposals)
    payload = json.dumps(view.to_model_payload(), ensure_ascii=False)
    for prefix in json.loads(REGISTRY.read_text(encoding="utf-8"))["prefixes"]:
        assert f"{prefix}:" not in payload
    for forbidden in ("score", "rank", "table", "column", "sql", "join", "resolved_key"):
        assert forbidden not in payload
