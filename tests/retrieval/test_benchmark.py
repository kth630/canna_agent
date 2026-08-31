"""The natural-question evaluator is approval-gated and question-safe."""

from __future__ import annotations

import hashlib
import json

import pytest

from canna.retrieval.benchmark import (
    BenchmarkError,
    EvaluationCase,
    evaluate_model,
    load_evaluation_proposal,
)
from canna.retrieval.index import RetrievalIndex, build_index
from canna.retrieval.settings import RuleSettings

from .conftest import StubEmbeddings, synthetic_registry, term


def test_proposal_requires_approval_and_matching_registry(tmp_path) -> None:
    vocabulary = synthetic_registry([term("syn:A", label="정확지표")])
    proposal = tmp_path / "proposal.jsonl"
    case = {
            "record_type": "evaluation_case",
            "case_id": "clear-1",
            "section": "clear",
            "question": "정확지표를 보여줘",
            "test_purpose": "schema test",
            "capability_under_test": "synthetic.metric",
            "question_structure": {"semantic_request": "metric"},
            "explicit_requirements": ["정확지표"],
            "semantic_clarity": "explicit",
            "expected_semantic_ids": ["syn:A"],
            "expected_status": "candidates",
            "failure_falsifies": "proposal schema",
            "registry_evidence": [
                {"semantic_id": "syn:A", "role": "label", "expression": "정확지표"}
            ],
            "failure_analysis_hints": ["registry_alias_gap"],
        }
    question_bytes = json.dumps(
        [[case["case_id"], case["question"]]],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    records = [
        {
            "record_type": "proposal_metadata",
            "proposal_id": "proposal-1",
            "approval_status": "unapproved",
            "registry_content_hash": vocabulary.content_hash,
            "questions_sha256": hashlib.sha256(question_bytes).hexdigest(),
        },
        case,
    ]
    proposal.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkError, match="approval-reference"):
        load_evaluation_proposal(proposal, vocabulary, approval_reference="")
    metadata, cases = load_evaluation_proposal(
        proposal, vocabulary, approval_reference="user-approved-test"
    )
    assert metadata["approval_reference"] == "user-approved-test"
    assert cases[0].question == "정확지표를 보여줘"


def test_evaluator_reports_metrics_without_question_text() -> None:
    vocabulary = synthetic_registry(
        [
            term("syn:A", label="정확지표", aliases=["승인별칭"]),
            term("syn:B", label="다른지표"),
        ]
    )
    build_provider = StubEmbeddings()
    manifest, entries, vectors = build_index(vocabulary, build_provider)
    index = RetrievalIndex(manifest, entries, vectors)
    provider = StubEmbeddings()
    cases = (
        EvaluationCase(
            "clear-1", "clear", "승인별칭을 알려줘", frozenset({"syn:A"}), ()
        ),
        EvaluationCase("unrelated-1", "unrelated", "저녁 메뉴 추천", frozenset(), ()),
        EvaluationCase(
            "diagnostic-1",
            "ambiguous_diagnostic",
            "지표를 알려줘",
            frozenset({"syn:A", "syn:B"}),
            (),
        ),
    )
    report = evaluate_model(
        vocabulary,
        index,
        provider,
        cases,
        rule_settings=RuleSettings(),
        thresholds=[-1.0, 0.5],
    )
    assert report["rule_only_recall"] == 1.0
    assert [row["top_k"] for row in report["ranking_metrics_without_threshold"]] == [
        1,
        3,
        5,
        10,
        20,
    ]
    assert report["question_text_in_report"] is False
    assert "승인별칭" not in json.dumps(report, ensure_ascii=False)
    assert report["threshold_basis"] == "explicit_per_model_values"
