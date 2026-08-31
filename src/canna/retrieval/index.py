"""The Semantic Registry embedding index: build, persist, load, search.

At 519 surface forms a vector database would be infrastructure without a
question to answer. The index is a JSON manifest beside a float32 sidecar, and
a query is an exhaustive cosine scan — reproducible, inspectable, and fast
enough to measure honestly.

Two separations are load-bearing:

* **Provenance.** The manifest records the model, its API contract, the vector
  width, the distance metric, the Semantic Registry content hash, the build
  time and what the build cost. Loading an index whose registry hash or
  provider identity no longer matches is a failure, not a warning, so a stale
  or foreign index can never quietly answer a question.
* **Kind.** ``index_kind`` states that these vectors are registry terms.
  Document vectors — DART filings and the like — are a different corpus with a
  different grain, and this loader refuses them rather than blending the two
  into one similarity space.
"""

from __future__ import annotations

import array
import hashlib
import json
import math
import os
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .embedding import (
    DISTANCE_COSINE,
    DISTANCE_INNER_PRODUCT,
    EmbeddingProvider,
    ProviderIdentity,
    UsageRecord,
    model_profile,
)
from .vocabulary import SurfaceForm, Vocabulary

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INDEX_PATH = ROOT / "data" / "processed" / "semantic_retrieval_index.json"
COMPARISON_INDEX_ROOT = ROOT / "data" / "processed" / "semantic_retrieval_indexes"

INDEX_KIND_REGISTRY_TERMS = "semantic_registry_terms"
SCHEMA_VERSION = 1
VECTOR_DTYPE = "float32"
VECTOR_BYTE_ORDER = "little"


def comparison_index_path(model: str) -> Path:
    """Dedicated manifest path for one approved comparison model."""
    profile = model_profile(model)
    return COMPARISON_INDEX_ROOT / profile.model / "manifest.json"


class IndexError_(RuntimeError):
    """The retrieval index is missing, stale or incompatible."""


@dataclass(frozen=True)
class IndexEntry:
    """One embedded surface form."""

    entry_id: str
    semantic_id: str
    role: str
    locale: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "semantic_id": self.semantic_id,
            "role": self.role,
            "locale": self.locale,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> IndexEntry:
        return cls(
            entry_id=str(payload["entry_id"]),
            semantic_id=str(payload["semantic_id"]),
            role=str(payload["role"]),
            locale=str(payload.get("locale", "")),
            text=str(payload.get("text", "")),
        )


@dataclass(frozen=True)
class ScoredEntry:
    entry: IndexEntry
    similarity: float


def _l2_normalize(vector: Sequence[float]) -> list[float]:
    numeric = [float(value) for value in vector]
    if not numeric or not all(math.isfinite(value) for value in numeric):
        raise IndexError_("a vector must contain finite numeric values")
    norm = math.sqrt(sum(value * value for value in numeric))
    if norm == 0.0:
        raise IndexError_("a zero vector cannot be normalized for cosine similarity")
    return [value / norm for value in numeric]


def _vectors_path(index_path: Path, digest: str) -> Path:
    """Content-addressed sidecar path for generation-safe publication."""
    return index_path.with_name(f"{index_path.stem}.{digest}.vectors.f32")


def _pack(vectors: Sequence[Sequence[float]]) -> bytes:
    flat = array.array("f", [value for vector in vectors for value in vector])
    if array.array("f").itemsize != 4:  # pragma: no cover - platform sanity
        raise IndexError_("float32 packing is unavailable on this platform")
    import sys

    if sys.byteorder != VECTOR_BYTE_ORDER:  # pragma: no cover - platform sanity
        flat.byteswap()
    return flat.tobytes()


def _unpack(payload: bytes, count: int, dimension: int) -> list[list[float]]:
    flat = array.array("f")
    flat.frombytes(payload)
    import sys

    if sys.byteorder != VECTOR_BYTE_ORDER:  # pragma: no cover - platform sanity
        flat.byteswap()
    if len(flat) != count * dimension:
        raise IndexError_(
            f"vector file holds {len(flat)} floats, expected {count * dimension}"
        )
    return [list(flat[row * dimension : (row + 1) * dimension]) for row in range(count)]


