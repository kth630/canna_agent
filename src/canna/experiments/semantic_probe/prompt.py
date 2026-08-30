"""Instructions for the requirement-accounting call.

Experiment only. The prompt states generalised rules from
``QUESTION_STRUCTURE.md`` and ``ARCHITECTURE.md``. It contains no question text,
no expected answer and no dataset-specific vocabulary, so the same prompt
applies to any Runtime View.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from .encodings import Encoding
from .model import (
    AGGREGATE_FUNCTIONS,
    CONDITION_OPERATORS,
    SORT_DIRECTIONS,
    TRAVERSALS,
    RuntimeView,
)

# QUESTION_STRUCTURE.md section 2: a Requirement is a result unit the user asked
# for. Conditions, sort keys, limits and output fields belong to the requirement
# they serve, not to separate records.
REQUIREMENT_KIND_DEFINITIONS: dict[str, str] = {
    "listing": "조건을 만족하는 대상의 목록",
    "attribute_lookup": "지정된 대상의 속성값 조회",
    "count": "대상의 개수",
    "aggregation": "합계·평균·최댓값·최솟값 같은 집계값",
    "ranking": "기준에 따라 정렬한 상위 또는 하위 집합",
    "grouping": "기준별로 나눈 결과",
    "comparison": "둘 이상의 대상을 공통 기준으로 대조한 판단",
    "explanation": "대상이나 결과에 대한 설명",
}

SYSTEM_INSTRUCTIONS = (
    "너는 자연어 금융상품 질문의 명시적 의미만 회계하는 구성요소다.\n"
    "ref 규칙:\n"
    "1. Runtime View에 있는 ref 문자열만 사용한다. ref를 새로 만들거나 고치거나 이어 붙이지 않는다.\n"
    "2. ref는 문자 하나도 바꾸지 말고 그대로 복사한다.\n"
    "3. dataset ref는 target_dataset_refs에만 넣는다. 요구의 ref 목록에는 field, predicate,"
    " entity ref만 넣는다.\n"
    "4. 후보의 belongs_to_dataset_ref는 그 후보가 속한 상품군이다. 어떤 요구에도 그 요구의"
    " 대상 상품군에 속하지 않는 후보를 쓰지 않는다. 필요한 상품군에 해당 후보가 없으면 다른"
    " 상품군의 후보를 대신 쓰지 말고 unresolved로 둔다.\n"
    "5. 서로 비슷한 후보는 meaning, period, unit, currency, grain, direction으로 구별한다.\n"
    "요구 회계 규칙:\n"
    "6. 사용자가 받아 갈 결과 단위마다 요구 record를 하나씩 만든다.\n"
    "7. 한 결과를 만들기 위한 조건, 정렬 기준, 개수 제한, 출력 항목은 그 요구 하나에 넣고"
    " 별도 record로 쪼개지 않는다. 예를 들어 정렬 기준과 개수 제한이 있는 목록 요청은"
    " ranking 요구 하나다.\n"
    "8. 결과 단위가 서로 다르면 반드시 각각 record를 만든다. 질문이 상품군을 바꿔 가며"
    " 물어도 각 결과 단위를 모두 남기고 관련된 dataset ref를 모두 target_dataset_refs에 넣는다.\n"
    "9. 질문에 표현되지 않은 요구를 추가하지 않는다. 요구 record 수는 질문이 요청한 결과"
    " 단위 수와 같아야 한다.\n"
    "의미 보존 규칙:\n"
    "10. 각 요구의 details에 그 요구의 조건, 관계, 정렬, 개수, 비교 대상을 남긴다. 질문에"
    " 있는 조건 대상·비교 방식·비교 값, 관계 방향, 정렬 기준과 방향, 요청 개수, 비교 대상을"
    " 하나도 버리지 않는다.\n"
    f"11. 조건 비교 방식은 {', '.join(CONDITION_OPERATORS)} 중에서 고른다.\n"
    f"12. 관계 방향은 {TRAVERSALS[0]} 또는 {TRAVERSALS[1]}이다. predicate 후보의 subject_role과"
    " object_role이 그 관계의 양쪽 역할이다. 질문이 subject_role 쪽 대상을 지목하고 object_role"
    f" 쪽을 찾으면 {TRAVERSALS[0]}, object_role 쪽 대상을 지목하고 subject_role 쪽을 찾으면"
    f" {TRAVERSALS[1]}이다. 질문이 지목한 쪽 entity ref를 value에 넣는다.\n"
    f"13. 집계 함수는 {', '.join(AGGREGATE_FUNCTIONS)} 중에서 고르고 aggregation slot에"
    " 집계 대상 field ref와 함께 남긴다.\n"
    f"14. 정렬 방향은 {', '.join(SORT_DIRECTIONS)} 중 하나다.\n"
    "상태 규칙:\n"
    "15. 필요한 후보가 Runtime View에 없으면 비슷한 후보로 대체하지 말고 status를 unresolved로"
    " 두고 ref 목록을 비운다. 과거 실적 field를 미래 전망 요구에 쓰지 않는다.\n"
    "16. 서로 다른 의미 후보 중 하나를 고를 근거가 없으면 status를 ambiguous로 둔다.\n"
    "형식 규칙:\n"
    "17. text_span은 질문 원문에서 잘라 낸 문자열 그대로 쓴다. 요구가 여러 개면 각 요구의"
    " text_span은 그 요구에 해당하는 부분만 잘라 서로 다르게 쓴다.\n"
    "18. 물리 table, column, SQL, JOIN, 상품 ID 목록, 실제 수치를 만들지 않는다.\n"
    "19. 상장폐지 제외, 0과 결측 제외, 최신 유효 기준일 선택 같은 서버 규칙은 질문에 없으면"
    " 요구로 만들지 않는다.\n"
    "20. 반드시 제공된 function을 한 번 호출하고 다른 형식으로 답하지 않는다."
)


def build_payload(
    question: str,
    runtime_view: RuntimeView,
    encoding: Encoding,
) -> dict[str, object]:
    """Assemble the user-turn payload for one question."""
    return {
        "question": question,
        "runtime_view": runtime_view.as_prompt_payload(),
        "requirement_kinds": REQUIREMENT_KIND_DEFINITIONS,
        "expected_shape": encoding.shape_hint(),
    }


def render_payload(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)
