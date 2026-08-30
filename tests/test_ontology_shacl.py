"""The five submission ontologies must parse and their SHACL shapes must bite.

The shapes are checked twice: against synthetic instances that encode the grain
decisions we care about, and against a bounded ABox projected out of the real
store.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pyshacl import validate
from rdflib import Graph

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "ontology"
STORE = ROOT / "data" / "processed" / "query_store.duckdb"

PREFIXES = """
@prefix cnn: <https://canna.local/ontology/core#> .
@prefix etkr: <https://canna.local/ontology/etf-kr#> .
@prefix inst: <https://canna.local/instance/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""

VALID_ABOX = PREFIXES + """
inst:source1 a cnn:DataSource ; cnn:sourceDigest "abc" ; cnn:sourcePrecedence 1 .
inst:scheme1 a cnn:IdentifierScheme .
inst:id1 a cnn:Identifier ; cnn:identifierValue "X1" ; cnn:identifierScheme inst:scheme1 ;
    cnn:resolutionStatus "declared_by_source" .
inst:p1 a etkr:DomesticExchangeTradedProduct ; cnn:subjectKey "domestic_etp:X1" ;
    cnn:familyOfSubject "domestic_etp" ; cnn:hasIdentifier inst:id1 .
inst:pf1 a cnn:Portfolio ; cnn:subjectKey "pf:domestic_etp:X1" ; cnn:identifierValue "X1" .
inst:sec1 a cnn:Security ; cnn:identifierValue "KR7005930003" ;
    cnn:identifierScheme inst:scheme1 ; cnn:resolutionStatus "checksum_verified" .
inst:h1 a cnn:HoldingObservation ; cnn:portfolioOfObservation inst:pf1 ;
    cnn:relationKind "direct_holding" ; cnn:asOfStatus "requested_only" ;
    cnn:sourceRecordId "rec-1" ; cnn:heldSecurity inst:sec1 ;
    cnn:heldSecurityIdentifierRaw "005930" .
inst:h2 a cnn:HoldingObservation ; cnn:portfolioOfObservation inst:pf1 ;
    cnn:relationKind "look_through_exposure" ; cnn:asOfStatus "effective_reported" ;
    cnn:sourceRecordId "rec-2" ; cnn:heldSecurityNameRaw "이름만 있는 보유 종목" .
inst:m1 a cnn:MetricObservation ; cnn:observedSubject inst:p1 ; cnn:metricType etkr:Return1Y ;
    cnn:valueStatus "valid" ; cnn:asOfStatus "effective_declared" ;
    cnn:numericValue "1.5"^^xsd:double ; cnn:fromSource inst:source1 ;
    cnn:sourceRowId "PREF01N001#1" .
inst:a1 a cnn:AttributeObservation ; cnn:observedSubject inst:p1 ;
    cnn:attributeType cnn:ProductName ; cnn:valueStatus "valid" ;
    cnn:fromSource inst:source1 ; cnn:labelValue "표본 상품" ; cnn:sourceRowId "PREF01N001#1" .
"""

