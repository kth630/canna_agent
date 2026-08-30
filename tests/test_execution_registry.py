"""The Execution Registry must refuse to publish when meaning and binding disagree.

Every case below is synthetic: the point is that the rule fails for any field,
not that a particular official column is currently wrong.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import duckdb
import pytest

from canna.registry.execution import RegistryMismatch, build_execution_registry

TERM = {
    "semantic_id": "tst:SampleReturn",
    "iri": "https://example.invalid/ontology#SampleReturn",
    "kind": "metric",
    "labels": {"ko": "표본 수익률"},
    "definition": "",
    "aliases": ["표본 성과"],
    "families": ["sample_family"],
    "grains": ["product"],
    "period_code": "P1Y",
    "unit_code": "percent_observed",
    "currency_policy": "",
    "allowed_operations": ["filter", "order"],
    "evidence_requirements": ["effective_as_of"],
    "comparison_group": "sample:return",
    "meaning_status": "unit_observed_only",
    "alignment_decision": "유지",
    "domain": [],
    "range": [],
    "inverse_of": "",
    "subclass_of": [],
    "shapes": [],
    "search_text": "표본 수익률",
}

BINDING = {
    "semantic_id": "tst:SampleReturn",
    "binding_kind": "metric",
    "family_id": "sample_family",
    "subject_grain": "product",
    "alignment_decision": "유지",
    "physical": {
        "source_table": "src_sample",
        "source_column": "sample_column",
        "declared_type": "numeric(28,2)",
        "physical_type": "DECIMAL(28,2)",
        "decimal_scale": 2,
        "type_role": "measure",
        "value_slot": "value",
        "comparison_requires_trim": False,
    },
    "unit_code": "percent_observed",
    "currency_source": "none",
    "period_code": "P1Y",
    "as_of_field": "sample_base_dt",
    "allowed_operations": ["eq", "lt", "order", "avg", "count"],
    "zero_semantics": "excluded_from_measure_population",
    "source_observations": {"nonblank_rows": 10},
    "observation_table": "metric_observation",
    "value_column": "numeric_value",
    "selector_column": "metric_id",
    "observed_coverage": {"observed_subjects": 10, "subject_total": 12},
}

BUILD_ID = "0123456789abcdef0123456789abcdef"
CATALOG = {
    "generated_at": "2026-08-31T00:00:00+00:00",
    "build": {"build_id": BUILD_ID, "store_path": "", "hash_mismatches": []},
    "grain_verification": {"uniqueness": [], "references": []},
    "sources": [],
    "tables": [],
    "join_paths": [
        {
            "join_id": "subject_to_portfolio_map",
            "left": "subject.subject_key",
            "right": "product_portfolio_map.subject_key",
            "declared_cardinality": "one_to_many",
            "dedup_requirement": "product_grain_distinct",
            "observed_matched_parents": 1,
            "observed_max_children_per_parent": 1,
            "note": "",
        }
    ],
    "semantic_bindings": [BINDING],
    "relation_bindings": [],
    "holdings_coverage": [],
    "conflicts": [],
}
SEMANTIC = {
    "generated_at": "2026-08-31T00:00:00+00:00",
    "ontology_files": [],
    "counts": {"total": 1},
    "terms": [TERM],
}
RELATIONS = (
    "relation_kind,forward_semantic_id,inverse_semantic_id,result_dedup,join_path_ids,note\n"
    "direct_holding,tst:holds,tst:heldBy,product_grain_distinct,subject_to_portfolio_map,\n"
)


def write_store(tmp_path: Path, build_id: str | None) -> Path:
    """A minimal store carrying the build manifest the registry checks."""
    store = tmp_path / "query_store.duckdb"
    connection = duckdb.connect(str(store))
    connection.execute(
        "CREATE TABLE build_manifest(build_id VARCHAR, generated_at VARCHAR, "
        "store_path VARCHAR, catalog_path VARCHAR)"
    )
    if build_id is not None:
        connection.execute(
            "INSERT INTO build_manifest VALUES (?, '2026-08-31T00:00:00+00:00', '', '')",
            [build_id],
        )
    connection.close()
    return store


def write_inputs(tmp_path: Path, catalog: dict, semantic: dict) -> dict[str, Path]:
    catalog_path = tmp_path / "data_catalog.json"
    semantic_path = tmp_path / "semantic_registry.json"
    relation_path = tmp_path / "relation_bindings.csv"
    if not catalog["build"].get("store_path"):
        catalog["build"]["store_path"] = str(write_store(tmp_path, BUILD_ID))
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    semantic_path.write_text(json.dumps(semantic, ensure_ascii=False), encoding="utf-8")
    relation_path.write_text(RELATIONS, encoding="utf-8")
    return {
        "catalog_path": catalog_path,
        "semantic_path": semantic_path,
        "relation_path": relation_path,
    }


def build(tmp_path: Path, *, catalog_patch=None, semantic_patch=None):
    catalog = copy.deepcopy(CATALOG)
    semantic = copy.deepcopy(SEMANTIC)
    if catalog_patch:
        catalog_patch(catalog)
    if semantic_patch:
        semantic_patch(semantic)
    return build_execution_registry(**write_inputs(tmp_path, catalog, semantic))


def test_matching_registries_publish_executable_operations(tmp_path: Path) -> None:
    payload = build(tmp_path)
    entry = payload["bindings"][0]
    assert entry["executable_operations"] == ["filter", "order"]
    assert entry["selector_value"] == "tst:SampleReturn"
    assert entry["meaning"]["aliases"] == ["표본 성과"]
    assert entry["observed_coverage"]["observed_subjects"] == 10


def test_unknown_semantic_id_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryMismatch, match="not declared in the ontology"):
        build(tmp_path, catalog_patch=lambda c: c["semantic_bindings"][0].update(
            {"semantic_id": "tst:Missing"}
        ))


def test_grain_mismatch_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryMismatch, match="grain"):
        build(tmp_path, catalog_patch=lambda c: c["semantic_bindings"][0].update(
            {"subject_grain": "product_class"}
        ))


def test_unit_mismatch_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryMismatch, match="unit"):
        build(tmp_path, catalog_patch=lambda c: c["semantic_bindings"][0].update(
            {"unit_code": "currency_amount"}
        ))


def test_period_mismatch_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryMismatch, match="period"):
        build(tmp_path, catalog_patch=lambda c: c["semantic_bindings"][0].update(
            {"period_code": "P3M"}
        ))


def test_kind_mismatch_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryMismatch, match="ontology declares"):
        build(tmp_path, semantic_patch=lambda s: s["terms"][0].update({"kind": "attribute"}))


def test_family_mismatch_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryMismatch, match="declared for"):
        build(tmp_path, catalog_patch=lambda c: c["semantic_bindings"][0].update(
            {"family_id": "other_family"}
        ))


def test_operation_the_physical_type_cannot_support_fails(tmp_path: Path) -> None:
    """Ranking must not be promised on a column whose zero semantics are unverified."""

    def patch(catalog: dict) -> None:
        binding = catalog["semantic_bindings"][0]
        binding["physical"]["type_role"] = "integer_unverified_zero_semantics"
        binding["allowed_operations"] = ["eq", "ne", "in", "count"]

    with pytest.raises(RegistryMismatch, match="does not support it"):
        build(tmp_path, catalog_patch=patch)


def test_currency_policy_without_a_currency_source_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryMismatch, match="requires a currency"):
        build(tmp_path, semantic_patch=lambda s: s["terms"][0].update(
            {"currency_policy": "from_subject_currency"}
        ))


def test_currency_source_without_a_policy_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryMismatch, match="without an ontology policy"):
        build(tmp_path, catalog_patch=lambda c: c["semantic_bindings"][0].update(
            {"currency_source": "field:some_currency"}
        ))


def test_unbound_source_fields_are_published_with_their_reason(tmp_path: Path) -> None:
    def patch(catalog: dict) -> None:
        catalog["semantic_bindings"].append(
            {
                "semantic_id": "",
                "binding_kind": "unbound",
                "family_id": "sample_family",
                "subject_grain": "product",
                "alignment_decision": "제외",
                "physical": {"source_table": "src_sample", "source_column": "dropped_column"},
                "note": "관측된 값이 모두 0",
            }
        )

    payload = build(tmp_path, catalog_patch=patch)
    assert payload["unbound_source_fields"][0]["reason"] == "관측된 값이 모두 0"
    assert payload["counts"]["unbound_source_fields"] == 1


def test_observed_relation_kind_without_a_declaration_fails(tmp_path: Path) -> None:
    def patch(catalog: dict) -> None:
        catalog["relation_bindings"].append(
            {"family_id": "sample_family", "relation_kind": "invented_kind", "observation_rows": 1}
        )

    with pytest.raises(RegistryMismatch, match="not declared"):
        build(tmp_path, catalog_patch=patch)


def test_relation_binding_publishes_both_directions(tmp_path: Path) -> None:
    def catalog_patch(catalog: dict) -> None:
        catalog["relation_bindings"].append(
            {"family_id": "sample_family", "relation_kind": "direct_holding", "observation_rows": 5}
        )

    def semantic_patch(semantic: dict) -> None:
        for semantic_id in ("tst:holds", "tst:heldBy"):
            term = copy.deepcopy(TERM)
            term.update({"semantic_id": semantic_id, "kind": "predicate"})
            semantic["terms"].append(term)

    payload = build(tmp_path, catalog_patch=catalog_patch, semantic_patch=semantic_patch)
    directions = {entry["direction"] for entry in payload["relation_bindings"]}
    assert directions == {"forward", "inverse"}
    assert all(entry["result_dedup"] == "product_grain_distinct"
               for entry in payload["relation_bindings"])


# ------------------------------------------------------- one generation only
def test_a_store_from_another_build_is_refused(tmp_path: Path) -> None:
    """A half-published generation must fail closed, not answer from mixed inputs."""
    catalog = copy.deepcopy(CATALOG)
    catalog["build"]["store_path"] = str(write_store(tmp_path, "ffffffffffffffffffffffffffffffff"))
    with pytest.raises(RegistryMismatch, match="different builds"):
        build_execution_registry(**write_inputs(tmp_path, catalog, copy.deepcopy(SEMANTIC)))


def test_a_store_without_a_build_manifest_row_is_refused(tmp_path: Path) -> None:
    catalog = copy.deepcopy(CATALOG)
    catalog["build"]["store_path"] = str(write_store(tmp_path, None))
    with pytest.raises(RegistryMismatch, match="different builds"):
        build_execution_registry(**write_inputs(tmp_path, catalog, copy.deepcopy(SEMANTIC)))


def test_a_catalog_without_a_build_id_is_refused(tmp_path: Path) -> None:
    catalog = copy.deepcopy(CATALOG)
    catalog["build"].pop("build_id")
    catalog["build"]["store_path"] = str(write_store(tmp_path, BUILD_ID))
    with pytest.raises(RegistryMismatch, match="records no build id"):
        build_execution_registry(**write_inputs(tmp_path, catalog, copy.deepcopy(SEMANTIC)))


def test_a_missing_store_is_refused(tmp_path: Path) -> None:
    catalog = copy.deepcopy(CATALOG)
    catalog["build"]["store_path"] = str(tmp_path / "not_built.duckdb")
    with pytest.raises(RegistryMismatch, match="store the catalog points at is missing"):
        build_execution_registry(**write_inputs(tmp_path, catalog, copy.deepcopy(SEMANTIC)))


def test_the_published_registry_records_the_build_it_came_from(tmp_path: Path) -> None:
    payload = build(tmp_path)
    assert payload["data_catalog"]["build_id"] == BUILD_ID
