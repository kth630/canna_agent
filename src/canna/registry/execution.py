"""Execution Registry generated from the Data Catalog and checked against the Semantic Registry.

The Data Catalog owns physical tables, columns, joins and observed coverage.
The Semantic Registry owns meaning, grain, unit, period, allowed operations and
Evidence requirements.  This module joins the two by stable semantic id and
refuses to emit a registry when the two sides disagree, so a build that would
let a query run under the wrong meaning fails instead.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data" / "processed"
CATALOG_PATH = DATA_DIR / "data_catalog.json"
SEMANTIC_PATH = DATA_DIR / "semantic_registry.json"
OUTPUT_PATH = DATA_DIR / "execution_registry.json"
RELATION_BINDINGS = ROOT / "catalog" / "relation_bindings.csv"

KIND_EXPECTATION = {
    "metric": {"metric"},
    "attribute": {"attribute"},
    "identity_key": {"identifier_scheme"},
    "identifier": {"identifier_scheme"},
    "class_group": {"identifier_scheme"},
}
# A semantic operation is executable only if the physical type role offers one
# of its concrete operations.
OPERATION_SUPPORT = {
    "filter": {"eq", "ne", "in", "lt", "lte", "gt", "gte", "contains"},
    "order": {"order"},
    "aggregate": {"avg", "sum", "min", "max"},
    "count": {"count"},
    "group": {"group"},
    "compare": {"lt", "gt", "eq"},
}


class RegistryMismatch(ValueError):
    """Semantic and physical sides disagree; the registry must not be published."""


def _assert_one_generation(catalog: dict[str, object]) -> str:
    """Refuse a catalog that does not belong to the store it points at.

    The build publishes the store and the catalog together, but a crash between
    the two moves could still leave a mismatched pair behind.  Reading the build
    id from both sides turns that into a refusal instead of a wrong answer.
    """
    build = catalog.get("build") or {}
    build_id = str(build.get("build_id") or "")
    if not build_id:
        raise RegistryMismatch(
            "the data catalog records no build id; rebuild the store before generating registries"
        )
    declared = str(build.get("store_path") or "")
    if not declared:
        raise RegistryMismatch("the data catalog records no store path")
    store = Path(declared)
    if not store.is_absolute():
        store = ROOT / store
    if not store.is_file():
        raise RegistryMismatch(f"the store the catalog points at is missing: {store}")
    connection = duckdb.connect(str(store), read_only=True)
    try:
        rows = connection.execute(
            "SELECT build_id FROM build_manifest ORDER BY generated_at DESC"
        ).fetchall()
    except duckdb.Error as error:
        raise RegistryMismatch(f"{store.name} carries no build manifest: {error}") from error
    finally:
        connection.close()
    recorded = [str(row[0]) for row in rows]
    if recorded != [build_id]:
        raise RegistryMismatch(
            f"store build id {recorded} does not match catalog build id {build_id!r}; "
            "the store and the catalog come from different builds"
        )
    return build_id


@dataclass(frozen=True)
class RelationBinding:
    relation_kind: str
    forward_semantic_id: str
    inverse_semantic_id: str
    result_dedup: str
    join_path_ids: str
    note: str


def _load_relation_bindings(path: Path | None = None) -> dict[str, RelationBinding]:
    target = path or RELATION_BINDINGS
    with target.open(encoding="utf-8-sig", newline="") as handle:
        rows = [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]
    return {row["relation_kind"]: RelationBinding(**row) for row in rows}


def _terms_by_id(semantic: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(term["semantic_id"]): term for term in semantic["terms"]}


def _check_binding(
    binding: dict[str, object], term: dict[str, object] | None
) -> tuple[list[str], list[str]]:
    """Return (mismatches, executable_operations) for one catalog binding."""
    semantic_id = str(binding["semantic_id"])
    kind = str(binding["binding_kind"])
    if term is None:
        return ([f"{semantic_id}: not declared in the ontology"], [])

    problems: list[str] = []
    expected = KIND_EXPECTATION.get(kind)
    if expected and term["kind"] not in expected:
        problems.append(
            f"{semantic_id}: catalog binds it as {kind} but the ontology declares {term['kind']}"
        )
    families = list(term.get("families") or [])
    if families and binding["family_id"] not in families:
        problems.append(
            f"{semantic_id}: bound for {binding['family_id']} but declared for {families}"
        )

    executable: list[str] = []
    if kind in {"metric", "attribute"}:
        grains = list(term.get("grains") or [])
        if str(binding["subject_grain"]) not in grains:
            problems.append(
                f"{semantic_id}: grain {binding['subject_grain']} does not match "
                f"ontology grains {grains}"
            )
        if str(term.get("unit_code") or "") != str(binding["unit_code"]):
            problems.append(
                f"{semantic_id}: unit {binding['unit_code']} does not match "
                f"ontology unit {term.get('unit_code')!r}"
            )
        period = str(binding["period_code"]) or "none"
        if str(term.get("period_code") or "none") != period and kind == "metric":
            problems.append(
                f"{semantic_id}: period {period} does not match "
                f"ontology period {term.get('period_code')!r}"
            )
        physical_operations = set(binding.get("allowed_operations") or [])
        for operation in term.get("allowed_operations") or []:
            support = OPERATION_SUPPORT.get(str(operation))
            if support is None:
                continue
            if support & physical_operations:
                executable.append(str(operation))
            else:
                problems.append(
                    f"{semantic_id}: ontology allows {operation} but the physical column role "
                    f"{binding['physical']['type_role']} does not support it"
                )
        currency_policy = str(term.get("currency_policy") or "")
        currency_source = str(binding.get("currency_source") or "none")
        if currency_policy and currency_source == "none":
            problems.append(
                f"{semantic_id}: ontology requires a currency ({currency_policy}) "
                "but the catalog binds none"
            )
        if not currency_policy and currency_source != "none":
            problems.append(
                f"{semantic_id}: catalog binds a currency source without an ontology policy"
            )
    return problems, sorted(set(executable))


def build_execution_registry(
    catalog_path: Path | None = None,
    semantic_path: Path | None = None,
    relation_path: Path | None = None,
) -> dict[str, object]:
    catalog = json.loads((catalog_path or CATALOG_PATH).read_text(encoding="utf-8"))
    build_id = _assert_one_generation(catalog)
    semantic = json.loads((semantic_path or SEMANTIC_PATH).read_text(encoding="utf-8"))
    relations = _load_relation_bindings(relation_path)
    terms = _terms_by_id(semantic)

    mismatches: list[str] = []
    bindings: list[dict[str, object]] = []
    unbound: list[dict[str, object]] = []

    for binding in catalog["semantic_bindings"]:
        if not binding.get("semantic_id"):
            unbound.append(
                {
                    "family_id": binding["family_id"],
                    "source_table": binding["physical"]["source_table"],
                    "source_column": binding["physical"]["source_column"],
                    "reason": binding.get("note") or "",
                    "alignment_decision": binding.get("alignment_decision"),
                }
            )
            continue
        term = terms.get(str(binding["semantic_id"]))
        problems, executable = _check_binding(binding, term)
        mismatches.extend(problems)
        if problems or term is None:
            continue
        bindings.append(
            {
                "semantic_id": binding["semantic_id"],
                "binding_kind": binding["binding_kind"],
                "family_id": binding["family_id"],
                "subject_grain": binding["subject_grain"],
                "meaning": {
                    "labels": term["labels"],
                    "aliases": term["aliases"],
                    "definition": term["definition"],
                    "comparison_group": term["comparison_group"],
                    "meaning_status": term["meaning_status"],
                    "alignment_decision": term["alignment_decision"],
                    "evidence_requirements": term["evidence_requirements"],
                },
                "physical": binding["physical"],
                "observation_table": binding.get("observation_table"),
                "selector_column": binding.get("selector_column"),
                "selector_value": binding["semantic_id"],
                "value_column": binding.get("value_column"),
                "unit_code": binding["unit_code"],
                "currency_source": binding["currency_source"],
                "period_code": binding["period_code"],
                "as_of_field": binding["as_of_field"],
                "semantic_operations": term["allowed_operations"],
                "executable_operations": executable,
                "physical_operations": binding["allowed_operations"],
                "zero_semantics": binding["zero_semantics"],
                "observed_coverage": binding.get("observed_coverage"),
                "source_observations": binding.get("source_observations"),
            }
        )

    relation_entries: list[dict[str, object]] = []
    join_paths = {path["join_id"]: path for path in catalog["join_paths"]}
    for observed in catalog["relation_bindings"]:
        kind = str(observed["relation_kind"])
        declared = relations.get(kind)
        if declared is None:
            mismatches.append(f"relation kind {kind!r} observed in data but not declared")
            continue
        if not declared.forward_semantic_id:
            relation_entries.append(
                {
                    "relation_kind": kind,
                    "family_id": observed["family_id"],
                    "executable": False,
                    "reason": declared.note,
                    "observed": observed,
                }
            )
            continue
        for semantic_id in (declared.forward_semantic_id, declared.inverse_semantic_id):
            term = terms.get(semantic_id)
            if term is None:
                mismatches.append(f"{semantic_id}: relation predicate not declared in the ontology")
                continue
            missing = [
                join_id
                for join_id in declared.join_path_ids.split("|")
                if join_id and join_id not in join_paths
            ]
            if missing:
                mismatches.append(f"{semantic_id}: unknown join path ids {missing}")
                continue
            relation_entries.append(
                {
                    "relation_kind": kind,
                    "semantic_id": semantic_id,
                    "direction": "forward"
                    if semantic_id == declared.forward_semantic_id
                    else "inverse",
                    "family_id": observed["family_id"],
                    "executable": True,
                    "result_dedup": declared.result_dedup,
                    "join_paths": [
                        join_paths[join_id] for join_id in declared.join_path_ids.split("|")
                    ],
                    "evidence_requirements": term["evidence_requirements"],
                    "meaning": {"labels": term["labels"], "aliases": term["aliases"]},
                    "observed": observed,
                }
            )

    if mismatches:
        raise RegistryMismatch(
            "semantic and execution registries disagree:\n" + "\n".join(sorted(set(mismatches)))
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "semantic_registry": {
            "generated_at": semantic["generated_at"],
            "ontology_files": semantic["ontology_files"],
            "term_count": semantic["counts"]["total"],
        },
        "data_catalog": {
            "generated_at": catalog["generated_at"],
            "build_id": build_id,
            "store_sha256": catalog["build"].get("store_sha256"),
            "store_path": catalog["build"]["store_path"],
            "hash_mismatches": catalog["build"]["hash_mismatches"],
            "sources": catalog["sources"],
        },
        "grain_verification": catalog["grain_verification"],
        "join_paths": catalog["join_paths"],
        "bindings": bindings,
        "relation_bindings": relation_entries,
        "holdings_coverage": catalog["holdings_coverage"],
        "conflicts": catalog["conflicts"],
        "unbound_source_fields": unbound,
        "counts": {
            "bindings": len(bindings),
            "distinct_semantic_ids": len({b["semantic_id"] for b in bindings}),
            "relation_bindings": len(relation_entries),
            "unbound_source_fields": len(unbound),
        },
    }


def write_execution_registry(output: Path | None = None, **kwargs) -> dict[str, object]:
    payload = build_execution_registry(**kwargs)
    target = output or OUTPUT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
