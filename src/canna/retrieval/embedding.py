"""Embedding provider boundary for Naver CLOVA Studio.

There is exactly one way this module may fail: loudly. A missing credential, a
refused request, a wrong vector width or a short response raises, and no code
path anywhere fabricates, zero-fills, hashes or randomises a vector to keep a
build or a query alive. A retrieval index that silently contained invented
vectors would produce confident nonsense that looks identical to a real result,
which is worse than not having an index at all.

The provider identity — id, model, dimension, distance metric, API contract —
travels with every vector it produces, so an index built by one provider can
never be searched by another.
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

# Provider contract values, not data or answer content.
PROVIDER_CLOVA_STUDIO = "clova_studio"
DEFAULT_MODEL = "clir-sts-dolphin"
DEFAULT_DIMENSION = 1024
DISTANCE_COSINE = "cosine"
DISTANCE_INNER_PRODUCT = "inner_product"
API_CONTRACT = "openai.embeddings.v1"
# Observed provider constraints, probed against the live endpoint on 2026-08-31:
# a list ``input`` is rejected with 40001 "convert error", and the default
# base64 ``encoding_format`` of the openai client is rejected with 40001
# "Invalid parameter: encoding_format". One text per call is the provider's
# limit, not a tuning choice.
MAX_INPUTS_PER_CALL = 1
ENCODING_FORMAT = "float"
# A full index build is several hundred sequential calls and the endpoint
# rate-limits (42901) well before that. Pacing and bounded backoff are how the
# build stays inside the provider's budget; they never soften a failure, which
# still raises once the retries are spent.
DEFAULT_MIN_INTERVAL_SECONDS = 0.0
DEFAULT_RATE_LIMIT_RETRIES = 6
RATE_LIMIT_BACKOFF_SECONDS = 2.0
RATE_LIMIT_BACKOFF_CAP_SECONDS = 60.0
API_KEY_ENV = "CLOVASTUDIO_API_KEY"
BASE_URL_ENV = "CLOVASTUDIO_API_BASE_URL"
DEFAULT_BASE_URL = "https://clovastudio.stream.ntruss.com/v1/openai"


@dataclass(frozen=True)
class ModelProfile:
    """Provider-published vector contract for one comparison model."""

    model: str
    api_contract: str
    service_contract: str
    dimension: int
    distance_metric: str
    vector_normalization: str


MODEL_PROFILES: dict[str, ModelProfile] = {
    "clir-sts-dolphin": ModelProfile(
        model="clir-sts-dolphin",
        api_contract=API_CONTRACT,
        service_contract="clova_embedding_v1",
        dimension=1024,
        distance_metric=DISTANCE_COSINE,
        vector_normalization="l2",
    ),
    "clir-emb-dolphin": ModelProfile(
        model="clir-emb-dolphin",
        api_contract=API_CONTRACT,
        service_contract="clova_embedding_v1",
        dimension=1024,
        distance_metric=DISTANCE_INNER_PRODUCT,
        vector_normalization="none",
    ),
    "bge-m3": ModelProfile(
        model="bge-m3",
        api_contract=API_CONTRACT,
        service_contract="clova_embedding_v2_dense",
        dimension=1024,
        distance_metric=DISTANCE_COSINE,
        vector_normalization="l2",
    ),
}


def model_profile(model: str) -> ModelProfile:
    """Return the approved comparison contract; unknown models fail closed."""
    try:
        return MODEL_PROFILES[model]
    except KeyError as error:
        supported = ", ".join(sorted(MODEL_PROFILES))
        raise EmbeddingError(
            f"unsupported CLOVA embedding model {model!r}; supported models: {supported}"
        ) from error


class EmbeddingError(RuntimeError):
    """The embedding provider could not produce usable vectors."""


class CredentialsMissing(EmbeddingError):
    """No API key is configured. This is a failure, never a fallback."""


@dataclass(frozen=True)
class ProviderIdentity:
    """What produced a vector. Recorded in the index and checked on load."""

    provider_id: str
    model: str
    dimension: int
    distance_metric: str
    api_contract: str
    base_url: str = ""
    service_contract: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "dimension": self.dimension,
            "distance_metric": self.distance_metric,
            "api_contract": self.api_contract,
            "base_url": self.base_url,
            "service_contract": self.service_contract,
        }

    def compatible_with(self, other: ProviderIdentity) -> tuple[bool, str]:
        for attribute in (
            "provider_id",
            "model",
            "dimension",
            "distance_metric",
            "api_contract",
            "base_url",
            "service_contract",
        ):
            mine = getattr(self, attribute)
            theirs = getattr(other, attribute)
            # schema-v1 indexes built before model comparison recorded the
            # model and transport API contract but not this additional service
            # discriminator. They remain usable for the same model; every new
            # build writes the field.
            if attribute == "service_contract" and (not mine or not theirs):
                continue
            if attribute == "base_url":
                mine = mine.rstrip("/")
                theirs = theirs.rstrip("/")
            if mine != theirs:
                return False, f"{attribute}: index={theirs!r} query={mine!r}"
        return True, ""


@dataclass
class UsageRecord:
    """Calls, tokens and time spent against the live API."""

    calls: int = 0
    texts: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0
    elapsed_ms: float = 0.0
    tokens_reported: bool = True
    rate_limit_retries: int = 0
    throttled_ms: float = 0.0

    def add(self, *, texts: int, prompt: int, total: int, elapsed_ms: float, reported: bool) -> None:
        self.calls += 1
        self.texts += texts
        self.prompt_tokens += prompt
        self.total_tokens += total
        self.elapsed_ms += elapsed_ms
        self.tokens_reported = self.tokens_reported and reported

    def estimated_cost(self, unit_price_per_1k_tokens: float | None) -> float | None:
        """Cost, or ``None`` when no rate has been supplied.

        A published price is not guessed here. Without a configured rate the
        report carries token counts and an explicit absence of cost.
        """
        if unit_price_per_1k_tokens is None:
            return None
        return (self.total_tokens / 1000.0) * unit_price_per_1k_tokens

    def to_dict(self, unit_price_per_1k_tokens: float | None = None) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "texts": self.texts,
            "prompt_tokens": self.prompt_tokens,
            "total_tokens": self.total_tokens,
            "tokens_reported_by_provider": self.tokens_reported,
            "rate_limit_retries": self.rate_limit_retries,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "throttled_ms": round(self.throttled_ms, 3),
            "unit_price_per_1k_tokens": unit_price_per_1k_tokens,
            "estimated_cost": self.estimated_cost(unit_price_per_1k_tokens),
        }


class EmbeddingProvider(Protocol):
    """Anything that can turn texts into vectors of a declared identity."""

    @property
    def identity(self) -> ProviderIdentity: ...

    @property
    def usage(self) -> UsageRecord: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class ClovaStudioEmbeddings:
    """Naver CLOVA Studio embeddings over its OpenAI-compatible endpoint."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        dimension: int | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        rate_limit_retries: int = DEFAULT_RATE_LIMIT_RETRIES,
        sleep: Any = time.sleep,
        client: Any | None = None,
    ) -> None:
        self._profile = model_profile(model)
        self._model = model
        requested_dimension = self._profile.dimension if dimension is None else dimension
        if requested_dimension != self._profile.dimension:
            raise EmbeddingError(
                f"model {model} requires {self._profile.dimension} dimensions, "
                f"not {requested_dimension}"
            )
        self._dimension = requested_dimension
        self._timeout = timeout
        self._max_retries = max_retries
        self._min_interval = max(0.0, min_interval_seconds)
        self._rate_limit_retries = max(0, rate_limit_retries)
        self._sleep = sleep
        self._next_call_at = 0.0
        self._client = client
        self._usage = UsageRecord()
        self._base_url = os.environ.get(BASE_URL_ENV, "").strip() or DEFAULT_BASE_URL

    @staticmethod
    def credentials_available() -> bool:
        return bool(os.environ.get(API_KEY_ENV, "").strip())

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            provider_id=PROVIDER_CLOVA_STUDIO,
            model=self._model,
            dimension=self._dimension,
            distance_metric=self._profile.distance_metric,
            api_contract=self._profile.api_contract,
            base_url=self._base_url,
            service_contract=self._profile.service_contract,
        )

    @property
    def max_inputs_per_call(self) -> int:
        return MAX_INPUTS_PER_CALL

    @property
    def usage(self) -> UsageRecord:
        return self._usage

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        api_key = os.environ.get(API_KEY_ENV, "").strip()
        if not api_key:
            raise CredentialsMissing(
                f"{API_KEY_ENV} is not set; embedding retrieval fails instead of "
                "producing substitute vectors"
            )
        try:
            from openai import OpenAI
        except ImportError as error:  # pragma: no cover - dependency is declared
            raise EmbeddingError("the openai client package is not installed") from error
        self._client = OpenAI(
            api_key=api_key,
            base_url=self._base_url,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )
        return self._client

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text, in order. One API call per text, by provider rule."""
        if not texts:
            return []
        client = self._ensure_client()
        return [self._embed_one(client, text) for text in texts]

    def _throttle(self) -> None:
        if self._min_interval <= 0.0:
            return
        now = time.monotonic()
        wait = self._next_call_at - now
        if wait > 0:
            self._sleep(wait)
            self._usage.throttled_ms += wait * 1000
        self._next_call_at = max(now, self._next_call_at) + self._min_interval

    def _embed_one(self, client: Any, text: str) -> list[float]:
        started = time.perf_counter()
        attempt = 0
        while True:
            self._throttle()
            try:
                response = client.embeddings.create(
                    input=text, model=self._model, encoding_format=ENCODING_FORMAT
                )
                break
            except Exception as error:
                if _is_rate_limit(error) and attempt < self._rate_limit_retries:
                    delay = min(
                        RATE_LIMIT_BACKOFF_SECONDS * (2**attempt),
                        RATE_LIMIT_BACKOFF_CAP_SECONDS,
                    )
                    self._usage.rate_limit_retries += 1
                    self._sleep(delay)
                    self._next_call_at = time.monotonic() + self._min_interval
                    attempt += 1
                    continue
                raise EmbeddingError(
                    f"CLOVA Studio embedding request failed for model {self._model}: {error}"
                ) from error
        elapsed_ms = (time.perf_counter() - started) * 1000
        payload = response if isinstance(response, dict) else response.model_dump()
        data = payload.get("data") or []
        if len(data) != 1:
            raise EmbeddingError(f"CLOVA Studio returned {len(data)} vectors for one input")
        usage = payload.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or prompt_tokens)
        self._usage.add(
            texts=1,
            prompt=prompt_tokens,
            total=total_tokens,
            elapsed_ms=elapsed_ms,
            reported=bool(usage),
        )
        vector = data[0].get("embedding")
        if not isinstance(vector, list) or not vector:
            raise EmbeddingError("CLOVA Studio returned an empty embedding")
        if len(vector) != self._dimension:
            raise EmbeddingError(
                f"expected {self._dimension}-dimensional vectors from {self._model}, "
                f"received {len(vector)}"
            )
        numeric = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in numeric):
            raise EmbeddingError("CLOVA Studio returned a non-finite embedding value")
        return numeric


def _is_rate_limit(error: Exception) -> bool:
    """Whether a provider failure is a throttle rather than a refusal."""
    status = getattr(error, "status_code", None)
    if status == 429:
        return True
    return "42901" in str(error) or "rate exceeded" in str(error).lower()


def load_dotenv_if_present(root: Any) -> None:
    """Read ``.env`` for local runs. Keys are never logged or written out."""
    from pathlib import Path

    env_path = Path(root) / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional locally
        return
    load_dotenv(env_path, override=False)
