"""Export unique domestic-ETF holdings identifiers from the read-only bundle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("data/incoming/holdings_20260829.zip"),
    )
    parser.add_argument(
        "--query-store",
        type=Path,
        default=Path("data/processed/query_store.duckdb"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/processed/exports"),
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_rows(bundle: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with zipfile.ZipFile(bundle) as archive:
        rows_member = "holdings_20260829/raw/domestic_etf/holdings_rows.jsonl"
        summary_member = "holdings_20260829/raw/domestic_etf/summary.json"
        rows = [
            json.loads(line)
            for line in archive.read(rows_member).decode("utf-8").splitlines()
            if line.strip()
        ]
        summary = json.loads(archive.read(summary_member).decode("utf-8"))
    return rows, summary


def _resolved_security_map(query_store: Path) -> dict[str, dict[str, Any]]:
    import duckdb

    connection = duckdb.connect(str(query_store), read_only=True)
    try:
        records = connection.execute(
            """
            SELECT identifier_value, security_key, security_name,
                   name_variant_count, resolution_status, observation_count
            FROM security
            WHERE scheme_id = 'cnn:KrxShortCodeIdentifier'
            ORDER BY identifier_value
            """
        ).fetchall()
    finally:
        connection.close()
    return {
        identifier_value: {
            "security_key": security_key,
            "registry_observed_name": security_name,
            "registry_name_variant_count": name_variant_count,
            "resolution_status": resolution_status,
            "registry_observation_count": observation_count,
        }
        for identifier_value, security_key, security_name, name_variant_count,
        resolution_status, observation_count in records
    }


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = _parse_args()
    rows, source_summary = _load_rows(args.bundle)
    resolved = _resolved_security_map(args.query_store)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    row_count = Counter()
    product_sets: defaultdict[str, set[str]] = defaultdict(set)
    product_isin_sets: defaultdict[str, set[str]] = defaultdict(set)
    name_sets: defaultdict[str, set[str]] = defaultdict(set)
    pair_count = Counter()
    pair_products: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    requested_dates = set()
    sources = set()
    scopes = set()

    for row in rows:
        identifier = str(row["component_ticker"])
        name = str(row["구성종목명"])
        product_ticker = str(row["product_ticker"])
        pair = (identifier, name)
        row_count[identifier] += 1
        product_sets[identifier].add(product_ticker)
        product_isin_sets[identifier].add(str(row.get("product_isin", "")))
        name_sets[identifier].add(name)
        pair_count[pair] += 1
        pair_products[pair].add(product_ticker)
        requested_dates.add(str(row.get("requested_date", "")))
        sources.add("pykrx.stock.get_etf_portfolio_deposit_file")
        scopes.add("full")

    def identifier_fields(identifier: str) -> dict[str, Any]:
        match = resolved.get(identifier)
        if match is None:
            return {
                "identifier_scheme": "cnn:SourceTickerIdentifierRaw",
                "identifier_status": "unverified_scheme",
                "format_matched_registry_key": "",
                "registry_observed_name": "",
                "registry_name_variant_count": "",
                "registry_resolution_status": "",
                "registry_observation_count": "",
            }
        return {
            "identifier_scheme": "cnn:KrxShortCodeIdentifier",
            "identifier_status": "format_matched",
            "format_matched_registry_key": match["security_key"],
            "registry_observed_name": match["registry_observed_name"] or "",
            "registry_name_variant_count": match["registry_name_variant_count"],
            "registry_resolution_status": match["resolution_status"],
            "registry_observation_count": match["registry_observation_count"],
        }

    identifier_rows = []
    for identifier in sorted(row_count):
        names = sorted(name_sets[identifier])
        metadata = identifier_fields(identifier)
        identifier_rows.append(
            {
                "source_identifier": identifier,
                **metadata,
                "raw_name_variants": " || ".join(names),
                "raw_name_variant_count": len(names),
                "observed_row_count": row_count[identifier],
                "etf_product_count": len(product_sets[identifier]),
                "etf_ticker_values": " || ".join(sorted(product_sets[identifier])),
                "etf_isin_values": " || ".join(
                    value for value in sorted(product_isin_sets[identifier]) if value
                ),
                "requested_as_of_values": " || ".join(sorted(requested_dates)),
                "snapshot_scope_values": " || ".join(sorted(scopes)),
                "entity_type_status": "not_classified_in_source",
            }
        )

    pair_rows = []
    for identifier, name in sorted(pair_count):
        pair_rows.append(
            {
                "source_identifier": identifier,
                "raw_security_name": name,
                **identifier_fields(identifier),
                "observed_row_count": pair_count[(identifier, name)],
                "etf_product_count": len(pair_products[(identifier, name)]),
                "etf_ticker_values": " || ".join(sorted(pair_products[(identifier, name)])),
                "entity_type_status": "not_classified_in_source",
            }
        )

    format_matched_rows = [
        row for row in identifier_rows if row["format_matched_registry_key"]
    ]

    identifier_fields_order = [
        "source_identifier", "identifier_scheme", "identifier_status",
        "format_matched_registry_key", "registry_observed_name",
        "registry_name_variant_count", "registry_resolution_status",
        "registry_observation_count",
        "raw_name_variants", "raw_name_variant_count", "observed_row_count",
        "etf_product_count", "etf_ticker_values", "etf_isin_values",
        "requested_as_of_values", "snapshot_scope_values", "entity_type_status",
    ]
    pair_fields_order = [
        "source_identifier", "raw_security_name", "identifier_scheme",
        "identifier_status", "format_matched_registry_key", "registry_observed_name",
        "registry_name_variant_count", "registry_resolution_status",
        "registry_observation_count",
        "observed_row_count", "etf_product_count", "etf_ticker_values",
        "entity_type_status",
    ]
    _write_csv(
        args.out_dir / "domestic_etf_holdings_unique_identifiers.csv",
        identifier_fields_order,
        identifier_rows,
    )
    _write_csv(
        args.out_dir / "domestic_etf_holdings_unique_ticker_name_pairs.csv",
        pair_fields_order,
        pair_rows,
    )
    _write_csv(
        args.out_dir / "domestic_etf_holdings_format_matched_krx_identifiers.csv",
        identifier_fields_order,
        format_matched_rows,
    )

    summary = {
        "source_bundle": str(args.bundle),
        "source_bundle_sha256": _sha256(args.bundle),
        "source_member": "holdings_20260829/raw/domestic_etf/holdings_rows.jsonl",
        "source_summary": source_summary,
        "product_family_in_source": "domestic_etf",
        "query_store_family_id": "domestic_etp",
        "holding_row_count": len(rows),
        "unique_identifier_count": len(identifier_rows),
        "unique_ticker_name_pair_count": len(pair_rows),
        "format_matched_identifier_count": len(format_matched_rows),
        "unverified_identifier_count": len(identifier_rows) - len(format_matched_rows),
        "unique_raw_name_count": len({name for names in name_sets.values() for name in names}),
        "requested_as_of_values": sorted(requested_dates),
        "snapshot_scope_values": sorted(scopes),
        "entity_type_status": "not classified; output contains holdings components, not only verified corporations",
        "outputs": [
            "domestic_etf_holdings_unique_identifiers.csv",
            "domestic_etf_holdings_unique_ticker_name_pairs.csv",
            "domestic_etf_holdings_format_matched_krx_identifiers.csv",
        ],
    }
    (args.out_dir / "domestic_etf_holdings_unique_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
