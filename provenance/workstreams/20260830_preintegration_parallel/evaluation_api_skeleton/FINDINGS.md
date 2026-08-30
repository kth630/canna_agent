# Stage 0-B — 평가 API 최소 수직 슬라이스 구현 기록

작업 단위: `IMPLEMENTATION_PLAN.md`의 `0-B. NCP minimal vertical slice`
정본 계약: `contracts/EVALUATION_API.md`
게이트 기록: 같은 디렉터리의 `GATE.md`
작업 시작 시 git: branch `main`, HEAD `250e69a7016f514f8a8c21b51cb6b102e803a2ea`, dirty

## 0. 작업 시작 시점의 git status (기록)

```text
 M AGENTS.md
 M IMPLEMENTATION_PLAN.md
 M provenance/MIGRATION_MANIFEST.json
 M pyproject.toml
 M tests/fixtures/README.md
 M tests/test_architecture_guards.py
?? provenance/MIGRATION_CHECKLIST.md
?? provenance/experiments/
?? scripts/
?? src/
?? tests/fixtures/semantic_grounding.jsonl
?? tests/fixtures/semantic_grounding_regression.jsonl
?? tests/fixtures/semantic_grounding_verification.jsonl
?? tests/fixtures/semantic_probe_catalog.json
?? tests/test_semantic_probe.py
?? tests/test_semantic_probe_live.py
```

위 6개 tracked 수정 파일은 이 작업 이전의 변경이며 건드리지 않았다. 종료 시점에도
동일하게 남아 있다(4절 diff 확인).

## 1. 작업 전 / 후 책임 차이

| 항목 | 작업 전 | 작업 후 |
|---|---|---|
| 외부 HTTP 경계 | 없음. 저장소에 서비스 코드가 없었다 | `GET /answer`가 실제 FastAPI 라우트로 존재 |
| 응답 봉투 | 문서(`contracts/EVALUATION_API.md`)에만 존재 | `AnswerEnvelope`로 코드에 고정되고 테스트로 강제 |
| Content-Type | 미구현 | `application/json; charset=utf-8` 명시적으로 반환 |
| 근거 없는 상태의 표현 | 없음 | `answer_status=refused`, `reasons=[no_data]`를 기계 판독 가능하게 반환하고 답변에서 정직하게 고지 |
| 답변 생성 | 없음 | 파이프라인 seam(`Responder`)만 존재. 실제 생성은 미구현 |
| 배포 가능성 | 없음 | `uvicorn canna.api:create_app --factory`로 기동 가능한 최소 슬라이스 |

새로 만들지 **않은** 책임: 질의 이해, Runtime View, HCX 호출, Registry, ontology,
DuckDB, Excel/holdings 적재, product·fund·holdings 연결, join/mapping, health endpoint.
`src/canna/api.py`는 `json`, `typing`, `fastapi`, 그리고 같은 패키지의 `answer_envelope`만
import한다.

## 2. 큰그림 게이트 요약

`GATE.md`에 7개 항목을 작성했다. 요약:

1. 목적: 평가자가 실제로 호출하는 전송 경계를 먼저 고정하고 NCP 제약을 조기에 관측한다.
2. capability: `임의의 (question_id, question) 문자열 쌍 → 계약이 정한 5개 문자열 field의
   UTF-8 JSON 응답`. 일반화 단위는 "질문"이 아니라 "요청"이다.
3. 계층: 신규는 전송 계층과 응답 조립 seam 하나뿐. 앞단 계층은 seam으로만 표시.
4. 계약 변경: 없음. 계약 문서·아키텍처·계획 문서 미수정.
5. 데이터 의미: grain 없음, coverage 0, as-of 주장 없음. 데이터 미연결은 오류가 아니라
   `refused` / `no_data` 상태다.
6. 하드코딩: 계약 field 이름·경로·media type·`refused`/`no_data` 어휘·근거 없음 고지
   문구 1개만 허용(6절).
7. 수용 기준: 200 / UTF-8 / 정확한 5개 문자열 schema / verbatim echo / 미정의 parameter
   안전성 + **echo 2개를 제외한 3개 field가 모든 변형 요청에서 동일**.

