# 구현 전 큰그림 게이트 — 0-B 평가 API 최소 수직 슬라이스

작업 단위: `IMPLEMENTATION_PLAN.md`의 `0-B. NCP minimal vertical slice`
정본 계약: `contracts/EVALUATION_API.md`
작성 시점 git HEAD: `250e69a7016f514f8a8c21b51cb6b102e803a2ea` (branch `main`, dirty)

## 1. 시스템 수준 목적

외부 평가자가 호출하는 `GET /answer`의 전송 경계를 실제 FastAPI 서비스로 먼저 세운다.
목적은 답을 잘 하는 것이 아니라, 이후 모든 단계가 그 위에 얹힐 응답 봉투(envelope)를
고정하고 NCP 배포 제약(cold start, latency, memory, 상시성)을 조기에 관측할 수 있는
가장 얇은 수직 슬라이스를 만드는 것이다.

## 2. 문항이 아닌 일반화된 capability

`임의의 (question_id, question) 문자열 쌍을 계약이 정한 5개 문자열 field의 UTF-8 JSON
응답으로 변환하고, 근거가 없을 때 그 사실을 정직하게 알린다.`

일반화 단위는 "질문 하나"가 아니라 "요청 하나"다. 이 슬라이스에서 응답 본문은
`question_id`/`question` echo를 제외하면 모든 입력에 대해 동일해야 한다. 즉 질문 내용에
반응하는 코드 경로가 존재하지 않는 것이 이번 단계의 정확성 조건이다.

## 3. 영향을 받는 아키텍처 계층

- 신규: 외부 전송 계층(HTTP/JSON envelope)과 응답 조립 seam 하나.
- 미구현으로 남기는 계층: Runtime View, HCX ①/②, 서버 검증·컴파일, Execution/Semantic
  Registry, DuckDB 실행, Evidence 생성.
- `ARCHITECTURE.md` 2절 파이프라인 중 이번에 만드는 것은 마지막 출력 봉투뿐이며, 그
  앞단은 seam(교체 지점)으로만 표시하고 채우지 않는다.

## 4. 변경되는 계약

없다. `contracts/EVALUATION_API.md`의 유효 요청 경계를 그대로 구현한다.
계약 문서, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, `CONTEXT.md`,
`QUESTION_STRUCTURE.md`는 수정하지 않는다.

계약이 아직 확정하지 않은 항목(빈 `question_id`/`question`의 외부 error envelope와 status,
health/readiness endpoint, `retrieved_context` size limit)은 이번 단계에서 결정하지 않고
`FINDINGS.md`의 미결 결정으로 보고한다.

## 5. 데이터 grain · coverage · freshness · 실패 의미

- data grain: 없음. 이 슬라이스는 어떤 데이터셋도 읽지 않는다(Excel/ZIP/DuckDB/Registry 전부 미접촉).
- coverage: `observed = 0`, `full` universe 미확인. 따라서 어떤 positive/negative/universal
  claim도 만들 수 없다.
- freshness: 참조 snapshot이 없으므로 as-of를 주장하지 않는다.
- 실패 의미: 데이터 미연결은 오류가 아니라 정상적인 `근거 없음` 상태다.
  `ARCHITECTURE.md` 5절 어휘로 `answer_status=refused`, `reasons=[no_data]`에 해당하며,
  이를 `retrieved_context`에 기계가 읽을 수 있게 남기고 `answer`에서 정직하게 말한다.
  `ARCHITECTURE.md` 6절에 따라 근거 없이 상품·수치·순위를 만들어내지 않는다.

## 6. 금지할 하드코딩과 허용할 안정 상수

금지(이 슬라이스에서 실제로 지킬 것):
- `question_id`, 정확한 question 문자열, CQ ID, case ID 기반 런타임 분기
- 특정 상품명·펀드명·수익률·날짜·행 수
- 평가 fixture import, 예상 답변 문자열
- Registry 밖의 field/predicate/alias/join 상수
- 이전 저장소 import·경로 fallback

허용할 안정 상수와 근거:
- `"/answer"` 경로와 `question_id`, `question`, `retrieved_context`, `think_trace`,
  `answer` field 이름: `contracts/EVALUATION_API.md`의 공식 외부 계약.
- `"application/json; charset=utf-8"`: 같은 계약이 명시한 Content-Type.
- `refused`, `no_data`: `ARCHITECTURE.md` 5절이 Confirmed로 정의한 status/reason 어휘.
- 데이터 근거가 없음을 알리는 한국어 일반 문구 1개: 질문·상품·수치에 독립이며 모든
  입력에 동일하게 적용되므로 문항 하드코딩이 아니다. 데이터가 연결되면 제거된다.

## 7. 수용 기준과 보지 않은 변형 질문

수용 기준:
1. 유효 요청에 HTTP 200과 `application/json; charset=utf-8` 반환.
2. 응답 key 집합이 계약의 5개와 정확히 일치하고 모든 값이 문자열.
3. `question_id`와 `question`이 입력 그대로 echo되며 비ASCII가 손상되지 않는다.
4. 미정의 query parameter(복수·중복·비ASCII 포함)에도 500이 발생하지 않는다.
5. `retrieved_context`는 기계 판독 가능한 JSON 문자열이고, `think_trace`는 단계 요약이며
   내부 chain-of-thought를 노출하지 않는다.

보지 않은 변형 요청(테스트에서 실제로 실행):
- 서로 다른 구조의 질문(단일/복수 requirement, 관계 조건, 비교, 답변 불가형)
- 비ASCII·공백·구두점·매우 긴 question_id
- 미정의 parameter 다수, 같은 이름 반복, 예약어처럼 보이는 이름
- 위 모든 변형에서 echo 2개를 제외한 3개 field가 **완전히 동일**할 것.
  이 불변식이 깨지면 질문 내용에 반응하는 분기가 생겼다는 뜻이므로 반증된다.

반증 조건: 어떤 입력에서든 `retrieved_context`/`think_trace`/`answer`가 달라지거나,
근거 없이 상품·수치를 언급하거나, 500이 발생하면 이 단계는 실패다.
