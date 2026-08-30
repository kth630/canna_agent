# 실제 데이터 × legacy Ontology 대조표

## 근거 범위

이 표는 2026-08-24 공식 Excel 4종과 `holdings_20260829.zip`만을 대상으로 한다.
현 배포본에서 재현한 값·coverage는 관측 근거이며, runtime 상수나 질문 제약이 아니다.
원본 column 전체를 사용자 capability로 승격하지 않는다.

## 1. entity·관계·관측 대조

| 의미 | legacy 표현 | 실제 데이터 관측 | grain/식별자·시점 | 판정 | 후속 의미 |
|---|---|---|---|---|---|
| 국내채권 상품과 source row | `bondkr:KoreanBond`, `BondLotContext` | `pd_no`는 20,497개 product 후보이나 21,882 source row의 유일 key는 `(pd_no,pd_exg_mkt,info_seq)` | product=`pd_no` 후보; source row=복합키; `info_base_dt` 관측 | 유지 | product와 row context 분리는 맞다. 날짜별 metric/source binding을 별도 보존한다. |
| 국내 ETF/ETN 상품·상장 | `DomesticExchangeTradedProduct`, `DomesticETF`, `DomesticETN`, `Listing` | `PREF01N001`은 ETF와 ETN을 함께 포함한다. `pd_itm_no`와 `pd_itm_no_ma`는 각 행에서 유일하며 ISIN은 일부만 존재 | product/listing snapshot 후보; `pd_isin_cd`는 행 병합 key가 아님 | 수정 | ETF/ETN의 실제 분류 원문과 listing/product 구분을 보존한다. 명시 질문의 Target이 source label을 선택하며, 이 감사가 전역 기본 모집단을 만들지 않는다. |
| 해외 ETF/ETN 상품·상장 | `GlobalExchangeTradedProduct`, `GlobalETF`, `GlobalETN`, `Listing` | `PREF02N001`도 ETF와 ETN을 포함하며 동일 ISIN과 Lipper ID가 복수 행에 나타난다 | listing row와 security 후보를 분리; `pd_itm_no`/ISIN의 scheme 검증 필요 | 수정 | ISIN만으로 행 또는 상품을 병합하지 않는다. 행별 가격 기준일이 다르다. |
| 공모펀드 class와 대표 grouping | `PublicFundShareClass`, `RepresentativeFund`, `hasShareClass` | 공식 table의 row는 `itm_no`별 class. 공모·판매중 관측에서 유효 `rptt_ksd_itm_no` 1,809개가 class 8,859개를 묶는다 | class=`itm_no` 후보; representative grouping=`rptt_ksd_itm_no` 후보 | 유지 | class와 grouping의 분리는 legacy와 맞는다. 0/sentinel과 식별자 scheme은 검증 상태로 남긴다. |
| 공모펀드 portfolio | legacy에는 `RepresentativeFund`만 있고 별도 portfolio entity/mapping이 없다 | holdings bundle은 class 8,859개→portfolio 1,809개 mapping을 제공하며 동일 portfolio를 최대 15 class가 공유 | product class→portfolio; holdings는 portfolio snapshot | 추가 | representative grouping과 portfolio를 자동 동일시하지 않는 별도 entity/관계가 필요하다. |
| metric observation | `MetricObservation`, `MetricType`, `observedEntity`, `asOfDate`, `source`, `valueStatus` | 공식 row 안에도 field별 기준일이 다르며 0·결측·sentinel이 존재 | subject×metric×period×effective date×source | 수정 | field별 effective date, unit/currency/period, source record를 필수 설계 입력으로 둔다. |
| requested/effective as-of | legacy `asOfDate`, `collectedAt` | 국내 ETF holdings `2026-08-22`는 요청일이며 실효일 미확인. 해외/공모 holdings와 공식 product metrics는 각기 날짜 범위가 다르다 | requested, effective, as-of status, collectedAt는 서로 다름 | 추가 | 하나의 `asOfDate`로 요청일·실효일을 덮어쓰지 않는다. |
| portfolio holding observation | `PortfolioHoldingObservation`, `portfolioProduct`, `heldSecurity`; SHACL은 둘 다 필수 | holdings 실제 grain은 portfolio×snapshot×raw holding record. 공모펀드는 security ID가 전부 없고 direct/look-through가 섞여 있다 | portfolio observation; resolved security relation은 조건부 | 수정 | raw holding 관측과 검증된 Security relation을 분리해야 한다. 현 shape는 공모펀드 raw row를 표현하지 못한다. |
| 직접 보유와 look-through | legacy `holdsSecurity` shortcut만 존재 | 공모펀드 `source`에 level1 direct와 level2 look-through가 공존한다 | relation kind와 parent portfolio가 별도 필요 | 추가 | `direct holding`과 `look-through exposure`를 별도 predicate/status로 둔다. shortcut은 chosen as-of와 relation kind를 잃지 않아야 한다. |
| holdings의 product 결과 | `holdsSecurity`는 ProjectProduct→Security shortcut | holdings는 product/class→portfolio→observation 구조이며 relation filter 후 product-grain dedup이 필요 | 결과=product/class; JOIN row는 결과가 아님 | 수정 | shortcut 또는 compiler는 `EXISTS`/product `DISTINCT`를 보장해야 하며 logical duplicate를 순위·count에 쓰지 않는다. |
| 식별자 model | `Identifier`, ISIN/RIC/Ticker/KSD/Project schemes | 공식 key와 external `held_security_id`가 혼재. 국내/해외 ETF placeholder ID가 있고 공모펀드 holdings는 ID 없음 | value×scheme×verification status | 수정 | 식별자 모양만으로 scheme을 확정하지 않는다. placeholder·ambiguous·unresolved는 Security relation이 아니다. |
| source·evidence | `DataSource`, `EvidenceDocument`, `sourceRecordId` | 공식 Excel source row와 ZIP raw/normalized record·collection failure가 모두 존재 | source/file/record/call/failure | 유지 | source precedence와 raw record provenance를 실제 binding에 보존한다. |
| coverage·failure | `ValueStatus`에는 value 상태만 있음 | holdings는 family/product/class/portfolio/call별 coverage와 2,294 failures를 보유 | claim universe와 failure cause는 value 상태와 독립 | 추가 | coverage/freshness/failure는 dynamic 운영 metadata로 두고, value status와 한 enum으로 합치지 않는다. |
| sale·trading status | `SaleStatusObservation`과 `TradingStatusObservation` 분리 | 공식 ETF에는 `pd_sale_yn`, `pd_tr_yn`; 공모펀드에는 `sale_yn`, `thco_sale_yn`이 별개 | source·as-of가 있는 status observation | 유지 | 두 상태를 합치지 않는다. blank/코드의 뜻은 근거 전까지 미확정이다. |
| role·benchmark | role nodes와 `BenchmarkAssignment` | 운용사/benchmark는 원문 문자열·출처별 값으로 존재하지만 entity resolution·충돌 해소가 미완료 | raw value→후보 entity/benchmark | 미확정 | 원문·source는 보존하되 Organization/Benchmark entity 병합이나 shortcut을 만들지 않는다. |
| theme·control 관계 | `ThemeAssignment`, `ControlRelationship` | 현재 공식·holdings 입력에 검증된 theme/control source 없음 | 해당 없음 | 제외 | 이번 source binding에는 포함하지 않는다. 미래 질문을 금지하거나 legacy term을 삭제하는 판정은 아니다. |