## 3. 일반화 단위와 영향 계층

- 일반화 단위: HTTP 요청 1건. 질문의 내용, 구조, 상품군, 답변 가능 여부는 코드 경로에
  전혀 영향을 주지 않는다.
- 이번 단계의 정확성 조건은 "질문에 반응하지 않는 것"이다. 이를
  `test_unseen_request_variants_share_one_answer_path`가 직접 반증 가능한 형태로 검사한다.
- 영향 계층: 외부 전송 경계 1개 계층. `ARCHITECTURE.md` 2절 파이프라인의 나머지 단계는
  `Responder` protocol 뒤에서 교체되며, 교체 시 외부 계약은 바뀌지 않는다.
- `create_app(responder=...)`는 이후 단계가 실제 파이프라인을 주입할 지점이다.
  import 시에는 아무 서비스도 만들지 않는다(`MIGRATION_CHECKLIST.md`의 `api.py` B 항목이
  금지한 "import 시 서비스 생성" 회피).

## 4. 새 상수와 허용 근거

| 상수 | 값 | 근거 |
|---|---|---|
| 경로 | `/answer` | `contracts/EVALUATION_API.md` 공식 외부 계약 |
| query parameter 이름 | `question_id`, `question` | 같은 계약 |
| 응답 field 이름 5개 | `question_id`, `question`, `retrieved_context`, `think_trace`, `answer` | 같은 계약 |
| `JSON_MEDIA_TYPE` | `application/json; charset=utf-8` | 같은 계약이 명시한 Content-Type |
| `_NO_EVIDENCE_STATUS` | `refused` | `ARCHITECTURE.md` 5절이 Confirmed로 정의한 `answer_status` 값 |
| `_NO_EVIDENCE_REASON` | `no_data` | `ARCHITECTURE.md` 5절이 예시한 구조화 reason |
| `_UNGROUNDED_ANSWER` | 근거 없음 고지 한국어 문구 1개 | 상품·수치·날짜·질문에 독립이며 모든 입력에 동일. 데이터가 연결되면 제거된다 |
| `_UNGROUNDED_THINK_TRACE` | 실행된/미실행 단계 요약 | 계약이 요구하는 감사 가능한 요약. 요청과 무관하게 동일 |
| `pipeline_stage` | `transport_only` | 이 배포가 전송 계층만 포함한다는 사실 표기. 내부 진단용이며 외부 계약 아님 |

넣지 **않은** 것: 상품명, 펀드명, 수익률, 날짜, 행 수, CQ ID, 평가 질문 문자열,
fixture import, Registry field/alias/join, 이전 저장소 경로.

`retrieved_context` 내부 JSON 형태(`sources`, `effective_as_of`, `applied_rules`,
`universe`, `results`)는 `ARCHITECTURE.md` 3절 Evidence 목록의 빈 슬롯을 그대로 둔 것이며,
계약으로 확정된 형식이 아니다. 코드 주석에도 provisional로 명시했다(6절 미결 결정 참조).

## 5. 실행한 실제 명령과 결과

### 5.1 API 테스트

```text
$ .venv/Scripts/python.exe -m pytest tests/test_api.py -q
..................................................                       [100%]
50 passed in 1.80s
```

### 5.2 Lint / format

```text
$ .venv/Scripts/python.exe -m ruff check src/canna/api.py src/canna/answer_envelope.py tests/test_api.py
All checks passed!

$ .venv/Scripts/python.exe -m ruff format tests/test_api.py
1 file reformatted
```

### 5.3 architecture guard — 부분 실행 (조정자 확인 필요)

조정 지시에 따라 **전체 architecture guard는 실행하지 않았다**. 0-A가 같은 시각에
`tests/fixtures/`를 수정 중이면 fixture를 읽는 guard 2개가 이 작업과 무관하게 실패할 수
있기 때문이다. fixture를 읽지 않는 guard 5개만 실행했다.

