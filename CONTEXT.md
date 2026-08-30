# Context

## 1. 목적과 문서 상태

Canna는 국내채권, 국내 ETF, 해외 ETF, 공모펀드와 검증된 외부 데이터를 바탕으로
자연어 질문에 적합한 금융상품을 조회·비교·설명하는 근거 기반 Agent다.

이 문서는 공식 요구사항, 공식 데이터 기준선, 검증된 데이터 관측, 일정과 provenance를
기록한다. 팀의 설계 결정은 `ARCHITECTURE.md`, 실험과 구현 순서는
`IMPLEMENTATION_PLAN.md`, 질문 의미 구조는 `QUESTION_STRUCTURE.md`가 각각 정본이다.

## 2. 확인된 대회 요구사항

- 제공 관계형 데이터를 활용해 금융상품 Agent를 구현한다.
- 외부 정형·비정형 데이터를 수집·결합할 수 있다.
- 검색 결과를 바탕으로 상품을 조회·비교·설명한다.
- 답변에 근거와 참조 데이터 또는 문서를 표시한다.
- 확인할 수 없는 질문은 확인할 수 없음을 명시하거나 필요한 조건을 요청한다.
- 근거 없는 수익률 전망이나 단정적 투자 추천을 생성하지 않는다.
- Intent 분석과 최종 답변 생성에는 NCP HyperCLOVA X를 사용한다.
- 도메인별 Turtle Ontology 5개를 제출한다.
- 평가 가능한 API와 재현 가능한 소스·환경·기술 제안서를 제출한다.

설명회 구두 안내에 따르면 평가는 단발 질문 35개이며 답변 가능 30개, 답변 불가 5개이고
문항별 부분점수는 없다. 애매한 질의는 출제하지 않는다는 안내가 있었다. 예시 질문이나
내부에서 만든 35개 질문 목록은 제품 사양이나 정답이 아니며 테스트 재료일 뿐이다.

## 3. 공식 제공 데이터 기준선

2026-08-24 배포본 8개 Excel을 공식 기준선으로 사용한다. 2026-07-11 배포본은 대체됐으며
실행 기준선으로 사용하지 않는다.

| table ID | 상품군 | data rows | data columns | 식별자 후보 |
|---|---|---:|---:|---|
| `PRBD01N001` | 국내채권 | 21,882 | 58 | `pd_no` |
| `PREF01N001` | 국내 ETF | 1,780 | 98 | `pd_itm_no` |
| `PREF02N001` | 해외 ETF | 6,037 | 49 | `pd_itm_no` |
| `PRFD01N001` | 공모펀드 | 23,676 | 75 | `itm_no` |

- 배포 기준일: 2026-08-24
- 국내 데이터: 영업일 2026-08-22까지
- 해외 데이터: 한국시간 2026-08-23 기준
- 원본 Excel은 `data/official_raw/`에 읽기 전용으로 둔다.
- 실제 파일 hash는 `provenance/MIGRATION_MANIFEST.json`에 기록한다.

### 데이터 적용 규칙

- 새 제공 데이터와 이전 데이터가 충돌하면 새 제공 데이터를 우선한다.
- 외부 데이터와 제공 데이터가 충돌하면 제공 데이터를 우선하고 충돌을 기록한다.
- 확인되지 않은 코드 의미를 추측하지 않는다.
- 조건·정렬·비교·집계에 사용하는 수치의 0과 결측은 평가 가능한 값이 없는 것으로
  취급해 해당 연산의 모집단에서 제외한다. 원본값은 수정하지 않는다.
- 국내채권 `buyable_quantity`는 사용하지 않는다. 상장폐지 또는 리스팅 종료가 확인된
  종목 외에는 구매 가능한 것으로 간주한다.
- 외부 데이터에는 source와 기준일을 보존한다.

### 2026-08-30 read-only data discovery 관측

`data/official_raw/`와 `data/incoming/`을 수정하지 않고 schema, 행 수, 결측, 중복,
식별자 후보와 날짜 범위를 조사했다. 상세 근거는
`provenance/experiments/stage_0c_data_discovery/FINDINGS.md`에 있다.

- 국내채권은 21,882개 source row와 `pd_no` 20,497개가 일치하지 않는다. 현재 파일에서
  (`pd_no`, `pd_exg_mkt`, `info_seq`)는 source-row 식별에 사용할 수 있지만, 이를 곧바로
  product grain이나 영구 canonical identifier로 일반화하지 않는다.
- 국내 ETF의 현재 sentinel-active 관측 모집단 1,161개 중 `du_er_1y`를 0·결측 제외 후
  사용할 수 있는 행은 964개, `cu_charge_rt`는 67개였다. 이 수치는 현재 source hash에
  대한 관측값이며 runtime 상수나 일반 coverage 규칙이 아니다.
