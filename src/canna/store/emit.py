"""Semantic coverage measurement and Data Catalog emission.

Coverage and freshness are dynamic: they are measured from the store that was
just built, never written into the ontology.  The Data Catalog produced here is
the only input the Execution Registry needs from the physical side.
"""

from __future__ import annotations

from datetime import UTC, datetime

from canna.store.schema import GRAIN_SOURCE_ROW, JOIN_PATHS, TABLE_GRAINS
from canna.store.types import (
    allowed_operations,
    binding_type_role,
    physical_type,
    zero_semantics,
)

OBSERVATION_TABLES = (
    ("metric_observation", "metric", "metric_id"),
    ("attribute_observation", "attribute", "attribute_id"),
)


class CoverageMixin:
    """Mixed into the store builder; expects ``connection`` and ``catalog``."""

    def build_semantic_coverage(self) -> None:
        """Measure per-semantic coverage in one pass per observation table.

        The row count is checked against the observed groups, so a coverage row
        can never go missing without failing the build.
        """
        self.connection.execute(
            """
            CREATE OR REPLACE TEMP TABLE subject_total AS
            SELECT family_id, subject_grain, count(*) AS subject_total FROM subject
            WHERE subject_grain IN ('product', 'product_class') GROUP BY 1, 2
            """
        )
        for family in self.catalog.families:
            info = self.source_tables.get(family.official_table_id)
            if info:
                self.connection.execute(
                    "INSERT INTO subject_total VALUES (?, 'source_row', ?)",
                    [family.family_id, int(info["row_count"])],
                )

        for table, kind, id_column in OBSERVATION_TABLES:
            self.connection.execute(
                f"""
                INSERT INTO semantic_coverage
                SELECT o.{id_column} || '|' || o.family_id || '|' || '{kind}',
                       o.{id_column}, '{kind}', o.family_id, o.subject_grain,
                       coalesce(t.subject_total, 0), o.observed_subjects, o.observation_rows,
                       o.valid_subjects, o.zero_excluded_subjects, o.parse_failed_subjects,
                       greatest(coalesce(t.subject_total, 0) - o.observed_subjects, 0),
                       o.max_observations_per_subject, o.effective_as_of_min,
                       o.effective_as_of_max, o.distinct_effective_as_of, o.unknown_as_of_rows
                FROM (
                    SELECT {id_column}, family_id, subject_grain,
                           count(DISTINCT subject_key) AS observed_subjects,
                           count(*) AS observation_rows,
                           count(DISTINCT subject_key) FILTER (
                               WHERE value_status = 'valid') AS valid_subjects,
                           count(DISTINCT subject_key) FILTER (
                               WHERE value_status = 'zero_excluded') AS zero_excluded_subjects,
                           count(DISTINCT subject_key) FILTER (
                               WHERE value_status IN ('parse_failed', 'date_parse_failed')
                           ) AS parse_failed_subjects,
                           max(per_subject) AS max_observations_per_subject,
                           min(effective_as_of) AS effective_as_of_min,
                           max(effective_as_of) AS effective_as_of_max,
                           count(DISTINCT effective_as_of) AS distinct_effective_as_of,
                           count(*) FILTER (
                               WHERE as_of_status <> 'effective_declared') AS unknown_as_of_rows
                    FROM (
                        SELECT *, count(*) OVER (PARTITION BY {id_column}, subject_key)
                               AS per_subject
                        FROM {table}
                    )
                    GROUP BY {id_column}, family_id, subject_grain
                ) o
                LEFT JOIN subject_total t
                  ON t.family_id = o.family_id AND t.subject_grain = o.subject_grain
                """
            )
        self.assert_coverage_complete()

    def assert_coverage_complete(self) -> dict[str, dict[str, int]]:
        """Every observed semantic group must have exactly one coverage row.

        A silently missing coverage row would let an answer claim a universe it
        never measured, so the mismatch fails the build instead of being logged.
        """
        measured: dict[str, dict[str, int]] = {}
        problems: list[str] = []
        for table, kind, id_column in OBSERVATION_TABLES:
            groups = self.connection.execute(
                f"SELECT count(*) FROM (SELECT DISTINCT {id_column}, family_id, subject_grain "
                f"FROM {table})"
            ).fetchone()[0]
            recorded = self.connection.execute(
                "SELECT count(*) FROM semantic_coverage WHERE binding_kind = ?", [kind]
            ).fetchone()[0]
            measured[kind] = {"observed_groups": groups, "coverage_rows": recorded}
            if groups != recorded:
                problems.append(f"{table}: {groups} observed groups but {recorded} coverage rows")
        if problems:
            raise ValueError("semantic coverage is incomplete: " + "; ".join(problems))
        return measured

    # --------------------------------------------------------- grain checks
    GRAIN_KEYS = (
        ("subject", "subject_key", "subject_identity"),
        ("product", "product_key", "product"),
        ("product_class", "product_class_key", "product_class"),
        ("product_class_group", "class_group_key", "product_class_group"),
        ("portfolio", "portfolio_key", "portfolio"),
        ("security", "security_key", "security"),
        ("metric_observation", "metric_id || '@' || source_row_id", "metric_observation"),
        ("attribute_observation", "attribute_id || '@' || source_row_id",
         "attribute_observation"),
        ("holding_observation", "holding_key", "raw_holding_observation"),
        ("product_portfolio_map", "map_id", "product_portfolio_mapping"),
        ("collection_failure", "failure_id", "collection_failure"),
        ("holdings_coverage", "coverage_id", "coverage_observation"),
        ("semantic_coverage", "coverage_key", "coverage_observation"),
        ("source_conflict", "conflict_id", "conflict_record"),
    )
    REFERENCES = (
        ("metric_observation", "subject_key", "subject", "subject_key"),
        ("attribute_observation", "subject_key", "subject", "subject_key"),
        ("holding_observation", "portfolio_key", "portfolio", "portfolio_key"),
        ("holding_observation", "security_key", "security", "security_key"),
        ("product_portfolio_map", "portfolio_key", "portfolio", "portfolio_key"),
        ("product_class", "class_group_key", "product_class_group", "class_group_key"),
    )

    def verify_grains(self) -> dict[str, object]:
        """Uniqueness and referential checks; a violation fails the build."""
        uniqueness: list[dict[str, object]] = []
        violations: list[str] = []
        source_tables = [
            row[0]
            for row in self.connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' "
                "AND table_name LIKE 'src_%' ORDER BY table_name"
            ).fetchall()
        ]
        checks = list(self.GRAIN_KEYS) + [
            (table, "source_row_id", "source_row") for table in source_tables
        ]
        for table, column, grain in checks:
            rows, distinct = self.connection.execute(
                f"SELECT count(*), count(DISTINCT {column}) FROM {table}"
            ).fetchone()
            uniqueness.append(
                {"table": table, "key": column, "grain": grain, "rows": rows, "distinct": distinct}
            )
            if rows != distinct:
                violations.append(f"{table}.{column} has {rows - distinct} duplicate keys")

        references: list[dict[str, object]] = []
        for table, column, parent, parent_column in self.REFERENCES:
            dangling = self.connection.execute(
                f"SELECT count(*) FROM {table} c WHERE c.{column} IS NOT NULL AND NOT EXISTS "
                f"(SELECT 1 FROM {parent} p WHERE p.{parent_column} = c.{column})"
            ).fetchone()[0]
            references.append(
                {
                    "from": f"{table}.{column}",
                    "to": f"{parent}.{parent_column}",
                    "dangling_rows": dangling,
                }
            )
            if dangling:
                violations.append(f"{table}.{column} has {dangling} rows without {parent}")

        if violations:
            raise ValueError("grain verification failed: " + "; ".join(violations))
        return {"uniqueness": uniqueness, "references": references}

    # ------------------------------------------------------------- catalog
    def _table_inventory(self) -> list[dict[str, object]]:
        inventory: list[dict[str, object]] = []
        rows = self.connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' "
            "ORDER BY table_name"
        ).fetchall()
        for (name,) in rows:
            count = self.connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            columns = [
                {"column": column, "type": data_type}
                for column, data_type, *_ in self.connection.execute(
                    f"DESCRIBE {name}"
                ).fetchall()
            ]
            inventory.append(
                {
                    "table": name,
                    "grain": self._declared_grain(name),
                    "row_count": count,
                    "columns": columns,
                }
            )
        return inventory

    @staticmethod
    def _declared_grain(table: str) -> str:
        if table.startswith("src_"):
            return GRAIN_SOURCE_ROW
        return TABLE_GRAINS.get(table, "derived")

    def _observed_join_paths(self) -> list[dict[str, object]]:
        observed: list[dict[str, object]] = []
        for join in JOIN_PATHS:
            measured = self.connection.execute(
                f"""
                SELECT count(*), coalesce(max(children), 0)
                FROM (SELECT l.{join.left_column} AS parent, count(*) AS children
                      FROM {join.left_table} l
                      JOIN {join.right_table} r ON r.{join.right_column} = l.{join.left_column}
                      GROUP BY 1)
                """
            ).fetchone()
            observed.append(
                {
                    "join_id": join.join_id,
                    "left": f"{join.left_table}.{join.left_column}",
                    "right": f"{join.right_table}.{join.right_column}",
                    "declared_cardinality": join.declared_cardinality,
                    "dedup_requirement": join.dedup_requirement,
                    "observed_matched_parents": measured[0],
                    "observed_max_children_per_parent": measured[1],
                    "note": join.note,
                }
            )
        return observed

    def _semantic_bindings(self) -> list[dict[str, object]]:
        coverage = {
            (row[0], row[1], row[2]): row
            for row in self.connection.execute(
                "SELECT semantic_id, family_id, binding_kind, subject_total, observed_subjects, "
                "observation_rows, valid_subjects, zero_excluded_subjects, parse_failed_subjects, "
                "missing_subjects, max_observations_per_subject, effective_as_of_min, "
                "effective_as_of_max, distinct_effective_as_of, unknown_as_of_rows "
                "FROM semantic_coverage"
            ).fetchall()
        }
        bindings: list[dict[str, object]] = []
        for binding in self.catalog.field_bindings:
            family = self.catalog.family_by_table(binding.table_id)
            info = self.source_tables[binding.table_id]
            declared = info["schema"][binding.field]["data_type"]
            duck_type, declared_role, scale = physical_type(declared)
            role_kind = binding_type_role(declared_role, binding.role, binding.value_slot)
            observation = info["observations"][binding.field]
            kind = {
                "metric": "metric",
                "attribute": "attribute",
                "identity_attribute": "attribute",
                "observation_context": "attribute",
            }.get(binding.role, binding.role)
            measured = coverage.get((binding.semantic_id, family.family_id, kind))
            record: dict[str, object] = {
                "semantic_id": binding.semantic_id,
                "binding_kind": kind,
                "family_id": family.family_id,
                "subject_grain": binding.subject_grain,
                "alignment_decision": binding.alignment_decision,
                "physical": {
                    "source_table": info["physical_table"],
                    "source_column": binding.field,
                    "declared_type": declared,
                    "physical_type": duck_type,
                    "decimal_scale": scale,
                    "declared_type_role": declared_role,
                    "type_role": role_kind,
                    "value_slot": binding.value_slot,
                    "comparison_requires_trim": observation["text_padding_observed"],
                },
                "unit_code": binding.unit_code,
                "currency_source": binding.currency_source,
                "period_code": binding.period_code,
                "as_of_field": binding.as_of_field,
                "allowed_operations": allowed_operations(role_kind)
                if binding.role in {"metric", "attribute", "identity_attribute",
                                    "observation_context"}
                else [],
                "zero_semantics": zero_semantics(role_kind),
                "source_observations": observation,
                "note": binding.note,
            }
            if binding.role == "metric":
                record["observation_table"] = "metric_observation"
                record["value_column"] = "numeric_value"
                record["selector_column"] = "metric_id"
            elif kind == "attribute":
                record["observation_table"] = "attribute_observation"
                record["value_column"] = (
                    "code_value" if binding.value_slot == "code" else "label_value"
                )
                record["selector_column"] = "attribute_id"
            elif binding.role in {"identity_key", "identifier", "class_group"}:
                record["observation_table"] = "identifier"
                record["value_column"] = "identifier_value"
                record["selector_column"] = "scheme_id"
            if measured:
                record["observed_coverage"] = {
                    "subject_total": measured[3],
                    "observed_subjects": measured[4],
                    "observation_rows": measured[5],
                    "valid_subjects": measured[6],
                    "zero_excluded_subjects": measured[7],
                    "parse_failed_subjects": measured[8],
                    "missing_subjects": measured[9],
                    "max_observations_per_subject": measured[10],
                    "effective_as_of_min": str(measured[11]) if measured[11] else None,
                    "effective_as_of_max": str(measured[12]) if measured[12] else None,
                    "distinct_effective_as_of": measured[13],
                    "unknown_as_of_rows": measured[14],
                }
            bindings.append(record)
        return bindings

    def _relation_bindings(self) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT family_id, relation_kind, count(*), count(DISTINCT portfolio_key),
                   count(DISTINCT security_key),
                   count(*) FILTER (WHERE security_key IS NULL),
                   min(effective_as_of), max(effective_as_of),
                   count(DISTINCT as_of_status), any_value(snapshot_scope)
            FROM holding_observation GROUP BY 1, 2 ORDER BY 1, 2
            """
        ).fetchall()
        return [
            {
                "family_id": row[0],
                "relation_kind": row[1],
                "observation_rows": row[2],
                "portfolios": row[3],
                "resolved_securities": row[4],
                "rows_without_resolved_security": row[5],
                "effective_as_of_min": str(row[6]) if row[6] else None,
                "effective_as_of_max": str(row[7]) if row[7] else None,
                "distinct_as_of_status": row[8],
                "snapshot_scope_example": row[9],
            }
            for row in rows
        ]

    def data_catalog(self, build_metadata: dict[str, object]) -> dict[str, object]:
        coverage_rows = [
            dict(zip([column[0] for column in self.connection.execute(
                "SELECT * FROM holdings_coverage LIMIT 0").description], row))
            for row in self.connection.execute("SELECT * FROM holdings_coverage").fetchall()
        ]
        sources = [
            dict(zip([column[0] for column in self.connection.execute(
                "SELECT * FROM data_source LIMIT 0").description], row))
            for row in self.connection.execute(
                "SELECT * FROM data_source ORDER BY source_precedence, source_id"
            ).fetchall()
        ]
        conflicts = self.connection.execute(
            "SELECT conflict_group, policy, count(*) FROM source_conflict GROUP BY 1, 2 ORDER BY 1"
        ).fetchall()
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "build": build_metadata,
            "grain_verification": self.verify_grains(),
            "sources": sources,
            "tables": self._table_inventory(),
            "join_paths": self._observed_join_paths(),
            "semantic_bindings": self._semantic_bindings(),
            "relation_bindings": self._relation_bindings(),
            "holdings_coverage": coverage_rows,
            "conflicts": [
                {"conflict_group": row[0], "policy": row[1], "record_count": row[2]}
                for row in conflicts
            ],
        }