```text
$ .venv/Scripts/python.exe -m pytest tests/test_architecture_guards.py -q \
    -k "governance or legacy_or_evaluation or branch_on_nonempty or serving_code or experiment_modules_declare"
.....                                                                    [100%]
5 passed, 2 deselected in 0.08s
```

- 실행됨: governance 문서 존재, legacy/evaluation import 금지, `question_id`/`test_id`/
  `case_id`/`cq_id` 분기 금지, serving code의 experiment import 금지, experiment 배너.
- 미실행(조정자가 0-A 종료 후 1회 실행할 것): `test_runtime_does_not_embed_source_workspace_or_fixture_questions`,
  `test_question_fixtures_declare_purpose_and_explicit_semantics`.
- 미실행 guard에 대한 자체 확인: 새 runtime 파일 2개에는 이전 저장소 경로 문자열이 없고,
  fixture 질문 문자열을 포함하지 않으며, `tests/fixtures/`를 전혀 수정하지 않았다.

### 5.4 실제 응답 관측

```text
valid                  -> 200 application/json; charset=utf-8
missing question_id    -> 422 application/json   {"detail":[{"type":"missing", ...}]}
missing question       -> 422 application/json   {"detail":[{"type":"missing", ...}]}
empty both             -> 200 application/json; charset=utf-8   (빈 문자열 그대로 echo)
undefined params       -> 200 application/json; charset=utf-8
```

`missing`의 422와 그 `detail` 본문은 FastAPI 기본 동작이며 내가 결정한 정책이 아니다.
6절 미결 결정 참조.

### 5.5 범위 확인

```text
$ git status --porcelain=v1
 M AGENTS.md
 M IMPLEMENTATION_PLAN.md
 M provenance/MIGRATION_MANIFEST.json
 M pyproject.toml
 M tests/fixtures/README.md
 M tests/test_architecture_guards.py
?? provenance/MIGRATION_CHECKLIST.md
?? provenance/experiments/
?? provenance/workstreams/
?? scripts/
?? src/
?? tests/fixtures/*.jsonl, semantic_probe_catalog.json
?? tests/test_api.py
?? tests/test_semantic_probe.py
?? tests/test_semantic_probe_live.py
```

`git diff --stat`의 6개 tracked 파일 변경은 작업 시작 시점 snapshot과 동일하며 이 작업이
만든 것이 아니다. 새로 추가된 것은 `provenance/workstreams/`, `src/canna/api.py`,
`src/canna/answer_envelope.py`, `tests/test_api.py`뿐이다. 수정 금지 경로
(`CONTEXT.md`, `QUESTION_STRUCTURE.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`,
`contracts/`, `provenance/MIGRATION_MANIFEST.json`, `data/`, 다른 provenance 작업
디렉터리, 기존 semantic probe 코드·fixture, `pyproject.toml`, `uv.lock`)는 모두 무변경이다.

## 6. 유효 요청 및 보지 않은 변형 요청 테스트

`tests/test_api.py`는 50개 테스트로 다음을 검사한다.

유효 요청 경계:
- HTTP 200과 `application/json; charset=utf-8` 정확 일치
- 응답 key 집합이 계약 5개와 **정확히** 일치, 모든 값이 `str`, echo 외 3개는 비어 있지 않음
- `question_id`/`question` verbatim echo(앞뒤 공백·개행·비ASCII 보존)
- 응답 본문이 UTF-8 bytes로 나가고 `\uXXXX` escape가 아님(원문 bytes가 body에 존재)

보지 않은 변형 요청(구현 중 사용하지 않은 형태 10종):
ranking, 복수 requirement, 관계 조건, 상품군 간 비교, 답변 불가형, 영문 질문,
앞뒤 공백, 예약문자(`/ ? & = # %`) 포함 ID, 비ASCII ID + 개행 질문, 512자 ID.

- 위 10종 전부에서 200/schema/echo가 성립한다.
- `test_unseen_request_variants_share_one_answer_path`: 10종의
  `retrieved_context`/`think_trace`/`answer`가 **모두 동일**함을 확인한다. 어떤 질문
  내용에도 반응하지 않는다는 것의 직접 반증 테스트다.
