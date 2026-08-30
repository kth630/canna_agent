"""The Data Catalog must cover every official field and reference only real semantics.

These tests read the authored catalog and the ontology, not the built store, so
they fail fast when a binding is added without a meaning or a field silently
disappears from the submission scope.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from canna.store.catalog import CatalogError, load_catalog

ROOT = Path(__file__).resolve().parents[1]
FIELD_CATALOG = (
    ROOT
    / "provenance"
    / "workstreams"
    / "20260830_preintegration_parallel"
    / "ontology_data_alignment"
    / "generated"
    / "official_field_catalog.csv"
)


def official_fields() -> set[tuple[str, str]]:
    with FIELD_CATALOG.open(encoding="utf-8-sig", newline="") as handle:
        return {(row["table_id"], row["field"]) for row in csv.DictReader(handle)}


def test_every_official_field_is_bound_or_explicitly_unbound() -> None:
    catalog = load_catalog()
    bound = [(binding.table_id, binding.field) for binding in catalog.field_bindings]
    assert len(bound) == len(set(bound)), "a field is bound twice"
    assert set(bound) == official_fields(), "catalog and 0-D field inventory disagree"


def test_unbound_and_as_of_fields_state_a_reason() -> None:
    catalog = load_catalog()
    silent = [
        binding.field
        for binding in catalog.field_bindings
        if binding.role in {"unbound", "as_of"} and not binding.note
    ]
    assert not silent, f"fields excluded from capability without a recorded reason: {silent}"


def test_every_binding_records_a_zero_d_decision() -> None:
    catalog = load_catalog()
    missing = [b.field for b in catalog.field_bindings if not b.alignment_decision]
    assert not missing


def test_family_keys_match_the_declared_identity_bindings() -> None:
    catalog = load_catalog()
    for family in catalog.families:
        keys = [
            binding
            for binding in catalog.bindings_for(family.official_table_id)
            if binding.role == "identity_key"
        ]
        assert len(keys) == 1, f"{family.family_id} must declare exactly one identity key"
        assert keys[0].field == family.official_key_field
        assert keys[0].subject_grain == family.result_grain


def test_metric_bindings_declare_a_unit_and_attribute_bindings_do_not() -> None:
    catalog = load_catalog()
    problems = []
    for binding in catalog.field_bindings:
        if binding.role == "metric" and binding.unit_code == "none":
            problems.append(f"{binding.field}: metric without a unit")
        if binding.role == "attribute" and binding.unit_code != "none":
            problems.append(f"{binding.field}: attribute must not claim a unit")
    assert not problems, problems


def test_as_of_reference_points_at_a_declared_as_of_field() -> None:
    catalog = load_catalog()
    for family in catalog.families:
        bindings = catalog.bindings_for(family.official_table_id)
        declared = {b.field for b in bindings if b.role == "as_of"}
        dangling = [
            b.field for b in bindings if b.as_of_field and b.as_of_field not in declared
        ]
        assert not dangling, f"{family.family_id}: as-of references without a date field: {dangling}"


def test_currency_source_points_at_a_field_in_the_same_table() -> None:
    catalog = load_catalog()
    for family in catalog.families:
        bindings = catalog.bindings_for(family.official_table_id)
        fields = {b.field for b in bindings}
        for binding in bindings:
            if binding.currency_field:
                assert binding.currency_field in fields, (
                    f"{binding.field}: currency source {binding.currency_field} is not in "
                    f"{family.official_table_id}"
                )


def test_every_catalog_semantic_id_exists_in_the_ontology() -> None:
    """A binding that names a meaning nobody declared must not reach the registry."""
    from canna.registry.semantic import build_registry

    declared = {term["semantic_id"] for term in build_registry()["terms"]}
    dangling = sorted(load_catalog().semantic_ids() - declared)
    assert not dangling, f"catalog references undeclared semantics: {dangling}"


def test_relation_and_identifier_rules_are_ordered_and_typed(tmp_path: Path) -> None:
    catalog = load_catalog()
    held = [rule for rule in catalog.identifier_rules if rule.scope == "held_security"]
    assert held, "held security identifier rules are required"
    assert held[-1].pattern == ".*", "the last held-security rule must be the catch-all"
    assert not held[-1].promote_to_security, "the catch-all must not promote to Security"
    for family in catalog.families:
        if family.holdings_family:
            assert catalog.relation_rules_for(family.family_id), (
                f"{family.family_id} collects holdings but declares no relation rule"
            )


def test_unknown_role_is_rejected(tmp_path: Path) -> None:
    """A catalog typo must fail the build instead of silently dropping a field."""
    source = ROOT / "catalog"
    for name in (
        "product_families.csv",
        "official_field_bindings.csv",
        "holdings_bindings.csv",
        "holdings_relation_rules.csv",
        "identifier_rules.csv",
        "conflict_groups.csv",
    ):
        (tmp_path / name).write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")
    path = tmp_path / "official_field_bindings.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    columns = lines[1].split(",")
    columns[3] = "not_a_role"
    lines[1] = ",".join(columns)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(tmp_path)
