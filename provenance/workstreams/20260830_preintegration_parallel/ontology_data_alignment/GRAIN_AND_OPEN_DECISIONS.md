# 조회 grain·식별자·시점과 결정 분류

## 1. 공통 조회 단위 후보

| 단위 | 의미 | 공식 데이터 근거 | holdings 근거 | legacy 상태 | 승인 후보 |
|---|---|---|---|---|---|
| Source row | 한 원본 record의 물리 관측 | 국내채권은 `(pd_no,pd_exg_mkt,info_seq)`가 유일; ETF/펀드는 각 workbook row | raw record 및 `source_record_id` | 일부 `ObservationContext` | product 결과와 절대 혼동하지 않는다. |
| Product | 사용자가 조회할 금융상품 또는 상장상품 | 채권 `pd_no` 후보, ETF/ETN `pd_itm_no` 계열, 해외 ETF/ETN listing row 후보 | ETF mapping의 `project_product_id` | `ProjectProduct` 및 상품군 subclass | 상품군별 canonical ID/scheme은 verification 상태와 함께 결정한다. |
| Product class | 같은 portfolio를 공유할 수 있는 판매·보수 단위 | 공모펀드 `itm_no` | public fund `product_mapping.project_product_id` | `FundShareClass`, `PublicFundShareClass` | 공모펀드 결과의 기본 반환 단위 후보. |
| Portfolio | holdings snapshot의 보유 주체 | 공식 공모펀드 `rptt_ksd_itm_no`는 grouping 후보이나 portfolio와 자동 동일시 불가 | public fund `portfolio_id`; ETF도 mapping으로 존재 | 없음 | class/product→portfolio를 명시적 관계로 추가한다. |
| Security | 검증된 식별자로 가리킬 수 있는 보유 증권 | 공식 ISIN·상품/상장 후보는 별도 검증 필요 | ETF 일부는 ID가 있으나 placeholder 존재; 공모펀드는 ID 없음 | `Security` | `resolved` identifier가 있을 때만 holdings relation endpoint로 쓴다. |
| Raw holding observation | source가 보고한 보유내역 | 공식 product metric과 다름 | portfolio×snapshot×raw record; name만 있는 공모펀드 행 포함 | 현 `PortfolioHoldingObservation`과 불일치 | Security 미해결 상태도 잃지 않는 관측 모델을 둔다. |
| Metric observation | 상품/class/listing에 대한 한 지표의 값 | subject×field/metric×period×field effective date×source | 해당 없음 | `MetricObservation` | value status, unit/currency/period, source row를 함께 보존한다. |

## 2. 관계 후보

| 관계 | 현재 근거 | 상태 | 주의 |
|---|---|---|---|
| product/class → portfolio | holdings `product_mapping` | 관측됨 | 공모펀드는 1:N/공유 관계이며 대표펀드와 동일시하지 않는다. |
| portfolio → raw holding observation | normalized holdings와 raw source | 관측됨 | snapshot, source record, direct/look-through kind가 필요하다. |
| raw holding observation → Security | ETF 일부는 identifier 후보, 공모펀드는 없음 | 조건부/미확정 | identifier scheme/status 또는 entity resolution 근거 없이는 관계를 만들지 않는다. |
| product → Security direct holding | ETF에서 observation을 통해 파생 가능 | 조건부 | chosen snapshot과 coverage를 붙인다. 단순 JOIN 결과를 product count/ranking에 쓰지 않는다. |
| product/class → look-through exposure | 공모펀드 level2 row 존재 | 관측됨 | direct holding과 별도이며 parent portfolio와 source resolution을 보존한다. |

## 3. identifier와 시간 상태 후보

| 대상 | 확인된 값/후보 | 승인 전 처리 |
|---|---|---|
| 국내채권 | `pd_no`; source-row 복합키 | `pd_no`를 product 후보로 두되 scheme과 영구 canonicality를 추정하지 않는다. |
| 국내 ETF | `pd_itm_no`, `pd_itm_no_ma`, 일부 ISIN/RIC/ticker | 서로 자동 병합하지 않으며, scheme·verification status를 별도 기록한다. |
| 해외 ETF | ISIN, RIC/티커, Lipper/CIK 후보 | ISIN=security, RIC/ticker=listing이라는 legacy 가설은 실제 mapping evidence로 재검증한다. |
| 공모펀드 | `itm_no`, `std_itm_no`, `ksd_itm_no`, `rptt_ksd_itm_no`, `fss_itm_no`, `mtco_itm_no` | 각 source scheme을 분리한다. `'0'` 및 비어 있는 값은 identifier가 아니다. |
| ETF holdings | domestic KRX 형태 ID; overseas selected ID 및 ISIN/ticker 원값 | placeholder·ambiguous·unresolved를 실제 Security로 승격하지 않는다. |
| 공모펀드 holdings | security name만 존재 | raw label로 보존한다. 이름만으로 Security relation이나 역검색 정답을 만들지 않는다. |
| 공식 metrics | field별 base/update date | file 배포일 하나로 freshness를 대체하지 않는다. |
| domestic ETF holdings | requested date `2026-08-22`, effective date 미확인 | requested/effective를 분리한다. |
| overseas/public holdings | reporting/settlement dates가 상품별로 분산 | effective as-of와 snapshot scope/freshness를 record한다. |