- 미정의 parameter: 10종 각각에 `top_k` 중복 2회, `question_id_extra`, 한글 이름
  parameter, 빈 이름 parameter를 함께 보내도 200이며 schema가 유지된다(500 없음).
- `test_ungrounded_answer_states_absence_without_numeric_claims`: 근거 없는 답변에
  숫자가 하나도 없음을 확인한다(수치 주장 금지).
- `test_think_trace_reports_stages_without_restating_the_request`: think_trace가 질문
  문자열이나 question_id를 담지 않음을 확인한다(내부 추론·입력 반향 노출 방지).
- `test_importing_the_module_does_not_construct_a_service`: import 시 서비스 생성 없음.

테스트 안의 질문 문자열은 **전송 입력**이며 semantic fixture가 아니다. 기대 답변,
기대 plan, CQ ID를 담지 않고 `tests/fixtures/`에 등록하지도 않았다.

## 7. 데이터 / coverage / freshness 한계

- 이 슬라이스는 어떤 데이터도 읽지 않는다. `data/official_raw/`, `data/incoming/`,
  DuckDB, Registry, ontology 모두 미접촉이다.
- coverage: observed universe 0, full universe 미확인. 따라서 positive lookup, global
  top-k/count/extrema, negative/universal claim 중 어느 것도 만들 수 없고 만들지 않는다.
- freshness: 참조 snapshot이 없어 `effective_as_of`를 `null`로 두고 as-of를 주장하지 않는다.
- 결과적으로 이 배포는 평가 질문 35개 중 **어느 것도 실제로 답하지 못한다**. 이는 이
  단계의 의도된 상태이며, 응답은 그 사실을 숨기지 않는다.
- NCP 배포 제약(cold start, latency, memory, 상시성)은 아직 **관측하지 않았다**. 이
  슬라이스는 그 관측을 가능하게 만든 것까지가 산출물이고, 실제 배포·측정은 다음 작업이다.
  기동 명령: `uvicorn canna.api:create_app --factory --host 0.0.0.0 --port 8000`.

## 8. 미결 결정 — 빈 입력과 부재 입력의 외부 처리 방식

`contracts/EVALUATION_API.md`는 `question_id`/`question`을 "필수, 비어 있지 않은 문자열"로
정하면서도 이를 위반한 요청의 **외부 status와 error envelope를 확정하지 않았다**. 그래서
이번 작업에서 422/400 또는 새 JSON schema를 임의로 결정하지 않았다. 현재 관측되는 동작은
"의도적으로 선택한 정책"이 아니라 "결정 전의 기본값"이다.

현재 관측 동작:

| 입력 | 현재 결과 | 성격 |
|---|---|---|
| parameter 자체가 없음 | HTTP 422, `application/json`, FastAPI 기본 `{"detail": [...]}` | 프레임워크 기본값. 계약 5개 field 봉투가 아니고 charset도 없다 |
| 빈 문자열 `""` | HTTP 200, 계약 5개 field, 빈 문자열 echo | 별도 검증을 넣지 않은 결과 |

관찰된 문제: 부재 입력에서 나가는 응답이 계약의 5-field 봉투도, 계약의 Content-Type도
아니다. 평가 harness가 항상 5개 field를 파싱한다고 가정하면 이 경로에서 깨진다.

선택지와 영향:

1. **모든 입력을 200 + 5-field 봉투로 흡수한다.** 빈/부재 입력도 `answer`에서 필요한
   조건을 요청하는 답변으로 처리(`reasons=[unresolved]` 계열).
   - 장점: 외부 계약이 단 하나의 응답 형태만 갖는다. 평가 harness가 절대 깨지지 않는다.
     "확인할 수 없는 질문은 확인할 수 없음을 명시"라는 대회 요구와 일관된다.
   - 단점: 클라이언트 오류와 서버의 정상 거절이 같은 형태가 되어 운영 진단이 어려워진다.
   - 필요 작업: FastAPI validation handler override.
