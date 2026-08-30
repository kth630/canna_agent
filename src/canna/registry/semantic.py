"""Semantic Registry generated from the submission ontology and its SHACL shapes.

The registry is a projection of the TTL files: stable semantic id, meaning,
labels, approved aliases, domain/range, grain, period/unit/currency, allowed
operations and Evidence requirements.  Physical tables, columns and runtime
coverage are deliberately absent — those belong to the Data Catalog and the
Execution Registry, which join to this registry by semantic id.

Rule-based exact retrieval and embedding retrieval both read this file, so the
same approved vocabulary backs either path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from rdflib import RDF, RDFS, Graph, URIRef
from rdflib.namespace import OWL, SH

ROOT = Path(__file__).resolve().parents[3]
ONTOLOGY_DIR = ROOT / "ontology"
OUTPUT_PATH = ROOT / "data" / "processed" / "semantic_registry.json"
CORE = "https://canna.local/ontology/core#"

TERM_KINDS = {
    f"{CORE}MetricType": "metric",
    f"{CORE}AttributeType": "attribute",
    f"{CORE}IdentifierScheme": "identifier_scheme",
}
STRUCTURAL_KINDS = {
    str(OWL.Class): "class",
    str(OWL.ObjectProperty): "predicate",
    str(OWL.DatatypeProperty): "data_property",
    str(SH.NodeShape): "shape",
}
FORBIDDEN_KEYS = ("table", "column", "sql", "coverage_count", "row_count")


class RegistryError(ValueError):
    """The ontology does not carry what the registry contract requires."""


@dataclass
class SemanticTerm:
    semantic_id: str
    iri: str
    kind: str
    labels: dict[str, str] = field(default_factory=dict)
    definition: str = ""
    aliases: list[str] = field(default_factory=list)
    families: list[str] = field(default_factory=list)
    grains: list[str] = field(default_factory=list)
    period_code: str = ""
    unit_code: str = ""
    currency_policy: str = ""
    allowed_operations: list[str] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    comparison_group: str = ""
    meaning_status: str = ""
    alignment_decision: str = ""
    domain: list[str] = field(default_factory=list)
    range: list[str] = field(default_factory=list)
    inverse_of: str = ""
    subclass_of: list[str] = field(default_factory=list)
    shapes: list[str] = field(default_factory=list)
    search_text: str = ""


def _recorded_path(path: Path) -> str:
    """Repository-relative when the file lives here, absolute otherwise."""
    if path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT)).replace("\\", "/")
    return str(path)


def _load_graph(directory: Path) -> tuple[Graph, list[dict[str, object]]]:
    graph = Graph()
    files: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.ttl")):
        before = len(graph)
        graph.parse(path, format="turtle")
        files.append(
            {
                "path": _recorded_path(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "triples": len(graph) - before,
            }
        )
    if not files:
        raise RegistryError(f"no ontology files found in {directory}")
    return graph, files


def _curie(graph: Graph, node: URIRef) -> str:
    prefix, _, name = graph.namespace_manager.compute_qname(str(node), generate=False)
    return f"{prefix}:{name}"


def _annotation_codes(graph: Graph, subject: URIRef, predicate: URIRef, code: URIRef) -> list[str]:
    codes: list[str] = []
    for value in graph.objects(subject, predicate):
        if isinstance(value, URIRef):
            resolved = list(graph.objects(value, code))
            codes.extend(str(item) for item in resolved)
        else:
            codes.append(str(value))
    return sorted(set(codes))


def build_registry(directory: Path | None = None) -> dict[str, object]:
    graph, files = _load_graph(directory or ONTOLOGY_DIR)
    core = {name: URIRef(CORE + name) for name in (
        "semanticGrain", "appliesToFamily", "observationPeriod", "unitKind", "currencyPolicy",
        "allowedOperation", "approvedAlias", "evidenceRequirement", "comparisonGroup",
        "meaningStatus", "alignmentDecision", "familyId", "periodCode", "unitCode",
        "operationCode", "statusCode",
    )}

    terms: dict[str, SemanticTerm] = {}
    for type_iri, kind in list(TERM_KINDS.items()) + list(STRUCTURAL_KINDS.items()):
        for subject in graph.subjects(RDF.type, URIRef(type_iri)):
            if not isinstance(subject, URIRef):
                continue
            semantic_id = _curie(graph, subject)
            existing = terms.get(semantic_id)
            if existing is not None:
                if existing.kind != kind and kind in TERM_KINDS.values():
                    existing.kind = kind
                continue
            labels = {
                (literal.language or "und"): str(literal)
                for literal in graph.objects(subject, RDFS.label)
            }
            comments = [str(literal) for literal in graph.objects(subject, RDFS.comment)]
            aliases = sorted({str(literal) for literal in graph.objects(subject, core["approvedAlias"])})
            term = SemanticTerm(
                semantic_id=semantic_id,
                iri=str(subject),
                kind=kind,
                labels=labels,
                definition=" ".join(comments),
                aliases=aliases,
                families=_annotation_codes(graph, subject, core["appliesToFamily"], core["familyId"]),
                grains=_annotation_codes(graph, subject, core["semanticGrain"], core["statusCode"]),
                period_code=next(
                    iter(
                        _annotation_codes(graph, subject, core["observationPeriod"], core["periodCode"])
                    ),
                    "",
                ),
                unit_code=next(
                    iter(_annotation_codes(graph, subject, core["unitKind"], core["unitCode"])), ""
                ),
                currency_policy=next(
                    (str(value) for value in graph.objects(subject, core["currencyPolicy"])), ""
                ),
                allowed_operations=_annotation_codes(
                    graph, subject, core["allowedOperation"], core["operationCode"]
                ),
                evidence_requirements=_annotation_codes(
                    graph, subject, core["evidenceRequirement"], core["statusCode"]
                ),
                comparison_group=next(
                    (str(value) for value in graph.objects(subject, core["comparisonGroup"])), ""
                ),
                meaning_status=next(
                    (str(value) for value in graph.objects(subject, core["meaningStatus"])), ""
                ),
                alignment_decision=next(
                    (str(value) for value in graph.objects(subject, core["alignmentDecision"])), ""
                ),
                domain=[
                    _curie(graph, value)
                    for value in graph.objects(subject, RDFS.domain)
                    if isinstance(value, URIRef)
                ],
                range=[
                    _curie(graph, value)
                    for value in graph.objects(subject, RDFS.range)
                    if isinstance(value, URIRef)
                ],
                inverse_of=next(
                    (
                        _curie(graph, value)
                        for value in graph.objects(subject, OWL.inverseOf)
                        if isinstance(value, URIRef)
                    ),
                    "",
                ),
                subclass_of=[
                    _curie(graph, value)
                    for value in graph.objects(subject, RDFS.subClassOf)
                    if isinstance(value, URIRef)
                ],
            )
            searchable = [term.labels.get(language, "") for language in sorted(term.labels)]
            searchable.extend(term.aliases)
            if term.definition:
                searchable.append(term.definition)
            term.search_text = " ".join(part for part in searchable if part)
            terms[semantic_id] = term

    for shape in graph.subjects(RDF.type, SH.NodeShape):
        for target in graph.objects(shape, SH.targetClass):
            if isinstance(target, URIRef):
                target_id = _curie(graph, target)
                if target_id in terms:
                    terms[target_id].shapes.append(_curie(graph, shape))
    for term in terms.values():
        term.shapes = sorted(set(term.shapes))

    _validate(terms)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "ontology",
        "ontology_files": files,
        "prefixes": {
            prefix: str(namespace)
            for prefix, namespace in graph.namespace_manager.namespaces()
            if str(namespace).startswith("https://canna.local/ontology/")
        },
        "counts": _counts(terms),
        "terms": [asdict(term) for term in sorted(terms.values(), key=lambda t: t.semantic_id)],
    }
    _assert_no_physical_binding(payload)
    return payload


def _counts(terms: dict[str, SemanticTerm]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for term in terms.values():
        counts[term.kind] = counts.get(term.kind, 0) + 1
    counts["total"] = len(terms)
    return counts


def _validate(terms: dict[str, SemanticTerm]) -> None:
    problems: list[str] = []
    for term in terms.values():
        if term.kind in {"metric", "attribute"}:
            if not term.labels:
                problems.append(f"{term.semantic_id}: no label")
            if not term.grains:
                problems.append(f"{term.semantic_id}: no semantic grain")
            if not term.unit_code:
                problems.append(f"{term.semantic_id}: no unit kind")
        if term.kind == "metric":
            if not term.period_code:
                problems.append(f"{term.semantic_id}: no observation period")
            if not term.comparison_group:
                problems.append(f"{term.semantic_id}: no comparison group")
            if not term.allowed_operations:
                problems.append(f"{term.semantic_id}: no allowed operation")
        if term.kind == "predicate" and not term.labels:
            problems.append(f"{term.semantic_id}: predicate without label")
    if problems:
        raise RegistryError("ontology is missing registry contract data:\n" + "\n".join(problems))


def _assert_no_physical_binding(payload: dict[str, object]) -> None:
    text = json.dumps(payload, ensure_ascii=False).lower()
    for key in FORBIDDEN_KEYS:
        marker = f'"{key}"'
        if marker in text:
            raise RegistryError(
                f"semantic registry must not carry physical binding data: found {marker}"
            )


def write_registry(output: Path | None = None, directory: Path | None = None) -> dict[str, object]:
    payload = build_registry(directory)
    target = output or OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_registry(path: Path | None = None) -> dict[str, object]:
    return json.loads((path or OUTPUT_PATH).read_text(encoding="utf-8"))
