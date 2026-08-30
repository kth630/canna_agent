"""Contract tests for the external evaluation boundary ``GET /answer``.

capability_under_test: ``evaluation_api_transport``

These check the transport contract of ``contracts/EVALUATION_API.md`` only:
status, media type, exact string schema, verbatim echo, and tolerance of
undefined query parameters. The strings below are transport inputs, not semantic
question fixtures - nothing here asserts what a grounded answer should say, and
no expected answer is encoded.

The central falsification is
:func:`test_unseen_request_variants_share_one_answer_path`: if any request ever
changes a non-echo field, a request-dependent branch has appeared and this stage
has failed.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from canna import api
from canna.answer_envelope import ENVELOPE_FIELDS, JSON_MEDIA_TYPE

CONTRACT_FIELDS = {
    "question_id",
    "question",
    "retrieved_context",
    "think_trace",
    "answer",
}
ECHO_FIELDS = {"question_id", "question"}
DERIVED_FIELDS = sorted(CONTRACT_FIELDS - ECHO_FIELDS)

# Structurally varied requests, including shapes never used while writing the
# implementation: single and multiple requirements, a relationship condition, a
# comparison, an out-of-domain request, and hostile identifier forms.
REQUEST_VARIANTS = [
    ("ranking", "request-001", "국내 ETF 중 1년 수익률이 높은 상품 10개를 보여줘"),
    (
        "two-requirements",
        "request-002",
        "총보수가 0.2% 이하인 해외 ETF의 개수와 그 평균 순자산을 알려줘",
    ),
    (
        "relationship-condition",
        "request-003",
        "삼성전자를 직접 보유한 국내 ETF 목록을 보여줘",
    ),
    (
        "comparison-across-families",
        "request-004",
        "국내채권과 공모펀드의 최근 1년 수익률 평균을 비교해줘",
    ),
    ("unanswerable", "request-005", "내일 코스피 지수를 알려줘"),
    ("ascii-question", "request-006", "What is a bond?"),
    ("surrounding-whitespace", "  request-007  ", "  공백이 앞뒤에 있는 질문  "),
    ("reserved-characters", "q/8?&=#%20", "특수문자 & 기호 = 포함 질문?"),
    ("non-ascii-id-and-newline", "리퀘스트-009", "질문\n두 줄에 걸친 요청"),
    ("very-long-id", "r" * 512, "긴 식별자를 가진 요청"),
]
VARIANT_PARAMS = [
    pytest.param(question_id, question, id=case) for case, question_id, question in REQUEST_VARIANTS
]


@pytest.fixture()
def client() -> TestClient:
    return TestClient(api.create_app())


@pytest.fixture()
def tolerant_client() -> TestClient:
    """Client that reports server errors as responses instead of re-raising."""
    return TestClient(api.create_app(), raise_server_exceptions=False)


def get_answer(client: TestClient, question_id: str, question: str):
    return client.get("/answer", params={"question_id": question_id, "question": question})


@pytest.mark.parametrize(("question_id", "question"), VARIANT_PARAMS)
def test_valid_request_returns_contract_status_and_media_type(
    client: TestClient, question_id: str, question: str
) -> None:
    """A valid request answers 200 with the exact contract media type."""
    response = get_answer(client, question_id, question)

    assert response.status_code == 200
    assert response.headers["content-type"] == JSON_MEDIA_TYPE


@pytest.mark.parametrize(("question_id", "question"), VARIANT_PARAMS)
def test_response_carries_exactly_the_five_contract_string_fields(
    client: TestClient, question_id: str, question: str
) -> None:
    """The payload is exactly the five required fields and every value is a string."""
    payload = get_answer(client, question_id, question).json()

    assert set(payload) == CONTRACT_FIELDS
    assert set(ENVELOPE_FIELDS) == CONTRACT_FIELDS
    assert all(isinstance(value, str) for value in payload.values())
    assert all(payload[field].strip() for field in DERIVED_FIELDS)


@pytest.mark.parametrize(("question_id", "question"), VARIANT_PARAMS)
def test_request_fields_are_echoed_verbatim(
    client: TestClient, question_id: str, question: str
) -> None:
    """Echo preserves the input exactly, including whitespace and non-ASCII."""
    payload = get_answer(client, question_id, question).json()

    assert payload["question_id"] == question_id
    assert payload["question"] == question


def test_response_body_is_utf8_without_ascii_escaping(client: TestClient) -> None:
    """Korean text crosses the wire as UTF-8 bytes, not as escape sequences."""
    question = "국내 ETF 중 순자산이 큰 상품을 알려줘"
    response = get_answer(client, "request-utf8", question)

    assert question.encode("utf-8") in response.content
    assert json.loads(response.content.decode("utf-8"))["question"] == question


@pytest.mark.parametrize(("question_id", "question"), VARIANT_PARAMS)
def test_undefined_query_parameters_never_produce_a_server_error(
    tolerant_client: TestClient, question_id: str, question: str
) -> None:
    """Undefined parameters are ignored rather than fatal (contract request rule)."""
    response = tolerant_client.get(
        "/answer",
        params=[
            ("question_id", question_id),
            ("question", question),
            ("top_k", "10"),
            ("top_k", "20"),
            ("question_id_extra", "x"),
            ("질의", "한글 파라미터"),
            ("", "empty-name"),
        ],
    )

    assert response.status_code == 200
    assert set(response.json()) == CONTRACT_FIELDS


def test_unseen_request_variants_share_one_answer_path(client: TestClient) -> None:
    """Falsifies per-question branching: non-echo fields must be identical.

    If any variant produced a different retrieved_context, think_trace or answer,
    the service would be reacting to question content it cannot ground.
    """
    derived = {
        case: tuple(
            get_answer(client, question_id, question).json()[field] for field in DERIVED_FIELDS
        )
        for case, question_id, question in REQUEST_VARIANTS
    }

    assert len(set(derived.values())) == 1, f"request-dependent answer path: {sorted(derived)}"


def test_retrieved_context_is_machine_readable_and_claims_no_evidence(client: TestClient) -> None:
    """retrieved_context is auditable JSON that asserts no source and no universe."""
    payload = get_answer(client, "request-context", "국내 ETF 목록을 보여줘").json()
    context = json.loads(payload["retrieved_context"])

    assert context["sources"] == []
    assert context["results"] == []
    assert context["universe"] is None
    assert context["effective_as_of"] is None
    assert context["answer_status"] == "refused"
    assert context["reasons"] == ["no_data"]


def test_think_trace_reports_stages_without_restating_the_request(client: TestClient) -> None:
    """think_trace is a stage summary, so it must not carry the request text."""
    question = "해외 ETF 중 총보수가 가장 낮은 상품을 알려줘"
    payload = get_answer(client, "request-trace", question).json()

    assert question not in payload["think_trace"]
    assert "request-trace" not in payload["think_trace"]


def test_ungrounded_answer_states_absence_without_numeric_claims(client: TestClient) -> None:
    """An answer with no evidence may not contain a figure of any kind."""
    payload = get_answer(client, "request-answer", "국내채권 수익률 상위 5개를 알려줘").json()

    assert not any(character.isdigit() for character in payload["answer"])


def test_importing_the_module_does_not_construct_a_service() -> None:
    """The app is built by a factory, so importing the module deploys nothing."""
    assert not hasattr(api, "app")


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({"question": "국내 ETF 목록을 보여줘"}, id="missing-question-id"),
        pytest.param({"question_id": "request-010"}, id="missing-question"),
        pytest.param({"question_id": "", "question": ""}, id="empty-both"),
        pytest.param({"question_id": "request-011", "question": ""}, id="empty-question"),
    ],
)
def test_absent_or_empty_input_is_not_a_server_error(
    tolerant_client: TestClient, params: dict[str, str]
) -> None:
    """Absent or empty input must not crash the service.

    The external status and error envelope for these cases are still undecided in
    contracts/EVALUATION_API.md, so this asserts only the invariant that holds
    under every candidate decision. It deliberately does not pin a status code.
    """
    response = tolerant_client.get("/answer", params=params)

    assert response.status_code < 500