## 2. 공식 지표 대조

| 상품군 | legacy MetricType/의미 | 현재 공식 field 및 관측 | 판정 | 제한·수정 근거 |
|---|---|---|---|---|
| 국내채권 | 발행일·만기·쿠폰·발행통화, 신용등급, 평가/매수/세후/세전 수익률, duration/convexity, 가격, 발행·잔액, 잔존일 | `PRBD01N001`에 대응 field가 존재. 판매·매수 계열은 634 rows에만 있고, exchange close price/yield는 0 제외 1,270 rows, 보장수익률은 256 rows | 유지/수정 | 의미 계열은 맞으나 모든 metric에 같은 universe가 없다. `pd_no` product aggregation과 source-row metric context를 분리한다. |
| 국내채권 | `AverageAnnualTaxYield`, `BuyableQuantity` | 전자는 전 행 0, 후자는 현 판매가능성 추론 금지 규칙이 이미 존재 | 제외/수정 | 원문 observation은 보존하되 유효 수치 capability 또는 판매가능성 claim으로 승격하지 않는다. |
| 국내 ETF/ETN | 공통 수익률(1D/1M/3M/6M/1Y/YTD), AUM/NAV/가격/거래량·대금, tracking error/volatility/distribution yield | `PREF01N001`의 기간별 `du_*`와 기준일이 존재. 1Y return은 active ETF 관측에서 0·결측 제외 964 rows | 유지/수정 | period별 별도 metric이며 같은 모집단으로 취급하지 않는다. field별 기준일이 20260820~20260824에 공존한다. |
| 국내 ETF/ETN | `TotalExpenseRate`, `OtherExpenseRate` | `cu_charge_rt`는 text percent이고 active ETF에서 0·결측 제외 67 rows; `cu_charge_etc_rt`는 값 있는 215 rows가 모두 0 | 수정/제외 | 총보수는 text parsing·unit 검증이 필요하다. 기타비용은 현재 유효 관측이 없어 binding을 만들지 않는다. |
| 국내 ETF/ETN | portfolio average maturity/effective duration/modified duration 등 | `fn_average_maturity`, `fn_effective_duration`, `fn_modified_duration`은 전부 결측 | 제외 | MetricType을 삭제하지 않고 현재 source binding·coverage 주장에서는 제외한다. |
| 해외 ETF/ETN | 공통 1D return, expense, 가격, AUM, 거래량·대금, premium/discount | `PREF02N001`에 `du_er_1d`, `cu_charge_rt`, `du_last_aum` 등 존재. 가격 기준일은 109개 값으로 분산 | 유지/수정 | 행별 freshness와 통화/단위 보존이 필요하다. `du_diff_rt`는 3 rows뿐이다. |
| 해외 ETF/ETN | 공통 1M/3M/6M/1Y/YTD return | 공식 table에는 `du_er_1d`만 존재 | 제외 | 1D 수익률을 장기 수익률로 변환하거나 legacy MetricType에 physical binding하지 않는다. |
| 공모펀드 | 기간별 return, net assets/base price/market value/distribution, 보수 구성요소, asset composition, risk grade | `PRFD01N001`에 대응 field가 존재. `fd_wk1_ern_r`는 전부 결측; `fd_yr1_ern_r`은 공모·판매중에서 0·결측 제외 6,913 rows | 유지/수정 | class-level metric이며 `fd_price_bas_dt`는 709개 값으로 분산된다. currency도 7종이다. |
| 공모펀드 | 단일 total expense | legacy는 구성 보수만 정의하며 공식도 운용/판매/신탁/일반사무 보수 4개를 분리 제공 | 유지 | 합계 MetricType/계산 규칙을 만들지 않는다. 합성 여부는 별도 사용자 결정이다. |
| 상품군 공통 | AUM/net assets/expense/return의 통합 비교 | ETF와 펀드가 서로 다른 통화·기간·universe·freshness를 가진다 | 제외 | cross-family ranking/count/extrema에 공통 metric이라고 선언하지 않는다. 호환 근거가 생기면 새 observation 조건으로 검토한다. |

