"""Build the reproducible query store and its Data Catalog.

Inputs are immutable: the read-only official workbooks, the read-only holdings
bundle, the 0-D provenance inventory that records their verified hashes, and the
authored Data Catalog under ``catalog/``.

No product name, date, row count or coverage number is written in this module.
Every table, column and count below is derived from those inputs, and anything
the sources do not prove — an unverified identifier scheme, an unknown snapshot
scope, a failed collection — is preserved as an explicit state instead of being
turned into 0, false or an absent row without a record.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from canna.store import sources
from canna.store.catalog import Catalog, CatalogError, FieldBinding, load_catalog
from canna.store.emit import CoverageMixin
from canna.store.holdings import HoldingsMixin
from canna.store.publish import build_lock, discard, publish_generation, temp_path
from canna.store.schema import DERIVED_TABLES
from canna.store.types import normalized_date_expression, physical_type

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "data" / "processed"
STORE_PATH = OUT_DIR / "query_store.duckdb"
CATALOG_PATH = OUT_DIR / "data_catalog.json"

ORDINAL = "__source_ordinal"
OFFICIAL_PRECEDENCE = 1


def _phase(message: str, started: float) -> float:
    """Phase timings go to stderr so a long rebuild stays observable."""
    now = time.monotonic()
    print(f"[build] {message}: {now - started:.1f}s", file=sys.stderr, flush=True)
    return now


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _trimmed(column: str) -> str:
    return f'nullif(trim("{column}"), \'\')'


class StoreBuilder(HoldingsMixin, CoverageMixin):
    def __init__(self, connection: duckdb.DuckDBPyConnection, catalog: Catalog) -> None:
        self.connection = connection
        self.catalog = catalog
        self.source_tables: dict[str, dict[str, object]] = {}
        self.notes: list[str] = []
        self.hash_mismatches: list[str] = []

    # ------------------------------------------------------------------ setup
    def create_schema(self) -> None:
        for ddl in DERIVED_TABLES.values():
            self.connection.execute(ddl)

    def register_source(
        self,
        source_id: str,
        kind: str,
        name: str,
        file_name: str,
        digest: str,
        recorded: str,
        precedence: int,
        collected_at: str,
        note: str,
    ) -> None:
        matches = digest == recorded
        if not matches:
            self.hash_mismatches.append(file_name)
        self.connection.execute(
            "INSERT INTO data_source VALUES (?,?,?,?,?,?,?,?,?,?)",
            [source_id, kind, name, file_name, digest, recorded, matches, precedence,
             collected_at, note],
        )

    # ---------------------------------------------------------- source mirror
    def load_official_table(self, source: sources.OfficialSource, staging: Path) -> None:
        data_path = sources.OFFICIAL_DIR / source.data_file
        schema_path = sources.OFFICIAL_DIR / source.schema_file
        self.register_source(
            source_id=source.table_id,
            kind="official",
            name=source.table_id,
            file_name=source.data_file,
            digest=sources.sha256(data_path),
            recorded=source.data_sha256,
            precedence=OFFICIAL_PRECEDENCE,
            collected_at="",
            note=source.source_row_grain,
        )
        self.register_source(
            source_id=f"{source.table_id}_schema",
            kind="official_schema",
            name=f"{source.table_id} schema",
            file_name=source.schema_file,
            digest=sources.sha256(schema_path),
            recorded=source.schema_sha256,
            precedence=OFFICIAL_PRECEDENCE,
            collected_at="",
            note="",
        )

        order, schema = sources.read_schema(schema_path)
        csv_path = staging / f"{source.table_id.lower()}.csv"
        row_count = sources.write_staging_csv(data_path, order, csv_path, ordinal_column=ORDINAL)
        if row_count != source.data_rows:
            raise ValueError(
                f"{source.table_id}: read {row_count} rows, provenance recorded {source.data_rows}"
            )

        table = f"src_{source.table_id.lower()}"
        staged = f"stg_{table}"
        self.connection.execute(
            f"CREATE TABLE {staged} AS "
            "SELECT * FROM read_csv(?, all_varchar = true, header = true)",
            [str(csv_path)],
        )
        projections = [
            f"{_quote(source.table_id)} || '#' || \"{ORDINAL}\" AS source_row_id",
            f'"{ORDINAL}"::BIGINT AS source_ordinal',
        ]
        column_types: dict[str, tuple[str, str, int | None]] = {}
        for name in order:
            duck_type, kind, scale = physical_type(schema[name]["data_type"])
            column_types[name] = (duck_type, kind, scale)
            projections.append(f'TRY_CAST("{name}" AS {duck_type}) AS "{name}"')
        self.connection.execute(
            f"CREATE TABLE {table} AS SELECT {', '.join(projections)} FROM {staged}"
        )
        observations = self._observe_columns(staged, table, order, column_types)
        self.connection.execute(f"DROP TABLE {staged}")

        self.source_tables[source.table_id] = {
            "physical_table": table,
            "row_count": row_count,
            "column_order": order,
            "schema": schema,
            "types": column_types,
            "observations": observations,
            "source_row_grain": source.source_row_grain,
            "identifier_candidates": source.identifier_candidates,
            "as_of_note": source.as_of_note,
        }

    def _observe_columns(
        self,
        staged: str,
        typed: str,
        order: list[str],
        column_types: dict[str, tuple[str, str, int | None]],
    ) -> dict[str, dict[str, object]]:
        """One scan over staged text and one over the typed table, not one per field."""
        terms: list[str] = []
        keys: list[str] = []
        for name in order:
            duck_type, _, _ = column_types[name]
            nonblank = f'"{name}" IS NOT NULL AND trim("{name}") <> \'\''
            terms.append(f"count(*) FILTER (WHERE {nonblank})")
            terms.append(
                f'count(*) FILTER (WHERE {nonblank} AND TRY_CAST("{name}" AS {duck_type}) IS NULL)'
            )
            terms.append(f'count(*) FILTER (WHERE "{name}" <> trim("{name}"))')
            keys.extend([f"nonblank::{name}", f"castfail::{name}", f"padded::{name}"])
        text_stats = dict(
            zip(keys, self.connection.execute(f"SELECT {', '.join(terms)} FROM {staged}").fetchone())
        )

        zero_stats: dict[str, int] = {}
        numeric = [name for name in order if column_types[name][1] != "label_or_code"]
        if numeric:
            terms = [f'count(*) FILTER (WHERE "{name}" = 0)' for name in numeric]
            zero_stats.update(
                zip(
                    numeric,
                    self.connection.execute(f"SELECT {', '.join(terms)} FROM {typed}").fetchone(),
                )
            )
        textual = [name for name in order if column_types[name][1] == "label_or_code"]
        if textual:
            # Zero counts for text columns come from the staged text, not from a cast.
            terms = [f"count(*) FILTER (WHERE trim(\"{name}\") = '0')" for name in textual]
            zero_stats.update(
                zip(
                    textual,
                    self.connection.execute(f"SELECT {', '.join(terms)} FROM {staged}").fetchone(),
                )
            )

        observations: dict[str, dict[str, object]] = {}
        for name in order:
            nonblank = int(text_stats[f"nonblank::{name}"])
            cast_failures = int(text_stats[f"castfail::{name}"])
            padded = int(text_stats[f"padded::{name}"])
            zeros = int(zero_stats.get(name) or 0)
            observations[name] = {
                "nonblank_rows": nonblank,
                "zero_like_rows": zeros,
                "usable_measure_rows": max(nonblank - zeros - cast_failures, 0),
                "cast_failures": cast_failures,
                "text_padding_observed": padded > 0,
            }
        return observations

    # -------------------------------------------------------------- entities
    def build_entities(self) -> None:
        for family in self.catalog.families:
            info = self.source_tables[family.official_table_id]
            table = info["physical_table"]
            bindings = self.catalog.bindings_for(family.official_table_id)
            by_role: dict[str, list[FieldBinding]] = defaultdict(list)
            for binding in bindings:
                by_role[binding.role].append(binding)

            keys = by_role["identity_key"]
            if len(keys) != 1 or keys[0].field != family.official_key_field:
                raise CatalogError(
                    f"{family.family_id}: exactly one identity key must match the declared key field"
                )
            key_field = keys[0].field
            names = {b.semantic_id: b for b in by_role["identity_attribute"]}
            name_col = self._identity_column(names, "cnn:ProductName")
            short_col = self._identity_column(names, "cnn:ProductShortName")
            subject_expr = f"{_quote(family.family_id)} || ':' || {_trimmed(key_field)}"

            if family.result_grain == "product":
                self.connection.execute(
                    f"""
                    INSERT INTO product
                    SELECT {subject_expr},
                           {_quote(family.family_id)},
                           {_quote(family.official_table_id)},
                           {_quote(key_field)},
                           {_trimmed(key_field)},
                           arg_min({name_col}, source_ordinal),
                           arg_min({short_col}, source_ordinal),
                           count(*),
                           count(DISTINCT {name_col}),
                           {_quote(family.official_table_id)}
                    FROM {table}
                    WHERE {_trimmed(key_field)} IS NOT NULL
                    GROUP BY {_trimmed(key_field)}
                    """
                )
            else:
                class_display = self._identity_column(
                    {b.semantic_id: b for b in by_role["attribute"]},
                    "fdpb:ShareClassDisplayName",
                )
                group_bindings = by_role["class_group"]
                group_field = group_bindings[0].field if group_bindings else None
                group_value = _trimmed(group_field) if group_field else "NULL"
                group_status = (
                    self._identifier_status_expression("official_identifier", group_value)
                    if group_field
                    else _quote("absent")
                )
                group_key = (
                    f"CASE WHEN {group_status} = 'declared_by_source' "
                    f"THEN 'grp:' || {_quote(family.family_id)} || ':' || {group_value} END"
                )
                self.connection.execute(
                    f"""
                    INSERT INTO product_class
                    SELECT {subject_expr},
                           {_quote(family.family_id)},
                           {_quote(family.official_table_id)},
                           {_quote(key_field)},
                           {_trimmed(key_field)},
                           arg_min({class_display}, source_ordinal),
                           arg_min({name_col}, source_ordinal),
                           arg_min({group_key}, source_ordinal),
                           arg_min({group_value}, source_ordinal),
                           arg_min({group_status}, source_ordinal),
                           count(*),
                           {_quote(family.official_table_id)}
                    FROM {table}
                    WHERE {_trimmed(key_field)} IS NOT NULL
                    GROUP BY {_trimmed(key_field)}
                    """
                )
                if group_bindings:
                    self.connection.execute(
                        f"""
                        INSERT INTO product_class_group
                        SELECT class_group_key,
                               family_id,
                               {_quote(group_bindings[0].semantic_id)},
                               class_group_value,
                               count(*),
                               {_quote(family.official_table_id)}
                        FROM product_class
                        WHERE class_group_key IS NOT NULL AND family_id = {_quote(family.family_id)}
                        GROUP BY class_group_key, family_id, class_group_value
                        """
                    )

        self.connection.execute(
            """
            INSERT INTO subject
            SELECT product_key, 'product', family_id, product_name, source_id FROM product
            UNION ALL
            SELECT product_class_key, 'product_class', family_id, product_name, source_id
            FROM product_class
            """
        )

    @staticmethod
    def _identity_column(bindings: dict[str, FieldBinding], semantic_id: str) -> str:
        binding = bindings.get(semantic_id)
        return _trimmed(binding.field) if binding else "NULL"

    def _identifier_status_expression(self, scope: str, value_expr: str) -> str:
        """Build a CASE from the catalog rules so status policy stays in the catalog."""
        branches = []
        fallback = _quote("unclassified")
        for rule in self.catalog.identifier_rules:
            if rule.scope != scope:
                continue
            if rule.pattern == ".*":
                fallback = _quote(rule.resolution_status)
                continue
            branches.append(
                f"WHEN regexp_matches({value_expr}, {_quote(rule.pattern)}) "
                f"THEN {_quote(rule.resolution_status)}"
            )
        if not branches:
            return f"CASE WHEN {value_expr} IS NULL THEN 'absent' ELSE {fallback} END"
        joined = " ".join(branches)
        return f"CASE WHEN {value_expr} IS NULL THEN 'absent' {joined} ELSE {fallback} END"

    def build_identifiers(self) -> None:
        for family in self.catalog.families:
            info = self.source_tables[family.official_table_id]
            table = info["physical_table"]
            subject_expr = (
                f"{_quote(family.family_id)} || ':' || {_trimmed(family.official_key_field)}"
            )
            roles = ("identity_key", "identifier", "class_group")
            for binding in self.catalog.bindings_for(family.official_table_id):
                if binding.role not in roles:
                    continue
                value = _trimmed(binding.field)
                status = self._identifier_status_expression("official_identifier", value)
                self.connection.execute(
                    f"""
                    INSERT INTO identifier
                    SELECT {subject_expr}, {_quote(binding.semantic_id)}, {value}, {status},
                           {_quote(family.official_table_id)}, source_row_id
                    FROM {table}
                    WHERE {value} IS NOT NULL AND {_trimmed(family.official_key_field)} IS NOT NULL
                    """
                )

    # ---------------------------------------------------------- observations
    def build_observations(self) -> None:
        for family in self.catalog.families:
            info = self.source_tables[family.official_table_id]
            table = info["physical_table"]
            types = info["types"]
            key_field = family.official_key_field
            subject_expr = f"{_quote(family.family_id)} || ':' || {_trimmed(key_field)}"
            source_id = _quote(family.official_table_id)
            declared_as_of = {
                binding.field
                for binding in self.catalog.bindings_for(family.official_table_id)
                if binding.role == "as_of"
            }

            groups: dict[str, list[FieldBinding]] = defaultdict(list)
            for binding in self.catalog.bindings_for(family.official_table_id):
                if binding.role in {"metric", "attribute", "identity_attribute",
                                    "observation_context"}:
                    groups[binding.semantic_id].append(binding)

            for semantic_id, members in groups.items():
                kinds = {member.role for member in members}
                if "metric" in kinds and len(kinds) > 1:
                    raise CatalogError(f"{semantic_id}: metric and attribute roles cannot mix")
                declared_grains = {member.subject_grain for member in members}
                if len(declared_grains) > 1:
                    raise CatalogError(f"{semantic_id}: one table binds it at several grains")
                observation_grain = declared_grains.pop()
                as_of_field = members[0].as_of_field
                if as_of_field and as_of_field not in declared_as_of:
                    raise CatalogError(
                        f"{semantic_id}: as-of field {as_of_field!r} is not declared as as_of"
                    )
                as_of_expr = (
                    normalized_date_expression(f'"{as_of_field}"') if as_of_field else "NULL"
                )
                as_of_status = (
                    f"CASE WHEN {as_of_expr} IS NOT NULL THEN 'effective_declared' "
                    "ELSE 'unknown' END"
                    if as_of_field
                    else _quote("not_declared")
                )
                if "metric" in kinds:
                    self._insert_metric(
                        table, semantic_id, members[0], types, subject_expr, observation_grain,
                        family.family_id, source_id, as_of_expr, as_of_status, key_field,
                    )
                else:
                    self._insert_attribute(
                        table, semantic_id, members, subject_expr, observation_grain,
                        family.family_id, source_id, as_of_expr, as_of_status, key_field,
                    )

    def _insert_metric(
        self,
        table: str,
        semantic_id: str,
        binding: FieldBinding,
        types: dict[str, tuple[str, str, int | None]],
        subject_expr: str,
        grain: str,
        family_id: str,
        source_id: str,
        as_of_expr: str,
        as_of_status: str,
        key_field: str,
    ) -> None:
        _, kind, _ = types[binding.field]
        column = f'"{binding.field}"'
        if kind == "label_or_code":
            value_expr = f"TRY_CAST(trim({column}) AS DOUBLE)"
            raw_expr = _trimmed(binding.field)
            present = f"{_trimmed(binding.field)} IS NOT NULL"
        else:
            value_expr = f"{column}::DOUBLE"
            raw_expr = "NULL"
            present = f"{column} IS NOT NULL"
        status = (
            f"CASE WHEN {value_expr} IS NULL THEN 'parse_failed' "
            f"WHEN {value_expr} = 0 THEN 'zero_excluded' ELSE 'valid' END"
        )
        currency = (
            _trimmed(binding.currency_field) if binding.currency_field else "NULL"
        )
        period = _quote(binding.period_code) if binding.period_code != "none" else "NULL"
        unit = _quote(binding.unit_code) if binding.unit_code != "none" else "NULL"
        self.connection.execute(
            f"""
            INSERT INTO metric_observation
            SELECT {subject_expr}, {_quote(grain)}, {_quote(family_id)}, {_quote(semantic_id)},
                   {value_expr}, {raw_expr}, {unit}, {currency}, {period},
                   {as_of_expr}, {as_of_status}, {status}, {source_id}, source_row_id
            FROM {table}
            WHERE {present} AND {_trimmed(key_field)} IS NOT NULL
            """
        )

    def _insert_attribute(
        self,
        table: str,
        semantic_id: str,
        members: list[FieldBinding],
        subject_expr: str,
        grain: str,
        family_id: str,
        source_id: str,
        as_of_expr: str,
        as_of_status: str,
        key_field: str,
    ) -> None:
        slots: dict[str, str] = {}
        for member in members:
            slot = member.value_slot
            if slot in slots:
                raise CatalogError(f"{semantic_id}: slot {slot!r} bound twice in one table")
            slots[slot] = member.field
        code = _trimmed(slots["code"]) if "code" in slots else "NULL"
        date_field = slots.get("date")
        date_value = normalized_date_expression(f'"{date_field}"') if date_field else "NULL"
        # The raw text is kept alongside the parsed value, so a date that does not
        # parse is still visible instead of disappearing.
        label_field = (
            slots.get("label") or slots.get("key") or slots.get("text") or slots.get("date")
        )
        if label_field:
            label = _trimmed(label_field)
        elif "value" in slots:
            label = f'CAST("{slots["value"]}" AS VARCHAR)'
        else:
            label = "NULL"
        present_parts = [f"{expr} IS NOT NULL" for expr in (code, label, date_value)
                         if expr != "NULL"]
        present = " OR ".join(present_parts) if present_parts else "FALSE"
        if date_field:
            status = (
                f"CASE WHEN {_trimmed(date_field)} IS NOT NULL AND {date_value} IS NULL "
                "THEN 'date_parse_failed' ELSE 'valid' END"
            )
        else:
            status = _quote("valid")
        self.connection.execute(
            f"""
            INSERT INTO attribute_observation
            SELECT {subject_expr}, {_quote(grain)}, {_quote(family_id)}, {_quote(semantic_id)},
                   {code}, {label}, {date_value},
                   {as_of_expr}, {as_of_status}, {status}, {source_id}, source_row_id
            FROM {table}
            WHERE ({present}) AND {_trimmed(key_field)} IS NOT NULL
            """
        )


def build(store_path: Path | None = None, catalog_path: Path | None = None) -> dict[str, object]:
    """Rebuild the store from the immutable sources and return a build summary."""
    catalog = load_catalog()
    official = sources.official_sources()
    declared_tables = {family.official_table_id for family in catalog.families}
    recorded_tables = {source.table_id for source in official}
    if declared_tables != recorded_tables:
        raise CatalogError(
            f"catalog families {sorted(declared_tables)} do not match recorded official "
            f"sources {sorted(recorded_tables)}"
        )

    target = store_path or STORE_PATH
    destination = catalog_path or CATALOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Build beside the real outputs and publish only after every check passed, so a
    # failed rebuild leaves the previous store and catalog exactly as they were.
    # The store and the catalog carry the same build id and are published as one
    # generation, so a reader never sees a new store beside an older catalog.
    with build_lock(target):
        token = str(os.getpid())
        build_id = uuid.uuid4().hex
        staging_store = temp_path(target, token)
        staging_catalog = temp_path(destination, token)
        discard(staging_store)
        discard(staging_catalog)
        try:
            catalog_payload = _build_into(
                staging_store, target, destination, catalog, official, build_id
            )
            catalog_payload["build"]["store_sha256"] = sources.sha256(staging_store)
            staging_catalog.write_text(
                json.dumps(catalog_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            publish_generation(
                [(staging_store, target), (staging_catalog, destination)], token
            )
        except BaseException:
            discard(staging_store)
            discard(staging_catalog)
            raise
    return summarize(catalog_payload)


def _build_into(
    staging_store: Path,
    target: Path,
    destination: Path,
    catalog: Catalog,
    official: list[sources.OfficialSource],
    build_id: str,
) -> dict[str, object]:
    """Fill one temporary store and return its verified Data Catalog payload."""
    connection = duckdb.connect(str(staging_store))
    clock = time.monotonic()
    try:
        builder = StoreBuilder(connection, catalog)
        builder.create_schema()
        with tempfile.TemporaryDirectory() as staging_dir:
            staging = Path(staging_dir)
            for source in official:
                builder.load_official_table(source, staging)
                clock = _phase(f"loaded {source.table_id}", clock)
            builder.build_entities()
            builder.build_identifiers()
            clock = _phase("built products, classes and identifiers", clock)
            builder.build_observations()
            clock = _phase("built metric and attribute observations", clock)
            builder.load_holdings(staging)
            clock = _phase("loaded the holdings bundle", clock)
            builder.build_portfolios_and_mappings()
            clock = _phase("built portfolios and mappings", clock)
            builder.build_securities_and_holdings()
            clock = _phase("built securities and holding observations", clock)
            builder.build_coverage_and_failures()
            builder.build_conflicts()
            builder.build_semantic_coverage()
            clock = _phase("built coverage, failures and conflicts", clock)

        store_path = (
            str(target.relative_to(ROOT)).replace("\\", "/")
            if target.is_relative_to(ROOT)
            else str(target)
        )
        catalog_path = (
            str(destination.relative_to(ROOT)).replace("\\", "/")
            if destination.is_relative_to(ROOT)
            else str(destination)
        )
        # The same build id lands in the store and in the catalog, so a reader can
        # refuse a pair that does not come from one build.
        connection.execute(
            "INSERT INTO build_manifest VALUES (?, ?, ?, ?)",
            [build_id, datetime.now(UTC).isoformat(), store_path, catalog_path],
        )
        metadata = {
            "build_id": build_id,
            "catalog_dir": catalog.paths.get("catalog_dir"),
            "hash_mismatches": builder.hash_mismatches,
            "official_tables": sorted(source.table_id for source in official),
            "store_path": store_path,
            "catalog_path": catalog_path,
        }
        catalog_payload = builder.data_catalog(metadata)
        _phase("verified grains and emitted the data catalog", clock)
        # Fold the write-ahead log into the file so the published artefact is one file.
        connection.execute("CHECKPOINT")
        return catalog_payload
    finally:
        connection.close()


def summarize(catalog_payload: dict[str, object]) -> dict[str, object]:
    tables = {table["table"]: table["row_count"] for table in catalog_payload["tables"]}
    bindings = catalog_payload["semantic_bindings"]
    kinds: dict[str, int] = {}
    for binding in bindings:
        kinds[str(binding["binding_kind"])] = kinds.get(str(binding["binding_kind"]), 0) + 1
    return {
        "status": "ok" if not catalog_payload["build"]["hash_mismatches"] else "hash_mismatch",
        "hash_mismatches": catalog_payload["build"]["hash_mismatches"],
        "grain_row_counts": {
            name: tables.get(name, 0)
            for name in (
                "product",
                "product_class",
                "product_class_group",
                "portfolio",
                "security",
                "metric_observation",
                "attribute_observation",
                "holding_observation",
                "product_portfolio_map",
                "collection_failure",
                "source_conflict",
            )
        },
        "source_row_counts": {
            name: count for name, count in sorted(tables.items()) if name.startswith("src_")
        },
        "binding_kinds": kinds,
        "distinct_semantic_ids": len({b["semantic_id"] for b in bindings if b["semantic_id"]}),
    }