VIOLATIONS = {
    "security_without_resolution": PREFIXES + """
inst:scheme1 a cnn:IdentifierScheme .
inst:sec2 a cnn:Security ; cnn:identifierValue "ZZZ" ; cnn:identifierScheme inst:scheme1 ;
    cnn:resolutionStatus "unverified_scheme" .
""",
    "holding_without_portfolio": PREFIXES + """
inst:h3 a cnn:HoldingObservation ; cnn:relationKind "direct_holding" ;
    cnn:asOfStatus "unknown" ; cnn:sourceRecordId "rec-3" ;
    cnn:heldSecurityNameRaw "이름" .
""",
    "holding_with_two_securities": PREFIXES + """
inst:scheme1 a cnn:IdentifierScheme .
inst:pf2 a cnn:Portfolio ; cnn:subjectKey "pf:x" ; cnn:identifierValue "x" .
inst:secA a cnn:Security ; cnn:identifierValue "A" ; cnn:identifierScheme inst:scheme1 ;
    cnn:resolutionStatus "format_matched" .
inst:secB a cnn:Security ; cnn:identifierValue "B" ; cnn:identifierScheme inst:scheme1 ;
    cnn:resolutionStatus "format_matched" .
inst:h4 a cnn:HoldingObservation ; cnn:portfolioOfObservation inst:pf2 ;
    cnn:relationKind "direct_holding" ; cnn:asOfStatus "unknown" ; cnn:sourceRecordId "rec-4" ;
    cnn:heldSecurityIdentifierRaw "A" ; cnn:heldSecurity inst:secA , inst:secB .
""",
    "metric_without_value_status": PREFIXES + """
inst:source1 a cnn:DataSource ; cnn:sourceDigest "abc" ; cnn:sourcePrecedence 1 .
inst:p2 a etkr:DomesticExchangeTradedProduct ; cnn:subjectKey "k" ;
    cnn:familyOfSubject "domestic_etp" .
inst:m2 a cnn:MetricObservation ; cnn:observedSubject inst:p2 ; cnn:metricType etkr:Return1Y ;
    cnn:asOfStatus "effective_declared" ; cnn:fromSource inst:source1 ;
    cnn:sourceRowId "PREF01N001#2" .
""",
    "attribute_without_any_value": PREFIXES + """
inst:source1 a cnn:DataSource ; cnn:sourceDigest "abc" ; cnn:sourcePrecedence 1 .
inst:p3 a etkr:DomesticExchangeTradedProduct ; cnn:subjectKey "k" ;
    cnn:familyOfSubject "domestic_etp" ; cnn:hasIdentifier inst:id3 .
inst:scheme1 a cnn:IdentifierScheme .
inst:id3 a cnn:Identifier ; cnn:identifierValue "K" ; cnn:identifierScheme inst:scheme1 ;
    cnn:resolutionStatus "declared_by_source" .
inst:a2 a cnn:AttributeObservation ; cnn:observedSubject inst:p3 ;
    cnn:attributeType cnn:ProductName ; cnn:valueStatus "valid" ; cnn:fromSource inst:source1 .
""",
    "product_without_identifier": PREFIXES + """
inst:p4 a etkr:DomesticExchangeTradedProduct ; cnn:subjectKey "domestic_etp:Y" ;
    cnn:familyOfSubject "domestic_etp" .
""",
}


def ontology_graph() -> Graph:
    graph = Graph()
    for path in sorted(ONTOLOGY.glob("*.ttl")):
        graph.parse(path, format="turtle")
    return graph


def run_shacl(data: Graph) -> tuple[bool, str]:
    shapes = ontology_graph()
    conforms, _, report = validate(
        data_graph=data,
        shacl_graph=shapes,
        ont_graph=shapes,
        inference="rdfs",
        advanced=True,
    )
    return conforms, report


def test_each_submission_ontology_parses() -> None:
    files = sorted(ONTOLOGY.glob("*.ttl"))
    assert len(files) == 5
    for path in files:
        graph = Graph()
        graph.parse(path, format="turtle")
        assert len(graph) > 0, path


def test_shapes_accept_a_conforming_abox() -> None:
    data = Graph()
    data.parse(data=VALID_ABOX, format="turtle")
    conforms, report = run_shacl(data)
    assert conforms, report


@pytest.mark.parametrize("case", sorted(VIOLATIONS))
def test_shapes_reject_grain_violations(case: str) -> None:
    data = Graph()
    data.parse(data=VIOLATIONS[case], format="turtle")
    conforms, report = run_shacl(data)
    assert not conforms, f"{case} should violate a shape\n{report}"


@pytest.mark.real_data
@pytest.mark.skipif(not STORE.exists(), reason="query store has not been built")
def test_projected_abox_from_the_real_store_conforms(tmp_path: Path) -> None:
    from canna.graph.project import project

    graph, counts = project(output=tmp_path / "abox_sample.ttl")
    assert counts["subjects"] > 0 and counts["metric_observations"] > 0
    assert counts["holdings"] > 0, "the sample must exercise the holdings shapes"
    conforms, report = run_shacl(graph)
    assert conforms, report
