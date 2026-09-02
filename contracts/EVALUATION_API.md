# Evaluation API Contract

## Authority

이 문서는 현재 확인된 공식 평가 API의 외부 경계만 기록한다. 내부 Runtime View,
semantic query wire format, Tool 수, retry 횟수, deterministic fixture plan은 공식 계약이
아니며 이 문서에서 확정하지 않는다.

## `GET /answer`

### Request

| query parameter | rule |
|---|---|
| `question_id` | 필수, 비어 있지 않은 문자열, 응답에 그대로 반환 |
| `question` | 필수, 비어 있지 않은 자연어 문자열 |

- 인증 header를 요구하지 않는다.
- POST body를 사용하지 않는다.
- 미정의 query parameter가 들어와도 500 오류를 내지 않는다.
- `question_id`는 correlation/echo 용도이며 runtime routing key로 사용하지 않는다.

### Response

- HTTP status: `200 OK`
- Content-Type: `application/json; charset=utf-8`
- 필수 field는 모두 문자열이다.

```json
{
  "question_id": "request-001",
  "question": "국내 ETF 중 1년 수익률이 높은 상품 10개를 보여줘",
  "retrieved_context": "{...}",
  "think_trace": "검증 및 조회 단계의 감사 가능한 요약",
  "answer": "근거 범위 안의 한국어 답변"
}
```

- 확인 불가 질문도 동일한 HTTP status와 schema를 유지한다.
- `retrieved_context`는 JSON 문자열로 source, as-of, applied rules, coverage/universe,
  실행 조건과 결과를 전달한다.
- `think_trace`는 내부 chain-of-thought가 아니라 validation, retrieval, evidence assembly의
  감사 가능한 요약이다.
- `answer`는 Evidence 범위 밖의 내용을 추가하지 않는다.

## HCX boundary

평가용 실행에서 질의 Intent 분석과 최종 답변 생성에는 NCP HyperCLOVA X를 사용한다.
서버 검증, SQL compilation, retrieval과 Evidence assembly는 결정적 코드로 수행할 수 있다.

## Pending implementation decisions

- validation error를 외부 envelope 안에서 표현하는 정확한 방식
- result truncation과 `retrieved_context` size limit
- health/readiness endpoint
- NCP deployment의 timeout/concurrency 정책
- HCX ① 내부 계약. nested/grouped-flat/JSON-in-string/line/one-line은 후속 실험에서
  production 생성 안정성을 확보하지 못했다. 현재 후보는 서버가 만든 전체 PlanOption의
  요청 단위 opaque `selected_plan_ref` 하나를 고르게 하는 방식이지만, 이는 Confirmed
  아키텍처 변경 승인 전 제안이며 외부 API 계약이 아니다.

위 항목은 실험과 배포 결과로 정하되 외부 `GET /answer` 계약을 깨지 않는다.
