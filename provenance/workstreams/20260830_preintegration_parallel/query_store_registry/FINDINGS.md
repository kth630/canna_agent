# 조회용 DB · Ontology/SHACL · Semantic/Execution Registry 구축 기록

상태: **구축 완료, 실제 데이터로 재현 검증됨**. 게이트는 같은 디렉터리의 `GATE.md`다.
이 문서는 실제 명령과 출력, 구조 결정의 근거, 남은 데이터 한계를 기록한다.

## 1. 산출물

| 경로 | 내용 |
|---|---|
| `catalog/` | Data Catalog 입력 7개(상품군, 공식 field 전수 binding, holdings binding, 관계 규칙, 식별자 규칙, 관계 predicate binding, 충돌 그룹) |
| `ontology/` | 제출용 TTL 5개와 SHACL shape, namespace·생성 규칙 문서 |
| `src/canna/store/` | 재현 가능한 store build(원본 mirror, grain 투영, 관측, 관계, coverage, 충돌, Data Catalog)와 원자적 publish·build lock |
| `src/canna/registry/` | Ontology → Semantic Registry, Data Catalog → Execution Registry와 불일치 검증 |
| `src/canna/graph/project.py` | store → ABox bounded sample 투영(SHACL 검증용이며 전체 KG 적재가 아니다) |
| `scripts/build_query_store.py`, `scripts/build_registries.py`, `scripts/project_abox.py` | 재현 명령 |
| `data/processed/` | `query_store.duckdb`(약 586MB), `data_catalog.json`, `semantic_registry.json`, `execution_registry.json`, `abox_sample.ttl` (모두 Git 제외) |

## 2. 조회용 DB 구조

물리 table은 **26개**다. 원본 mirror 8개와 정규화·관측·관계·운영 table 18개로 나뉜다.
grain별 table을 분리했고, 어떤 관계 JOIN도 상품 결과 grain과 섞이지 않는다.

| grain | table | 2026-08-31 build 행 수 |
|---|---|---:|
| source row | `src_prbd01n001` / `src_pref01n001` / `src_pref02n001` / `src_prfd01n001` | 21,882 / 1,780 / 6,037 / 23,676 |
| source row (외부) | `src_holdings_product_mapping` / `holdings` / `coverage` / `failures` | 15,981 / 1,521,512 / 3 / 2,294 |
| product | `product` | 28,314 |
| product class | `product_class` | 23,676 |
| product class group | `product_class_group` | 6,877 |
| portfolio | `portfolio` | 8,476 |
| security | `security` | 190,280 |
| metric observation | `metric_observation` | 828,004 |
| attribute observation | `attribute_observation` | 1,270,019 |
| raw holding observation | `holding_observation` | 1,521,512 |
| product↔portfolio mapping | `product_portfolio_map` | 15,981 |
| coverage / failure / conflict | `holdings_coverage`, `semantic_coverage`, `collection_failure`, `source_conflict` | 3 / 219 / 2,294 / 1,240 |
| 정체성·출처·식별 | `subject`, `identifier`, `data_source`, `held_identifier_classification` | 250,746 / 194,264 / 9 / 196,752 |

derived 18개 = product, product_class, product_class_group, portfolio, security, subject,
identifier, metric_observation, attribute_observation, holding_observation,
product_portfolio_map, holdings_coverage, semantic_coverage, collection_failure,
source_conflict, data_source, held_identifier_classification, build_manifest.

`subject`는 product·product class·portfolio·security를 하나의 key 공간으로 묶는 식별
table이며, 관측·매핑·향후 문서 관계가 모두 이 key를 참조한다.

행 수는 현재 source hash에 대한 관측이며 runtime 규칙이 아니다.

### 구조 결정의 근거

- 국내채권은 `pd_no` 20,497개와 source row 21,882개가 다르다. product와 source row를
  분리하고, 지표 관측에 `source_row_id`를 남겨 상품 순위 전에 선택 규칙을 강제한다.
- 공모펀드 공식 행은 클래스 단위다. 클래스를 결과 grain으로 두고, 대표 종목번호 묶음은
  `product_class_group`으로 분리했다. 묶음(6,877)과 포트폴리오(1,809)는 수가 다르다.
- 외부 번들의 `project_product_id`가 네 상품군 모두에서 공식 key와 정확히 일치한다
  (domestic_etp 1,164/1,164, overseas_etp 5,958/5,958, public_fund 8,859/8,859). 이
  관측을 근거로 공식 subject와 외부 mapping을 직접 조인한다.
- 공모펀드 mapping의 `portfolio_id`는 8,859행 모두 공식 `rptt_ksd_itm_no`와 값이 같다.
  그래도 포트폴리오를 대표 묶음과 동일 개체로 만들지 않고 관계로만 연결한다.
- 보유 관측의 관계 종류는 번들 README가 문서화한 source 문자열 규칙으로 판정한다.
  `unclassified` 관측은 0이며, 규칙이 맞지 않는 행은 `unclassified`로 남고 관계 실행에
  쓰이지 않는다.

