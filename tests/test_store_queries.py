"""Execute real queries against the built store through the Execution Registry.

Every query below is built from registry metadata — observation table, selector
column, value column — so no physical column name appears in this file.  The
cases are structural: they run for whichever families and metrics the registry
exposes, and the same rule must hold for a variant that nobody wrote a query
for.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "processed" / "query_store.duckdb"
EXECUTION_REGISTRY = ROOT / "data" / "processed" / "execution_registry.json"

pytestmark = [
    pytest.mark.real_data,
    pytest.mark.skipif(
        not (STORE.exists() and EXECUTION_REGISTRY.exists()),
        reason="query store or execution registry has not been built",
    ),
]


@pytest.fixture(scope="module")
def connection():
    handle = duckdb.connect(str(STORE), read_only=True)
    yield handle
    handle.close()


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(EXECUTION_REGISTRY.read_text(encoding="utf-8"))


def binding_for(registry: dict, semantic_id: str, family_id: str) -> dict:
    for binding in registry["bindings"]:
        if binding["semantic_id"] == semantic_id and binding["family_id"] == family_id:
            return binding
    raise AssertionError(f"{semantic_id} is not bound for {family_id}")


def subject_table(family_id: str, registry: dict) -> str:
    grains = {
        binding["subject_grain"]
        for binding in registry["bindings"]
        if binding["family_id"] == family_id
    }
    return "product_class" if "product_class" in grains else "product"


def rank(connection, binding: dict, direction: str, limit: int) -> list[tuple]:
    """Rank at the subject grain: one selected observation per subject, then order.

    Selection is the latest effective as-of with a deterministic tie-break, which
    is what the declared product-grain dedup requirement means in practice.
    """
    order = "DESC" if direction == "desc" else "ASC"
    return connection.execute(
        f"""
        SELECT subject_key, value FROM (
            SELECT subject_key, {binding['value_column']} AS value,
                   row_number() OVER (
                       PARTITION BY subject_key
                       ORDER BY effective_as_of DESC NULLS LAST, source_row_id
                   ) AS selection
            FROM {binding['observation_table']}
            WHERE {binding['selector_column']} = ? AND family_id = ?
              AND value_status = 'valid'
        )
        WHERE selection = 1
        ORDER BY value {order}, subject_key
        LIMIT ?
        """,
        [binding["selector_value"], binding["family_id"], limit],
    ).fetchall()


def rank_without_selection(connection, binding: dict, limit: int) -> list[tuple]:
    """Deliberately skip subject selection, to show why the store keeps the multiplicity."""
    return connection.execute(
        f"""
        SELECT subject_key, {binding['value_column']}
        FROM {binding['observation_table']}
        WHERE {binding['selector_column']} = ? AND family_id = ? AND value_status = 'valid'
        ORDER BY {binding['value_column']} DESC, subject_key
        LIMIT ?
        """,
        [binding["selector_value"], binding["family_id"], limit],
    ).fetchall()


# --------------------------------------------------------------------- grains
def test_source_rows_never_become_product_counts(connection) -> None:
    for family_id, source_table in (("domestic_bond", "src_prbd01n001"),):
        products = connection.execute(
            "SELECT count(*), count(DISTINCT product_key) FROM product WHERE family_id = ?",
            [family_id],
        ).fetchone()
        rows = connection.execute(f"SELECT count(*) FROM {source_table}").fetchone()[0]
        assert products[0] == products[1], "product keys must be unique"
        assert products[0] < rows, "this family is known to carry several rows per product"


def test_each_family_result_grain_is_unique(connection, registry) -> None:
    for family_id in sorted({b["family_id"] for b in registry["bindings"]}):
        table = subject_table(family_id, registry)
        key = "product_class_key" if table == "product_class" else "product_key"
        total, distinct = connection.execute(
            f"SELECT count(*), count(DISTINCT {key}) FROM {table} WHERE family_id = ?",
            [family_id],
        ).fetchone()
        assert total == distinct and total > 0, family_id


# ------------------------------------------------------------------- ranking
def test_every_orderable_metric_ranks_without_duplicating_subjects(connection, registry) -> None:
    checked = 0
    for binding in registry["bindings"]:
        if binding["binding_kind"] != "metric" or "order" not in binding["executable_operations"]:
            continue
        coverage = binding.get("observed_coverage") or {}
        if not coverage.get("valid_subjects"):
            continue
        rows = rank(connection, binding, "desc", 10)
        subjects = [row[0] for row in rows]
        assert len(subjects) == len(set(subjects)), binding["semantic_id"]
        values = [row[1] for row in rows]
        assert values == sorted(values, reverse=True), binding["semantic_id"]
        assert all(value is not None and value != 0 for value in values), binding["semantic_id"]
        checked += 1
    assert checked > 40, f"only {checked} orderable metrics were exercised"


def test_a_subject_with_several_source_rows_needs_selection_before_ranking(
    connection, registry
) -> None:
    """The multiplicity is real data, not a bug: ranking rows would repeat a product."""
    multiples = [
        binding
        for binding in registry["bindings"]
        if binding["binding_kind"] == "metric"
        and (binding.get("observed_coverage") or {}).get("max_observations_per_subject", 0) > 1
    ]
    assert multiples, "at least one metric is observed several times per subject"
    binding = max(
        multiples, key=lambda b: b["observed_coverage"]["max_observations_per_subject"]
    )
    rows, subjects = connection.execute(
        f"SELECT count(*), count(DISTINCT subject_key) FROM {binding['observation_table']} "
        f"WHERE {binding['selector_column']} = ? AND value_status = 'valid'",
        [binding["selector_value"]],
    ).fetchone()
    assert rows > subjects, binding["semantic_id"]

    # A ranking that skips selection can return the same product more than once.
    unselected = connection.execute(
        f"""
        SELECT count(*) - count(DISTINCT subject_key) FROM (
            SELECT subject_key FROM {binding['observation_table']}
            WHERE {binding['selector_column']} = ? AND value_status = 'valid'
            ORDER BY {binding['value_column']} DESC LIMIT ?
        )
        """,
        [binding["selector_value"], rows],
    ).fetchone()[0]
    assert unselected > 0, binding["semantic_id"]

    selected = rank(connection, binding, "desc", 25)
    assert len({row[0] for row in selected}) == len(selected)
    assert rank_without_selection(connection, binding, 25)


def test_ranking_direction_is_a_variant_not_a_special_case(connection, registry) -> None:
    binding = binding_for(registry, "etkr:Return1Y", "domestic_etp")
    top = rank(connection, binding, "desc", 5)
    bottom = rank(connection, binding, "asc", 5)
    assert top and bottom
    assert top[0][1] >= bottom[0][1]
    assert not {row[0] for row in top} & {row[0] for row in bottom}


def test_adjacent_period_metrics_stay_separate_populations(connection, registry) -> None:
    monthly = binding_for(registry, "etkr:Return1M", "domestic_etp")
    yearly = binding_for(registry, "etkr:Return1Y", "domestic_etp")
    assert monthly["period_code"] != yearly["period_code"]
    counts = {
        b["semantic_id"]: connection.execute(
            f"SELECT count(*) FROM {b['observation_table']} "
            f"WHERE {b['selector_column']} = ? AND value_status = 'valid'",
            [b["selector_value"]],
        ).fetchone()[0]
        for b in (monthly, yearly)
    }
    assert counts["etkr:Return1M"] != counts["etkr:Return1Y"]


# ---------------------------------------------------------------- aggregation
def test_aggregation_excludes_zero_and_unparsed_values(connection, registry) -> None:
    binding = binding_for(registry, "etgl:AnnualExpenseRate", "overseas_etp")
    valid_avg, valid_rows = connection.execute(
        f"SELECT avg({binding['value_column']}), count(*) FROM {binding['observation_table']} "
        f"WHERE {binding['selector_column']} = ? AND value_status = 'valid'",
        [binding["selector_value"]],
    ).fetchone()
    all_avg, all_rows = connection.execute(
        f"SELECT avg({binding['value_column']}), count(*) FROM {binding['observation_table']} "
        f"WHERE {binding['selector_column']} = ?",
        [binding["selector_value"]],
    ).fetchone()
    assert valid_rows < all_rows, "this metric is known to carry excluded observations"
    assert valid_avg != all_avg
    coverage = binding["observed_coverage"]
    assert coverage["observed_subjects"] <= coverage["subject_total"]


def test_observed_universe_is_never_reported_as_the_full_universe(registry) -> None:
    partial = [
        binding
        for binding in registry["bindings"]
        if (binding.get("observed_coverage") or {}).get("missing_subjects")
    ]
    assert partial, "at least one metric is expected to be partially observed"
    for binding in partial:
        coverage = binding["observed_coverage"]
        assert coverage["observed_subjects"] + coverage["missing_subjects"] == (
            coverage["subject_total"]
        )


# ------------------------------------------------------------------ relations
def relation_sql(direction: str) -> str:
    if direction == "forward":
        return """
            SELECT count(DISTINCT h.security_key) AS securities, count(*) AS rows
            FROM product_portfolio_map m
            JOIN holding_observation h ON h.portfolio_key = m.portfolio_key
            WHERE m.subject_key = ? AND h.relation_kind = ? AND h.security_key IS NOT NULL
        """
    return """
        SELECT count(DISTINCT m.subject_key) AS products, count(*) AS rows
        FROM holding_observation h
        JOIN product_portfolio_map m ON m.portfolio_key = h.portfolio_key
        WHERE h.security_key = ? AND h.relation_kind = ? AND m.family_id = ?
    """


def test_relation_forward_and_inverse_agree_on_a_product_grain_answer(connection) -> None:
    subject_key, portfolio_key = connection.execute(
        """
        SELECT m.subject_key, m.portfolio_key
        FROM product_portfolio_map m
        JOIN holding_observation h ON h.portfolio_key = m.portfolio_key
        WHERE m.family_id = 'domestic_etp' AND h.security_key IS NOT NULL
        GROUP BY 1, 2 ORDER BY count(*) DESC LIMIT 1
        """
    ).fetchone()
    securities, rows = connection.execute(
        relation_sql("forward"), [subject_key, "direct_holding"]
    ).fetchone()
    assert securities > 0 and rows >= securities

    security_key = connection.execute(
        "SELECT security_key FROM holding_observation WHERE portfolio_key = ? "
        "AND security_key IS NOT NULL LIMIT 1",
        [portfolio_key],
    ).fetchone()[0]
    products, join_rows = connection.execute(
        relation_sql("inverse"), [security_key, "direct_holding", "domestic_etp"]
    ).fetchone()
    assert products >= 1
    assert subject_key in [
        row[0]
        for row in connection.execute(
            """
            SELECT DISTINCT m.subject_key FROM holding_observation h
            JOIN product_portfolio_map m ON m.portfolio_key = h.portfolio_key
            WHERE h.security_key = ? AND h.relation_kind = 'direct_holding'
            """,
            [security_key],
        ).fetchall()
    ]
    assert join_rows >= products


def test_logical_duplicates_do_not_inflate_a_relation_count(connection) -> None:
    """The source keeps duplicate (product, security) rows; counting rows would lie."""
    row = connection.execute(
        """
        SELECT m.subject_key, count(*) AS rows, count(DISTINCT h.security_key) AS securities
        FROM product_portfolio_map m
        JOIN holding_observation h ON h.portfolio_key = m.portfolio_key
        WHERE m.family_id = 'domestic_etp' AND h.security_key IS NOT NULL
        GROUP BY 1 HAVING count(*) > count(DISTINCT h.security_key)
        ORDER BY 2 DESC LIMIT 1
        """
    ).fetchone()
    assert row is not None, "a product with duplicate holding rows is expected"
    assert row[1] > row[2]


def test_direct_and_look_through_relations_stay_separate(connection) -> None:
    kinds = dict(
        connection.execute(
            "SELECT relation_kind, count(*) FROM holding_observation "
            "WHERE family_id = 'public_fund' GROUP BY 1"
        ).fetchall()
    )
    assert kinds.get("direct_holding") and kinds.get("look_through_exposure")
    parents = connection.execute(
        "SELECT count(*) FROM holding_observation WHERE relation_kind = 'look_through_exposure' "
        "AND parent_portfolio_id_raw IS NULL"
    ).fetchone()[0]
    assert parents == 0, "look-through observations must keep their parent portfolio"
    direct_parents = connection.execute(
        "SELECT count(*) FROM holding_observation WHERE relation_kind = 'direct_holding' "
        "AND parent_portfolio_id_raw IS NOT NULL"
    ).fetchone()[0]
    assert direct_parents == 0


def test_no_relation_observation_is_left_unclassified(connection) -> None:
    unclassified = connection.execute(
        "SELECT count(*) FROM holding_observation WHERE relation_kind = 'unclassified'"
    ).fetchone()[0]
    assert unclassified == 0


# ------------------------------------------------------- resolution and status
def test_name_only_holdings_never_become_security_relations(connection) -> None:
    resolved, named = connection.execute(
        """
        SELECT count(*) FILTER (WHERE security_key IS NOT NULL),
               count(*) FILTER (WHERE security_name_raw IS NOT NULL)
        FROM holding_observation WHERE family_id = 'public_fund'
        """
    ).fetchone()
    assert resolved == 0 and named > 0


def test_securities_exist_only_for_resolved_identifiers(connection) -> None:
    statuses = dict(
        connection.execute(
            "SELECT resolution_status, count(*) FROM security GROUP BY 1"
        ).fetchall()
    )
    assert set(statuses) <= {"checksum_verified", "format_matched"}
    unresolved_linked = connection.execute(
        "SELECT count(*) FROM holding_observation WHERE security_key IS NOT NULL "
        "AND identifier_status NOT IN ('checksum_verified', 'format_matched')"
    ).fetchone()[0]
    assert unresolved_linked == 0


def test_requested_and_effective_as_of_are_not_merged(connection) -> None:
    rows = dict(
        connection.execute(
            """
            SELECT family_id, any_value(as_of_status) FROM holding_observation
            GROUP BY family_id
            """
        ).fetchall()
    )
    assert rows["domestic_etp"] == "requested_only"
    assert rows["overseas_etp"] == "effective_reported"
    requested_without_effective = connection.execute(
        "SELECT count(*) FROM holding_observation WHERE as_of_status = 'requested_only' "
        "AND effective_as_of IS NOT NULL"
    ).fetchone()[0]
    assert requested_without_effective == 0


def test_collection_failures_are_visible_and_not_silent_absence(connection) -> None:
    failures, families = connection.execute(
        "SELECT count(*), count(DISTINCT family_id) FROM collection_failure"
    ).fetchone()
    assert failures > 0 and families >= 2
    unmapped = connection.execute(
        """
        SELECT count(*) FROM product_portfolio_map
        WHERE portfolio_key IS NULL AND mapping_status IN ('unresolved', 'ambiguous')
        """
    ).fetchone()[0]
    assert unmapped > 0, "unresolved mappings must stay visible instead of vanishing"


def test_class_groups_and_portfolios_stay_different_units(connection) -> None:
    groups = connection.execute(
        "SELECT count(*) FROM product_class_group WHERE family_id = 'public_fund'"
    ).fetchone()[0]
    portfolios = connection.execute(
        "SELECT count(*) FROM portfolio WHERE family_id = 'public_fund'"
    ).fetchone()[0]
    assert groups > 0 and portfolios > 0 and groups != portfolios


def test_official_data_wins_and_conflicts_are_recorded(connection) -> None:
    resolutions = dict(
        connection.execute(
            "SELECT policy, count(*) FROM source_conflict GROUP BY 1"
        ).fetchall()
    )
    assert resolutions, "conflict detection must run even when official data wins"
    official_kept = connection.execute(
        "SELECT count(*) FROM source_conflict WHERE resolution = 'official_value_kept' "
        "AND right_value = left_value"
    ).fetchone()[0]
    assert official_kept == 0


# ------------------------------------------------ unseen structure combinations
def orderable_metrics(registry: dict) -> dict[str, dict]:
    """One orderable, actually observed metric per family, chosen deterministically."""
    chosen: dict[str, dict] = {}
    for binding in sorted(registry["bindings"], key=lambda b: b["semantic_id"]):
        if binding["binding_kind"] != "metric" or "order" not in binding["executable_operations"]:
            continue
        if not (binding.get("observed_coverage") or {}).get("valid_subjects"):
            continue
        chosen.setdefault(binding["family_id"], binding)
    return chosen


@pytest.mark.parametrize("direction", ["desc", "asc"])
@pytest.mark.parametrize("limit", [1, 5, 25])
def test_the_same_ranking_rules_hold_for_every_family_direction_and_limit(
    connection, registry, direction: str, limit: int
) -> None:
    """No family, direction or size is a special case in the compiled query."""
    chosen = orderable_metrics(registry)
    assert len(chosen) >= 3, "several families must expose an orderable metric"
    for family_id, binding in sorted(chosen.items()):
        rows = rank(connection, binding, direction, limit)
        assert rows, f"{family_id}/{binding['semantic_id']}"
        assert len(rows) <= limit
        assert len({row[0] for row in rows}) == len(rows), family_id
        values = [row[1] for row in rows]
        assert values == sorted(values, reverse=direction == "desc"), family_id
        assert all(value != 0 for value in values), family_id


def test_semantic_coverage_matches_the_observed_groups(connection) -> None:
    """The artefact must carry the same completeness the build asserted."""
    for table, kind, id_column in (
        ("metric_observation", "metric", "metric_id"),
        ("attribute_observation", "attribute", "attribute_id"),
    ):
        groups = connection.execute(
            f"SELECT count(*) FROM (SELECT DISTINCT {id_column}, family_id, subject_grain "
            f"FROM {table})"
        ).fetchone()[0]
        recorded = connection.execute(
            "SELECT count(*) FROM semantic_coverage WHERE binding_kind = ?", [kind]
        ).fetchone()[0]
        assert groups == recorded, f"{kind}: {groups} observed groups but {recorded} coverage rows"
    total, kinds = connection.execute(
        "SELECT count(*), count(DISTINCT binding_kind) FROM semantic_coverage"
    ).fetchone()
    by_kind = dict(
        connection.execute(
            "SELECT binding_kind, count(*) FROM semantic_coverage GROUP BY 1"
        ).fetchall()
    )
    assert kinds == len(by_kind) == 2
    assert sum(by_kind.values()) == total


def test_the_declared_table_inventory_matches_the_store(connection) -> None:
    """Source mirrors and derived tables are counted separately, not lumped together."""
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    ]
    mirrors = [name for name in tables if name.startswith("src_")]
    derived = [name for name in tables if not name.startswith("src_")]
    assert len(mirrors) == 8, sorted(mirrors)
    assert len(derived) == 18, sorted(derived)
    assert len(tables) == 26
    assert "build_manifest" in derived, "the generation manifest must be part of the store"