- 해외 ETF 공식 표에는 다기간 수익률 field가 없고 1일 수익률만 있다. 공모펀드에는
  승인된 단일 총보수 field가 없으며 여러 보수 구성요소가 따로 있다. 없는 기간이나
  합성 지표를 의미 확인 없이 만들지 않는다.
- 한 상품 row 안에서도 업무 field별 effective date가 다를 수 있다. freshness는 파일명이나
  배포일 하나가 아니라 실제 capability가 사용하는 field와 source 기준으로 확인한다.
- 0·결측 제외 규칙은 수치 연산에 사용하는 measure에 적용한다. `0`이 정상 code나 flag인
  field에 같은 규칙을 적용하지 않는다.
- 상품군 간 지표의 의미, 단위, 통화, 기간과 모집단이 같다는 근거가 확인되기 전에는
  통합 ranking이나 직접 비교를 지원한다고 가정하지 않는다.

이 관측을 바탕으로 2026-08-30 사용자와 Codex는 현재 제출 범위의 공식 네 상품군,
외부 holdings와 기존 Ontology 5개를 먼저 전체 대조하기로 결정했다. 대조표에서 의미·지표·
관계를 `유지 | 수정 | 제외 | 추가`로 판정하고 조회 grain을 승인한 뒤, 조회용 DB·Execution
Registry와 새 Ontology/SHACL·Semantic Registry를 병렬 구축한다. 이는 모든 원본 column을
지원 의미로 승격하거나 미래 외부 데이터 계약을 미리 만든다는 뜻이 아니다. 최신 실행
결정은
`provenance/workstreams/20260830_preintegration_parallel/DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md`에
기록한다.

## 4. 평가 API의 공식 경계

- `GET /answer`
- 요청 query parameter: 비어 있지 않은 `question_id`, `question`
- 응답: HTTP 200, JSON, `application/json; charset=utf-8`
- 필수 문자열 field: `question_id`, `question`, `retrieved_context`, `think_trace`, `answer`
- 확인 불가 질문도 같은 응답 schema를 유지한다.
- 인증 header나 POST body를 요구하지 않는다.
- 미정의 query parameter가 들어와도 500 오류를 내지 않는다.

상세한 공식 경계와 내부에서 확정하지 않은 부분은 `contracts/EVALUATION_API.md`에 분리한다.

## 5. Holdings 수집 번들 관측

읽기 전용 원본 번들은 `data/incoming/holdings_20260829.zip`이다.

- ZIP SHA-256: `93fc5f2c4c4ee00fe3bf7ac74bade43beb546b7eb36df3cfce4d5cac3d247a29`
- ZIP 무결성 및 내부 manifest의 28개 file size/hash 일치 확인
- normalized row 수:
  - `product_mapping`: 15,981
  - `holdings`: 1,521,512
  - `coverage`: 3
  - `failures`: 2,294
- exact duplicate row 0, `source_record_id` 중복 0, mapping에 연결되지 않는 holdings 0

이 번들의 normalized v1은 실행 schema의 정본이 아니다. v2를 만들 때 다음을 해결해야 한다.

1. 국내 ETF의 `holding_as_of=2026-08-22`는 확인된 실효일이 아니라 요청일이다.
2. 공모펀드 holdings 48,201행의 `held_security_id`가 전부 비어 있어 역방향 종목 관계
   검색에는 entity resolution이 필요하다.
3. 공모펀드 direct holding과 look-through exposure를 별도 predicate와 grain으로 나눈다.
4. 공모펀드의 product→portfolio mapping과 KOFIA source resolution 상태를 분리한다.
5. held security ID에 KRX/ISIN/CUSIP 등의 scheme을 명시한다.
6. coverage의 product/class/portfolio/call grain을 분리한다.
7. 공모펀드 `sale_yn='판매중'`은 의미 검증 전까지 공식 eligibility가 아니라 collection
   scope로 표현한다.
8. 국내 ETF weight는 대부분 0이므로 weight filter/ranking capability를 노출하지 않는다.
9. 상품군별 snapshot freshness가 달라 freshness 상태 없이 통합 current ranking을 하지 않는다.
10. 관계 검색은 logical duplicate 때문에 단순 JOIN 후 행 순위를 매기지 않고
    `EXISTS` 또는 product grain `DISTINCT`를 사용한다.

일부 문제는 normalized v2 재생성으로 해결 가능하지만, 해외 ETF unresolved 원인 분리,
공모펀드 security ID, 오래된 snapshot의 완전성은 추가 검증이나 수집이 필요하다.

## 6. 일정과 provenance

- 기존 공지 기준 제출 마감: 2026-09-06 23:59
- 운영 안내 기간: 2026-09-07~2026-09-20
- 이전 작업공간 기준 commit:
  `11dfd6fe340d6cf8881edc5526db5e2fe287dd5b`
- 이전 작업공간은 dirty 상태로 보존하며 이 저장소는 그 Git history나 runtime에 의존하지 않는다.

일정과 API가 추가 공지로 변경되면 공식 최신 자료를 확인한 뒤 사용자 승인하에 갱신한다.