## 4. 기존 7개 항목의 결정 분류

질문이 명확하면 Target, 반환 grain, source field는 질문 구조와 실제 evidence로 고른다.
따라서 이를 전역 기본값이나 사전 질문 제한으로 바꾸지 않는다.

### ARCHITECTURE에서 이미 확정

| 기존 항목 | 확정된 원칙 |
|---|---|
| 공모펀드 `RepresentativeFund`와 holdings `Portfolio` | product/class와 portfolio를 구분하고 product/class→portfolio mapping을 명시한다. |
| requested/effective as-of, freshness | requested/effective/as-of status/freshness를 구분한다. 동적 freshness·coverage는 Ontology TTL이 아니라 실제 관측/Execution Registry에 둔다. |
| direct holding과 look-through | 별도 predicate와 grain으로 보존한다. 관계 뒤 ranking/count는 product grain dedup을 적용한다. |
| coverage·failure | value status와 독립이며 coverage 밖·수집 실패·미해결을 `false`나 `0`으로 바꾸지 않는다. |

### 구현 중 증거로 결정

| 기존 항목 | 구현 시 evidence로 정할 내용 |
|---|---|
| ETF/ETN·종료/거래정지·공모/판매 class Target | 명시 질문의 Target과 source label을 연결한다. 종료·상장 상태 같은 서버 invariant는 source code 의미와 기준일 근거를 검증해 적용한다. 전역 기본 모집단은 만들지 않는다. |
| identifier scheme·placeholder·raw holding SHACL | source별 scheme/verification status, placeholder 판별, identifier 없는 raw holding의 shape를 실제 binding·source evidence로 확정한다. |
| 공모펀드 보수 합계 | 현재는 4개 구성요소만 각각 보존한다. 공식 합산 정의가 없으면 합성 MetricType/binding을 만들지 않는다. |
| 상품군 간 비교 | `unit/currency/period/universe/freshness` 호환성 증거가 있는 field 조합에서만 실제 실행이 가능하다. 현재는 전역 비교 binding이 없다. |

### 사용자 결정 필요

현재 0-D 범위에는 없음. 향후 공식 근거 없이 새로운 합성 지표를 제품 의미로 채택하거나,
현재 제출 범위를 넘어 새 외부 source를 계약에 추가하려는 경우에만 사용자 결정으로 올린다.

## 5. 다음 workstream handoff

| 수신 | 이 감사가 넘기는 것 | 아직 넘기지 않는 것 |
|---|---|---|
| A — 공식 데이터/Execution Registry | source row, product 후보, metric observation grain, field-level as-of와 measure/code 구분 | 물리 table/column binding 또는 runtime coverage 규칙 |
| D — holdings/관계 | product/class→portfolio, raw holding, identifier/as-of/failure 분리, direct/look-through 요구 | 공모펀드 name entity resolution이나 특정 질문용 역검색 규칙 |
| F — Ontology/Semantic Registry/Retriever | 수정·추가할 semantic concept와 legacy term 상태 | 새 TTL/SHACL/semantic ID의 최종 형식 |
| B/C/E | claim/evidence가 지켜야 할 grain·coverage 한계 | logical plan, Tool API, API envelope, 배포 구현 |

## 6. 완료 checklist

전수 증거의 실제 명령·hash·행 수는 `COMPLETENESS_EVIDENCE.md`와 `generated/audit_evidence.json`에
있다. 그 증거가 생성된 뒤에만 아래 항목을 체크한다.

- [x] official schema 280개 field가 data header와 순서 일치 검증 후 각각 catalogued 됐다.
- [x] legacy TTL 5개의 named declaration 298개가 각각 상태·근거·미확정 사유와 함께 기록됐다.
- [x] holdings ZIP의 실제 member 29개(내부 MANIFEST가 hash를 싣는 28개 파일 + MANIFEST 자체)와 normalized field 51개를 기록했다.
- [x] source row와 product/class/portfolio/security/raw holding/metric observation을 구분했다.
- [x] requested/effective as-of, coverage/failure, direct/look-through, identifier 미해결을 `0` 또는 `false`로 바꾸지 않았다.
- [x] 질문 문자열, case ID, 현재 상품명·행 수를 제품 규칙으로 사용하지 않았다.
