# 구현 전 큰그림 게이트 — 조회용 DB · Ontology/SHACL · Semantic/Execution Registry

작성 시점 기준 commit: `3e20e6f`. 근거 문서는 `AGENTS.md`, `ARCHITECTURE.md`,
`DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md`, `CURRENT_STATUS_20260830.md`와
완료·동결된 0-D 산출물이다. 0-D 감사는 다시 수행하지 않고 입력으로만 사용한다.

## 목적

공식 네 상품군과 현재 holdings 전체를 대상으로, 의미(Ontology/Semantic Registry)와
실행(조회용 DB/Execution Registry)을 stable semantic ID 하나로 결합한 재현 가능한
기반을 만든다. 특정 질문·상품·날짜에 맞춘 경로를 만들지 않는다.

## 일반화 capability

문항이 아니라 다음 네 가지 일반 능력을 만든다.

1. `source-to-grain projection`: 원본 source row를 product / product class /
   portfolio / security / metric observation / raw holding observation의 서로 다른
   grain으로 손실 없이 투영한다.
2. `semantic-to-physical binding`: 의미 ID를 물리 table/column/join/operation에
   연결하고 불일치를 build 실패로 만든다.
3. `provenance-preserving observation`: 값 하나마다 source, source row, requested·
   effective as-of, value status, unit/period/currency를 함께 보존한다.
4. `relation traversal with product-grain dedup`: product/class ↔ portfolio ↔
   holding observation ↔ security 관계를 양방향으로 순회하되 결과 grain에서
   중복을 제거한다.

## 영향 계층과 계약

- 신규: `ontology/`(제출용 TTL 5개 + SHACL), `catalog/`(Data Catalog binding 입력),
  `src/canna/store/`, `src/canna/registry/`, `src/canna/graph/`.
- 산출물: `data/processed/query_store.duckdb`, `data_catalog.json`,
  `semantic_registry.json`, `execution_registry.json`, `abox_sample.ttl`.
- 변경하지 않음: `/answer` envelope, HCX 계약, Runtime View·compiler·Tool 표면.
  이 작업은 그 계층이 사용할 기반만 제공한다.
- `ARCHITECTURE.md` §7·§8의 Confirmed 결정을 그대로 구현하며 바꾸지 않는다.

## 데이터 grain·coverage·freshness·실패 의미

- source row grain은 원본 mirror table이 보존한다. 국내채권은 `(pd_no, pd_exg_mkt,
  info_seq)` 21,882행이 유일하고 `pd_no`는 20,497개이므로 product 결과와 절대 섞지
  않는다.
- product grain은 상품군별 공식 key로 정의하고, 공모펀드는 class grain을 별도
  table로 둔다. class를 묶는 `rptt_ksd_itm_no`는 grouping 후보로만 보존하고
  portfolio와 동일시하지 않는다.
- portfolio는 외부 holdings 번들의 portfolio가 정본이며 product/class→portfolio는
  명시적 mapping table로 둔다.
- Security는 scheme과 resolution status가 확인된 식별자에만 만든다. 공모펀드
  holdings는 security ID가 없으므로 raw holding observation으로만 보존한다.
- metric observation은 subject × metric × period × effective as-of × source로
  기록하고 unit/currency/value status를 함께 남긴다.
- requested as-of와 effective as-of를 분리하고, 확인되지 않은 실효일은
  `as_of_status`로 남긴다.
- coverage와 collection failure는 value status와 다른 축으로 저장한다. 수집 실패,
  미해결 mapping, coverage 밖은 `0`이나 `false`로 바꾸지 않는다.
- 공식 데이터와 외부 데이터가 충돌하면 공식 데이터를 우선하고 충돌 record를 남긴다.

## 금지할 하드코딩과 허용할 안정 상수

금지: CQ ID·question_id·질문 문자열 분기, 평가 fixture의 runtime 사용, 특정 상품명·
날짜·행 수·현재 coverage 수치, Registry가 소유할 alias/field/predicate/join의 Python
상수 중복, 추측한 식별자·코드 의미, 이전 저장소 코드·TTL 복사 또는 경로 연결,
원본 Excel/ZIP 수정.

허용: 공식 table ID와 공식 field 이름, 0-D가 기록한 검증된 source hash, 번들이 자체
문서화한 source record 포맷의 결정적 parse 규칙(근거를 catalog에 기록), Ontology에서
생성된 stable semantic ID, 격리된 테스트의 expected value.

값 의미가 확인되지 않은 코드(예: 여부 flag의 극성, text 보수요율의 단위)는 원문을
보존하고 registry에 `unverified` 상태로 표시하되, 그 값을 근거로 한 서버 invariant를
이번 범위에서 만들지 않는다.

## 수용 기준

1. 원본 hash 불변 상태에서 전체 데이터로 DB build가 재현된다.
2. grain별 uniqueness와 관계 JOIN 후 product-grain dedup이 테스트로 증명된다.
3. Ontology 5개가 parse되고 SHACL이 store에서 투영한 ABox를 검증한다.
4. Semantic Registry가 Ontology/SHACL에서만 생성되고 물리 binding과 동적
   coverage/freshness를 담지 않는다.
5. Execution Registry가 Data Catalog에서 생성되고, semantic ID·type·grain·unit·
   binding 불일치에서 build가 실제로 실패한다.
6. 공식 field 전수가 catalog에서 `bound` 또는 사유가 있는 `unbound` 상태를 가진다.
7. SQL filter/order/count/aggregate와 holdings 양방향 관계가 실제 데이터에서
   실행된다.

## 보지 않은 변형 질문 대응

테스트는 CQ 회귀가 아니라 구조 조합으로 만든다. 같은 구조의 unseen paraphrase,
인접 field(기간 이웃·수익률/변동성 이웃), 관계 방향 반전(상품→종목, 종목→상품),
coverage boundary(미해결 security, 실패한 수집, 오래된 snapshot), grain 경계
(source row vs product, class vs portfolio)를 변형 축으로 사용한다. 질문 문자열은
테스트 안에서만 존재하고 런타임 분기 조건이 되지 않는다.

## 이번 범위 밖

OpenDART 문서 수집, 문서 Vector 인덱스, 별도 Graph DB 도입, Runtime View·HCX·
compiler·Tool 구현. 다만 subject 공통 ID와 source/document 확장 지점을 지금 남겨
나중에 DB와 Registry를 다시 만들지 않게 한다.