## 3. 보존한 상태

- **as-of**: 국내 ETF 보유내역은 `requested_only`(요청일만 확인)로, 해외·공모펀드는
  `effective_reported`로 기록한다. 요청일을 실효일 column에 넣지 않는다.
- **식별자**: 보유 종목 식별자는 형식 규칙으로 scheme을 판정하고 ISIN은 검사숫자까지
  확인한다. 관측 분포는 `checksum_verified` 1,344,679 / `format_matched` 55,894 /
  `unverified_scheme` 72,736 / `absent` 48,201 / `format_matched_checksum_failed` 2다.
  Security는 해석된 식별자에서만 만든다(190,280개). 공모펀드 보유내역은 식별자가 없어
  종목 관계를 만들지 않고 이름 원값만 남긴다.
- **coverage와 실패**: 번들 coverage 3행에 공식 subject 수, 매핑된 subject 수, 관측된
  포트폴리오·subject 수, 관측 행 수, 해석된 종목 행 수를 함께 기록한다. 수집 실패
  2,294건은 별도 table로 남아 "보유 없음"으로 바뀌지 않는다.
- **값 상태**: 0과 결측을 원본에서 바꾸지 않고 `zero_excluded`, `parse_failed`,
  `date_parse_failed`로 표시한다. 지표별 관측 모집단은 `semantic_coverage`가 가진다.
  관측 그룹 수와 coverage 행 수가 다르면 build가 실패한다(metric 108, attribute 111,
  합계 219이 실제 관측 그룹 수와 일치함을 build와 테스트가 각각 확인한다).
- **충돌**: 같은 의미의 두 출처가 다르면 기록한다. 현재 운용사명 1,208건, 기초지수명
  32건이 서로 다르고, 공식 상품명과 외부 상품명이 다른 사례는 0건이다.

## 4. Registry

- Semantic Registry는 TTL 5개에서만 생성한다. 용어 331개(지표 111, 속성 96, 식별자
  scheme 22, class 37, predicate 18, data property 29, shape 18)이며 물리 binding·행 수·
  coverage 문자열이 들어가면 생성이 실패한다.
- Execution Registry는 Data Catalog에서 생성하고 Semantic Registry와 대조한다. binding
  245개, 고유 semantic ID 210개, 관계 binding 8개(3개 상품군 × 정·역방향, 공모펀드는
  direct와 look-through 분리), 사유가 기록된 unbound source field 35개.
- 실제로 잡아낸 불일치 예: 기간 미선언(일간 고가·저가·시가·NAV 등락), text 원문에서
  parse한 총보수의 연산 가능성, 소수점 없는 정수 column의 정렬 요구, 공모펀드 클래스
  grain에서 쓰이는 공통 속성의 grain 선언 누락. 모두 build 실패로 드러나 온톨로지 또는
  catalog를 고친 뒤에야 통과했다.

## 5. 실행한 검증

```powershell
uv run python scripts/build_query_store.py
uv run python scripts/build_registries.py
uv run python scripts/project_abox.py
uv run python -m pytest tests/ -q --basetemp <고유 경로>
uv run python -m ruff check src/canna scripts/build_query_store.py scripts/build_registries.py scripts/project_abox.py tests
git diff --check
uv run python scripts/audit_0d_inventory.py --verify
```

결과.

- store build: `status=ok`, `hash_mismatches=[]`, 단계별 소요 16.4s/3.5s/8.6s/24.5s(원본
  적재), 2.6s(개체), 20.8s(관측), 8.1s(번들), 0.5s(포트폴리오), 44.7s(종목·보유),
  19.3s(coverage·충돌), 4.0s(grain 검증·catalog) — 전체 약 2분 30초.
- registry build: `status=ok`, semantic 331 용어, execution 245 binding, 관계 binding 8.
- ABox 투영: triple 5,191, `shacl_conforms=true`.
- 테스트: **325 passed, 1 skipped**. skip은 HyperCLOVA X 실호출 테스트가 provider 응답
  실패로 스스로 건너뛴 것이며 이번 작업과 무관하다. 같은 커밋에서 두 번 재실행하면
  **326 passed, 0 skipped**다. architecture guard 포함.
- lint: 이번 작업 파일 `All checks passed!`. `git diff --check` 오류 없음.
- 물리 table 26개 확인(원본 mirror 8 + 파생 18).
- coverage 대조: metric 관측 그룹 108 = coverage 행 108, attribute 111 = 111, 합계 219.
- 원본 무결성: `MIGRATION_MANIFEST.json`의 9개 원본 hash 전부 일치, 0-D 감사 `status=ok`.

grain 검증은 build 안에서 강제된다. uniqueness 18개 key, 참조 무결성 6개 경로 모두
위반 0이며, 위반이 있으면 build가 예외로 멈춘다.

## 6. 남은 데이터 한계

