"""Data Catalog inputs.

The catalog is the authored bridge between semantic ids and physical source
fields.  It is data, not code: aliases, field lists, predicates and joins stay
out of Python so the registries remain the single owner of each concern.

Loading validates structure only.  Whether a semantic id actually exists is
decided later, when the Execution Registry is checked against the Semantic
Registry generated from the ontology.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CATALOG_DIR = ROOT / "catalog"

FIELD_ROLES = {
    "identity_key",
    "identity_attribute",
    "identifier",
    "class_group",
    "metric",
    "attribute",
    "as_of",
    "observation_context",
    "unbound",
}
VALUE_SLOTS = {"key", "value", "code", "label", "date", "text"}
ALIGNMENT_DECISIONS = {"유지", "수정", "제외", "추가", "미확정"}
SUBJECT_GRAINS = {"product", "product_class", "source_row", "portfolio", "security"}
RESULT_GRAINS = {"product", "product_class"}


class CatalogError(ValueError):
    """A catalog input that the build must not silently work around."""


@dataclass(frozen=True)
class FieldBinding:
    table_id: str
    field: str
    semantic_id: str
    role: str
    value_slot: str
    subject_grain: str
    unit_code: str
    currency_source: str
    period_code: str
    as_of_field: str
    alignment_decision: str
    conflict_group: str
    note: str

    @property
    def currency_field(self) -> str | None:
        if self.currency_source.startswith("field:"):
            return self.currency_source.split(":", 1)[1]
        return None


@dataclass(frozen=True)
class ProductFamily:
    family_id: str
    label_ko: str
    official_table_id: str
    holdings_family: str
    result_grain: str
    official_key_field: str
    holdings_join_field: str
    portfolio_id_scheme: str
    namespace_prefix: str
    collection_scope_note: str
    holdings_as_of_role: str
    holdings_as_of_evidence: str


@dataclass(frozen=True)
class HoldingsBinding:
    normalized_table: str
    field: str
    semantic_id: str
    role: str
    target_table: str
    target_column: str
    note: str


@dataclass(frozen=True)
class RelationRule:
    product_family: str
    source_pattern: str
    relation_kind: str
    parent_group_index: str
    evidence: str
    compiled: re.Pattern[str]

    def match(self, source_text: str) -> tuple[str, str | None] | None:
        found = self.compiled.search(source_text or "")
        if found is None:
            return None
        parent = found.group(int(self.parent_group_index)) if self.parent_group_index else None
        return self.relation_kind, parent


@dataclass(frozen=True)
class IdentifierRule:
    scope: str
    pattern: str
    scheme_id: str
    resolution_status: str
    promote_to_security: bool
    checksum: str
    evidence: str
    compiled: re.Pattern[str]


@dataclass(frozen=True)
class ConflictGroup:
    conflict_group: str
    left_source_kind: str
    right_source_kind: str
    policy: str
    note: str


@dataclass(frozen=True)
class Catalog:
    field_bindings: tuple[FieldBinding, ...]
    families: tuple[ProductFamily, ...]
    holdings_bindings: tuple[HoldingsBinding, ...]
    relation_rules: tuple[RelationRule, ...]
    identifier_rules: tuple[IdentifierRule, ...]
    conflict_groups: tuple[ConflictGroup, ...]
    paths: dict[str, str] = field(default_factory=dict)

    def family_by_table(self, table_id: str) -> ProductFamily:
        for family in self.families:
            if family.official_table_id == table_id:
                return family
        raise CatalogError(f"no product family declares official table {table_id}")

    def family_by_holdings(self, holdings_family: str) -> ProductFamily | None:
        for family in self.families:
            if family.holdings_family and family.holdings_family == holdings_family:
                return family
        return None

    def bindings_for(self, table_id: str) -> list[FieldBinding]:
        return [binding for binding in self.field_bindings if binding.table_id == table_id]

    def semantic_ids(self) -> set[str]:
        ids = {b.semantic_id for b in self.field_bindings if b.semantic_id}
        ids |= {b.semantic_id for b in self.holdings_bindings if b.semantic_id}
        ids |= {rule.scheme_id for rule in self.identifier_rules if rule.scheme_id}
        return ids

    def relation_rules_for(self, family_id: str) -> list[RelationRule]:
        return [rule for rule in self.relation_rules if rule.product_family == family_id]


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise CatalogError(f"missing catalog input: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]
    if not rows:
        raise CatalogError(f"empty catalog input: {path}")
    return rows


def load_catalog(directory: Path | None = None) -> Catalog:
    base = directory or CATALOG_DIR

    families: list[ProductFamily] = []
    for row in _rows(base / "product_families.csv"):
        if row["result_grain"] not in RESULT_GRAINS:
            raise CatalogError(f"{row['family_id']}: unknown result grain {row['result_grain']!r}")
        families.append(ProductFamily(**row))
    family_ids = {family.family_id for family in families}
    table_ids = {family.official_table_id for family in families}
    if len(family_ids) != len(families) or len(table_ids) != len(families):
        raise CatalogError("product family ids and official table ids must both be unique")

    bindings: list[FieldBinding] = []
    seen: set[tuple[str, str]] = set()
    for row in _rows(base / "official_field_bindings.csv"):
        binding = FieldBinding(**row)
        if binding.table_id not in table_ids:
            raise CatalogError(f"{binding.field}: unknown official table {binding.table_id}")
        if binding.role not in FIELD_ROLES:
            raise CatalogError(f"{binding.field}: unknown role {binding.role!r}")
        if binding.value_slot not in VALUE_SLOTS:
            raise CatalogError(f"{binding.field}: unknown value slot {binding.value_slot!r}")
        if binding.subject_grain not in SUBJECT_GRAINS:
            raise CatalogError(f"{binding.field}: unknown subject grain {binding.subject_grain!r}")
        if binding.alignment_decision not in ALIGNMENT_DECISIONS:
            raise CatalogError(f"{binding.field}: unknown 0-D decision {binding.alignment_decision!r}")
        needs_id = binding.role not in {"as_of", "unbound"}
        if needs_id and not binding.semantic_id:
            raise CatalogError(f"{binding.field}: role {binding.role} requires a semantic id")
        if not needs_id and binding.semantic_id:
            raise CatalogError(f"{binding.field}: role {binding.role} must not claim a semantic id")
        key = (binding.table_id, binding.field)
        if key in seen:
            raise CatalogError(f"duplicate binding for {key}")
        seen.add(key)
        bindings.append(binding)

    holdings: list[HoldingsBinding] = []
    for row in _rows(base / "holdings_bindings.csv"):
        holdings.append(HoldingsBinding(**row))

    relation_rules: list[RelationRule] = []
    for row in _rows(base / "holdings_relation_rules.csv"):
        if row["product_family"] not in family_ids:
            raise CatalogError(f"relation rule for unknown family {row['product_family']!r}")
        relation_rules.append(RelationRule(**row, compiled=re.compile(row["source_pattern"])))

    identifier_rules: list[IdentifierRule] = []
    for row in _rows(base / "identifier_rules.csv"):
        promote = row.pop("promote_to_security").lower() == "true"
        identifier_rules.append(
            IdentifierRule(**row, promote_to_security=promote, compiled=re.compile(row["pattern"]))
        )

    conflicts = [ConflictGroup(**row) for row in _rows(base / "conflict_groups.csv")]
    declared_groups = {group.conflict_group for group in conflicts}
    for binding in bindings:
        if binding.conflict_group and binding.conflict_group not in declared_groups:
            raise CatalogError(
                f"{binding.field}: conflict group {binding.conflict_group!r} is not declared"
            )

    return Catalog(
        field_bindings=tuple(bindings),
        families=tuple(families),
        holdings_bindings=tuple(holdings),
        relation_rules=tuple(relation_rules),
        identifier_rules=tuple(identifier_rules),
        conflict_groups=tuple(conflicts),
        paths={
            "catalog_dir": str(base.relative_to(ROOT)).replace("\\", "/")
            if base.is_relative_to(ROOT)
            else str(base)
        },
    )


def classify_identifier(rules: tuple[IdentifierRule, ...], scope: str, value: str) -> IdentifierRule | None:
    """First matching rule wins, so rule order in the catalog is the policy."""
    for rule in rules:
        if rule.scope != scope:
            continue
        if rule.compiled.search(value or ""):
            return rule
    return None
