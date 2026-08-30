"""Offline verification of the stage 0-A probe harness.

These tests never call the provider. They prove the harness itself detects the
failure modes it claims to measure, so a live run's numbers mean something.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from canna.experiments.semantic_probe.encodings import ENCODINGS, FUNCTION_NAME
from canna.experiments.semantic_probe.model import (
    QuestionSemantics,
    RequirementDetail,
    RequirementRecord,
)
from canna.experiments.semantic_probe.probe import ProbeCase, run_case, summarise
from canna.experiments.semantic_probe.provider import (
    OUTCOME_MODEL_NO_TOOL_CALL,
    OUTCOME_OK,
    HcxSemanticProvider,
    classify_error,
)
from canna.experiments.semantic_probe.runtime_view import (
    CandidateCatalog,
    RefMinter,
    permutation,
    rebuild_view,
)
from canna.experiments.semantic_probe.scoring import normalize_value, score_result
from canna.experiments.semantic_probe.transcript import credential_values, redact, write_records

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures"
CATALOG_PATH = FIXTURE_DIR / "semantic_probe_catalog.json"
FIXTURE_FILES = (
    FIXTURE_DIR / "semantic_grounding.jsonl",
    FIXTURE_DIR / "semantic_grounding_regression.jsonl",
    FIXTURE_DIR / "semantic_grounding_verification.jsonl",
)


@pytest.fixture(scope="module")
def catalog() -> CandidateCatalog:
    return CandidateCatalog.from_mapping(json.loads(CATALOG_PATH.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def fixture_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in FIXTURE_FILES:
        records.extend(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return records


class RecordingChat:
    """Stand-in for the bound provider chat that returns a scripted tool call."""

    def __init__(self, arguments: dict[str, object] | None) -> None:
        self._arguments = arguments

    def invoke(self, messages: list[object]) -> object:
        arguments = self._arguments

        class Response:
            content = ""
            tool_calls = (
                [] if arguments is None else [{"name": FUNCTION_NAME, "args": arguments}]
            )

        return Response()


def provider_returning(arguments: dict[str, object] | None) -> HcxSemanticProvider:
    def factory(model: str, timeout: int, tool_schema: dict[str, object]) -> RecordingChat:
        return RecordingChat(arguments)

    return HcxSemanticProvider(chat_factory=factory)


def build_case(records: list[dict[str, object]], test_id: str) -> ProbeCase:
    for record in records:
        if record["test_id"] == test_id:
            return ProbeCase.from_fixture(record)
    raise AssertionError(f"fixture not found: {test_id}")


def view_for(catalog: CandidateCatalog, case: ProbeCase, seed: int):
    return catalog.build_view(case.candidate_keys, RefMinter(random.Random(seed)))


# --- fixture integrity -------------------------------------------------------


def test_every_fixture_is_executable(catalog: CandidateCatalog, fixture_records) -> None:
    known = set(catalog.keys())
    for record in fixture_records:
        case = ProbeCase.from_fixture(record)
        unknown = sorted(set(case.candidate_keys) - known)
        assert not unknown, f"{case.test_id} references unknown candidates: {unknown}"
        expectation = case.expectation
        expected_keys = expectation.ref_universe() - expectation.target_dataset_keys
        assert expected_keys <= set(case.candidate_keys), (
            f"{case.test_id} expects candidates that are not in its runtime view"
        )
        assert expectation.target_dataset_keys <= set(case.candidate_keys)
        assert all(option for option in expectation.requirement_sets)


def test_every_fixture_anchors_its_requirements_in_the_question(fixture_records) -> None:
    for record in fixture_records:
        case = ProbeCase.from_fixture(record)
        for option in case.expectation.requirement_sets:
            for requirement in option:
                assert requirement.span_anchors, f"{case.test_id}/{requirement.label} has no anchor"
                for anchor in requirement.span_anchors:
                    assert anchor in case.question, (
                        f"{case.test_id}/{requirement.label} anchor {anchor!r} is not in the question"
                    )


def test_fixture_ids_and_splits_are_consistent(fixture_records) -> None:
    ids = [record["test_id"] for record in fixture_records]
    assert len(ids) == len(set(ids))
    splits = {record["split"] for record in fixture_records}
    assert splits == {"primary", "regression", "verification"}


def test_every_fixture_view_contains_the_owning_dataset(
    catalog: CandidateCatalog, fixture_records
) -> None:
    for record in fixture_records:
        case = ProbeCase.from_fixture(record)
        # build_view raises when a candidate's owning dataset is absent
        catalog.build_view(case.candidate_keys, RefMinter(random.Random(0)))


# --- runtime view ------------------------------------------------------------


def test_refs_are_request_scoped(catalog: CandidateCatalog, fixture_records) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    first = view_for(catalog, case, 1)
    second = view_for(catalog, case, 2)
    assert first.refs().isdisjoint(second.refs())


def test_dataset_membership_travels_as_a_request_scoped_ref(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "vf_dataset_ownership_positive_001")
    view = view_for(catalog, case, 3)
    ref_by_key = view.ref_by_key()
    payload = view.as_prompt_payload()
    fields = {item["ref"]: item for item in payload["field_candidates"]}
    fund_field = fields[ref_by_key["f.fund_pub.net_assets"]]
    etf_field = fields[ref_by_key["f.etf_kr.net_assets"]]
    assert fund_field["belongs_to_dataset_ref"] == ref_by_key["ds.public_fund"]
    assert etf_field["belongs_to_dataset_ref"] == ref_by_key["ds.domestic_etf"]
    assert fund_field["belongs_to_dataset_ref"] != etf_field["belongs_to_dataset_ref"]


def test_catalog_and_dataset_keys_never_reach_the_provider_payload(
    catalog: CandidateCatalog, fixture_records
) -> None:
    for record in fixture_records:
        case = ProbeCase.from_fixture(record)
        payload = json.dumps(view_for(catalog, case, 4).as_prompt_payload(), ensure_ascii=False)
        assert "dataset_key" not in payload
        for key in catalog.keys():  # noqa: SIM118 - tuple accessor, not a mapping
            assert key not in payload


def test_view_rejects_a_field_without_its_owning_dataset(catalog: CandidateCatalog) -> None:
    with pytest.raises(ValueError, match="not in this runtime view"):
        catalog.build_view(["f.etf_kr.return_1y"], RefMinter(random.Random(5)))


def test_candidate_order_is_seeded_and_reproducible(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    keys = case.candidate_keys
    assert permutation(keys, None) == keys
    assert permutation(keys, 11) == permutation(keys, 11)
    shuffles = {permutation(keys, seed) for seed in range(30)}
    assert len(shuffles) > 1
    permuted = catalog.build_view(keys, RefMinter(random.Random(6)), order_seed=11)
    assert permuted.presentation_order == permutation(keys, 11)
    assert set(permuted.key_by_ref().values()) == set(keys)


def test_rebuild_view_restores_an_archived_view(catalog: CandidateCatalog, fixture_records) -> None:
    case = build_case(fixture_records, "vf_dataset_ownership_positive_001")
    view = view_for(catalog, case, 7)
    restored = rebuild_view(catalog, view.key_by_ref())
    assert restored.refs() == view.refs()
    assert restored.key_by_ref() == view.key_by_ref()
    assert {c.catalog_key: c.dataset_ref for c in restored.all_candidates()} == {
        c.catalog_key: c.dataset_ref for c in view.all_candidates()
    }


# --- encodings ---------------------------------------------------------------


def test_encodings_decode_to_the_same_semantics() -> None:
    detail = {"slot": "condition", "ref": "f1", "operator": "gte", "value": "5"}
    payloads = {
        "nested": {
            "target_dataset_refs": ["d1"],
            "requirements": [
                {
                    "requirement_id": "r1",
                    "text_span": "1년 수익률",
                    "kind": "ranking",
                    "status": "mapped",
                    "refs": ["f1"],
                    "details": [detail],
                }
            ],
        },
        "grouped_flat": {
            "target_dataset_refs": ["d1"],
            "requirement_records": [
                {
                    "requirement_id": "r1",
                    "text_span": "1년 수익률",
                    "kind": "ranking",
                    "status": "mapped",
                }
            ],
            "ref_records": [{"requirement_id": "r1", "ref": "f1"}],
            "detail_records": [{"requirement_id": "r1", **detail}],
        },
        "delimited": {
            "target_dataset_refs": ["d1"],
            "requirement_lines": ["REQ|r1|ranking|mapped|1년 수익률"],
            "ref_lines": ["REF|r1|f1"],
            "detail_lines": ["DET|r1|condition|f1|gte|5"],
        },
    }
    decoded = {name: ENCODINGS[name].decode(payload) for name, payload in payloads.items()}
    assert len(set(decoded.values())) == 1
    only = next(iter(decoded.values()))
    assert only.requirements[0].details_for("condition")[0].value == "5"


def test_flat_encodings_keep_details_attached_to_their_requirement() -> None:
    grouped = ENCODINGS["grouped_flat"].decode(
        {
            "target_dataset_refs": ["d1"],
            "requirement_records": [
                {"requirement_id": "r1", "text_span": "a", "kind": "count", "status": "mapped"},
                {
                    "requirement_id": "r2",
                    "text_span": "b",
                    "kind": "aggregation",
                    "status": "mapped",
                },
            ],
            "ref_records": [
                {"requirement_id": "r2", "ref": "f2"},
                {"requirement_id": "r1", "ref": "f1"},
            ],
            "detail_records": [
                {"requirement_id": "r2", "slot": "limit", "value": "5"},
                {"requirement_id": "r1", "slot": "condition", "ref": "f1", "operator": "gte"},
            ],
        }
    )
    by_id = {record.requirement_id: record for record in grouped.requirements}
    assert by_id["r1"].refs == ("f1",)
    assert by_id["r1"].details_for("condition")[0].operator == "gte"
    assert by_id["r2"].details_for("limit")[0].value == "5"


def test_blank_ref_slots_are_not_invented_refs() -> None:
    semantics = ENCODINGS["grouped_flat"].decode(
        {
            "target_dataset_refs": ["d1"],
            "requirement_records": [
                {"requirement_id": "r1", "text_span": "a", "kind": "listing", "status": "unresolved"}
            ],
            "ref_records": [{"requirement_id": "r1", "ref": ""}],
            "detail_records": [],
        }
    )
    assert semantics.requirements[0].refs == ()


# --- scoring -----------------------------------------------------------------


def test_normalize_value_only_strips_formatting() -> None:
    assert normalize_value("1조 원") == "1조"
    assert normalize_value("0.1 %") == "0.1"
    assert normalize_value("1,000,000") == "1000000"
    assert normalize_value("10년") == "10"
    assert normalize_value("1조") != normalize_value("1000000000000")


def correct_ranking(view, question_case) -> QuestionSemantics:
    ref = view.ref_by_key()
    return QuestionSemantics(
        target_dataset_refs=(ref["ds.domestic_etf"],),
        requirements=(
            RequirementRecord(
                requirement_id="r1",
                text_span="최근 1년 수익률이 높은 상품 10개",
                kind="ranking",
                status="mapped",
                refs=(ref["f.etf_kr.return_1y"],),
                details=(
                    RequirementDetail(
                        slot="order", ref=ref["f.etf_kr.return_1y"], operator="descending"
                    ),
                    RequirementDetail(slot="limit", value="10"),
                ),
            ),
        ),
    )


def test_scoring_accepts_a_correct_accounting(catalog: CandidateCatalog, fixture_records) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    view = view_for(catalog, case, 10)
    score = score_result(case.question, view, correct_ranking(view, case), case.expectation)
    assert score.case_pass
    assert score.requirement_recall == 1.0
    assert score.requirement_precision == 1.0
    assert score.matched_alternative == 0


def test_scoring_rejects_a_lost_sort_direction(catalog: CandidateCatalog, fixture_records) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    view = view_for(catalog, case, 11)
    ref = view.ref_by_key()
    semantics = QuestionSemantics(
        target_dataset_refs=(ref["ds.domestic_etf"],),
        requirements=(
            RequirementRecord(
                requirement_id="r1",
                text_span="최근 1년 수익률이 높은 상품 10개",
                kind="ranking",
                status="mapped",
                refs=(ref["f.etf_kr.return_1y"],),
                details=(
                    RequirementDetail(
                        slot="order", ref=ref["f.etf_kr.return_1y"], operator="ascending"
                    ),
                    RequirementDetail(slot="limit", value="10"),
                ),
            ),
        ),
    )
    assert not score_result(case.question, view, semantics, case.expectation).case_pass


def test_scoring_rejects_a_lost_limit(catalog: CandidateCatalog, fixture_records) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    view = view_for(catalog, case, 12)
    ref = view.ref_by_key()
    semantics = QuestionSemantics(
        target_dataset_refs=(ref["ds.domestic_etf"],),
        requirements=(
            RequirementRecord(
                requirement_id="r1",
                text_span="최근 1년 수익률이 높은 상품 10개",
                kind="ranking",
                status="mapped",
                refs=(ref["f.etf_kr.return_1y"],),
                details=(
                    RequirementDetail(
                        slot="order", ref=ref["f.etf_kr.return_1y"], operator="descending"
                    ),
                ),
            ),
        ),
    )
    assert not score_result(case.question, view, semantics, case.expectation).case_pass


def test_scoring_rejects_a_lost_condition_value(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "sg_field_meaning_neighbor_001")
    view = view_for(catalog, case, 13)
    ref = view.ref_by_key()

    def build(value: str) -> QuestionSemantics:
        return QuestionSemantics(
            target_dataset_refs=(ref["ds.domestic_etf"],),
            requirements=(
                RequirementRecord(
                    requirement_id="r1",
                    text_span="순자산총액이 1조원 이상인 상품이 몇 개인지",
                    kind="count",
                    status="mapped",
                    refs=(ref["f.etf_kr.net_assets"],),
                    details=(
                        RequirementDetail(
                            slot="condition",
                            ref=ref["f.etf_kr.net_assets"],
                            operator="gte",
                            value=value,
                        ),
                    ),
                ),
            ),
        )

    assert score_result(case.question, view, build("1조원"), case.expectation).case_pass
    assert not score_result(case.question, view, build(""), case.expectation).case_pass


def test_scoring_rejects_a_reversed_relationship_direction(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "sg_relationship_security_to_product_001")
    view = view_for(catalog, case, 14)
    ref = view.ref_by_key()

    def build(traversal: str, anchor_key: str) -> QuestionSemantics:
        return QuestionSemantics(
            target_dataset_refs=(ref["ds.domestic_etf"],),
            requirements=(
                RequirementRecord(
                    requirement_id="r1",
                    text_span="가온전자를 직접 보유한 국내 ETF 목록",
                    kind="listing",
                    status="mapped",
                    refs=(ref["p.directly_holds_security"], ref["e.security_alpha_common"]),
                    details=(
                        RequirementDetail(
                            slot="relationship",
                            ref=ref["p.directly_holds_security"],
                            operator=traversal,
                            value=ref[anchor_key],
                        ),
                    ),
                ),
            ),
        )

    assert score_result(
        case.question, view, build("object_to_subject", "e.security_alpha_common"), case.expectation
    ).case_pass
    assert not score_result(
        case.question, view, build("subject_to_object", "e.security_alpha_common"), case.expectation
    ).case_pass
    assert not score_result(
        case.question,
        view,
        build("object_to_subject", "e.security_alpha_preferred"),
        case.expectation,
    ).case_pass


def test_scoring_rejects_an_extra_requirement(catalog: CandidateCatalog, fixture_records) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    view = view_for(catalog, case, 15)
    ref = view.ref_by_key()
    base = correct_ranking(view, case)
    semantics = QuestionSemantics(
        target_dataset_refs=base.target_dataset_refs,
        requirements=(
            *base.requirements,
            RequirementRecord(
                requirement_id="r2",
                text_span="상품 10개",
                kind="count",
                status="mapped",
                refs=(ref["f.etf_kr.return_1y"],),
            ),
        ),
    )
    score = score_result(case.question, view, semantics, case.expectation)
    assert not score.case_pass
    assert score.requirement_precision < 1.0
    assert score.extra_requirement_ids == ("r2",)


def test_scoring_rejects_a_missing_or_foreign_span(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    view = view_for(catalog, case, 16)
    base = correct_ranking(view, case)
    for span in ("", "이 질문에 없는 문장"):
        semantics = QuestionSemantics(
            target_dataset_refs=base.target_dataset_refs,
            requirements=(base.requirements[0].model_copy(update={"text_span": span}),),
        )
        score = score_result(case.question, view, semantics, case.expectation)
        assert not score.case_pass
        assert not score.spans_verbatim


def test_scoring_rejects_two_requirements_sharing_one_span(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "sg_requirements_two_001")
    view = view_for(catalog, case, 17)
    ref = view.ref_by_key()
    condition = RequirementDetail(
        slot="condition", ref=ref["f.bond_kr.remaining_days"], operator="lte", value="1년"
    )
    shared = case.question
    semantics = QuestionSemantics(
        target_dataset_refs=(ref["ds.domestic_bond"],),
        requirements=(
            RequirementRecord(
                requirement_id="r1",
                text_span=shared,
                kind="count",
                status="mapped",
                refs=(ref["f.bond_kr.remaining_days"],),
                details=(condition,),
            ),
            RequirementRecord(
                requirement_id="r2",
                text_span=shared,
                kind="aggregation",
                status="mapped",
                refs=(ref["f.bond_kr.coupon_rate"],),
            ),
        ),
    )
    score = score_result(case.question, view, semantics, case.expectation)
    assert not score.spans_distinct
    assert not score.case_pass


def test_scoring_accepts_a_declared_equivalent_decomposition(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "sg_comparison_two_entities_001")
    view = view_for(catalog, case, 18)
    ref = view.ref_by_key()
    subjects = (
        RequirementDetail(slot="comparison_subject", ref=ref["e.product_index_replication"]),
        RequirementDetail(slot="comparison_subject", ref=ref["e.product_futures_replication"]),
    )
    semantics = QuestionSemantics(
        target_dataset_refs=(ref["ds.domestic_etf"],),
        requirements=(
            RequirementRecord(
                requirement_id="r1",
                text_span="청람 대표지수 지수형 ETF",
                kind="attribute_lookup",
                status="mapped",
                refs=(ref["f.etf_kr.return_1y"], ref["e.product_index_replication"]),
            ),
            RequirementRecord(
                requirement_id="r2",
                text_span="청람 대표지수 선물형 ETF",
                kind="attribute_lookup",
                status="mapped",
                refs=(ref["f.etf_kr.return_1y"], ref["e.product_futures_replication"]),
            ),
            RequirementRecord(
                requirement_id="r3",
                text_span="1년 수익률을 비교해줘",
                kind="comparison",
                status="mapped",
                refs=(
                    ref["f.etf_kr.return_1y"],
                    ref["e.product_index_replication"],
                    ref["e.product_futures_replication"],
                ),
                details=subjects,
            ),
        ),
    )
    score = score_result(case.question, view, semantics, case.expectation)
    assert score.case_pass
    assert score.matched_alternative == 1


def test_scoring_rejects_a_comparison_that_became_two_lookups(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "sg_comparison_two_entities_001")
    view = view_for(catalog, case, 19)
    ref = view.ref_by_key()
    semantics = QuestionSemantics(
        target_dataset_refs=(ref["ds.domestic_etf"],),
        requirements=(
            RequirementRecord(
                requirement_id="r1",
                text_span="청람 대표지수 지수형 ETF",
                kind="attribute_lookup",
                status="mapped",
                refs=(ref["f.etf_kr.return_1y"], ref["e.product_index_replication"]),
            ),
            RequirementRecord(
                requirement_id="r2",
                text_span="청람 대표지수 선물형 ETF",
                kind="attribute_lookup",
                status="mapped",
                refs=(ref["f.etf_kr.return_1y"], ref["e.product_futures_replication"]),
            ),
        ),
    )
    assert not score_result(case.question, view, semantics, case.expectation).case_pass


def test_scoring_rejects_an_invented_ref(catalog: CandidateCatalog, fixture_records) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    view = view_for(catalog, case, 20)
    base = correct_ranking(view, case)
    mutated = base.requirements[0].refs[0].upper()
    semantics = QuestionSemantics(
        target_dataset_refs=base.target_dataset_refs,
        requirements=(base.requirements[0].model_copy(update={"refs": (mutated,)}),),
    )
    score = score_result(case.question, view, semantics, case.expectation)
    assert not score.ref_integrity
    assert score.invented_refs == (mutated,)
    assert not score.case_pass


def test_scoring_detects_an_invented_ref_inside_a_detail(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "sg_relationship_security_to_product_001")
    view = view_for(catalog, case, 21)
    ref = view.ref_by_key()
    semantics = QuestionSemantics(
        target_dataset_refs=(ref["ds.domestic_etf"],),
        requirements=(
            RequirementRecord(
                requirement_id="r1",
                text_span="가온전자를 직접 보유한 국내 ETF 목록",
                kind="listing",
                status="mapped",
                refs=(ref["p.directly_holds_security"], ref["e.security_alpha_common"]),
                details=(
                    RequirementDetail(
                        slot="relationship",
                        ref=ref["p.directly_holds_security"],
                        operator="object_to_subject",
                        value="zzzzzzzz",
                    ),
                ),
            ),
        ),
    )
    score = score_result(case.question, view, semantics, case.expectation)
    assert score.invented_refs == ("zzzzzzzz",)
    assert not score.case_pass


def test_scoring_requires_unresolved_for_an_absent_candidate(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "vf_dataset_ownership_absent_001")
    view = view_for(catalog, case, 22)
    ref = view.ref_by_key()
    substituted = QuestionSemantics(
        target_dataset_refs=(ref["ds.overseas_etf"],),
        requirements=(
            RequirementRecord(
                requirement_id="r1",
                text_span="괴리율이 가장 낮은 5개",
                kind="ranking",
                status="mapped",
                refs=(ref["f.etf_kr.divergence_rate"],),
            ),
        ),
    )
    assert not score_result(case.question, view, substituted, case.expectation).case_pass

    refused = QuestionSemantics(
        target_dataset_refs=(ref["ds.overseas_etf"],),
        requirements=(
            RequirementRecord(
                requirement_id="r1",
                text_span="괴리율이 가장 낮은 5개",
                kind="ranking",
                status="unresolved",
            ),
        ),
    )
    assert score_result(case.question, view, refused, case.expectation).case_pass


def test_scoring_can_disable_detail_checks_for_archived_runs(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    view = view_for(catalog, case, 23)
    ref = view.ref_by_key()
    without_details = QuestionSemantics(
        target_dataset_refs=(ref["ds.domestic_etf"],),
        requirements=(
            RequirementRecord(
                requirement_id="r1",
                text_span="최근 1년 수익률이 높은 상품 10개",
                kind="ranking",
                status="mapped",
                refs=(ref["f.etf_kr.return_1y"],),
            ),
        ),
    )
    assert not score_result(case.question, view, without_details, case.expectation).case_pass
    relaxed = score_result(
        case.question, view, without_details, case.expectation, check_details=False
    )
    assert relaxed.case_pass
    assert relaxed.details_checked is False


# --- probe and provider ------------------------------------------------------


def test_probe_run_scores_a_scripted_provider(catalog: CandidateCatalog, fixture_records) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    view = view_for(catalog, case, 24)
    ref = view.ref_by_key()
    provider = provider_returning(
        {
            "target_dataset_refs": [ref["ds.domestic_etf"]],
            "requirements": [
                {
                    "requirement_id": "r1",
                    "text_span": "최근 1년 수익률이 높은 상품 10개",
                    "kind": "ranking",
                    "status": "mapped",
                    "refs": [ref["f.etf_kr.return_1y"]],
                    "details": [
                        {
                            "slot": "order",
                            "ref": ref["f.etf_kr.return_1y"],
                            "operator": "descending",
                        },
                        {"slot": "limit", "value": "10"},
                    ],
                }
            ],
        }
    )
    run = run_case(
        case,
        ENCODINGS["nested"],
        catalog,
        provider,
        RefMinter(random.Random(24)),
        order_seed=None,
        repeat_index=0,
    )
    assert run.provider_result.outcome == OUTCOME_OK
    assert run.passed
    record = run.as_record()
    assert record["candidate_presentation_order"] == list(case.candidate_keys)
    assert record["order_seed"] is None
    assert record["score"]["case_pass"] is True


def test_probe_records_a_model_response_failure(catalog: CandidateCatalog, fixture_records) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    run = run_case(case, ENCODINGS["nested"], catalog, provider_returning(None))
    assert run.provider_result.outcome == OUTCOME_MODEL_NO_TOOL_CALL
    assert run.provider_result.failed_at_model
    assert not run.provider_result.failed_at_provider
    assert run.score is None
    summary = summarise([run])
    assert summary["model_response_failures"] == 1
    assert summary["provider_failures"] == 0
    assert summary["run_pass_rate"] is None


def test_provider_failure_is_not_a_model_failure(catalog: CandidateCatalog, fixture_records) -> None:
    def failing_factory(model: str, timeout: int, tool_schema: dict[str, object]) -> object:
        raise RuntimeError("Error code: 400 - {'status': {'code': '40009'}}")

    provider = HcxSemanticProvider(chat_factory=failing_factory, transport_retries=0)
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    run = run_case(case, ENCODINGS["nested"], catalog, provider)
    assert run.provider_result.failed_at_provider
    assert not run.provider_result.failed_at_model
    assert run.provider_result.error_kind == "api"
    assert run.provider_result.error_code == "40009"
    summary = summarise([run])
    assert summary["provider_failures"] == 1
    assert summary["provider_error_codes"] == ["40009"]
    assert summary["scored_runs"] == 0


def test_summary_separates_stable_and_order_sensitive_cases(
    catalog: CandidateCatalog, fixture_records
) -> None:
    case = build_case(fixture_records, "sg_field_period_neighbor_001")
    passing = run_case(case, ENCODINGS["nested"], catalog, provider_returning(None))
    summary = summarise([passing, passing])
    assert summary["cases"] == 1
    assert summary["repeats_per_case"] == 2
    # A provider/model failure leaves the case unscored: it is neither a stable
    # failure nor evidence that candidate order mattered.
    assert summary["cases_with_at_least_one_scored_run"] == 0
    assert summary["stable_fail_test_ids"] == []
    assert summary["order_sensitive_test_ids"] == []
    assert summary["never_scored_test_ids"] == [case.test_id]


def test_transport_error_classification() -> None:
    assert classify_error("Connection error.") == ("transport", "")
    assert classify_error("Read timed out") == ("transport", "")
    assert classify_error("something else") == ("unknown", "")


def test_transcript_removes_credential_values(tmp_path: Path) -> None:
    environ = {"CLOVASTUDIO_API_KEY": "nv-secret-value-1234", "HOME": "/home/someone"}
    secrets = credential_values(environ)
    assert secrets == ("nv-secret-value-1234",)
    # A value from a non-credential variable must survive untouched.
    assert redact("/home/someone", secrets) == "/home/someone"
    path = tmp_path / "transcript.jsonl"
    written = write_records(
        path, [{"error_message": "auth failed for nv-secret-value-1234"}], environ=environ
    )
    text = path.read_text(encoding="utf-8")
    assert written == 1
    assert "nv-secret-value-1234" not in text
    assert "<redacted>" in text