class RetrievalIndex:
    """Loaded vectors plus the manifest that says what they are."""

    def __init__(
        self,
        manifest: Mapping[str, object],
        entries: Sequence[IndexEntry],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        if len(entries) != len(vectors):
            raise IndexError_("index entry count does not match vector count")
        self.manifest = dict(manifest)
        self.entries = tuple(entries)
        self._vectors = tuple(tuple(vector) for vector in vectors)
        dimension = self.identity.dimension
        if any(len(vector) != dimension for vector in self._vectors):
            raise IndexError_("an index vector does not match the declared dimension")
        if any(not math.isfinite(value) for vector in self._vectors for value in vector):
            raise IndexError_("the index contains a non-finite vector value")

    @property
    def identity(self) -> ProviderIdentity:
        provider = self.manifest.get("provider") or {}
        if not isinstance(provider, Mapping):
            raise IndexError_("index manifest has no provider identity")
        return ProviderIdentity(
            provider_id=str(provider.get("provider_id", "")),
            model=str(provider.get("model", "")),
            dimension=int(provider.get("dimension", 0)),
            distance_metric=str(provider.get("distance_metric", "")),
            api_contract=str(provider.get("api_contract", "")),
            base_url=str(provider.get("base_url", "")),
            service_contract=str(provider.get("service_contract", "")),
        )

    @property
    def registry_content_hash(self) -> str:
        registry = self.manifest.get("registry") or {}
        return str(registry.get("content_hash", "")) if isinstance(registry, Mapping) else ""

    @property
    def index_kind(self) -> str:
        return str(self.manifest.get("index_kind", ""))

    def summary(self) -> dict[str, Any]:
        """Manifest without the entry list, for embedding in a result."""
        return {
            key: value
            for key, value in self.manifest.items()
            if key not in {"entries", "settings"}
        }

    def vector_for_entry(self, entry_id: str) -> tuple[float, ...]:
        """Return one stored vector for offline, corpus-wide evaluation."""
        for entry, vector in zip(self.entries, self._vectors, strict=True):
            if entry.entry_id == entry_id:
                return vector
        raise IndexError_(f"unknown index entry id: {entry_id}")

    def search(self, query_vector: Sequence[float], top_k: int, threshold: float) -> list[ScoredEntry]:
        """Exhaustive scan under the distance contract recorded in the manifest."""
        identity = self.identity
        query = _prepare_vector(query_vector, identity.distance_metric)
        if len(query) != identity.dimension:
            raise IndexError_(
                f"query vector has {len(query)} dimensions, index has {identity.dimension}"
            )
        scored: list[ScoredEntry] = []
        for entry, vector in zip(self.entries, self._vectors, strict=True):
            similarity = sum(a * b for a, b in zip(query, vector, strict=True))
            if similarity >= threshold:
                scored.append(ScoredEntry(entry, similarity))
        scored.sort(key=lambda item: (-item.similarity, item.entry.entry_id))
        return scored[:top_k]


def build_index(
    vocabulary: Vocabulary,
    provider: EmbeddingProvider,
    unit_price_per_1k_tokens: float | None = None,
) -> tuple[dict[str, Any], list[IndexEntry], list[list[float]]]:
    """Embed every searchable surface form. Any provider failure aborts."""
    forms: tuple[SurfaceForm, ...] = vocabulary.embeddable_forms()
    if not forms:
        raise IndexError_("the semantic registry exposes no embeddable surface forms")
    identity = provider.identity
    started = time.perf_counter()
    raw = provider.embed([form.text for form in forms])
    build_ms = (time.perf_counter() - started) * 1000
    if len(raw) != len(forms):
        raise IndexError_(f"provider returned {len(raw)} vectors for {len(forms)} forms")
    wrong_widths = sorted({len(vector) for vector in raw if len(vector) != identity.dimension})
    if wrong_widths:
        raise IndexError_(
            f"provider returned vector dimensions {wrong_widths}, expected {identity.dimension}"
        )
    vectors = [_prepare_vector(vector, identity.distance_metric) for vector in raw]
    entries = [
        IndexEntry(
            entry_id=form.form_id,
            semantic_id=form.semantic_id,
            role=form.role,
            locale=form.locale,
            text=form.text,
        )
        for form in forms
    ]
    usage: UsageRecord = provider.usage
    manifest: dict[str, Any] = {
        "index_kind": INDEX_KIND_REGISTRY_TERMS,
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": identity.to_dict(),
        "vector_dtype": VECTOR_DTYPE,
        "vector_byte_order": VECTOR_BYTE_ORDER,
        "vector_normalization": _normalization_for(identity.distance_metric),
        "registry": {
            "source_path": vocabulary.source_path,
            "content_hash": vocabulary.content_hash,
            "term_count": len(vocabulary),
            "searchable_term_count": len(vocabulary) - len(vocabulary.unsearchable_ids()),
            "terms_without_searchable_text": list(vocabulary.unsearchable_ids()),
        },
        "entry_count": len(entries),
        "entries_by_role": _count_roles(entries),
        "build_elapsed_ms": round(build_ms, 3),
        "usage": usage.to_dict(unit_price_per_1k_tokens),
    }
    return manifest, entries, vectors


def _count_roles(entries: Sequence[IndexEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.role] = counts.get(entry.role, 0) + 1
    return dict(sorted(counts.items()))


def write_index(
    manifest: Mapping[str, object],
    entries: Sequence[IndexEntry],
    vectors: Sequence[Sequence[float]],
    path: Path | None = None,
) -> Path:
    """Publish a manifest and content-addressed vector generation safely.

    The sidecar name includes its content hash.  It is committed before the
    manifest that vouches for it, so failure while replacing the manifest
    leaves the previous manifest and previous sidecar usable as one generation.
    """
    index_path = path or DEFAULT_INDEX_PATH
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if len(entries) != len(vectors):
        raise IndexError_("cannot write an index with different entry and vector counts")
    provider = manifest.get("provider") or {}
    dimension = int(provider.get("dimension", 0)) if isinstance(provider, Mapping) else 0
    if dimension < 1 or any(len(vector) != dimension for vector in vectors):
        raise IndexError_("cannot write vectors that do not match the manifest dimension")
    payload = _pack(vectors)
    digest = hashlib.sha256(payload).hexdigest()
    vector_path = _vectors_path(index_path, digest)
    vector_existed = vector_path.is_file()
    _atomic_write_bytes(vector_path, payload)

    complete = dict(manifest)
    complete["vectors_path"] = vector_path.name
    complete["vectors_sha256"] = digest
    complete["vectors_bytes"] = len(payload)
    complete["entries"] = [entry.to_dict() for entry in entries]
    try:
        _atomic_write_bytes(
            index_path,
            (json.dumps(complete, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    except BaseException:
        if not vector_existed:
            vector_path.unlink(missing_ok=True)
        raise
    return index_path


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def load_index(path: Path | None = None) -> RetrievalIndex:
    index_path = path or DEFAULT_INDEX_PATH
    if not index_path.is_file():
        raise IndexError_(
            f"retrieval index not found at {index_path}; build it with "
            "scripts/build_retrieval_index.py"
        )
    manifest = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise IndexError_("index manifest must be a JSON object")
    kind = str(manifest.get("index_kind", ""))
    if kind != INDEX_KIND_REGISTRY_TERMS:
        raise IndexError_(
            f"index at {index_path} is of kind {kind!r}; semantic registry retrieval "
            f"only accepts {INDEX_KIND_REGISTRY_TERMS!r}"
        )
    if int(manifest.get("schema_version", 0)) != SCHEMA_VERSION:
        raise IndexError_(
            f"index schema version {manifest.get('schema_version')!r} is not "
            f"{SCHEMA_VERSION}; rebuild the index"
        )
    if str(manifest.get("vector_dtype", "")) != VECTOR_DTYPE:
        raise IndexError_("index vector dtype is not float32")
    if str(manifest.get("vector_byte_order", "")) != VECTOR_BYTE_ORDER:
        raise IndexError_("index vector byte order is incompatible")
    provider = manifest.get("provider") or {}
    if not isinstance(provider, Mapping):
        raise IndexError_("index manifest has no provider identity")
    metric = str(provider.get("distance_metric", ""))
    expected_normalization = _normalization_for(metric)
    if str(manifest.get("vector_normalization", "")) != expected_normalization:
        raise IndexError_(
            "index vector normalization does not match its distance metric "
            f"({metric!r} requires {expected_normalization!r})"
        )
    if not str(manifest.get("generated_at", "")):
        raise IndexError_("index manifest has no generation time")
    registry = manifest.get("registry") or {}
    if not isinstance(registry, Mapping) or not str(registry.get("content_hash", "")):
        raise IndexError_("index manifest has no Semantic Registry hash")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise IndexError_("index manifest has no entries array")
    entries = [IndexEntry.from_dict(item) for item in raw_entries]
    if int(manifest.get("entry_count", -1)) != len(entries):
        raise IndexError_("index entry count does not match its manifest")
    entry_ids = [entry.entry_id for entry in entries]
    if len(entry_ids) != len(set(entry_ids)):
        raise IndexError_("index contains duplicate entry ids")
    vectors_name = str(manifest.get("vectors_path", ""))
    if not vectors_name or Path(vectors_name).name != vectors_name:
        raise IndexError_("index vector path must name a local sidecar")
    vector_path = index_path.parent / vectors_name
    if not vector_path.is_file():
        raise IndexError_(f"vector file {vector_path} is missing")
    payload = vector_path.read_bytes()
    recorded_bytes = int(manifest.get("vectors_bytes", -1))
    if recorded_bytes != len(payload):
        raise IndexError_("vector file size does not match the manifest")
    expected = str(manifest.get("vectors_sha256", ""))
    if not expected:
        raise IndexError_("index manifest has no vector hash")
    actual = hashlib.sha256(payload).hexdigest()
    if expected != actual:
        raise IndexError_("vector file does not match the hash recorded in the manifest")
    dimension = int(provider.get("dimension", 0)) if isinstance(provider, Mapping) else 0
    if dimension < 1:
        raise IndexError_("index manifest does not declare a vector dimension")
    vectors = _unpack(payload, len(entries), dimension)
    manifest.pop("entries", None)
    return RetrievalIndex(manifest, entries, vectors)


def _normalization_for(distance_metric: str) -> str:
    if distance_metric == DISTANCE_COSINE:
        return "l2"
    if distance_metric == DISTANCE_INNER_PRODUCT:
        return "none"
    raise IndexError_(f"unsupported retrieval distance metric: {distance_metric!r}")


def _prepare_vector(vector: Sequence[float], distance_metric: str) -> list[float]:
    if distance_metric == DISTANCE_COSINE:
        return _l2_normalize(vector)
    if distance_metric == DISTANCE_INNER_PRODUCT:
        numeric = [float(value) for value in vector]
        if not numeric or not all(math.isfinite(value) for value in numeric):
            raise IndexError_("a vector must contain finite numeric values")
        return numeric
    raise IndexError_(f"unsupported retrieval distance metric: {distance_metric!r}")


def assert_usable(
    index: RetrievalIndex,
    vocabulary: Vocabulary,
    identity: ProviderIdentity,
) -> None:
    """Refuse an index built from another registry state or another model."""
    if index.registry_content_hash != vocabulary.content_hash:
        raise IndexError_(
            "retrieval index was built from a different Semantic Registry "
            f"(index={index.registry_content_hash[:12]}, "
            f"registry={vocabulary.content_hash[:12]}); rebuild the index"
        )
    compatible, difference = identity.compatible_with(index.identity)
    if not compatible:
        raise IndexError_(
            f"retrieval index was built by a different embedding provider ({difference}); "
            "rebuild the index"
        )
    unknown = sorted(
        {entry.semantic_id for entry in index.entries if not vocabulary.has(entry.semantic_id)}
    )
    if unknown:
        raise IndexError_(f"index references semantic ids absent from the registry: {unknown[:5]}")
    expected_forms = {
        (form.semantic_id, form.role, form.locale, form.text)
        for form in vocabulary.embeddable_forms()
    }
    indexed_forms = {
        (entry.semantic_id, entry.role, entry.locale, entry.text) for entry in index.entries
    }
    if len(index.entries) != len(expected_forms) or expected_forms != indexed_forms:
        missing = sorted(expected_forms - indexed_forms)[:3]
        extra = sorted(indexed_forms - expected_forms)[:3]
        raise IndexError_(
            "retrieval index does not cover the Registry's embeddable forms "
            f"(missing={missing}, extra={extra}); rebuild the index"
        )
