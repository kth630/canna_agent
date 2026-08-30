"""External holdings bundle: portfolios, relations, securities, coverage.

The bundle is read-only.  Its mapping status, snapshot scope, collection
failures and unverified identifier schemes are carried into the store as
explicit states; none of them is converted into a missing row, a zero or a
false relation.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from canna.store import sources
from canna.store.catalog import CatalogError, FieldBinding
from canna.store.types import normalized_date_expression

HOLDINGS_SOURCE_ID = "external_holdings_bundle"
EXTERNAL_PRECEDENCE = 2

SOURCE_ROW_KEYS = {
    "product_mapping": "product_family || '|' || project_product_id",
    "holdings": "source_record_id",
    "coverage": "product_family",
}
FAILURE_ORDER = (
    "product_family, source_product_id, project_product_id, stage, error_code, "
    "error_message, attempted_at"
)


def isin_checksum_ok(value: str) -> bool:
    """ISO 6166 check digit over the alphanumeric body."""
    if len(value) != 12:
        return False
    digits = ""
    for character in value[:-1]:
        if character.isdigit():
            digits += character
        elif character.isalpha():
            digits += str(ord(character.upper()) - 55)
        else:
            return False
    total = 0
    for position, character in enumerate(reversed(digits)):
        doubled = int(character) * (2 if position % 2 == 0 else 1)
        total += doubled // 10 + doubled % 10
    return (10 - total % 10) % 10 == int(value[-1])


class HoldingsMixin:
    """Mixed into the store builder; expects ``connection`` and ``catalog``."""

    def _quoted(self, value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _family_case(self, column: str) -> str:
        branches = [
            f"WHEN {column} = {self._quoted(family.holdings_family)} "
            f"THEN {self._quoted(family.family_id)}"
            for family in self.catalog.families
            if family.holdings_family
        ]
        return f"CASE {' '.join(branches)} END"

    def _family_property_case(self, column: str, attribute: str) -> str:
        branches = []
        for family in self.catalog.families:
            if not family.holdings_family:
                continue
            value = getattr(family, attribute)
            branches.append(
                f"WHEN {column} = {self._quoted(family.holdings_family)} "
                f"THEN {self._quoted(value)}"
            )
        return f"CASE {' '.join(branches)} END" if branches else "NULL"

    # ------------------------------------------------------------ ingestion
    def load_holdings(self, staging: Path) -> None:
        self.staging_dir = staging
        bundle = sources.extract_holdings(staging)
        self.register_source(
            source_id=HOLDINGS_SOURCE_ID,
            kind="external",
            name=bundle.archive.stem,
            file_name=bundle.archive.name,
            digest=bundle.sha256,
            recorded=bundle.recorded_sha256,
            precedence=EXTERNAL_PRECEDENCE,
            collected_at=bundle.collected_at,
            note="읽기 전용 외부 번들의 normalized 산출물만 사용한다",
        )
        for name, path in sorted(bundle.normalized.items()):
            key = SOURCE_ROW_KEYS.get(name)
            row_id = (
                f"'{name}#' || {key}"
                if key
                else f"'{name}#' || row_number() OVER (ORDER BY {FAILURE_ORDER})"
            )
            self.connection.execute(
                f"CREATE TABLE src_holdings_{name} AS "
                f"SELECT {row_id} AS source_row_id, * FROM read_parquet(?)",
                [str(path)],
            )
            counted = self.connection.execute(
                f"SELECT count(*), count(DISTINCT source_row_id) FROM src_holdings_{name}"
            ).fetchone()
            if counted[0] != counted[1]:
                raise ValueError(f"src_holdings_{name}: source row id is not unique")
            self.source_tables[f"holdings_{name}"] = {
                "physical_table": f"src_holdings_{name}",
                "row_count": counted[0],
                "column_order": [
                    row[0]
                    for row in self.connection.execute(f"DESCRIBE src_holdings_{name}").fetchall()
                ],
                "source_row_grain": "external bundle normalized record",
                "source_id": HOLDINGS_SOURCE_ID,
            }

    # ------------------------------------------------------------ portfolios
    def build_portfolios_and_mappings(self) -> None:
        family_id = self._family_case("m.product_family")
        scheme = self._family_property_case("m.product_family", "portfolio_id_scheme")
        self.connection.execute(
            f"""
            INSERT INTO portfolio
            SELECT DISTINCT 'pf:' || {family_id} || ':' || trim(m.portfolio_id),
                   {family_id}, trim(m.portfolio_id), {scheme},
                   'declared_by_external_source', {self._quoted(HOLDINGS_SOURCE_ID)}
            FROM src_holdings_product_mapping m
            WHERE nullif(trim(m.portfolio_id), '') IS NOT NULL
            """
        )
        holdings_family = self._family_case("h.product_family")
        self.connection.execute(
            f"""
            INSERT INTO portfolio
            SELECT DISTINCT 'pf:' || {holdings_family} || ':' || trim(h.portfolio_id),
                   {holdings_family}, trim(h.portfolio_id),
                   {self._family_property_case('h.product_family', 'portfolio_id_scheme')},
                   'observed_only_in_holdings', {self._quoted(HOLDINGS_SOURCE_ID)}
            FROM src_holdings_holdings h
            WHERE nullif(trim(h.portfolio_id), '') IS NOT NULL
              AND 'pf:' || {holdings_family} || ':' || trim(h.portfolio_id)
                  NOT IN (SELECT portfolio_key FROM portfolio)
            """
        )
        subject_expr = f"{family_id} || ':' || trim(m.project_product_id)"
        self.connection.execute(
            f"""
            INSERT INTO product_portfolio_map
            SELECT m.source_row_id, {subject_expr},
                   COALESCE(s.subject_grain, 'unmatched_official_subject'), {family_id},
                   CASE WHEN nullif(trim(m.portfolio_id), '') IS NULL THEN NULL
                        ELSE 'pf:' || {family_id} || ':' || trim(m.portfolio_id) END,
                   m.mapping_status, m.mapping_basis, nullif(trim(m.source_product_id), ''),
                   nullif(trim(m.product_name), ''), nullif(trim(m.isin), ''),
                   nullif(trim(m.ticker), ''), nullif(trim(m.cik), ''),
                   s.subject_key IS NOT NULL, m.source,
                   {self._quoted(HOLDINGS_SOURCE_ID)}, m.source_row_id
            FROM src_holdings_product_mapping m
            LEFT JOIN subject s ON s.subject_key = {subject_expr}
            """
        )

    # ------------------------------------------------- securities and holdings
    def _classify_held_identifiers(self) -> list[str]:
        rules = [rule for rule in self.catalog.identifier_rules if rule.scope == "held_security"]
        if not rules:
            raise CatalogError("no held_security identifier rules declared")
        scheme_case, status_case, promote_case = ["CASE"], ["CASE"], ["CASE"]
        for rule in rules:
            condition = f"regexp_matches(value, {self._quoted(rule.pattern)})"
            scheme_case.append(f"WHEN {condition} THEN {self._quoted(rule.scheme_id)}")
            status_case.append(f"WHEN {condition} THEN {self._quoted(rule.resolution_status)}")
            promote_case.append(f"WHEN {condition} THEN {str(rule.promote_to_security).lower()}")
        for case in (scheme_case, status_case, promote_case):
            case.append("END")
        self.connection.execute(
            f"""
            CREATE TABLE held_identifier_classification AS
            SELECT value, {' '.join(scheme_case)} AS scheme_id,
                   {' '.join(status_case)} AS resolution_status,
                   {' '.join(promote_case)} AS promote_to_security
            FROM (SELECT DISTINCT COALESCE(trim(held_security_id), '') AS value
                  FROM src_holdings_holdings)
            """
        )
        checked = [rule.scheme_id for rule in rules if rule.checksum == "isin_mod10"]
        if not checked:
            return []
        placeholders = ", ".join(self._quoted(scheme) for scheme in checked)
        values = [
            value
            for (value,) in self.connection.execute(
                "SELECT value FROM held_identifier_classification "
                f"WHERE scheme_id IN ({placeholders})"
            ).fetchall()
        ]
        # Row-at-a-time inserts do not scale to a whole identifier universe, so the
        # verdicts are staged as one file and loaded in a single scan.
        verdict_path = self.staging_dir / "identifier_checksum.csv"
        with verdict_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["value", "passed"])
            for value in values:
                writer.writerow([value, "true" if isin_checksum_ok(value) else "false"])
        self.connection.execute(
            "CREATE TABLE held_identifier_checksum AS "
            "SELECT value, passed FROM read_csv(?, header = true, "
            "columns = {'value': 'VARCHAR', 'passed': 'BOOLEAN'})",
            [str(verdict_path)],
        )
        self.connection.execute(
            """
            UPDATE held_identifier_classification AS c
            SET resolution_status = CASE WHEN k.passed THEN 'checksum_verified'
                                         ELSE 'format_matched_checksum_failed' END,
                promote_to_security = k.passed
            FROM held_identifier_checksum k
            WHERE k.value = c.value
            """
        )
        return checked

    def build_securities_and_holdings(self) -> None:
        self._classify_held_identifiers()
        self.connection.execute("DROP TABLE IF EXISTS held_identifier_checksum")
        family_id = self._family_case("h.product_family")
        as_of_role = self._family_property_case("h.product_family", "holdings_as_of_role")
        as_of_date = normalized_date_expression("h.holding_as_of")
        self.connection.execute(
            f"""
            CREATE TABLE holding_staging AS
            SELECT h.source_row_id, {family_id} AS family_id,
                   CASE WHEN nullif(trim(h.portfolio_id), '') IS NULL THEN NULL
                        ELSE 'pf:' || {family_id} || ':' || trim(h.portfolio_id) END
                        AS portfolio_key,
                   CASE WHEN c.promote_to_security
                        THEN 'sec:' || c.scheme_id || ':' || c.value END AS security_key,
                   c.scheme_id, c.resolution_status,
                   nullif(trim(h.held_security_id), '') AS held_security_id_raw,
                   nullif(trim(h.isin), '') AS held_isin_raw,
                   nullif(trim(h.ticker), '') AS held_ticker_raw,
                   nullif(trim(h.security_name), '') AS security_name_raw,
                   h.quantity_value, nullif(trim(h.quantity_unit), '') AS quantity_unit,
                   h.value_amount, nullif(trim(h.value_amount_unit), '') AS value_amount_unit,
                   nullif(trim(h.currency), '') AS currency,
                   h.weight_value, nullif(trim(h.weight_unit), '') AS weight_unit,
                   CASE WHEN {as_of_role} = 'requested' THEN {as_of_date} END AS requested_as_of,
                   CASE WHEN {as_of_role} = 'effective' THEN {as_of_date} END AS effective_as_of,
                   CASE WHEN {as_of_date} IS NULL THEN 'unknown'
                        WHEN {as_of_role} = 'requested' THEN 'requested_only'
                        ELSE 'effective_reported' END AS as_of_status,
                   nullif(trim(h.snapshot_scope), '') AS snapshot_scope,
                   h.source AS source_reference, h.source_record_id,
                   {family_id} || ':' || trim(h.project_product_id) AS called_subject_key
            FROM src_holdings_holdings h
            LEFT JOIN held_identifier_classification c
              ON c.value = COALESCE(trim(h.held_security_id), '')
            """
        )
        relation_expr, parent_expr = self._relation_expressions()
        self.connection.execute(
            f"""
            INSERT INTO holding_observation
            SELECT s.source_row_id, s.family_id, s.portfolio_key, s.security_key,
                   {relation_expr}, {parent_expr}, s.called_subject_key,
                   s.held_security_id_raw, s.held_isin_raw, s.held_ticker_raw, s.security_name_raw,
                   s.scheme_id, s.resolution_status, s.quantity_value, s.quantity_unit,
                   s.value_amount, s.value_amount_unit, s.currency, s.weight_value, s.weight_unit,
                   s.requested_as_of, s.effective_as_of, s.as_of_status, s.snapshot_scope,
                   s.source_reference, s.source_record_id,
                   {self._quoted(HOLDINGS_SOURCE_ID)}, s.source_row_id
            FROM holding_staging s
            """
        )
        self.connection.execute("DROP TABLE holding_staging")
        self.connection.execute(
            f"""
            INSERT INTO security
            SELECT security_key, any_value(identifier_scheme_id), any_value(held_security_id_raw),
                   arg_min(security_name_raw, source_record_id),
                   count(DISTINCT security_name_raw), any_value(identifier_status), count(*),
                   {self._quoted(HOLDINGS_SOURCE_ID)}
            FROM holding_observation
            WHERE security_key IS NOT NULL
            GROUP BY security_key
            """
        )
        self.connection.execute(
            """
            INSERT INTO subject
            SELECT security_key, 'security', NULL, security_name, source_id FROM security
            UNION ALL
            SELECT portfolio_key, 'portfolio', family_id, portfolio_id_raw, source_id FROM portfolio
            """
        )

    def _relation_expressions(self) -> tuple[str, str]:
        kind_branches: list[str] = []
        parent_branches: list[str] = []
        for family in self.catalog.families:
            for rule in self.catalog.relation_rules_for(family.family_id):
                guard = (
                    f"s.family_id = {self._quoted(family.family_id)} AND "
                    f"regexp_matches(s.source_reference, {self._quoted(rule.source_pattern)})"
                )
                kind_branches.append(f"WHEN {guard} THEN {self._quoted(rule.relation_kind)}")
                if rule.parent_group_index:
                    parent_branches.append(
                        f"WHEN {guard} THEN nullif(regexp_extract(s.source_reference, "
                        f"{self._quoted(rule.source_pattern)}, "
                        f"{int(rule.parent_group_index)}), '')"
                    )
        kind = f"CASE {' '.join(kind_branches)} ELSE 'unclassified' END"
        parent = f"CASE {' '.join(parent_branches)} END" if parent_branches else "NULL"
        return kind, parent

    # -------------------------------------------------- coverage and failures
    def build_coverage_and_failures(self) -> None:
        family_id = self._family_case("c.product_family")
        self.connection.execute(
            f"""
            INSERT INTO holdings_coverage
            SELECT 'coverage:' || {family_id}, {family_id},
                   {self._family_property_case('c.product_family', 'result_grain')},
                   c.eligible_count, c.attempted_count, c.success_count, c.failed_count,
                   c.exact_mapped_count, c.ambiguous_count, c.unresolved_count,
                   c.full_snapshot_count, c.partial_snapshot_count, c.unknown_snapshot_count,
                   c.holding_as_of_min, c.holding_as_of_max,
                   (SELECT count(*) FROM subject s WHERE s.family_id = {family_id}
                      AND s.subject_grain IN ('product', 'product_class')),
                   (SELECT count(DISTINCT m.subject_key) FROM product_portfolio_map m
                      WHERE m.family_id = {family_id} AND m.portfolio_key IS NOT NULL),
                   (SELECT count(DISTINCT h.portfolio_key) FROM holding_observation h
                      WHERE h.family_id = {family_id}),
                   (SELECT count(DISTINCT m.subject_key) FROM product_portfolio_map m
                      JOIN holding_observation h ON h.portfolio_key = m.portfolio_key
                      WHERE m.family_id = {family_id}),
                   (SELECT count(*) FROM holding_observation h WHERE h.family_id = {family_id}),
                   (SELECT count(*) FROM holding_observation h
                      WHERE h.family_id = {family_id} AND h.security_key IS NOT NULL),
                   (SELECT count(*) FROM holding_observation h
                      WHERE h.family_id = {family_id} AND h.relation_kind = 'unclassified'),
                   {self._family_property_case('c.product_family', 'holdings_as_of_role')},
                   {self._family_property_case('c.product_family', 'collection_scope_note')},
                   {self._quoted(HOLDINGS_SOURCE_ID)}
            FROM src_holdings_coverage c
            """
        )
        failure_family = self._family_case("f.product_family")
        self.connection.execute(
            f"""
            INSERT INTO collection_failure
            SELECT f.source_row_id, {failure_family},
                   CASE WHEN nullif(trim(f.project_product_id), '') IS NULL THEN NULL
                        ELSE {failure_family} || ':' || trim(f.project_product_id) END,
                   nullif(trim(f.source_product_id), ''), f.stage, f.error_code, f.error_message,
                   f.retryable, f.attempted_at,
                   {self._quoted(HOLDINGS_SOURCE_ID)}, f.source_row_id
            FROM src_holdings_failures f
            """
        )

    # ------------------------------------------------------------ conflicts
    def build_conflicts(self) -> None:
        groups = {group.conflict_group: group for group in self.catalog.conflict_groups}
        members: dict[str, list[FieldBinding]] = defaultdict(list)
        for binding in self.catalog.field_bindings:
            if binding.conflict_group:
                members[binding.conflict_group].append(binding)

        for name, group in groups.items():
            bindings = members.get(name, [])
            if group.right_source_kind == "external":
                for binding in bindings:
                    family = self.catalog.family_by_table(binding.table_id)
                    self.connection.execute(
                        f"""
                        INSERT INTO source_conflict
                        SELECT 'conflict:' || {self._quoted(name)} || ':' || m.subject_key,
                               {self._quoted(name)}, {self._quoted(group.policy)}, m.subject_key,
                               {self._quoted(binding.semantic_id)}, s.display_name,
                               {self._quoted(binding.table_id)}, NULL, m.external_product_name,
                               {self._quoted(HOLDINGS_SOURCE_ID)}, 'official_value_kept'
                        FROM product_portfolio_map m
                        JOIN subject s ON s.subject_key = m.subject_key
                        WHERE m.family_id = {self._quoted(family.family_id)}
                          AND m.external_product_name IS NOT NULL
                          AND s.display_name IS NOT NULL
                          AND m.external_product_name <> s.display_name
                        """
                    )
                continue
            by_table: dict[str, list[FieldBinding]] = defaultdict(list)
            for binding in bindings:
                by_table[binding.table_id].append(binding)
            for table_id, table_bindings in by_table.items():
                if len(table_bindings) < 2:
                    continue
                family = self.catalog.family_by_table(table_id)
                table = self.source_tables[table_id]["physical_table"]
                left, right = table_bindings[0], table_bindings[1]
                left_value = f"nullif(trim(\"{left.field}\"), '')"
                right_value = f"nullif(trim(\"{right.field}\"), '')"
                key_value = f"nullif(trim(\"{family.official_key_field}\"), '')"
                self.connection.execute(
                    f"""
                    INSERT INTO source_conflict
                    SELECT 'conflict:' || {self._quoted(name)} || ':' || source_row_id,
                           {self._quoted(name)}, {self._quoted(group.policy)},
                           {self._quoted(family.family_id)} || ':' || {key_value},
                           {self._quoted(left.semantic_id)}, {left_value},
                           {self._quoted(table_id)},
                           {self._quoted(right.semantic_id)}, {right_value},
                           {self._quoted(table_id)}, 'recorded_without_precedence'
                    FROM {table}
                    WHERE {left_value} IS NOT NULL AND {right_value} IS NOT NULL
                      AND {left_value} <> {right_value}
                    """
                )
