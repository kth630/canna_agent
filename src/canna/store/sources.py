"""Read-only access to the immutable official workbooks and holdings bundle.

Nothing here writes to ``data/official_raw`` or ``data/incoming``.  Recorded
hashes come from 0-D provenance, and a mismatch is reported rather than
silently accepted, because every derived row inherits that custody claim.
"""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[3]
OFFICIAL_DIR = ROOT / "data" / "official_raw"
INCOMING_DIR = ROOT / "data" / "incoming"
PROVENANCE_DIR = (
    ROOT
    / "provenance"
    / "workstreams"
    / "20260830_preintegration_parallel"
    / "ontology_data_alignment"
    / "generated"
)
OFFICIAL_INVENTORY = PROVENANCE_DIR / "official_source_inventory.csv"
MIGRATION_MANIFEST = ROOT / "provenance" / "MIGRATION_MANIFEST.json"

SCHEMA_HEADINGS = {
    "field": "컬럼명",
    "data_type": "데이터타입",
    "nullable": "Nullable",
    "comment": "컬럼코멘트",
}
NORMALIZED_MEMBER_PREFIX = "normalized/"


@dataclass(frozen=True)
class OfficialSource:
    table_id: str
    data_file: str
    schema_file: str
    data_sha256: str
    schema_sha256: str
    data_rows: int
    source_row_grain: str
    identifier_candidates: str
    as_of_note: str


@dataclass(frozen=True)
class HoldingsBundle:
    archive: Path
    sha256: str
    recorded_sha256: str
    member_hashes: dict[str, str]
    normalized: dict[str, Path]
    collected_at: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def official_sources(inventory: Path | None = None) -> list[OfficialSource]:
    path = inventory or OFFICIAL_INVENTORY
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path.name}: no recorded official sources")
    return [
        OfficialSource(
            table_id=row["table_id"],
            data_file=row["data_file"],
            schema_file=row["schema_file"],
            data_sha256=row["data_sha256"],
            schema_sha256=row["schema_sha256"],
            data_rows=int(row["data_rows"]),
            source_row_grain=row["source_row_grain"],
            identifier_candidates=row["identifier_candidates"],
            as_of_note=row["as_of_fields"],
        )
        for row in rows
    ]


def recorded_bundle_hash(manifest: Path | None = None) -> tuple[str, str]:
    """Return the recorded archive name and hash for the incoming holdings bundle."""
    path = manifest or MIGRATION_MANIFEST
    payload = json.loads(path.read_text(encoding="utf-8"))
    for artifact in payload.get("immutable_local_artifacts", []):
        destination = str(artifact.get("destination", ""))
        if destination.startswith("data/incoming/") and destination.endswith(".zip"):
            return Path(destination).name, str(artifact["sha256"])
    raise ValueError(f"{path.name}: no incoming bundle recorded")


def read_schema(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        rows = workbook.active.iter_rows(values_only=True)
        headings = [str(value).strip() if value is not None else "" for value in next(rows)]
        index = {heading: position for position, heading in enumerate(headings)}
        missing = set(SCHEMA_HEADINGS.values()).difference(index)
        if missing:
            raise ValueError(f"{path.name}: missing schema headings {sorted(missing)}")
        order: list[str] = []
        schema: dict[str, dict[str, str]] = {}
        for row in rows:
            raw = row[index[SCHEMA_HEADINGS["field"]]]
            if raw is None:
                continue
            name = str(raw).strip()
            order.append(name)
            schema[name] = {
                key: str(row[index[heading]] or "")
                for key, heading in SCHEMA_HEADINGS.items()
                if key != "field"
            }
        return order, schema
    finally:
        workbook.close()


def write_staging_csv(
    path: Path, order: list[str], target: Path, ordinal_column: str | None = None
) -> int:
    """Stream a workbook to CSV as raw text, preserving source padding verbatim.

    ``ordinal_column`` records the source row order so every derived row can be
    traced back to one physical record without inventing a business key.
    """
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        rows = workbook.active.iter_rows(values_only=True)
        headers = [str(value).strip() if value is not None else "" for value in next(rows)]
        if headers != order:
            raise ValueError(f"{path.name}: data header order differs from schema")
        count = 0
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(([ordinal_column] if ordinal_column else []) + order)
            for row in rows:
                count += 1
                values = [None if value is None else str(value) for value in row]
                writer.writerow(([count] if ordinal_column else []) + values)
        return count
    finally:
        workbook.close()


def extract_holdings(destination: Path, archive: Path | None = None) -> HoldingsBundle:
    """Copy only the normalized members out of the read-only bundle."""
    name, recorded = recorded_bundle_hash()
    path = archive or (INCOMING_DIR / name)
    actual = sha256(path)
    normalized: dict[str, Path] = {}
    with zipfile.ZipFile(path) as bundle:
        manifest_member = next(
            member for member in bundle.namelist() if member.endswith("MANIFEST.json")
        )
        manifest = json.loads(bundle.read(manifest_member).decode("utf-8"))
        for member in bundle.namelist():
            tail = member.split("/", 1)[-1]
            if not tail.startswith(NORMALIZED_MEMBER_PREFIX) or not tail.endswith(".parquet"):
                continue
            target = destination / Path(tail).name
            target.write_bytes(bundle.read(member))
            normalized[Path(tail).stem] = target
    files = manifest.get("files", manifest.get("file_hashes", {}))
    if isinstance(files, list):
        member_hashes = {entry["path"]: entry["sha256"] for entry in files}
    else:
        member_hashes = {key: str(value) for key, value in files.items()}
    collected_at = str(manifest.get("generated_at_utc") or "")
    return HoldingsBundle(
        archive=path,
        sha256=actual,
        recorded_sha256=recorded,
        member_hashes=member_hashes,
        normalized=normalized,
        collected_at=collected_at,
    )
