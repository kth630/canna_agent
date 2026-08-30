"""Project a bounded ABox sample out of the query store for SHACL validation.

The store is the system of record; this projection shows that its rows can be
expressed as instances of the submission ontology without inventing relations.

This is a *sample*, not a Knowledge Graph: it takes a few subjects per family and
a few observations per subject, which is enough to prove shape conformance.  A
full KG load would extend this same seam and is not part of the current scope.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD

ROOT = Path(__file__).resolve().parents[3]
STORE_PATH = ROOT / "data" / "processed" / "query_store.duckdb"
OUTPUT_PATH = ROOT / "data" / "processed" / "abox_sample.ttl"

CNN = Namespace("https://canna.local/ontology/core#")
INST = Namespace("https://canna.local/instance/")
FAMILY_CLASS = {
    "domestic_bond": "https://canna.local/ontology/bond-kr#KoreanBond",
    "domestic_etp": "https://canna.local/ontology/etf-kr#DomesticExchangeTradedProduct",
    "overseas_etp": "https://canna.local/ontology/etf-gl#GlobalExchangeTradedProduct",
    "public_fund": "https://canna.local/ontology/fund-pub#PublicFundShareClass",
}


def _node(*parts: str) -> URIRef:
    from urllib.parse import quote

    return URIRef(INST + "/".join(quote(str(part), safe="") for part in parts))


def project(
    store_path: Path | None = None,
    output: Path | None = None,
    subjects_per_family: int = 8,
    observations_per_subject: int = 6,
) -> tuple[Graph, dict[str, int]]:
    connection = duckdb.connect(str(store_path or STORE_PATH), read_only=True)
    graph = Graph()
    graph.bind("cnn", CNN)
    graph.bind("inst", INST)
    counts = {"subjects": 0, "identifiers": 0, "metric_observations": 0,
              "attribute_observations": 0, "holdings": 0, "securities": 0,
              "portfolios": 0, "mappings": 0, "failures": 0, "sources": 0}
    try:
        for row in connection.execute(
            "SELECT source_id, sha256, source_precedence FROM data_source"
        ).fetchall():
            node = _node("source", row[0])
            graph.add((node, RDF.type, CNN.DataSource))
            graph.add((node, CNN.sourceDigest, Literal(row[1])))
            graph.add((node, CNN.sourcePrecedence, Literal(int(row[2]), datatype=XSD.integer)))
            counts["sources"] += 1

        sample_keys: list[str] = []
        for family, class_iri in FAMILY_CLASS.items():
            table, key = (
                ("product_class", "product_class_key")
                if family == "public_fund"
                else ("product", "product_key")
            )
            rows = connection.execute(
                f"SELECT {key}, family_id, product_name FROM {table} "
                "WHERE family_id = ? ORDER BY 1 LIMIT ?",
                [family, subjects_per_family],
            ).fetchall()
            for subject_key, family_id, name in rows:
                node = _node("subject", subject_key)
                graph.add((node, RDF.type, URIRef(class_iri)))
                graph.add((node, CNN.subjectKey, Literal(subject_key)))
                graph.add((node, CNN.familyOfSubject, Literal(family_id)))
                if name:
                    graph.add((node, CNN.labelValue, Literal(name)))
                sample_keys.append(subject_key)
                counts["subjects"] += 1

        placeholders = ", ".join("?" for _ in sample_keys)
        for subject_key, scheme_id, value, status in connection.execute(
            f"SELECT subject_key, scheme_id, identifier_value, verification_status FROM identifier "
            f"WHERE subject_key IN ({placeholders})",
            sample_keys,
        ).fetchall():
            node = _node("identifier", subject_key, scheme_id, value)
            graph.add((node, RDF.type, CNN.Identifier))
            graph.add((node, CNN.identifierValue, Literal(value)))
            graph.add((node, CNN.resolutionStatus, Literal(status)))
            graph.add((node, CNN.identifierScheme, URIRef(_scheme_iri(scheme_id))))
            graph.add((_node("subject", subject_key), CNN.hasIdentifier, node))
            counts["identifiers"] += 1

        for table, type_node, kind in (
            ("metric_observation", CNN.MetricObservation, "metric"),
            ("attribute_observation", CNN.AttributeObservation, "attribute"),
        ):
            id_column = "metric_id" if kind == "metric" else "attribute_id"
            rows = connection.execute(
                f"""
                SELECT {id_column} || '@' || source_row_id, subject_key, {id_column},
                       value_status, as_of_status,
                       source_id, source_row_id,
                       {'numeric_value' if kind == 'metric' else 'code_value'},
                       {'NULL' if kind == 'metric' else 'label_value'},
                       {'NULL' if kind == 'metric' else 'date_value'},
                       effective_as_of
                FROM (SELECT *, row_number() OVER (PARTITION BY subject_key ORDER BY {id_column})
                             AS position
                      FROM {table} WHERE subject_key IN ({placeholders}))
                WHERE position <= ?
                """,
                [*sample_keys, observations_per_subject],
            ).fetchall()
            for row in rows:
                node = _node(kind, row[0])
                graph.add((node, RDF.type, type_node))
                graph.add((node, CNN.observedSubject, _node("subject", row[1])))
                predicate = CNN.metricType if kind == "metric" else CNN.attributeType
                graph.add((node, predicate, URIRef(_scheme_iri(row[2]))))
                graph.add((node, CNN.valueStatus, Literal(row[3])))
                graph.add((node, CNN.asOfStatus, Literal(row[4])))
                graph.add((node, CNN.fromSource, _node("source", row[5])))
                graph.add((node, CNN.sourceRowId, Literal(row[6])))
                if kind == "metric" and row[7] is not None:
                    graph.add((node, CNN.numericValue, Literal(float(row[7]), datatype=XSD.double)))
                if kind == "attribute":
                    if row[7] is not None:
                        graph.add((node, CNN.codeValue, Literal(row[7])))
                    if row[8] is not None:
                        graph.add((node, CNN.labelValue, Literal(row[8])))
                    if row[9] is not None:
                        graph.add((node, CNN.dateValue, Literal(str(row[9]), datatype=XSD.date)))
                if row[10] is not None:
                    graph.add((node, CNN.effectiveAsOf, Literal(str(row[10]), datatype=XSD.date)))
                counts[f"{kind}_observations"] += 1

        mappings = connection.execute(
            f"SELECT map_id, subject_key, portfolio_key, mapping_status, mapping_basis "
            f"FROM product_portfolio_map WHERE subject_key IN ({placeholders})",
            sample_keys,
        ).fetchall()
        portfolio_keys: list[str] = []
        for map_id, subject_key, portfolio_key, status, basis in mappings:
            node = _node("mapping", map_id)
            graph.add((node, RDF.type, CNN.ProductPortfolioMapping))
            graph.add((node, CNN.mappedSubject, _node("subject", subject_key)))
            graph.add((node, CNN.mappingStatusValue, Literal(status)))
            if basis:
                graph.add((node, CNN.mappingBasis, Literal(basis)))
            if portfolio_key:
                graph.add((node, CNN.mappedPortfolio, _node("portfolio", portfolio_key)))
                graph.add(
                    (_node("subject", subject_key), CNN.mapsToPortfolio,
                     _node("portfolio", portfolio_key))
                )
                portfolio_keys.append(portfolio_key)
            counts["mappings"] += 1

        for portfolio_key in sorted(set(portfolio_keys)):
            row = connection.execute(
                "SELECT portfolio_key, portfolio_id_raw FROM portfolio WHERE portfolio_key = ?",
                [portfolio_key],
            ).fetchone()
            node = _node("portfolio", row[0])
            graph.add((node, RDF.type, CNN.Portfolio))
            graph.add((node, CNN.subjectKey, Literal(row[0])))
            graph.add((node, CNN.identifierValue, Literal(row[1])))
            counts["portfolios"] += 1

        if portfolio_keys:
            holding_placeholders = ", ".join("?" for _ in set(portfolio_keys))
            holdings = connection.execute(
                f"""
                SELECT holding_key, portfolio_key, security_key, relation_kind, as_of_status,
                       held_security_id_raw, security_name_raw, source_record_id, quantity_value,
                       weight_value, effective_as_of, requested_as_of, snapshot_scope
                FROM (SELECT *, row_number() OVER (PARTITION BY portfolio_key ORDER BY holding_key)
                             AS position
                      FROM holding_observation
                      WHERE portfolio_key IN ({holding_placeholders}))
                WHERE position <= ?
                """,
                [*sorted(set(portfolio_keys)), observations_per_subject],
            ).fetchall()
            securities: list[str] = []
            for row in holdings:
                node = _node("holding", row[0])
                graph.add((node, RDF.type, CNN.HoldingObservation))
                graph.add((node, CNN.portfolioOfObservation, _node("portfolio", row[1])))
                graph.add((node, CNN.relationKind, Literal(row[3])))
                graph.add((node, CNN.asOfStatus, Literal(row[4])))
                graph.add((node, CNN.sourceRecordId, Literal(row[7])))
                if row[2]:
                    graph.add((node, CNN.heldSecurity, _node("security", row[2])))
                    securities.append(row[2])
                if row[5]:
                    graph.add((node, CNN.heldSecurityIdentifierRaw, Literal(row[5])))
                if row[6]:
                    graph.add((node, CNN.heldSecurityNameRaw, Literal(row[6])))
                if row[8] is not None:
                    graph.add((node, CNN.quantityValue, Literal(float(row[8]), datatype=XSD.double)))
                if row[9] is not None:
                    graph.add((node, CNN.weightValue, Literal(float(row[9]), datatype=XSD.double)))
                if row[10] is not None:
                    graph.add((node, CNN.effectiveAsOf, Literal(str(row[10]), datatype=XSD.date)))
                if row[11] is not None:
                    graph.add((node, CNN.requestedAsOf, Literal(str(row[11]), datatype=XSD.date)))
                if row[12]:
                    graph.add((node, CNN.snapshotScope, Literal(row[12])))
                counts["holdings"] += 1

            for security_key in sorted(set(securities)):
                row = connection.execute(
                    "SELECT security_key, scheme_id, identifier_value, resolution_status, "
                    "security_name FROM security WHERE security_key = ?",
                    [security_key],
                ).fetchone()
                node = _node("security", row[0])
                graph.add((node, RDF.type, CNN.Security))
                graph.add((node, CNN.identifierValue, Literal(row[2])))
                graph.add((node, CNN.identifierScheme, URIRef(_scheme_iri(row[1]))))
                graph.add((node, CNN.resolutionStatus, Literal(row[3])))
                if row[4]:
                    graph.add((node, CNN.labelValue, Literal(row[4])))
                counts["securities"] += 1

        for row in connection.execute(
            "SELECT failure_id, family_id, error_code, source_id FROM collection_failure LIMIT ?",
            [subjects_per_family],
        ).fetchall():
            node = _node("failure", row[0])
            graph.add((node, RDF.type, CNN.CollectionFailure))
            graph.add((node, CNN.codeValue, Literal(row[2])))
            graph.add((node, CNN.fromSource, _node("source", row[3])))
            counts["failures"] += 1
    finally:
        connection.close()

    target = output or OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=target, format="turtle")
    return graph, counts


def _scheme_iri(semantic_id: str) -> str:
    prefix, name = semantic_id.split(":", 1)
    base = {
        "cnn": "https://canna.local/ontology/core#",
        "bdkr": "https://canna.local/ontology/bond-kr#",
        "etkr": "https://canna.local/ontology/etf-kr#",
        "etgl": "https://canna.local/ontology/etf-gl#",
        "fdpb": "https://canna.local/ontology/fund-pub#",
    }[prefix]
    return base + name
