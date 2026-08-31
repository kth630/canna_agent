"""Index reproducibility, provenance and the refusals that keep it honest.

An index is only worth what its manifest can prove. These tests hold the
provenance fields to the contract, and then try four ways to serve a question
from vectors that do not belong to it — a moved registry, another model, a
tampered sidecar, another corpus — and require each to raise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from canna.retrieval.embedding import ProviderIdentity, UsageRecord
from canna.retrieval.index import (
    INDEX_KIND_REGISTRY_TERMS,
    SCHEMA_VERSION,
    IndexError_,
    assert_usable,
    build_index,
    comparison_index_path,
    load_index,
    write_index,
)

from .conftest import StubEmbeddings, synthetic_registry, term

REQUIRED_MANIFEST_KEYS = {
    "index_kind",
    "schema_version",
    "generated_at",
    "provider",
    "registry",
    "entry_count",
    "usage",
    "vector_normalization",
}
REQUIRED_PROVIDER_KEYS = {
    "provider_id",
    "model",
    "dimension",
    "distance_metric",
    "api_contract",
    "service_contract",
}


@pytest.fixture
def small_vocabulary():
    return synthetic_registry(
        [
            term("syn:A", label="첫번째지표", aliases=["첫지표"], definition="첫 번째 설명"),
            term("syn:B", label="두번째지표", definition="두 번째 설명"),
            term("syn:C", label="세번째지표"),
        ]
    )


@pytest.fixture
def built(small_vocabulary, tmp_path: Path):
    provider = StubEmbeddings()
    manifest, entries, vectors = build_index(small_vocabulary, provider)
    path = write_index(manifest, entries, vectors, tmp_path / "index.json")
    return small_vocabulary, provider, path


def vector_sidecar(path: Path) -> Path:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return path.parent / manifest["vectors_path"]


def test_manifest_records_everything_a_rebuild_decision_needs(built) -> None:
    vocabulary, provider, path = built
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert REQUIRED_MANIFEST_KEYS <= manifest.keys()
    assert REQUIRED_PROVIDER_KEYS <= manifest["provider"].keys()
    assert manifest["index_kind"] == INDEX_KIND_REGISTRY_TERMS
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["provider"]["model"] == provider.identity.model
    assert manifest["provider"]["dimension"] == provider.identity.dimension
    assert manifest["provider"]["distance_metric"] == "cosine"
    assert manifest["registry"]["content_hash"] == vocabulary.content_hash
    assert manifest["generated_at"]
    assert manifest["usage"]["calls"] == manifest["entry_count"]


def test_comparison_indexes_are_isolated_by_model() -> None:
    paths = {
        comparison_index_path(model)
        for model in ("clir-sts-dolphin", "clir-emb-dolphin", "bge-m3")
    }
    assert len(paths) == 3
    assert all(path.name == "manifest.json" for path in paths)


def test_manifest_reports_terms_without_searchable_text() -> None:
    vocabulary = synthetic_registry(
        [term("syn:A", label="라벨"), term("syn:Silent")]  # no label, no alias, no definition
    )
    manifest, _, _ = build_index(vocabulary, StubEmbeddings())
    assert manifest["registry"]["terms_without_searchable_text"] == ["syn:Silent"]
    assert manifest["registry"]["searchable_term_count"] == 1


def test_index_covers_every_embeddable_form(built) -> None:
    vocabulary, _, path = built
    index = load_index(path)
    assert {entry.entry_id for entry in index.entries} == {
        form.form_id for form in vocabulary.embeddable_forms()
    }
    assert sum(index.manifest["entries_by_role"].values()) == len(index.entries)


def test_rebuilding_from_the_same_input_reproduces_the_same_vectors(
    small_vocabulary, tmp_path: Path
) -> None:
    first = write_index(*build_index(small_vocabulary, StubEmbeddings()), tmp_path / "a.json")
    second = write_index(*build_index(small_vocabulary, StubEmbeddings()), tmp_path / "b.json")
    assert (
        json.loads(first.read_text("utf-8"))["vectors_sha256"]
        == json.loads(second.read_text("utf-8"))["vectors_sha256"]
    )
    assert vector_sidecar(first).read_bytes() == vector_sidecar(second).read_bytes()


def test_vectors_survive_the_float32_round_trip(built) -> None:
    _, _, path = built
    index = load_index(path)
    for entry, _ in zip(index.entries, index.entries, strict=True):
        assert entry.semantic_id


def test_a_changed_registry_hash_makes_the_index_unusable(built) -> None:
    _, provider, path = built
    index = load_index(path)
    moved = synthetic_registry([term("syn:A", label="완전히다른라벨")])
    with pytest.raises(IndexError_, match="different Semantic Registry"):
        assert_usable(index, moved, provider.identity)


def test_a_different_model_makes_the_index_unusable(built) -> None:
    vocabulary, provider, path = built
    index = load_index(path)
    other = ProviderIdentity(
        provider_id=provider.identity.provider_id,
        model="some-other-model",
        dimension=provider.identity.dimension,
        distance_metric="cosine",
        api_contract=provider.identity.api_contract,
    )
    with pytest.raises(IndexError_, match="different embedding provider"):
        assert_usable(index, vocabulary, other)


def test_a_stub_built_index_is_refused_by_the_production_provider(built) -> None:
    """The test convenience cannot leak into a production answer."""
    from canna.retrieval.embedding import ClovaStudioEmbeddings

    vocabulary, _, path = built
    index = load_index(path)
    with pytest.raises(IndexError_, match="different embedding provider"):
        assert_usable(index, vocabulary, ClovaStudioEmbeddings().identity)


def test_a_different_dimension_makes_the_index_unusable(built) -> None:
    vocabulary, provider, path = built
    index = load_index(path)
    other = ProviderIdentity(
        provider_id=provider.identity.provider_id,
        model=provider.identity.model,
        dimension=provider.identity.dimension + 1,
        distance_metric="cosine",
        api_contract=provider.identity.api_contract,
    )
    with pytest.raises(IndexError_, match="different embedding provider"):
        assert_usable(index, vocabulary, other)


def test_a_tampered_vector_file_is_refused(built) -> None:
    _, _, path = built
    vectors = vector_sidecar(path)
    payload = bytearray(vectors.read_bytes())
    payload[0] ^= 0xFF
    vectors.write_bytes(bytes(payload))
    with pytest.raises(IndexError_, match="does not match the hash"):
        load_index(path)


def test_a_missing_vector_file_is_refused(built) -> None:
    _, _, path = built
    vector_sidecar(path).unlink()
    with pytest.raises(IndexError_, match="missing"):
        load_index(path)


def test_a_document_vector_index_is_refused(built) -> None:
    """DART document vectors are a different corpus and never blend in here."""
    _, _, path = built
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["index_kind"] = "dart_documents"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(IndexError_, match="only accepts"):
        load_index(path)


def test_an_older_schema_version_is_refused(built) -> None:
    _, _, path = built
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["schema_version"] = SCHEMA_VERSION - 1
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(IndexError_, match="schema version"):
        load_index(path)


def test_an_index_naming_unknown_terms_is_refused(built) -> None:
    _vocabulary, provider, path = built
    index = load_index(path)
    smaller = synthetic_registry([term("syn:A", label="첫번째지표", aliases=["첫지표"],
                                       definition="첫 번째 설명")])
    with pytest.raises(IndexError_):
        assert_usable(index, smaller, provider.identity)


def test_a_missing_index_reports_how_to_build_one(tmp_path: Path) -> None:
    with pytest.raises(IndexError_, match="build_retrieval_index"):
        load_index(tmp_path / "absent.json")


def test_search_honours_threshold_and_top_k(built) -> None:
    _, provider, path = built
    index = load_index(path)
    query = provider.embed(["첫번째지표"])[0]
    everything = index.search(query, top_k=100, threshold=-1.0)
    assert len(everything) == len(index.entries)
    assert everything[0].similarity == pytest.approx(1.0)
    assert everything == sorted(
        everything, key=lambda item: (-item.similarity, item.entry.entry_id)
    )
    assert len(index.search(query, top_k=2, threshold=-1.0)) == 2
    assert index.search(query, top_k=100, threshold=1.01) == []


def test_a_query_of_the_wrong_width_is_refused(built) -> None:
    _, _, path = built
    index = load_index(path)
    with pytest.raises(IndexError_, match="dimensions"):
        index.search([0.1, 0.2, 0.3], top_k=5, threshold=0.0)


def test_a_zero_vector_is_refused_rather_than_scored(built) -> None:
    _, provider, path = built
    index = load_index(path)
    with pytest.raises(IndexError_, match="zero vector"):
        index.search([0.0] * provider.identity.dimension, top_k=5, threshold=0.0)


def test_inner_product_index_keeps_raw_vectors_and_scores_without_l2(tmp_path) -> None:
    vocabulary = synthetic_registry(
        [term("syn:A", label="하나"), term("syn:B", label="둘")]
    )

    class InnerProductProvider:
        def __init__(self) -> None:
            self._usage = UsageRecord()

        @property
        def identity(self):
            return ProviderIdentity(
                provider_id="test_inner_product",
                model="test-ip",
                dimension=2,
                distance_metric="inner_product",
                api_contract="test.v1",
            )

        @property
        def usage(self):
            return self._usage

        def embed(self, texts):
            vectors = [[2.0, 0.0], [1.0, 1.0]][: len(texts)]
            for _text in texts:
                self._usage.add(texts=1, prompt=1, total=1, elapsed_ms=0, reported=True)
            return vectors

    provider = InnerProductProvider()
    manifest, entries, vectors = build_index(vocabulary, provider)
    assert manifest["vector_normalization"] == "none"
    assert vectors[0] == [2.0, 0.0]
    path = write_index(manifest, entries, vectors, tmp_path / "ip.json")
    index = load_index(path)
    scored = index.search([3.0, 0.0], top_k=2, threshold=-1.0)
    assert scored[0].similarity == pytest.approx(6.0)


def test_a_failed_build_leaves_the_previous_index_in_place(small_vocabulary, tmp_path: Path) -> None:
    path = write_index(*build_index(small_vocabulary, StubEmbeddings()), tmp_path / "index.json")
    before = path.read_bytes()

    class FailingProvider(StubEmbeddings):
        def embed(self, texts):
            raise RuntimeError("provider is down")

    with pytest.raises(RuntimeError, match="provider is down"):
        build_index(small_vocabulary, FailingProvider())
    assert path.read_bytes() == before


def test_a_failed_manifest_publish_leaves_the_previous_generation_usable(
    small_vocabulary, tmp_path: Path, monkeypatch
) -> None:
    import canna.retrieval.index as index_module

    path = write_index(*build_index(small_vocabulary, StubEmbeddings()), tmp_path / "index.json")
    before_manifest = path.read_bytes()
    before_sidecar = vector_sidecar(path)
    original_write = index_module._atomic_write_bytes

    def fail_manifest(target, payload):
        if target == path:
            raise OSError("injected manifest publish failure")
        return original_write(target, payload)

    monkeypatch.setattr(index_module, "_atomic_write_bytes", fail_manifest)
    changed = synthetic_registry(
        [term("syn:Changed", label="바뀐표면형", aliases=["다른표면형"])]
    )
    with pytest.raises(OSError, match="injected"):
        write_index(*build_index(changed, StubEmbeddings()), path)

    assert path.read_bytes() == before_manifest
    assert vector_sidecar(path) == before_sidecar
    loaded = load_index(path)
    assert_usable(loaded, small_vocabulary, StubEmbeddings().identity)


def test_manifest_without_a_vector_hash_is_refused(built) -> None:
    _, _, path = built
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.pop("vectors_sha256")
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(IndexError_, match="no vector hash"):
        load_index(path)


def test_index_must_cover_every_registry_surface_form(built) -> None:
    vocabulary, provider, path = built
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["entries"][-1]["text"] = "registry에 없는 변조된 표면형"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    index = load_index(path)
    with pytest.raises(IndexError_, match="does not cover"):
        assert_usable(index, vocabulary, provider.identity)