2. **부재/빈 입력은 4xx로 두되 본문을 계약 봉투 형태로 통일한다.**
   - 장점: 프로토콜 오류와 의미적 거절을 구분한다.
   - 단점: 4xx status를 계약이 아직 승인하지 않았다. 평가 harness의 비-200 처리 방식이
     확인되지 않았다.
3. **현재 기본값 유지.**
   - 단점: 부재 입력에서 응답 형태가 두 가지가 되고 charset도 달라진다. 권장하지 않는다.

추천: 1번. 단, `question_id`가 비면 correlation echo 대상이 없다는 점을 어떻게 표현할지가
남는다. 이는 사용자와 Codex가 계약 문서에서 결정할 사항이므로 **구현하지 않았다**.

### 부수적으로 확정 필요한 항목 (모두 계약의 pending 목록에 이미 있음)

- `retrieved_context` 내부 JSON schema와 size limit. 현재 형태는 provisional이며
  `ARCHITECTURE.md` 3절 Evidence 목록의 빈 슬롯일 뿐이다.
- health/readiness endpoint: `MIGRATION_CHECKLIST.md`가 이번 단계에서 `/health`를 금지해
  만들지 않았다. NCP 배포에서 상시성 점검이 필요해지면 계약 결정이 선행되어야 한다.
- NCP timeout/concurrency 정책.

### packaging 관측 (수정하지 않음)

`pyproject.toml`과 `uv.lock`은 수정 금지 경로이므로 손대지 않았고, 실제로 이번 구현에
packaging 변경이 **필요하지 않았다**(`fastapi`가 이미 dependency에 있고 환경에 설치되어
있다). 다만 관측된 잠재 취약점 하나를 보고한다.

- `tests/test_api.py`는 `fastapi.testclient.TestClient`를 통해 `httpx`를 필요로 하는데,
  `httpx`는 `pyproject.toml`의 dependency에도 dev group에도 선언되어 있지 않다. 현재는
  `langchain-naver` 경유로 전이 설치되어 동작한다.
- 영향: 상위 의존성이 바뀌면 API 테스트가 환경 문제로 실패할 수 있다.
- 제안: dev group에 `httpx`를 명시적으로 추가. 조정자 판단으로 별도 처리 요청.

## 9. 수정 파일 목록

신규 생성:

- `src/canna/api.py` — `GET /answer` 라우트, `create_app` factory, `Responder` seam,
  근거 없음 응답 생성기
- `src/canna/answer_envelope.py` — 외부 응답 봉투(`AnswerEnvelope`, `JSON_MEDIA_TYPE`)
- `tests/test_api.py` — 전송 계약 테스트 50개
- `provenance/workstreams/20260830_preintegration_parallel/evaluation_api_skeleton/GATE.md`
- `provenance/workstreams/20260830_preintegration_parallel/evaluation_api_skeleton/FINDINGS.md`

기존 파일 수정: **없음**. 삭제: 없음.

## 10. 아키텍처 / 계약 이탈 여부

이탈 없음.

- `contracts/EVALUATION_API.md`의 유효 요청 경계를 그대로 구현했고 계약 문서를 수정하지 않았다.
- `ARCHITECTURE.md`의 Confirmed 결정을 바꾸지 않았다. 5절 status/reason 어휘를 사용만 했다.
- `AGENTS.md` 금지 사항 대조: CQ/question_id/질문 문자열 분기 없음, fixture import 없음,
  상품명·날짜·행 수 고정 없음, Registry 상수 중복 없음, 이전 저장소 의존 없음,
  원본 데이터 미수정.
- `MIGRATION_CHECKLIST.md`의 `api.py`/`test_api.py` B 판정 준수: 책임(`GET /answer`,
  UTF-8 JSON, 5개 문자열 응답, echo, 미정의 parameter 안전성)만 새로 작성했고, 이전
  파일을 복사하지 않았으며 금지된 `/health`, import 시 서비스 생성, 기존 runtime/settings
  의존, 고정 문구·고정 수치를 만들지 않았다.
- 결정하지 않고 남긴 것: 빈/부재 입력의 외부 처리(8절). 이것이 이 작업에서 유일하게
  계약 결정을 요구하는 지점이다.
