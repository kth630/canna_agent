"""Derived schema of the query store.

Each table states one grain.  Source rows, products, product classes,
portfolios, securities, metric observations and raw holding observations never
share a table, so a relation join can never be mistaken for a product result.

The join declarations below describe the schema this module creates; observed
cardinality is measured at build time and published by the Execution Registry.
"""

from __future__ import annotations

from dataclasses import dataclass

GRAIN_SOURCE_ROW = "source_row"
GRAIN_PRODUCT = "product"
GRAIN_PRODUCT_CLASS = "product_class"
GRAIN_PORTFOLIO = "portfolio"
GRAIN_SECURITY = "security"
GRAIN_METRIC_OBSERVATION = "metric_observation"
GRAIN_ATTRIBUTE_OBSERVATION = "attribute_observation"
GRAIN_HOLDING_OBSERVATION = "raw_holding_observation"
GRAIN_COVERAGE = "coverage_observation"
GRAIN_FAILURE = "collection_failure"
GRAIN_MAPPING = "product_portfolio_mapping"


@dataclass(frozen=True)
class JoinPath:
    join_id: str
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    declared_cardinality: str
    dedup_requirement: str
    note: str


DERIVED_TABLES: dict[str, str] = {
    "build_manifest": """
        CREATE TABLE build_manifest (
            build_id VARCHAR NOT NULL,
            generated_at VARCHAR NOT NULL,
            store_path VARCHAR,
            catalog_path VARCHAR
        )""",
    "data_source": """
        CREATE TABLE data_source (
            source_id VARCHAR PRIMARY KEY,
            source_kind VARCHAR NOT NULL,
            source_name VARCHAR,
            source_file VARCHAR,
            sha256 VARCHAR,
            recorded_sha256 VARCHAR,
            hash_matches BOOLEAN,
            source_precedence INTEGER NOT NULL,
            collected_at VARCHAR,
            note VARCHAR
        )""",
    "subject": """
        CREATE TABLE subject (
            subject_key VARCHAR NOT NULL,
            subject_grain VARCHAR NOT NULL,
            family_id VARCHAR,
            display_name VARCHAR,
            source_id VARCHAR
        )""",
    "product": """
        CREATE TABLE product (
            product_key VARCHAR PRIMARY KEY,
            family_id VARCHAR NOT NULL,
            official_table_id VARCHAR NOT NULL,
            official_key_field VARCHAR NOT NULL,
            official_key_value VARCHAR NOT NULL,
            product_name VARCHAR,
            product_short_name VARCHAR,
            source_row_count BIGINT NOT NULL,
            name_variant_count BIGINT,
            source_id VARCHAR
        )""",
    "product_class": """
        CREATE TABLE product_class (
            product_class_key VARCHAR PRIMARY KEY,
            family_id VARCHAR NOT NULL,
            official_table_id VARCHAR NOT NULL,
            official_key_field VARCHAR NOT NULL,
            official_key_value VARCHAR NOT NULL,
            class_display_name VARCHAR,
            product_name VARCHAR,
            class_group_key VARCHAR,
            class_group_value VARCHAR,
            class_group_status VARCHAR,
            source_row_count BIGINT NOT NULL,
            source_id VARCHAR
        )""",
    "product_class_group": """
        CREATE TABLE product_class_group (
            class_group_key VARCHAR PRIMARY KEY,
            family_id VARCHAR NOT NULL,
            group_scheme_id VARCHAR NOT NULL,
            group_value VARCHAR NOT NULL,
            class_count BIGINT NOT NULL,
            source_id VARCHAR
        )""",
    "identifier": """
        CREATE TABLE identifier (
            subject_key VARCHAR NOT NULL,
            scheme_id VARCHAR NOT NULL,
            identifier_value VARCHAR NOT NULL,
            verification_status VARCHAR NOT NULL,
            source_id VARCHAR,
            source_row_id VARCHAR
        )""",
    "metric_observation": """
        CREATE TABLE metric_observation (
            subject_key VARCHAR NOT NULL,
            subject_grain VARCHAR NOT NULL,
            family_id VARCHAR NOT NULL,
            metric_id VARCHAR NOT NULL,
            numeric_value DOUBLE,
            raw_text_value VARCHAR,
            unit_code VARCHAR,
            currency_code VARCHAR,
            period_code VARCHAR,
            effective_as_of DATE,
            as_of_status VARCHAR NOT NULL,
            value_status VARCHAR NOT NULL,
            source_id VARCHAR NOT NULL,
            source_row_id VARCHAR NOT NULL
        )""",
    "attribute_observation": """
        CREATE TABLE attribute_observation (
            subject_key VARCHAR NOT NULL,
            subject_grain VARCHAR NOT NULL,
            family_id VARCHAR NOT NULL,
            attribute_id VARCHAR NOT NULL,
            code_value VARCHAR,
            label_value VARCHAR,
            date_value DATE,
            effective_as_of DATE,
            as_of_status VARCHAR NOT NULL,
            value_status VARCHAR NOT NULL,
            source_id VARCHAR NOT NULL,
            source_row_id VARCHAR NOT NULL
        )""",
    "portfolio": """
        CREATE TABLE portfolio (
            portfolio_key VARCHAR PRIMARY KEY,
            family_id VARCHAR NOT NULL,
            portfolio_id_raw VARCHAR NOT NULL,
            portfolio_id_scheme VARCHAR,
            identifier_status VARCHAR NOT NULL,
            source_id VARCHAR
        )""",
    "product_portfolio_map": """
        CREATE TABLE product_portfolio_map (
            map_id VARCHAR PRIMARY KEY,
            subject_key VARCHAR NOT NULL,
            subject_grain VARCHAR NOT NULL,
            family_id VARCHAR NOT NULL,
            portfolio_key VARCHAR,
            mapping_status VARCHAR NOT NULL,
            mapping_basis VARCHAR,
            source_product_id_raw VARCHAR,
            external_product_name VARCHAR,
            external_isin VARCHAR,
            external_ticker VARCHAR,
            external_cik VARCHAR,
            subject_matches_official BOOLEAN NOT NULL,
            source_reference VARCHAR,
            source_id VARCHAR NOT NULL,
            source_row_id VARCHAR NOT NULL
        )""",
    "security": """
        CREATE TABLE security (
            security_key VARCHAR NOT NULL,
            scheme_id VARCHAR NOT NULL,
            identifier_value VARCHAR NOT NULL,
            security_name VARCHAR,
            name_variant_count BIGINT,
            resolution_status VARCHAR NOT NULL,
            observation_count BIGINT NOT NULL,
            source_id VARCHAR
        )""",
    "holding_observation": """
        CREATE TABLE holding_observation (
            holding_key VARCHAR NOT NULL,
            family_id VARCHAR NOT NULL,
            portfolio_key VARCHAR,
            security_key VARCHAR,
            relation_kind VARCHAR NOT NULL,
            parent_portfolio_id_raw VARCHAR,
            called_subject_key VARCHAR,
            held_security_id_raw VARCHAR,
            held_isin_raw VARCHAR,
            held_ticker_raw VARCHAR,
            security_name_raw VARCHAR,
            identifier_scheme_id VARCHAR NOT NULL,
            identifier_status VARCHAR NOT NULL,
            quantity_value DOUBLE,
            quantity_unit VARCHAR,
            value_amount DOUBLE,
            value_amount_unit VARCHAR,
            currency VARCHAR,
            weight_value DOUBLE,
            weight_unit VARCHAR,
            requested_as_of DATE,
            effective_as_of DATE,
            as_of_status VARCHAR NOT NULL,
            snapshot_scope VARCHAR,
            source_reference VARCHAR,
            source_record_id VARCHAR,
            source_id VARCHAR NOT NULL,
            source_row_id VARCHAR NOT NULL
        )""",
    "holdings_coverage": """
        CREATE TABLE holdings_coverage (
            coverage_id VARCHAR PRIMARY KEY,
            family_id VARCHAR NOT NULL,
            subject_grain VARCHAR NOT NULL,
            eligible_count BIGINT,
            attempted_count BIGINT,
            success_count BIGINT,
            failed_count BIGINT,
            exact_mapped_count BIGINT,
            ambiguous_count BIGINT,
            unresolved_count BIGINT,
            full_snapshot_count BIGINT,
            partial_snapshot_count BIGINT,
            unknown_snapshot_count BIGINT,
            holding_as_of_min VARCHAR,
            holding_as_of_max VARCHAR,
            official_subject_count BIGINT,
            mapped_subject_count BIGINT,
            observed_portfolio_count BIGINT,
            observed_subject_count BIGINT,
            holding_row_count BIGINT,
            resolved_security_row_count BIGINT,
            unclassified_relation_count BIGINT,
            as_of_role VARCHAR,
            collection_scope_note VARCHAR,
            source_id VARCHAR
        )""",
    "collection_failure": """
        CREATE TABLE collection_failure (
            failure_id VARCHAR PRIMARY KEY,
            family_id VARCHAR NOT NULL,
            subject_key VARCHAR,
            source_product_id_raw VARCHAR,
            stage VARCHAR,
            error_code VARCHAR,
            error_message VARCHAR,
            retryable VARCHAR,
            attempted_at VARCHAR,
            source_id VARCHAR NOT NULL,
            source_row_id VARCHAR NOT NULL
        )""",
    "semantic_coverage": """
        CREATE TABLE semantic_coverage (
            coverage_key VARCHAR PRIMARY KEY,
            semantic_id VARCHAR NOT NULL,
            binding_kind VARCHAR NOT NULL,
            family_id VARCHAR NOT NULL,
            subject_grain VARCHAR NOT NULL,
            subject_total BIGINT NOT NULL,
            observed_subjects BIGINT NOT NULL,
            observation_rows BIGINT NOT NULL,
            valid_subjects BIGINT,
            zero_excluded_subjects BIGINT,
            parse_failed_subjects BIGINT,
            missing_subjects BIGINT,
            max_observations_per_subject BIGINT,
            effective_as_of_min DATE,
            effective_as_of_max DATE,
            distinct_effective_as_of BIGINT,
            unknown_as_of_rows BIGINT
        )""",
    "source_conflict": """
        CREATE TABLE source_conflict (
            conflict_id VARCHAR PRIMARY KEY,
            conflict_group VARCHAR NOT NULL,
            policy VARCHAR NOT NULL,
            subject_key VARCHAR NOT NULL,
            left_semantic_id VARCHAR,
            left_value VARCHAR,
            left_source_id VARCHAR,
            right_semantic_id VARCHAR,
            right_value VARCHAR,
            right_source_id VARCHAR,
            resolution VARCHAR NOT NULL
        )""",
}

