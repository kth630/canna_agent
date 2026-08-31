"""The Retriever merges candidates and decides nothing.

Two properties are defended hardest here:

* an embedding neighbour, however high its similarity, never becomes grounding
  evidence and never wins the merged order over a term the question named;
* the result carries no table, column, join, SQL or plan, so nothing downstream
  can mistake a candidate for something ready to execute.
"""

from __future__ import annotations

import json

import pytest

from canna.retrieval.candidates import (
    FORBIDDEN_PAYLOAD_KEYS,
    PATH_UNAVAILABLE,
    REASON_COMPETING_MEANINGS,
    REASON_NO_CANDIDATES,
    REASON_NO_GROUNDING_EVIDENCE,
    SOURCE_EMBEDDING,
    SOURCE_RULE,
    STATUS_AMBIGUOUS,
    STATUS_CANDIDATES,
    STATUS_UNRESOLVED,
)
from canna.retrieval.embedding import EmbeddingError, ProviderIdentity, UsageRecord
from canna.retrieval.index import build_index, load_index, write_index
from canna.retrieval.retriever import Retriever
from canna.retrieval.settings import EmbeddingSettings, RetrievalSettings, RuleSettings
from canna.retrieval.vocabulary import TIER_PHRASE, TIER_SUBSTRING

from .conftest import StubEmbeddings, synthetic_registry, term


def make_retriever(vocabulary, tmp_path, settings=None, with_embedding=True):
    settings = settings or RetrievalSettings(
        basis="test_fixture", embedding=EmbeddingSettings(similarity_threshold=0.0, top_k=50)
    )
    if not with_embedding:
        return Retriever(vocabulary, settings)
    provider = StubEmbeddings()
    path = write_index(*build_index(vocabulary, provider), tmp_path / "index.json")
    return Retriever(vocabulary, settings, load_index(path), StubEmbeddings())


@pytest.fixture
def family_vocabulary():
    """Two families that share a metric name, plus period neighbours."""
    return synthetic_registry(
        [
            term("syn:FamA", label="가군상품", kind="class", families=["a"]),
            term("syn:FamB", label="나군상품", kind="class", families=["b"]),
            term("syn:A.Ret1Y", label="1년수익률", families=["a"]),
            term("syn:B.Ret1Y", label="1년수익률", families=["b"]),
            term("syn:A.Ret3Y", label="3년수익률", families=["a"]),
            term("syn:A.Fee", label="총보수", aliases=["보수"], families=["a"]),
        ]
    )


def test_a_question_naming_a_term_yields_a_grounding_candidate(family_vocabulary, tmp_path) -> None:
    retriever = make_retriever(family_vocabulary, tmp_path)
    result = retriever.retrieve("3년수익률 알려줘")
    candidate = result.candidate("syn:A.Ret3Y")
    assert candidate is not None
    assert candidate.grounding_eligible
    assert candidate.source(SOURCE_RULE).match_tier == TIER_PHRASE


def test_a_question_naming_nothing_is_unresolved(family_vocabulary, tmp_path) -> None:
    settings = RetrievalSettings(
        basis="test_fixture", embedding=EmbeddingSettings(similarity_threshold=0.99, top_k=10)
    )
    retriever = make_retriever(family_vocabulary, tmp_path, settings)
    result = retriever.retrieve("완전히 무관한 다른 이야기입니다")
    assert result.status == STATUS_UNRESOLVED
    assert result.reasons == (REASON_NO_CANDIDATES,)
    assert result.candidates == ()


def test_competing_meanings_are_reported_not_chosen(family_vocabulary, tmp_path) -> None:
    retriever = make_retriever(family_vocabulary, tmp_path)
    result = retriever.retrieve("1년수익률이 궁금해")
    assert result.status == STATUS_AMBIGUOUS
    assert REASON_COMPETING_MEANINGS in result.reasons
    assert [item.semantic_ids for item in result.ambiguous_expressions] == [
        ("syn:A.Ret1Y", "syn:B.Ret1Y")
    ]
    # Both survive; the Retriever narrows nothing on its own.
    assert {"syn:A.Ret1Y", "syn:B.Ret1Y"} <= set(result.semantic_ids)


def test_normalized_equivalent_forms_are_still_reported_as_competing(tmp_path) -> None:
    vocabulary = synthetic_registry(
        [term("syn:A", label="가 나 다"), term("syn:B", aliases=["가나다"])]
    )
    result = make_retriever(vocabulary, tmp_path).retrieve("가나다")
    assert result.status == STATUS_AMBIGUOUS
    assert result.ambiguous_expressions[0].semantic_ids == ("syn:A", "syn:B")


