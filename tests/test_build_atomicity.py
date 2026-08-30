"""A failed or concurrent rebuild must never damage the published outputs.

The failures below are injected, so these tests run in seconds and do not touch
the immutable sources.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from canna.store import build as build_module
from canna.store.emit import CoverageMixin
from canna.store.publish import (
    LOCK_SUFFIX,
    TEMP_PREFIX,
    BuildLockError,
    PublishRollbackError,
    build_lock,
    discard,
    publish,
    publish_generation,
    temp_path,
)

PREVIOUS_STORE = b"previous store bytes"
PREVIOUS_CATALOG = {"generated_at": "earlier", "tables": []}


@pytest.fixture
def published(tmp_path: Path) -> dict[str, Path]:
    store = tmp_path / "query_store.duckdb"
    catalog = tmp_path / "data_catalog.json"
    store.write_bytes(PREVIOUS_STORE)
    catalog.write_text(json.dumps(PREVIOUS_CATALOG), encoding="utf-8")
    return {"store": store, "catalog": catalog}


def assert_untouched(published: dict[str, Path]) -> None:
    assert published["store"].read_bytes() == PREVIOUS_STORE
    assert json.loads(published["catalog"].read_text(encoding="utf-8")) == PREVIOUS_CATALOG


@pytest.fixture
def unbuilt(tmp_path: Path) -> dict[str, Path]:
    """A first build: neither artefact exists yet."""
    return {"store": tmp_path / "query_store.duckdb", "catalog": tmp_path / "data_catalog.json"}


def leftovers(directory: Path) -> list[str]:
    return sorted(
        path.name
        for path in directory.iterdir()
        if path.name.startswith(TEMP_PREFIX) or path.name.endswith(LOCK_SUFFIX)
    )


def test_a_failure_before_any_write_keeps_the_previous_outputs(published, monkeypatch) -> None:
    monkeypatch.setattr(
        build_module.StoreBuilder,
        "create_schema",
        lambda self: (_ for _ in ()).throw(RuntimeError("injected schema failure")),
    )
    with pytest.raises(RuntimeError, match="injected schema failure"):
        build_module.build(store_path=published["store"], catalog_path=published["catalog"])
    assert_untouched(published)
    assert not leftovers(published["store"].parent)


def test_a_failure_after_the_store_is_written_keeps_the_previous_outputs(
    published, monkeypatch
) -> None:
    """The catalog is produced last, so a late failure is the dangerous one."""

    def fail_after_filling(staging_store, target, destination, catalog, official, build_id):
        duckdb.connect(str(staging_store)).close()
        assert staging_store.exists(), "the build must write beside the target, not onto it"
        raise RuntimeError("injected verification failure")

    monkeypatch.setattr(build_module, "_build_into", fail_after_filling)
    with pytest.raises(RuntimeError, match="injected verification failure"):
        build_module.build(store_path=published["store"], catalog_path=published["catalog"])
    assert_untouched(published)
    assert not leftovers(published["store"].parent)


def test_a_failure_publishing_the_second_artefact_rolls_the_first_one_back(
    published, monkeypatch
) -> None:
    """The store and the catalog are one generation: neither may land alone."""
    import canna.store.publish as publish_module

    real_publish = publish_module.publish
    calls: list[Path] = []

    def fail_on_the_catalog(temporary: Path, target: Path) -> None:
        calls.append(target)
        if target == published["catalog"]:
            raise OSError("injected catalog publish failure")
        real_publish(temporary, target)

    monkeypatch.setattr(publish_module, "publish", fail_on_the_catalog)

    def fill_store(staging_store, target, destination, catalog, official, build_id):
        duckdb.connect(str(staging_store)).close()
        return {"build": {"hash_mismatches": []}, "tables": [], "semantic_bindings": []}

    monkeypatch.setattr(build_module, "_build_into", fill_store)
    with pytest.raises(OSError, match="injected catalog publish failure"):
        build_module.build(store_path=published["store"], catalog_path=published["catalog"])

    assert calls == [published["store"], published["catalog"]], "both publishes were attempted"
    assert_untouched(published)
    assert not leftovers(published["store"].parent)


def test_publish_generation_restores_every_earlier_target(tmp_path: Path, monkeypatch) -> None:
    first, second = tmp_path / "first.bin", tmp_path / "second.bin"
    first.write_bytes(b"old-first")
    second.write_bytes(b"old-second")
    staging_first = temp_path(first, "token")
    staging_second = temp_path(second, "token")
    staging_first.write_bytes(b"new-first")
    staging_second.write_bytes(b"new-second")

    import canna.store.publish as publish_module

    real_replace = publish_module.os.replace
    failed_once = False

    def fail_on_second_target(source, destination):
        nonlocal failed_once
        if Path(destination) == second and not failed_once:
            failed_once = True
            raise OSError("injected replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(publish_module.os, "replace", fail_on_second_target)
    with pytest.raises(OSError, match="injected replace failure"):
        publish_generation([(staging_first, first), (staging_second, second)], "token")

    assert first.read_bytes() == b"old-first", "the first target must roll back"
    assert second.read_bytes() == b"old-second"
    assert not [path for path in tmp_path.iterdir() if path.name.startswith(TEMP_PREFIX)
                and "previous" in path.name]


def test_publish_generation_publishes_every_target_together(tmp_path: Path) -> None:
    first, second = tmp_path / "first.bin", tmp_path / "second.bin"
    first.write_bytes(b"old-first")
    second.write_bytes(b"old-second")
    staging_first = temp_path(first, "token")
    staging_second = temp_path(second, "token")
    staging_first.write_bytes(b"new-first")
    staging_second.write_bytes(b"new-second")
    publish_generation([(staging_first, first), (staging_second, second)], "token")
    assert (first.read_bytes(), second.read_bytes()) == (b"new-first", b"new-second")
    assert not leftovers(tmp_path)


def test_publish_generation_refuses_before_moving_anything_if_a_file_is_missing(
    tmp_path: Path,
) -> None:
    first, second = tmp_path / "first.bin", tmp_path / "second.bin"
    first.write_bytes(b"old-first")
    second.write_bytes(b"old-second")
    staging_first = temp_path(first, "token")
    staging_first.write_bytes(b"new-first")
    with pytest.raises(FileNotFoundError):
        publish_generation(
            [(staging_first, first), (temp_path(second, "token"), second)], "token"
        )
    assert first.read_bytes() == b"old-first"
    assert second.read_bytes() == b"old-second"


def test_the_store_and_the_catalog_share_one_build_id(published, monkeypatch) -> None:
    """Both artefacts of a generation must be readable as one build."""
    recorded: dict[str, str] = {}

    def fill_store(staging_store, target, destination, catalog, official, build_id):
        recorded["build_id"] = build_id
        connection = duckdb.connect(str(staging_store))
        connection.execute(
            "CREATE TABLE build_manifest(build_id VARCHAR, generated_at VARCHAR, "
            "store_path VARCHAR, catalog_path VARCHAR)"
        )
        connection.execute("INSERT INTO build_manifest VALUES (?, '', '', '')", [build_id])
        connection.close()
        return {
            "build": {"build_id": build_id, "hash_mismatches": []},
            "tables": [],
            "semantic_bindings": [],
        }

    monkeypatch.setattr(build_module, "_build_into", fill_store)
    build_module.build(store_path=published["store"], catalog_path=published["catalog"])

    catalog = json.loads(published["catalog"].read_text(encoding="utf-8"))
    assert catalog["build"]["build_id"] == recorded["build_id"]
    assert catalog["build"]["store_sha256"]
    connection = duckdb.connect(str(published["store"]), read_only=True)
    try:
        stored = connection.execute("SELECT build_id FROM build_manifest").fetchall()
    finally:
        connection.close()
    assert stored == [(recorded["build_id"],)]


def test_a_concurrent_build_fails_fast_and_changes_nothing(published) -> None:
    lock = published["store"].with_name(published["store"].name + LOCK_SUFFIX)
    lock.write_text("pid=999999\n", encoding="utf-8")
    try:
        with pytest.raises(BuildLockError, match="another build holds"):
            build_module.build(store_path=published["store"], catalog_path=published["catalog"])
        assert_untouched(published)
    finally:
        lock.unlink()


def test_the_lock_is_released_after_a_failed_build(published, monkeypatch) -> None:
    monkeypatch.setattr(
        build_module.StoreBuilder,
        "create_schema",
        lambda self: (_ for _ in ()).throw(RuntimeError("injected failure")),
    )
    with pytest.raises(RuntimeError):
        build_module.build(store_path=published["store"], catalog_path=published["catalog"])
    with build_lock(published["store"]):
        pass


def test_publish_replaces_in_one_step(tmp_path: Path) -> None:
    target = tmp_path / "artefact.bin"
    target.write_bytes(b"old")
    staging = temp_path(target, "token")
    staging.write_bytes(b"new")
    publish(staging, target)
    assert target.read_bytes() == b"new"
    assert not staging.exists()


def test_publish_refuses_an_artefact_with_an_open_write_ahead_log(tmp_path: Path) -> None:
    target = tmp_path / "artefact.duckdb"
    target.write_bytes(b"old")
    staging = temp_path(target, "token")
    staging.write_bytes(b"new")
    Path(f"{staging}.wal").write_bytes(b"pending")
    with pytest.raises(RuntimeError, match="companion"):
        publish(staging, target)
    assert target.read_bytes() == b"old"
    discard(staging)


def test_publishing_removes_a_stale_write_ahead_log_of_the_old_target(tmp_path: Path) -> None:
    target = tmp_path / "artefact.duckdb"
    target.write_bytes(b"old")
    Path(f"{target}.wal").write_bytes(b"stale")
    staging = temp_path(target, "token")
    staging.write_bytes(b"new")
    publish(staging, target)
    assert not Path(f"{target}.wal").exists()


# ------------------------------------------------------- coverage completeness
class CoverageProbe(CoverageMixin):
    def __init__(self, connection) -> None:
        self.connection = connection


def coverage_fixture() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE metric_observation(subject_key VARCHAR, subject_grain VARCHAR, "
        "family_id VARCHAR, metric_id VARCHAR)"
    )
    connection.execute(
        "CREATE TABLE attribute_observation(subject_key VARCHAR, subject_grain VARCHAR, "
        "family_id VARCHAR, attribute_id VARCHAR)"
    )
    connection.execute("CREATE TABLE semantic_coverage(semantic_id VARCHAR, binding_kind VARCHAR)")
    connection.execute(
        "INSERT INTO metric_observation VALUES ('s1', 'product', 'f', 'x:One'), "
        "('s2', 'product', 'f', 'x:Two')"
    )
    connection.execute("INSERT INTO attribute_observation VALUES ('s1', 'product', 'f', 'x:Name')")
    connection.execute(
        "INSERT INTO semantic_coverage VALUES ('x:One', 'metric'), ('x:Two', 'metric'), "
        "('x:Name', 'attribute')"
    )
    return connection


def test_complete_coverage_reports_matching_counts() -> None:
    probe = CoverageProbe(coverage_fixture())
    measured = probe.assert_coverage_complete()
    assert measured["metric"] == {"observed_groups": 2, "coverage_rows": 2}
    assert measured["attribute"] == {"observed_groups": 1, "coverage_rows": 1}


@pytest.mark.parametrize("kind", ["metric", "attribute"])
def test_a_missing_coverage_row_fails_the_build(kind: str) -> None:
    connection = coverage_fixture()
    victim = connection.execute(
        "SELECT semantic_id FROM semantic_coverage WHERE binding_kind = ? ORDER BY 1", [kind]
    ).fetchone()[0]
    connection.execute("DELETE FROM semantic_coverage WHERE semantic_id = ?", [victim])
    with pytest.raises(ValueError, match="semantic coverage is incomplete"):
        CoverageProbe(connection).assert_coverage_complete()


# ------------------------------------------------- first build and mixed states
def fail_publishing(monkeypatch, doomed: Path) -> list[Path]:
    """Let every publish through except the one for ``doomed``."""
    import canna.store.publish as publish_module

    real_publish = publish_module.publish
    calls: list[Path] = []

    def publish_except_doomed(temporary: Path, target: Path) -> None:
        calls.append(target)
        if target == doomed:
            raise OSError("injected publish failure")
        real_publish(temporary, target)

    monkeypatch.setattr(publish_module, "publish", publish_except_doomed)
    return calls


def fill_store(staging_store, target, destination, catalog, official, build_id):
    duckdb.connect(str(staging_store)).close()
    return {"build": {"build_id": build_id, "hash_mismatches": []},
            "tables": [], "semantic_bindings": []}


def test_a_first_build_that_fails_on_the_second_publish_leaves_no_artefact(
    unbuilt, monkeypatch
) -> None:
    """Nothing existed before, so nothing may exist after a failed generation."""
    calls = fail_publishing(monkeypatch, unbuilt["catalog"])
    monkeypatch.setattr(build_module, "_build_into", fill_store)
    with pytest.raises(OSError, match="injected publish failure"):
        build_module.build(store_path=unbuilt["store"], catalog_path=unbuilt["catalog"])

    assert calls == [unbuilt["store"], unbuilt["catalog"]], "both publishes were attempted"
    assert not unbuilt["store"].exists(), "the store must not survive a failed first generation"
    assert not unbuilt["catalog"].exists()
    assert not leftovers(unbuilt["store"].parent)


def test_a_failed_generation_with_only_a_previous_store_restores_it(
    unbuilt, monkeypatch
) -> None:
    unbuilt["store"].write_bytes(PREVIOUS_STORE)
    calls = fail_publishing(monkeypatch, unbuilt["catalog"])
    monkeypatch.setattr(build_module, "_build_into", fill_store)
    with pytest.raises(OSError, match="injected publish failure"):
        build_module.build(store_path=unbuilt["store"], catalog_path=unbuilt["catalog"])

    assert calls == [unbuilt["store"], unbuilt["catalog"]]
    assert unbuilt["store"].read_bytes() == PREVIOUS_STORE
    assert not unbuilt["catalog"].exists()
    assert not leftovers(unbuilt["store"].parent)


def test_a_failed_generation_with_only_a_previous_catalog_restores_it(tmp_path: Path) -> None:
    """The surviving artefact is the second one here, so the first must be removed."""
    store = tmp_path / "query_store.duckdb"
    catalog = tmp_path / "data_catalog.json"
    catalog.write_text(json.dumps(PREVIOUS_CATALOG), encoding="utf-8")
    staging_store = temp_path(store, "token")
    staging_catalog = temp_path(catalog, "token")
    staging_store.write_bytes(b"new store")
    staging_catalog.write_text("{}", encoding="utf-8")

    import canna.store.publish as publish_module

    real_replace = publish_module.os.replace
    failed_once = False

    def fail_on_the_catalog(source, destination):
        nonlocal failed_once
        if Path(destination) == catalog and not failed_once:
            failed_once = True
            raise OSError("injected replace failure")
        real_replace(source, destination)

    original = publish_module.os.replace
    publish_module.os.replace = fail_on_the_catalog
    try:
        with pytest.raises(OSError, match="injected replace failure"):
            publish_generation([(staging_store, store), (staging_catalog, catalog)], "token")
    finally:
        publish_module.os.replace = original

    assert json.loads(catalog.read_text(encoding="utf-8")) == PREVIOUS_CATALOG
    assert not store.exists(), "the newly published store must be removed again"
    assert not leftovers(tmp_path)


def test_publish_generation_removes_every_new_target_it_created(tmp_path: Path) -> None:
    first, second = tmp_path / "first.bin", tmp_path / "second.bin"
    staging_first = temp_path(first, "token")
    staging_second = temp_path(second, "token")
    staging_first.write_bytes(b"new-first")
    staging_second.write_bytes(b"new-second")

    import canna.store.publish as publish_module

    real_replace = publish_module.os.replace

    def fail_on_second(source, destination):
        if Path(destination) == second:
            raise OSError("injected replace failure")
        real_replace(source, destination)

    original = publish_module.os.replace
    publish_module.os.replace = fail_on_second
    try:
        with pytest.raises(OSError, match="injected replace failure"):
            publish_generation([(staging_first, first), (staging_second, second)], "token")
    finally:
        publish_module.os.replace = original

    assert not first.exists() and not second.exists()
    assert not leftovers(tmp_path)


def test_a_rollback_that_cannot_restore_is_reported_with_its_cause(tmp_path: Path) -> None:
    """A half-restored generation must be loud, not silently accepted."""
    first, second = tmp_path / "first.bin", tmp_path / "second.bin"
    first.write_bytes(b"old-first")
    second.write_bytes(b"old-second")
    staging_first = temp_path(first, "token")
    staging_second = temp_path(second, "token")
    staging_first.write_bytes(b"new-first")
    staging_second.write_bytes(b"new-second")

    import canna.store.publish as publish_module

    real_replace = publish_module.os.replace

    def fail_on_second_and_on_restore(source, destination):
        if Path(destination) == second or Path(source).name.startswith(TEMP_PREFIX) and "previous" in Path(source).name:
            raise OSError("injected failure")
        real_replace(source, destination)

    original = publish_module.os.replace
    publish_module.os.replace = fail_on_second_and_on_restore
    try:
        with pytest.raises(PublishRollbackError, match="could not be fully restored") as error:
            publish_generation([(staging_first, first), (staging_second, second)], "token")
    finally:
        publish_module.os.replace = original

    assert isinstance(error.value.__cause__, OSError), "the original failure must stay visible"
