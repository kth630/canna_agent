"""FastAPI service exposing the external evaluation contract ``GET /answer``.

This module owns the transport boundary defined in
``contracts/EVALUATION_API.md`` and nothing else. Question understanding, the
Runtime View, semantic-query validation, query execution and Evidence assembly
(``ARCHITECTURE.md`` section 2) are deliberately absent; they attach later at
the ``Responder`` seam without changing anything visible from outside.

Because no data source is connected yet, the shipped responder answers every
request the same way: it echoes the correlation fields and states plainly that
there is no evidence to answer from. The request never selects a code path, so
there is nothing here that a specific evaluation question could match.

The app is built by :func:`create_app` rather than at import time, so importing
this module constructs no service::

    uvicorn canna.api:create_app --factory --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
from typing import Protocol

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, Response

from .answer_envelope import JSON_MEDIA_TYPE, AnswerEnvelope

# ARCHITECTURE.md section 5 keeps status, reasons and universe on separate axes.
# With no data connected, the only honest state is a refusal caused by absent
# data - not a partial result over an observed universe.
_NO_EVIDENCE_STATUS = "refused"
_NO_EVIDENCE_REASON = "no_data"

# General statement of the evidence situation. It mentions no product, figure,
# date or question, and is emitted identically for every request; it disappears
# once retrieval and Evidence assembly are connected.
_UNGROUNDED_ANSWER = (
    "현재 이 서비스에는 조회 가능한 데이터가 연결되어 있지 않아, 질문에 대한 근거 있는 "
    "답변을 드릴 수 없습니다. 근거 없이 상품, 수치, 순위 또는 전망을 만들어내지 않습니다."
)

# contracts/EVALUATION_API.md: think_trace is an auditable summary of the
# validation / retrieval / evidence-assembly stages, not internal reasoning.
# It reports which stages ran, so it is request-independent by construction.
_UNGROUNDED_THINK_TRACE = (
    "1) 요청 접수: question_id와 question을 변형 없이 보존했다. "
    "2) 응답 계약 검증: 외부 계약이 요구하는 5개 문자열 field로 응답을 구성했다. "
    "3) 조회: Runtime View 후보 회수, semantic query 검증·컴파일, 데이터 조회는 이 배포에 "
    "연결되어 있지 않아 실행하지 않았다. "
    "4) Evidence: 실행 결과가 없으므로 source, as-of, applied rules, universe를 주장하지 않는다. "
    "5) 답변: 근거 없음을 그대로 알린다."
)


def _ungrounded_retrieved_context() -> str:
    """Machine-readable record of the fact that nothing was retrieved.

    The internal shape of ``retrieved_context`` is not yet a settled contract
    (``contracts/EVALUATION_API.md``, pending decisions), so this carries only
    what can be asserted truthfully today: the evidence state and empty slots
    for the Evidence fields of ``ARCHITECTURE.md`` section 3.
    """
    return json.dumps(
        {
            "answer_status": _NO_EVIDENCE_STATUS,
            "reasons": [_NO_EVIDENCE_REASON],
            "pipeline_stage": "transport_only",
            "sources": [],
            "effective_as_of": None,
            "applied_rules": [],
            "universe": None,
            "results": [],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


class Responder(Protocol):
    """Seam between the transport boundary and the answering pipeline."""

    def __call__(self, *, question_id: str, question: str) -> AnswerEnvelope: ...


def ungrounded_responder(*, question_id: str, question: str) -> AnswerEnvelope:
    """Build the response used while no evidence source is connected.

    ``question`` is echoed but never inspected: with no Runtime View there is no
    defensible way to react to its content, and reacting to it would be the
    fixed-answer failure mode this stage exists to avoid.
    """
    return AnswerEnvelope(
        question_id=question_id,
        question=question,
        retrieved_context=_ungrounded_retrieved_context(),
        think_trace=_UNGROUNDED_THINK_TRACE,
        answer=_UNGROUNDED_ANSWER,
    )


def create_app(responder: Responder = ungrounded_responder) -> FastAPI:
    """Create the evaluation service.

    Undeclared query parameters are ignored by the router, which is how the
    contract's "no 500 on undefined query parameters" rule is met.
    """
    app = FastAPI(
        title="Canna evaluation API",
        description="External evaluation boundary defined by contracts/EVALUATION_API.md.",
        version="0.1.0",
    )

    @app.get("/answer", response_model=AnswerEnvelope)
    def answer(
        question_id: str = Query(description="Correlation identifier echoed back verbatim."),
        question: str = Query(description="Natural-language question, echoed back verbatim."),
    ) -> Response:
        envelope = responder(question_id=question_id, question=question)
        # JSONResponse serialises with ensure_ascii=False and encodes UTF-8; the
        # media type is set explicitly because the contract requires the charset.
        return JSONResponse(content=envelope.model_dump(), media_type=JSON_MEDIA_TYPE)

    return app
