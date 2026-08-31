"""Shared retrieval test material.

The stub provider lives here, in the tests, and never in ``src``. Runtime code
has no substitute-vector path at all: if it did, a missing credential would
quietly degrade into confident nonsense. Because the stub declares its own
provider identity, an index it builds can never be searched by the real CLOVA
provider — the compatibility check rejects it — so this convenience cannot leak
into a production answer.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from pathlib import Path

import pytest

from canna.retrieval.embedding import ProviderIdentity, UsageRecord
from canna.retrieval.normalize import normalize
from canna.retrieval.settings import EmbeddingSettings, RetrievalSettings, RuleSettings
from canna.retrieval.vocabulary import Vocabulary, build_vocabulary, load_vocabulary

ROOT = Path(__file__).resolve().parents[2]

STUB_PROVIDER_ID = "test_stub"
STUB_MODEL = "deterministic-character-hash"
STUB_DIMENSION = 64


class StubEmbeddings:
    """Deterministic character-shingle vectors. Test material, never runtime.

    The vectors carry a crude but real notion of similarity: texts sharing
    character bigrams land closer together. That is enough to exercise ranking,
    thresholds and merging without spending a live call, and it is deliberately
    a different provider identity from anything production uses.
    """

    def __init__(self, dimension: int = STUB_DIMENSION) -> None:
        self._dimension = dimension
        self._usage = UsageRecord()

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider_id=STUB_PROVIDER_ID,
            model=STUB_MODEL,
            dimension=self._dimension,
            distance_metric="cosine",
            api_contract="test.stub.v1",
        )

    @property
    def usage(self) -> UsageRecord:
        return self._usage

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vectors.append(self._vector(text))
            self._usage.add(texts=1, prompt=len(text), total=len(text), elapsed_ms=0.0, reported=True)
        return vectors

    def _vector(self, text: str) -> list[float]:
        normalized = normalize(text) or "empty"
        vector = [0.0] * self._dimension
        shingles = [normalized[index : index + 2] for index in range(max(1, len(normalized) - 1))]
        for shingle in shingles:
            digest = hashlib.sha256(shingle.encode("utf-8")).digest()
            vector[digest[0] % self._dimension] += 1.0
        if not any(vector):  # pragma: no cover - defensive
            vector[0] = 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector]


@pytest.fixture(scope="session")
def registry_available() -> bool:
    return (ROOT / "data" / "processed" / "semantic_registry.json").is_file()


@pytest.fixture(scope="session")
def vocabulary(registry_available: bool) -> Vocabulary:
    if not registry_available:
        pytest.skip("semantic registry has not been generated in this workspace")
    return load_vocabulary()


@pytest.fixture
def settings() -> RetrievalSettings:
    return RetrievalSettings(
        basis="test_fixture",
        rule=RuleSettings(),
        embedding=EmbeddingSettings(similarity_threshold=0.0, top_k=25),
    )


def synthetic_registry(terms: list[dict[str, object]]) -> Vocabulary:
    """A registry payload built in the test, for rules that must hold generally."""
    payload = {
        "prefixes": {"syn": "https://canna.local/ontology/synthetic#"},
        "counts": {"total": len(terms)},
        "ontology_files": [],
        "terms": terms,
    }
    return build_vocabulary(json.loads(json.dumps(payload, ensure_ascii=False)), "synthetic")


def term(
    semantic_id: str,
    label: str = "",
    aliases: Sequence[str] = (),
    definition: str = "",
    kind: str = "metric",
    families: Sequence[str] = (),
) -> dict[str, object]:
    return {
        "semantic_id": semantic_id,
        "kind": kind,
        "labels": {"ko": label} if label else {},
        "aliases": list(aliases),
        "definition": definition,
        "families": list(families),
        "grains": ["product"],
        "period_code": "",
        "unit_code": "none",
        "currency_policy": "",
        "allowed_operations": ["filter"],
        "comparison_group": "",
        "meaning_status": "",
        "evidence_requirements": [],
        "domain": [],
        "range": [],
        "inverse_of": "",
    }