def test_proposal_only_evidence_is_ambiguous_never_confirmed(tmp_path) -> None:
    vocabulary = synthetic_registry([term("syn:A", label="가나다라마바사아자")])
    retriever = make_retriever(vocabulary, tmp_path)
    result = retriever.retrieve("가나다라마바 라고 들었다")
    assert result.status == STATUS_AMBIGUOUS
    assert REASON_NO_GROUNDING_EVIDENCE in result.reasons
    assert result.grounding_eligible == ()
    assert result.candidate("syn:A").source(SOURCE_RULE).match_tier == TIER_SUBSTRING


def test_embedding_candidates_are_never_grounding_eligible(family_vocabulary, tmp_path) -> None:
    retriever = make_retriever(family_vocabulary, tmp_path)
    result = retriever.retrieve("총보수")
    embedding_only = [
        candidate
        for candidate in result.candidates
        if candidate.source_names == (SOURCE_EMBEDDING,)
    ]
    assert embedding_only, "the embedding path should contribute candidates of its own"
    for candidate in embedding_only:
        assert not candidate.grounding_eligible
        assert candidate.source(SOURCE_EMBEDDING).grounding_eligible is False


def test_embedding_top_k_is_applied_after_stable_id_deduplication(tmp_path) -> None:
    class FixedEmbeddings:
        def __init__(self) -> None:
            self._usage = UsageRecord()

        @property
        def identity(self):
            return ProviderIdentity("fixed", "fixed", 2, "cosine", "test.fixed.v1")

        @property
        def usage(self):
            return self._usage

        def embed(self, texts):
            vectors = []
            for text in texts:
                vector = [0.99, 0.1] if text == "마바사" else [1.0, 0.0]
                vectors.append(vector)
                self._usage.add(texts=1, prompt=1, total=1, elapsed_ms=0.0, reported=True)
            return vectors

    vocabulary = synthetic_registry(
        [
            term("syn:A", label="가나다", aliases=["가나다별칭1", "가나다별칭2"]),
            term("syn:B", label="마바사"),
        ]
    )
    builder = FixedEmbeddings()
    path = write_index(*build_index(vocabulary, builder), tmp_path / "index.json")
    settings = RetrievalSettings(
        basis="test_fixture",
        embedding=EmbeddingSettings(similarity_threshold=-1.0, top_k=2),
    )
    result = Retriever(vocabulary, settings, load_index(path), FixedEmbeddings()).retrieve(
        "embedding-query"
    )
    embedded = result.from_source(SOURCE_EMBEDDING)
    assert [candidate.semantic_id for candidate in embedded] == ["syn:A", "syn:B"]


def test_the_top_embedding_hit_does_not_outrank_a_named_term(family_vocabulary, tmp_path) -> None:
    retriever = make_retriever(family_vocabulary, tmp_path)
    result = retriever.retrieve("총보수 알려줘")
    assert result.candidates[0].semantic_id == "syn:A.Fee"
    assert result.candidates[0].grounding_eligible
    tail = [candidate for candidate in result.candidates if not candidate.grounding_eligible]
    grounded = [candidate for candidate in result.candidates if candidate.grounding_eligible]
    assert [candidate.merged_rank for candidate in grounded] < [
        candidate.merged_rank for candidate in tail
    ] or not tail


def test_both_paths_are_recorded_separately_on_a_shared_candidate(
    family_vocabulary, tmp_path
) -> None:
    retriever = make_retriever(family_vocabulary, tmp_path)
    result = retriever.retrieve("총보수")
    candidate = result.candidate("syn:A.Fee")
    assert candidate.source_names == (SOURCE_EMBEDDING, SOURCE_RULE)
    rule = candidate.source(SOURCE_RULE)
    embedding = candidate.source(SOURCE_EMBEDDING)
    assert rule.matched_expression and rule.rank >= 1 and rule.match_tier
    assert embedding.matched_expression and embedding.rank >= 1
    assert embedding.detail["model"]
    assert embedding.detail["distance_metric"] == "cosine"