TABLE_GRAINS: dict[str, str] = {
    "data_source": "source_record",
    "subject": "subject_identity",
    "product": GRAIN_PRODUCT,
    "product_class": GRAIN_PRODUCT_CLASS,
    "product_class_group": "product_class_group",
    "identifier": "identifier_assertion",
    "metric_observation": GRAIN_METRIC_OBSERVATION,
    "attribute_observation": GRAIN_ATTRIBUTE_OBSERVATION,
    "portfolio": GRAIN_PORTFOLIO,
    "product_portfolio_map": GRAIN_MAPPING,
    "security": GRAIN_SECURITY,
    "holding_observation": GRAIN_HOLDING_OBSERVATION,
    "holdings_coverage": GRAIN_COVERAGE,
    "collection_failure": GRAIN_FAILURE,
    "semantic_coverage": GRAIN_COVERAGE,
    "source_conflict": "conflict_record",
    "held_identifier_classification": "identifier_classification",
    "build_manifest": "build_record",
}

JOIN_PATHS: tuple[JoinPath, ...] = (
    JoinPath(
        join_id="product_to_metric_observation",
        left_table="product",
        left_column="product_key",
        right_table="metric_observation",
        right_column="subject_key",
        declared_cardinality="one_to_many",
        dedup_requirement="product_grain_distinct_after_selection",
        note="한 상품이 같은 지표를 여러 source row 에서 가질 수 있어 선택 규칙 없이 순위를 매기지 않는다",
    ),
    JoinPath(
        join_id="product_class_to_metric_observation",
        left_table="product_class",
        left_column="product_class_key",
        right_table="metric_observation",
        right_column="subject_key",
        declared_cardinality="one_to_many",
        dedup_requirement="product_class_grain_distinct_after_selection",
        note="클래스 단위 지표이며 대표 grouping 으로 합치지 않는다",
    ),
    JoinPath(
        join_id="product_to_attribute_observation",
        left_table="product",
        left_column="product_key",
        right_table="attribute_observation",
        right_column="subject_key",
        declared_cardinality="one_to_many",
        dedup_requirement="product_grain_distinct_after_selection",
        note="",
    ),
    JoinPath(
        join_id="product_class_to_attribute_observation",
        left_table="product_class",
        left_column="product_class_key",
        right_table="attribute_observation",
        right_column="subject_key",
        declared_cardinality="one_to_many",
        dedup_requirement="product_class_grain_distinct_after_selection",
        note="",
    ),
    JoinPath(
        join_id="subject_to_portfolio_map",
        left_table="subject",
        left_column="subject_key",
        right_table="product_portfolio_map",
        right_column="subject_key",
        declared_cardinality="one_to_many",
        dedup_requirement="product_grain_distinct",
        note="상품·클래스에서 portfolio 로 가는 명시 mapping",
    ),
    JoinPath(
        join_id="portfolio_map_to_portfolio",
        left_table="product_portfolio_map",
        left_column="portfolio_key",
        right_table="portfolio",
        right_column="portfolio_key",
        declared_cardinality="many_to_one",
        dedup_requirement="none",
        note="여러 클래스가 같은 portfolio 를 공유한다",
    ),
    JoinPath(
        join_id="portfolio_to_holding_observation",
        left_table="portfolio",
        left_column="portfolio_key",
        right_table="holding_observation",
        right_column="portfolio_key",
        declared_cardinality="one_to_many",
        dedup_requirement="exists_or_distinct_before_ranking",
        note="원천에 논리적 중복 행이 있어 행 수를 상품 수로 쓰지 않는다",
    ),
    JoinPath(
        join_id="holding_observation_to_security",
        left_table="holding_observation",
        left_column="security_key",
        right_table="security",
        right_column="security_key",
        declared_cardinality="many_to_one",
        dedup_requirement="none",
        note="식별자가 해석된 관측만 Security 에 연결된다",
    ),
)