## 3. 외부 holdings 대조

| 상품군 | 실제 bundle data | legacy와의 적합성 | 판정 | 보존해야 할 상태 |
|---|---|---|---|---|
| 국내 ETF | 1,161 product→portfolio mappings, 1,160 success holdings. KRX 형태 `held_security_id`, name, quantity/value가 있음. weight는 대부분 0이며 나머지는 100 | portfolio holding 관측 패턴은 맞으나 requested date를 `asOfDate`로 둘 수 없고 ID scheme/placeholder가 미확정 | 수정 | requested as-of, identifier status, raw source record, physical/logical duplicate, coverage/failure |
| 해외 ETF | 5,527 mappings, 4,964 success holdings. N-PORT security ID는 ISIN>CUSIP>ticker 선택값이며 reporting date 19개 | portfolio holding 관측은 맞으나 identifier scheme이 row별 명시되지 않고 filing/mapping/parse failure가 분리돼야 함 | 수정 | effective reporting date, ID scheme/status, quantity/value/currency/weight unit, coverage/failure cause |
| 공모펀드 | 8,859 class→1,809 portfolio mappings. 48,201 holdings rows는 name·quantity/value만 있고 security ID·ticker·weight가 없음. direct/look-through 공존 | class→portfolio 구조는 legacy class/representative 모델을 보완한다. 필수 `heldSecurity` shape에는 맞지 않는다 | 수정/추가 | raw security-name observation, direct/look-through kind, parent portfolio, unknown snapshot scope, effective as-of, source resolution state |

## 4. 이번 감사의 결론

1. legacy Ontology의 **관측 중심 모델과 국내채권 row/product 분리, 공모펀드 class/grouping
   구분은 유효**하다.
2. 새 모델에는 **portfolio를 대표펀드와 구분**, holdings의 **raw observation과 resolved
   Security relation 분리**, **requested/effective as-of**, **direct/look-through**, 그리고
   value status와 독립된 **coverage/failure/freshness** 표현이 필요하다.
3. legacy MetricType의 존재는 현재 source binding이나 완전 coverage를 의미하지 않는다.
   실제 field·period·unit·currency·effective date를 가진 경우만 후속 Registry가 binding한다.
4. 이 결론은 특정 질문을 막지 않는다. 실제 실행 시 질문의 요구와 해당 evidence의
   resolution/coverage를 대조해 claim 가능 범위를 정한다.