- 국내 ETF 보유내역의 실효일은 여전히 확인되지 않았다. 요청일만 있는 상태로 남는다.
- 공모펀드 보유내역은 종목 식별자가 없어 종목 기준 역방향 검색에 쓸 수 없다. 이름
  기반 entity resolution은 별도 결정이 필요하다.
- 공모펀드 결산일이 2014년부터 2026년까지 흩어져 있어 상품 간 비교 전에 기준일 필터가
  필요하다. look-through 행은 자펀드마다 복제돼 있어 모펀드 단위 집계에는 상위
  포트폴리오 기준 중복 제거가 필요하다.
- 해외 ETF의 `unresolved` 431건은 후보 없음과 다건 후보가 섞여 있어 원인을 분리할 수
  없다. 번들이 구분 정보를 남기지 않았다.
- 국내 ETF 보유 비중은 대부분 0이라 비중 기반 순위 capability를 열지 않았다.
- 상품군 간 통합 비교는 단위·통화·기간·모집단 호환 근거가 없어 비교 그룹을 상품군
  안으로 제한했다.
- 코드 값 의미(여부 flag 극성, 위험등급 서열, 섹터 코드)는 미확정 상태로 보존했다.

## 7. DART·Vector 확장 지점

지금 만들지 않았지만, 나중에 DB와 Registry를 다시 만들지 않도록 다음 seam을 남겼다.

- `subject` table의 subject key(`{family}:{official_key}`, `pf:...`, `sec:...`)가 문서
  관계의 고정 참조점이다. 문서 table은 `subject_key`와 `source_id`만 추가하면 된다.
- `data_source`가 출처·hash·수집 시각·우선순위를 이미 관리한다. DART 수집은 새 source
  행으로 추가되고 공식 데이터 우선 규칙이 그대로 적용된다.
- `holdings_coverage`와 `collection_failure`의 구조가 상품군별 수집 결과를 표현하므로
  문서 수집 coverage도 같은 모양으로 붙는다.
- Execution Registry의 binding은 `observation_table`·`selector_column`·`value_column`로
  executor를 기술하므로 같은 자리에 Vector executor를 얹는 형태가 된다. 다만 이는
  "추가 설계 없이 붙는다"는 뜻이 아니다. 기존 semantic ID와 핵심 DB를 갈아엎지는 않지만,
  Document·Chunk·Evidence 개념을 온톨로지에 추가하고 Vector executor·index·filter binding을
  새로 설계해야 한다. 그 결과 Semantic Registry와 Execution Registry 모두 확장된다.
- 현재 `src/canna/graph/project.py`가 만드는 ABox는 **전체 Knowledge Graph가 아니라 SHACL
  검증용 bounded sample**이다(상품군당 subject 8개, subject당 관측 6개 상한). 전체 KG
  적재는 같은 투영 경로를 확장해 별도로 수행해야 한다.

## 8. 빌드 안전성

- build는 같은 디렉터리의 임시 파일에 store를 만들고, grain·coverage 검증과 Data Catalog
  생성까지 끝낸 뒤 connection을 닫고 교체한다. 실패하면 기존 `query_store.duckdb`와
  `data_catalog.json`이 그대로 남는다.
- store와 catalog는 **하나의 generation**이다. 둘을 함께 교체하되 각 target을 먼저 옆으로
  옮겨 두므로, 두 번째 교체가 실패하면 먼저 옮긴 target이 이전 바이트로 복구된다. 부분
  교체 상태가 밖에 남지 않는다.
- 두 산출물은 같은 `build_id`를 가진다. store는 `build_manifest` table에, catalog는
  `build.build_id`에 기록하고 store 파일의 SHA-256도 catalog에 남긴다. Registry build는
  두 값을 대조해 다르거나 없으면 **fail-closed**로 거부한다. 프로세스가 두 교체 사이에서
  죽어 반쪽 generation이 남더라도 registry가 그 조합으로 실행되지 않는다.
- 동시 빌드는 `query_store.duckdb.build-lock`으로 fail-fast 처리한다. 실패해도 lock은
  해제된다.
- 실패 주입 테스트 15개가 이 성질을 검증한다(초기 실패, store를 쓴 뒤 실패, **두 번째
  publish 실패 후 양쪽 복구**, generation 롤백·전체 교체·사전 거부, 동시 빌드, lock 해제,
  원자적 교체, WAL 동반 파일 처리, build_id 공유, coverage 누락 감지).

## 9. 사용자 검수 필요

구현이 만든 구조 변형 질문 초안은 `tests/fixtures/`에서 제거하고
`PROPOSED_TEST_QUESTIONS.md`/`.jsonl`로 옮겼다. 어떤 테스트도 이 파일을 읽지 않는다.
대상이 지목되지 않아 모호한 3개와 사용자 질문이 아닌 내부 불변조건 2개는 초안에서
제외했고, 남은 7개 중 3개도 내부 상태 질문에 가까워 함께 판단을 요청한다. 구조 불변식은
질문 문자열 없이 직접 테스트가 검증한다.
