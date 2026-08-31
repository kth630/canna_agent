"""Threshold evidence is corpus-wide and does not import question fixtures."""

from canna.retrieval.evaluation import cross_form_sweep
from canna.retrieval.index import RetrievalIndex, build_index

from .conftest import StubEmbeddings, synthetic_registry, term


def test_cross_form_sweep_excludes_self_and_collapses_by_semantic_id() -> None:
    vocabulary = synthetic_registry(
        [
            term("syn:A", label="가나다라", aliases=["가나다라별칭"]),
            term("syn:B", label="마바사아"),
        ]
    )
    manifest, entries, vectors = build_index(vocabulary, StubEmbeddings())
    index = RetrievalIndex(manifest, entries, vectors)
    report = cross_form_sweep(vocabulary, index, thresholds=[-1.0], top_ks=[10])
    assert report["query_entry_count"] == 2
    assert report["semantic_terms_evaluated"] == 1
    assert report["sweep"][0]["same_semantic_id_recall"] == 1.0
    assert report["decision_status"] == "structural_evidence_only_not_product_settled"
