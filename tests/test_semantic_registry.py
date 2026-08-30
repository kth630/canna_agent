"""The Semantic Registry must be a faithful, physical-free projection of the ontology."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from canna.registry.semantic import RegistryError, build_registry

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "ontology"

MINIMAL_CORE = """
@prefix cnn: <https://canna.local/ontology/core#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
cnn:semanticGrain a owl:AnnotationProperty .
cnn:unitKind a owl:AnnotationProperty .
cnn:observationPeriod a owl:AnnotationProperty .
cnn:allowedOperation a owl:AnnotationProperty .
cnn:comparisonGroup a owl:AnnotationProperty .
cnn:approvedAlias a owl:AnnotationProperty .
cnn:statusCode a owl:AnnotationProperty .
cnn:unitCode a owl:AnnotationProperty .
cnn:periodCode a owl:AnnotationProperty .
cnn:operationCode a owl:AnnotationProperty .
cnn:MetricType a owl:Class .
cnn:ProductGrain a cnn:SemanticGrain ; cnn:statusCode "product" .
cnn:PercentObserved a cnn:Unit ; cnn:unitCode "percent_observed" .
cnn:Period1Y a cnn:Period ; cnn:periodCode "P1Y" .
cnn:OrderOperation a cnn:Operation ; cnn:operationCode "order" .
"""

COMPLETE_METRIC = """
cnn:SampleReturn a cnn:MetricType ;
    rdfs:label "표본 수익률"@ko ;
    cnn:approvedAlias "표본 성과"@ko ;
    cnn:semanticGrain cnn:ProductGrain ;
    cnn:unitKind cnn:PercentObserved ;
    cnn:observationPeriod cnn:Period1Y ;
    cnn:allowedOperation cnn:OrderOperation ;
    cnn:comparisonGroup "sample:return" .
"""

METRIC_WITHOUT_UNIT = """
cnn:SampleReturn a cnn:MetricType ;
    rdfs:label "표본 수익률"@ko ;
    cnn:semanticGrain cnn:ProductGrain ;
    cnn:observationPeriod cnn:Period1Y ;
    cnn:allowedOperation cnn:OrderOperation ;
    cnn:comparisonGroup "sample:return" .
"""


def write_ontology(directory: Path, body: str) -> Path:
    (directory / "core.ttl").write_text(MINIMAL_CORE + body, encoding="utf-8")
    return directory


def test_submission_ontology_produces_a_registry() -> None:
    payload = build_registry(ONTOLOGY)
    assert payload["counts"]["metric"] > 0
    assert payload["counts"]["attribute"] > 0
    assert payload["counts"]["identifier_scheme"] > 0
    assert payload["counts"]["predicate"] > 0
    assert len(payload["ontology_files"]) == 5, "five submission ontologies are expected"


def test_registry_carries_meaning_not_physical_binding() -> None:
    payload = build_registry(ONTOLOGY)
    text = json.dumps(payload, ensure_ascii=False)
    for physical in ("src_pref01n001", "du_er_1y", "SELECT ", "duckdb"):
        assert physical not in text, f"the semantic registry leaked physical binding: {physical}"


def test_every_metric_term_is_retrievable_by_rule_and_by_embedding_text() -> None:
    payload = build_registry(ONTOLOGY)
    for term in payload["terms"]:
        if term["kind"] != "metric":
            continue
        assert term["labels"], f"{term['semantic_id']} has no label for rule-based retrieval"
        assert term["search_text"].strip(), f"{term['semantic_id']} has no embedding text"
        assert term["comparison_group"], term["semantic_id"]


def test_period_neighbours_stay_distinguishable() -> None:
    """Adjacent periods must not collapse into one meaning."""
    payload = build_registry(ONTOLOGY)
    by_id = {term["semantic_id"]: term for term in payload["terms"]}
    periods = {
        term_id: term["period_code"]
        for term_id, term in by_id.items()
        if term["kind"] == "metric" and term["comparison_group"] == "domestic_etp:return"
    }
    assert len(set(periods.values())) == len(periods), "return metrics share a period code"


def test_incomplete_metric_declaration_fails_the_build(tmp_path: Path) -> None:
    write_ontology(tmp_path, METRIC_WITHOUT_UNIT)
    with pytest.raises(RegistryError):
        build_registry(tmp_path)


def test_complete_minimal_metric_declaration_passes(tmp_path: Path) -> None:
    write_ontology(tmp_path, COMPLETE_METRIC)
    payload = build_registry(tmp_path)
    term = next(t for t in payload["terms"] if t["semantic_id"] == "cnn:SampleReturn")
    assert term["unit_code"] == "percent_observed"
    assert term["period_code"] == "P1Y"
    assert term["allowed_operations"] == ["order"]
    assert "표본 성과" in term["search_text"]
