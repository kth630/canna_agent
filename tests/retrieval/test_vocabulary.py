"""The searchable vocabulary is a projection of the registry, not a copy of it.

These tests state rules that must hold for every term in the registry, present
and future. None of them names a product, a date, a row count or an evaluation
question; where a concrete term is needed it is synthesised inside the test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from canna.retrieval.vocabulary import (
    EVIDENCE_FIELDS,
    ROLE_ALIAS,
    ROLE_DEFINITION,
    ROLE_LABEL,
    ROLE_SEMANTIC_ID,
    TIER_SUBSTRING,
    VocabularyError,
    build_vocabulary,
    content_hash,
    load_vocabulary,
)

from .conftest import synthetic_registry, term


def test_every_registry_term_becomes_exactly_one_vocabulary_term(vocabulary) -> None:
    payload = json.loads(Path(vocabulary.source_path).read_text(encoding="utf-8"))
    assert len(vocabulary) == len(payload["terms"])
    assert len({item.semantic_id for item in vocabulary.terms}) == len(vocabulary)


def test_surface_forms_come_only_from_registry_text(vocabulary) -> None:
    """No synonym may exist that the ontology did not approve."""
    payload = json.loads(Path(vocabulary.source_path).read_text(encoding="utf-8"))
    approved = {entry["semantic_id"]: entry for entry in payload["terms"]}
    for item in vocabulary.terms:
        entry = approved[item.semantic_id]
        permitted = {item.semantic_id, str(entry.get("definition") or "")}
        permitted.update(str(value) for value in (entry.get("labels") or {}).values())
        permitted.update(str(value) for value in (entry.get("aliases") or []))
        for form in item.forms:
            assert any(form.text == " ".join(str(value).split()) for value in permitted), (
                f"{item.semantic_id} exposes a surface form absent from the registry: {form.text!r}"
            )


def test_terms_without_searchable_text_are_reported_not_dropped(vocabulary) -> None:
    unsearchable = set(vocabulary.unsearchable_ids())
    for semantic_id in unsearchable:
        assert vocabulary.has(semantic_id), "an unsearchable term must still be addressable"
    for item in vocabulary.terms:
        has_text = any(form.role != ROLE_SEMANTIC_ID for form in item.forms)
        assert has_text == (item.semantic_id not in unsearchable)


def test_role_contracts_forbid_partial_matches_on_ids_and_definitions() -> None:
    vocabulary = synthetic_registry(
        [term("syn:A", label="라벨", aliases=["별칭"], definition="설명 문장이다")]
    )
    by_role = {form.role: form for form in vocabulary.term("syn:A").forms}
    assert not by_role[ROLE_SEMANTIC_ID].allows(TIER_SUBSTRING)
    assert not by_role[ROLE_DEFINITION].allows(TIER_SUBSTRING)
    assert by_role[ROLE_LABEL].allows(TIER_SUBSTRING)
    assert by_role[ROLE_ALIAS].allows(TIER_SUBSTRING)


def test_embeddable_forms_cover_label_alias_and_definition() -> None:
    vocabulary = synthetic_registry(
        [term("syn:A", label="라벨", aliases=["별칭", "다른이름"], definition="설명")]
    )
    roles = sorted(form.role for form in vocabulary.embeddable_forms())
    assert roles == [ROLE_ALIAS, ROLE_ALIAS, ROLE_DEFINITION, ROLE_LABEL]


def test_evidence_carries_meaning_and_no_physical_binding(vocabulary) -> None:
    forbidden = {"table", "column", "sql", "join", "row_count", "coverage_count"}
    for item in vocabulary.terms:
        assert set(item.evidence) == set(EVIDENCE_FIELDS)
        serialized = json.dumps(item.evidence, ensure_ascii=False).lower()
        for key in forbidden:
            assert f'"{key}"' not in serialized


def test_content_hash_ignores_generation_time_but_not_meaning() -> None:
    base = {
        "prefixes": {},
        "counts": {"total": 1},
        "ontology_files": [],
        "terms": [term("syn:A", label="라벨")],
    }
    with_time = dict(base, generated_at="2026-08-31T00:00:00Z")
    later = dict(base, generated_at="2026-09-01T00:00:00Z")
    assert content_hash(with_time) == content_hash(later)

    changed = json.loads(json.dumps(base))
    changed["terms"][0]["labels"]["ko"] = "다른라벨"
    assert content_hash(changed) != content_hash(base)


def test_duplicate_semantic_ids_are_rejected() -> None:
    payload = {
        "prefixes": {},
        "counts": {},
        "ontology_files": [],
        "terms": [term("syn:A", label="하나"), term("syn:A", label="둘")],
    }
    with pytest.raises(VocabularyError, match="duplicate semantic id"):
        build_vocabulary(payload)


def test_empty_registry_is_rejected() -> None:
    with pytest.raises(VocabularyError):
        build_vocabulary({"terms": []})


def test_loading_is_deterministic(vocabulary) -> None:
    again = load_vocabulary()
    assert again.content_hash == vocabulary.content_hash
    assert [item.semantic_id for item in again.terms] == [
        item.semantic_id for item in vocabulary.terms
    ]
    assert [form.form_id for form in again.rule_forms()] == [
        form.form_id for form in vocabulary.rule_forms()
    ]
