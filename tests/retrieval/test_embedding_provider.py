"""The embedding provider fails loudly or not at all.

Every test here describes a way the outside world can let the system down —
no credential, a refused request, a wrong vector width, a short response — and
requires the same answer: raise. The one exception is a rate limit, which is
the provider asking for patience rather than refusing, and which still raises
once the retries are spent.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from canna.retrieval.embedding import (
    API_KEY_ENV,
    DEFAULT_DIMENSION,
    DEFAULT_MODEL,
    DISTANCE_COSINE,
    DISTANCE_INNER_PRODUCT,
    ENCODING_FORMAT,
    MAX_INPUTS_PER_CALL,
    ClovaStudioEmbeddings,
    CredentialsMissing,
    EmbeddingError,
    UsageRecord,
    model_profile,
)

ROOT = Path(__file__).resolve().parents[2]
RETRIEVAL_SOURCE = ROOT / "src" / "canna" / "retrieval"


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self) -> dict:
        return self._payload


class RecordingClient:
    """Stands in for the OpenAI-compatible client and records what it was sent."""

    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.embeddings = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def vector_payload(dimension: int = DEFAULT_DIMENSION, tokens: int = 7) -> FakeResponse:
    return FakeResponse(
        {
            "data": [{"index": 0, "embedding": [0.1] * dimension}],
            "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
        }
    )


class RateLimit(Exception):
    status_code = 429

    def __str__(self) -> str:
        return "Error code: 429 - rate exceeded"


def test_the_declared_identity_matches_the_confirmed_provider_contract() -> None:
    identity = ClovaStudioEmbeddings().identity
    assert identity.provider_id == "clova_studio"
    assert identity.model == DEFAULT_MODEL == "clir-sts-dolphin"
    assert identity.dimension == DEFAULT_DIMENSION == 1024
    assert identity.distance_metric == DISTANCE_COSINE == "cosine"
    assert identity.base_url.startswith("https://")


def test_the_three_comparison_models_have_distinct_provider_contracts() -> None:
    sts = model_profile("clir-sts-dolphin")
    emb = model_profile("clir-emb-dolphin")
    bge = model_profile("bge-m3")
    assert {sts.dimension, emb.dimension, bge.dimension} == {1024}
    assert sts.distance_metric == bge.distance_metric == DISTANCE_COSINE
    assert emb.distance_metric == DISTANCE_INNER_PRODUCT
    assert bge.service_contract == "clova_embedding_v2_dense"
    assert ClovaStudioEmbeddings(model="bge-m3").identity.service_contract == (
        "clova_embedding_v2_dense"
    )


def test_unknown_models_and_dimension_overrides_fail_closed() -> None:
    with pytest.raises(EmbeddingError, match="unsupported"):
        ClovaStudioEmbeddings(model="invented-model")
    with pytest.raises(EmbeddingError, match="requires 1024"):
        ClovaStudioEmbeddings(model="bge-m3", dimension=512)


def test_a_missing_credential_raises_instead_of_substituting_vectors(monkeypatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    provider = ClovaStudioEmbeddings()
    assert not ClovaStudioEmbeddings.credentials_available()
    with pytest.raises(CredentialsMissing):
        provider.embed(["무엇이든"])


def test_an_empty_credential_is_treated_as_missing(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "   ")
    assert not ClovaStudioEmbeddings.credentials_available()
    with pytest.raises(CredentialsMissing):
        ClovaStudioEmbeddings().embed(["무엇이든"])


def test_requests_honour_the_probed_provider_constraints() -> None:
    client = RecordingClient([vector_payload(), vector_payload()])
    provider = ClovaStudioEmbeddings(client=client)
    provider.embed(["첫번째", "두번째"])
    assert len(client.calls) == 2, "the endpoint takes one text per call"
    for call, text in zip(client.calls, ["첫번째", "두번째"], strict=True):
        assert call["input"] == text, "input must be a bare string, not a list"
        assert call["encoding_format"] == ENCODING_FORMAT
        assert call["model"] == DEFAULT_MODEL
    assert MAX_INPUTS_PER_CALL == 1


def test_a_refused_request_raises(monkeypatch) -> None:
    client = RecordingClient([RuntimeError("Error code: 400 - invalid parameter")])
    provider = ClovaStudioEmbeddings(client=client, rate_limit_retries=0)
    with pytest.raises(EmbeddingError, match="400"):
        provider.embed(["질문"])


def test_a_wrong_vector_width_raises(monkeypatch) -> None:
    client = RecordingClient([vector_payload(dimension=512)])
    provider = ClovaStudioEmbeddings(client=client)
    with pytest.raises(EmbeddingError, match="1024-dimensional"):
        provider.embed(["질문"])


def test_a_non_finite_vector_is_refused() -> None:
    payload = vector_payload().model_dump()
    payload["data"][0]["embedding"][0] = float("nan")
    provider = ClovaStudioEmbeddings(client=RecordingClient([FakeResponse(payload)]))
    with pytest.raises(EmbeddingError, match="non-finite"):
        provider.embed(["질문"])


def test_an_empty_embedding_raises() -> None:
    client = RecordingClient([FakeResponse({"data": [{"index": 0, "embedding": []}], "usage": {}})])
    with pytest.raises(EmbeddingError, match="empty embedding"):
        ClovaStudioEmbeddings(client=client).embed(["질문"])


def test_a_short_response_raises() -> None:
    client = RecordingClient([FakeResponse({"data": [], "usage": {}})])
    with pytest.raises(EmbeddingError, match="0 vectors"):
        ClovaStudioEmbeddings(client=client).embed(["질문"])


def test_a_rate_limit_is_retried_then_still_fails() -> None:
    slept: list[float] = []
    client = RecordingClient([RateLimit(), RateLimit(), vector_payload()])
    provider = ClovaStudioEmbeddings(client=client, rate_limit_retries=3, sleep=slept.append)
    provider.embed(["질문"])
    assert provider.usage.rate_limit_retries == 2
    assert slept == [2.0, 4.0], "backoff must grow rather than hammer the endpoint"

    exhausted = ClovaStudioEmbeddings(
        client=RecordingClient([RateLimit(), RateLimit()]),
        rate_limit_retries=1,
        sleep=lambda _: None,
    )
    with pytest.raises(EmbeddingError, match="429"):
        exhausted.embed(["질문"])


def test_pacing_waits_between_calls() -> None:
    slept: list[float] = []
    client = RecordingClient([vector_payload(), vector_payload()])
    provider = ClovaStudioEmbeddings(client=client, min_interval_seconds=0.5, sleep=slept.append)
    provider.embed(["하나", "둘"])
    assert provider.usage.throttled_ms > 0.0
    assert slept, "a paced build must actually wait"


def test_usage_records_calls_and_tokens() -> None:
    client = RecordingClient([vector_payload(tokens=7), vector_payload(tokens=11)])
    provider = ClovaStudioEmbeddings(client=client)
    provider.embed(["하나", "둘"])
    usage = provider.usage
    assert usage.calls == 2
    assert usage.texts == 2
    assert usage.total_tokens == 18
    assert usage.tokens_reported


def test_missing_provider_token_counts_are_declared_not_invented() -> None:
    client = RecordingClient([FakeResponse({"data": [{"index": 0, "embedding": [0.1] * 1024}]})])
    provider = ClovaStudioEmbeddings(client=client)
    provider.embed(["질문"])
    assert provider.usage.total_tokens == 0
    assert provider.usage.tokens_reported is False


def test_cost_is_absent_until_a_rate_is_supplied() -> None:
    usage = UsageRecord(calls=10, texts=10, prompt_tokens=100, total_tokens=100)
    assert usage.estimated_cost(None) is None
    assert usage.to_dict()["estimated_cost"] is None
    assert usage.estimated_cost(2.0) == pytest.approx(0.2)


def test_no_runtime_module_fabricates_a_vector() -> None:
    """A structural guard: retrieval may not reach for randomness or a hash-vector."""
    offenders: list[str] = []
    for path in sorted(RETRIEVAL_SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                for name in names:
                    if name.split(".")[0] in {"random", "secrets", "numpy"}:
                        offenders.append(f"{path.name}:{node.lineno} imports {name}")
    assert not offenders, "retrieval must not manufacture vectors: " + "; ".join(offenders)


def test_no_runtime_module_prints_or_writes_the_api_key() -> None:
    for path in sorted(RETRIEVAL_SOURCE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "api_key" in line and any(sink in line for sink in ("print(", "write", "log")):
                pytest.fail(f"{path.name} may expose the api key: {line.strip()}")