def test_each_path_reports_its_own_count_and_latency(family_vocabulary, tmp_path) -> None:
    retriever = make_retriever(family_vocabulary, tmp_path)
    result = retriever.retrieve("총보수 알려줘")
    sources = {path.source for path in result.paths}
    assert sources == {SOURCE_RULE, SOURCE_EMBEDDING}
    for path in result.paths:
        assert path.latency_ms >= 0.0
        assert path.candidate_count >= 0
    embedding_path = next(path for path in result.paths if path.source == SOURCE_EMBEDDING)
    assert embedding_path.detail["entries_scanned"] == len(retriever.index.entries)


def test_rule_only_retrieval_is_a_configuration_not_a_fallback(family_vocabulary) -> None:
    retriever = Retriever(family_vocabulary, RetrievalSettings(basis="test_fixture"))
    assert not retriever.embedding_enabled
    result = retriever.retrieve("총보수 알려줘")
    assert {path.source for path in result.paths} == {SOURCE_RULE}
    assert result.index_manifest == {}


def test_embedding_failure_is_explicit_and_does_not_remove_rule_results(
    family_vocabulary, tmp_path
) -> None:
    class UnavailableEmbeddings(StubEmbeddings):
        def embed(self, texts):
            raise EmbeddingError("provider unavailable")

    builder = StubEmbeddings()
    path = write_index(*build_index(family_vocabulary, builder), tmp_path / "index.json")
    retriever = Retriever(
        family_vocabulary,
        RetrievalSettings(basis="test_fixture"),
        load_index(path),
        UnavailableEmbeddings(),
    )
    result = retriever.retrieve("총보수 알려줘")
    assert result.candidate("syn:A.Fee").grounding_eligible
    embedding_path = next(path for path in result.paths if path.source == SOURCE_EMBEDDING)
    assert embedding_path.availability == PATH_UNAVAILABLE
    assert embedding_path.unavailable_reason == "provider_error"
    assert embedding_path.candidate_count == 0


def test_an_index_without_a_provider_is_rejected(family_vocabulary, tmp_path) -> None:
    path = write_index(*build_index(family_vocabulary, StubEmbeddings()), tmp_path / "index.json")
    with pytest.raises(ValueError, match="supplied together"):
        Retriever(family_vocabulary, RetrievalSettings(basis="t"), load_index(path), None)


def test_the_result_carries_no_physical_binding_or_plan(family_vocabulary, tmp_path) -> None:
    retriever = make_retriever(family_vocabulary, tmp_path)
    payload = json.dumps(retriever.retrieve("1년수익률과 총보수").to_dict(), ensure_ascii=False)
    lowered = payload.lower()
    for key in FORBIDDEN_PAYLOAD_KEYS:
        assert f'"{key}"' not in lowered
    for token in ("select ", " from ", "duckdb", "execution_registry"):
        assert token not in lowered


def test_the_result_carries_registry_evidence_for_every_candidate(
    family_vocabulary, tmp_path
) -> None:
    retriever = make_retriever(family_vocabulary, tmp_path)
    for candidate in retriever.retrieve("1년수익률").candidates:
        assert candidate.registry_evidence["kind"]
        assert candidate.registry_content_hash == retriever.vocabulary.content_hash
        assert "grains" in candidate.registry_evidence
        assert "allowed_operations" in candidate.registry_evidence


def test_results_are_reproducible(family_vocabulary, tmp_path) -> None:
    retriever = make_retriever(family_vocabulary, tmp_path)
    question = "가군상품의 1년수익률과 총보수"
    first = retriever.retrieve(question).to_dict()
    second = retriever.retrieve(question).to_dict()
    for payload in (first, second):
        payload.pop("latency_ms")
        for path in payload["paths"]:
            path.pop("latency_ms")
    assert first == second


def test_the_settings_basis_travels_with_every_result(family_vocabulary, tmp_path) -> None:
    settings = RetrievalSettings(basis="provisional_untested", rule=RuleSettings())
    retriever = make_retriever(family_vocabulary, tmp_path, settings)
    assert retriever.retrieve("총보수").settings_basis == "provisional_untested"


def test_status_is_candidates_when_one_meaning_is_named_outright(tmp_path) -> None:
    vocabulary = synthetic_registry(
        [term("syn:A", label="유일한지표"), term("syn:B", label="전혀다른것")]
    )
    settings = RetrievalSettings(
        basis="test_fixture", embedding=EmbeddingSettings(similarity_threshold=0.99, top_k=5)
    )
    retriever = make_retriever(vocabulary, tmp_path, settings)
    result = retriever.retrieve("유일한지표 알려줘")
    assert result.status == STATUS_CANDIDATES
    assert result.reasons == ()
