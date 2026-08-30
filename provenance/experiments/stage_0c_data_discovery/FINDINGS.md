# 공식 데이터 read-only discovery — 관측 기록

## 0. 이 문서의 지위

이 문서는 **관측 기록**이다. 아키텍처, 구현 계획, 계약, 데이터 의미를 확정하지 않는다.
정본 문서(`CONTEXT.md`, `QUESTION_STRUCTURE.md`, `ARCHITECTURE.md`,
`IMPLEMENTATION_PLAN.md`, `contracts/`)와 `provenance/MIGRATION_MANIFEST.json`은
이 작업으로 변경하지 않았다. 새 단계를 만들지도 않았다.

여기서 "확정"이라고 쓴 항목은 원본 파일에서 직접 재현한 사실이라는 뜻이며,
그 사실을 실행 계약으로 채택할지는 사용자와 Codex의 결정이다.

원본 데이터는 수정하지 않았다. Excel은 `read_only=True, data_only=True` 스트리밍으로
읽었고, holdings ZIP은 normalized parquet 4개만 시스템 임시 디렉터리로 복사해
DuckDB 메모리 DB에서 질의했다. 저장소에 생성한 파일은 이 문서 하나다.

## 1. 무결성 재확인

`provenance/MIGRATION_MANIFEST.json`의 `immutable_local_artifacts` 9건 전부
SHA-256과 byte size 일치. mismatch 0.

## 2. 행·열 기준선 재현

| table ID | data rows | data cols | schema cols | header 순서 일치 | 완전 중복 행 |
|---|---:|---:|---:|:--:|---:|
| `PRBD01N001` | 21,882 | 58 | 58 | yes | 0 |
| `PREF01N001` | 1,780 | 98 | 98 | yes | 0 |
| `PREF02N001` | 6,037 | 49 | 49 | yes | 0 |
| `PRFD01N001` | 23,676 | 75 | 75 | yes | 0 |

`CONTEXT.md` 3절의 기준선과 일치한다. 각 테이블의 schema workbook은
`순번/컬럼명/데이터타입/Nullable/컬럼코멘트` 5열이고 data workbook의 header와
순서까지 같다.

## 3. 선행 감사 보고서 수치 대조

| 감사 보고서 주장 | 이 관측 | 판정 |
|---|---|---|
| 국내채권 `pd_no` 고유 20,497 / 중복 초과 1,385 | 동일 | 일치 |
| 국내 ETF `pd_itm_no`, `pd_itm_no_ma` 1,780/1,780 고유 | 동일 | 일치 |
| 국내 ETF `pd_isin_cd` 1,208행 | 동일 | 일치 |
| 해외 ETF ISIN 중복 초과 63 | `pd_isin_cd` 63, `pd_lipper_id` 63 | 일치 |
| 공모펀드 `itm_no` 23,676 고유 / `rptt_ksd_itm_no` 6,885 | 동일 | 일치 |
| 국내 ETF eligible 1,164 | ETF ∧ 종료일 sentinel = **1,161**, 종료일 결측 ETF 3행을 더하면 1,164 | 일치, 차이의 출처 확정 |
| eligible 중 `du_er_1y` 964 | 964 | 일치 |
| eligible 중 순자산 관련 1,161 | `pd_net_tamt` 1,161 | 일치 |
| 공모펀드 8,859 classes / 1,809 portfolios | `ksd_itm_no` 8,859 / `rptt_ksd_itm_no` distinct 1,809 (공모∧판매중) | 일치 |
| JOIN 행 팽창 75,856 / 1,402,333 / 161,888 | 동일 | 일치 |
| **eligible 중 `cu_charge_rt` 215가 "0·결측이 아니다"** | nonblank는 215가 맞지만 그중 **148행이 값 `'0'`** 이다. 0을 제외한 실제 universe는 **67** | **정정 필요** |

`cu_charge_rt` 정정은 결과를 바꾼다. `CONTEXT.md` 3절의 0·결측 제외 규칙을 적용하면
국내 ETF 총보수 질의의 모집단은 eligible 1,161개 중 **67개(5.8%)** 다.
215(18.5%)로 알고 coverage 정책을 세우면 잘못된 partial 판정이 나온다.

## 4. 상품군별 관측

### 4.1 국내 ETF (`PREF01N001`)

**모집단 정의가 하나가 아니다.**

| 정의 | 행 수 |
|---|---:|
| 전체 행 | 1,780 |
| `pd_grp_no='ETF'` | 1,235 |
| ETF ∧ `pd_lste_dt='99991231'` | 1,161 |
| ETF ∧ 종료 sentinel ∧ `pd_tr_yn='0'` | 1,160 |
| ETF ∧ 종료 sentinel ∧ `pd_sale_yn='1'` | 1,160 |

- `pd_grp_no`는 `ETF` 1,235 / `ETN` 545 두 값이다. 이 테이블은 국내 ETF 전용이 아니다.
  "국내 ETF" 질문의 Target이 1,235인지 1,161인지는 정의 결정 사항이다.
- `pd_lste_dt`(거래종료일자)는 미종료를 `99991231` sentinel로 표현한다(1,535행).
  ETF 중 과거 종료일을 가진 행이 71개 있다.
- 종료일이 결측인 3행은 전부 `pd_grp_no='ETF'`이며 **모든 지표가 결측**이다.
  그중 한 행은 `pd_itm_no='KR'`, `pd_nm='.'` 인 손상 레코드다.
  이 3행은 어떤 정의로도 답변 가능한 내용을 만들지 못한다.
- eligible(1,161) 안에도 거래정지(`pd_tr_yn='1'`) 상품이 1개 남아 있고, 그 상품이
  `pd_net_tamt` 최솟값(89,477,660)이다. **"순자산이 가장 작은 ETF"를 물으면
  거래정지 상품이 1위로 나온다.**
- `pd_lstg_dt`에 `10001231` sentinel, `pd_curr_cd`에 `CURR_CD_000` 1행이 있다.

**지표별 queryable universe** (eligible 1,161 기준, 결측·0 제외):

| field | 코멘트 | nonblank | 0 제외 후 | 비율 |
|---|---|---:|---:|---:|
| `pd_net_tamt` | 순자산총액 | 1,161 | 1,161 | 100.0% |
| `du_last_nav` | 최종NAV | 1,161 | 1,161 | 100.0% |
| `du_last_aum` | 최종AUM | 1,161 | 1,161 | 100.0% |
| `du_chas_errt` | 추적오차율 | 1,161 | 1,160 | 99.9% |
| `du_er_1m` | 수익률_1M | 1,148 | 1,144 | 98.5% |
| `du_diff_rt` | 괴리율 | 1,161 | 1,131 | 97.4% |
| `du_er_3m` | 수익률_3M | 1,102 | 1,096 | 94.4% |
| `du_er_6m` | 수익률_6M | 1,049 | 1,045 | 90.0% |
| `du_er_ytd` | 수익률_YTD | 1,037 | 1,035 | 89.1% |
| `du_vlty_1y` | 연환산 변동성 1Y | 966 | 965 | 83.1% |
| `du_er_1y` | 수익률_1Y | 966 | **964** | 83.0% |
| `pd_circ_net_tamt` | 유통순자산총액 | 1,161 | **669** | 57.6% |
| `cu_charge_rt` | 총보수요율 | 215 | **67** | 5.8% |
| `cu_charge_etc_rt` | 기타비용요율 | 215 | **0** | 0.0% |

- 수익률은 기간이 길수록 모집단이 작아진다(1M 98.5% → 1Y 83.0%). 기간이 다른 두
  지표를 같은 모집단으로 취급할 수 없다.
- `pd_net_tamt`(순자산총액)와 `pd_circ_net_tamt`(유통순자산총액)는 이름이 비슷하지만
  universe가 1,161 대 669다. 인접 field 혼동이 실제로 결과를 바꾼다.
- `cu_charge_rt`는 선언 타입이 `text`이며 값은 `'0.4'`, `'0.49'`, `'0.52'` 같은
  퍼센트 문자열이다. eligible 안의 실제 분포는 0이 148개, 나머지 17개 값에 67개가
  흩어져 있다(최소 0.07, 최대 0.64).
- `cu_charge_etc_rt`는 값이 존재하는 215행 전부가 `'0'`이다. 구분력이 0이다.

**freshness는 eligible 안에서는 균일하다.** 각 날짜 컬럼이 eligible에서 단일값을 갖는다.

| 날짜 컬럼 | eligible 값 |
|---|---|
| `pd_dvid_prc_base_dt` (분배 NAV 기준일) | 20260820 |
| `du_nav_base_dt`, `du_upt_dt`, `wu_upt_dt`, `du_vlty_base_dt`, `du_diff_rt_base_dt` | 20260821 |
| `fn_base_dt`, `ref_base_dt` | 20260822 |
| `cu_upt_dt` (변동갱신일자) | 20260824 |

- 즉 국내 ETF의 as-of는 **행 단위가 아니라 field 단위**이며 20260820~20260824의
  4개 날짜가 공존한다. 전체 테이블에서 관측되는 20260410까지의 분산은 전부
  종료된 상품에서 나온다.
- `fn_base_dt`는 eligible 1,161 중 1,108행에만 있다.

### 4.2 해외 ETF (`PREF02N001`)

- **다기간 수익률 컬럼이 존재하지 않는다.** 수익률 계열은 `du_er_1d`(수익률_1D)
  하나뿐이다. 1개월·3개월·1년 수익률로 해외 ETF를 정렬·비교·집계하는 요구는
  공식 데이터만으로는 **구조적으로 실행 불가능**하다.
- `du_diff_rt`(괴리율)는 6,037행 중 **3행**에만 있다.
- eligibility flag에 구분력이 없다: `pd_sale_yn`은 6,023행 전부 `'1'`,
  `pd_tr_yn`은 6,023행 전부 `'0'`, 나머지는 결측이다.
- `pd_grp_no`는 ETF 5,972 / ETN 65다.
- 통화: `pd_trd_ccy` 전부 `USD`, `pd_curr_cd`는 USD 6,025 · INR 1 · 결측 11.
  **`du_last_aum`은 USD, 국내 ETF `pd_net_tamt`는 KRW다. 환율 데이터가 없으므로
  두 상품군의 순자산을 같은 축에서 정렬·비교할 수 없다.**
- `du_base_dt_match_yn`이 6,023행 전부 `'N'`이다. NAV 기준일과 종가 기준일이
  일치하는 행이 없다.
- `du_clpr_base_dt`는 109개 값으로 분산되고 최고 5,687행이 20260821, 최고령은
  20250728이다. 국내 ETF와 달리 **행 단위 staleness가 실재한다.**
- 지표 coverage: `cu_charge_rt` 5,618/6,037(93.1%), `du_last_aum` 5,821(96.4%),
  `du_last_nav` 758(12.6%), `pd_lst_price`(액면가)는 6,023행 중 6,022행이 0.
- `pd_exg_mkt_cd`에 `AMX/NAS/NYS`와 함께 `102`, `101` 코드가 섞여 있다. 의미 미확인.

### 4.3 국내채권 (`PRBD01N001`)

- **source-row grain은 `pd_no`가 아니라 `(pd_no, pd_exg_mkt, info_seq)`다.**
  조합별 유일성을 직접 검증했다.

| 후보 key | distinct | 중복 초과 | 한 key 최대 행 | 판정 |
|---|---:|---:|---:|---|
| `pd_no` | 20,497 | 1,385 | 4 | 유일하지 않음 |
| `pd_no + pd_exg_mkt` | 21,574 | 308 | 3 | 유일하지 않음 |
| `pd_no + info_seq` | 20,805 | 1,077 | 2 | 유일하지 않음 |
| **`pd_no + pd_exg_mkt + info_seq`** | **21,882** | **0** | **1** | **유일** |

  `pd_exg_mkt`는 장내 17,746 / 장외 4,136, `info_seq`는 1이 21,574 · 2가 307 · 3이 1이다.
  중복된 `pd_no` 1,078개 그룹 안에서 실제로 값이 갈리는 컬럼은
  `pd_exg_mkt`와 `exg_close_price`·`exg_close_yield`·`exg_close_price_base_dt`가
  1,077개 그룹, 판매 계열 634행 블록이 326개 그룹이다.
  **같은 채권이 장내·장외로 두 번 실린다. 행을 세면 상품이 1,385건 부풀려진다.**
  product grain은 `pd_no`(20,497), source-row grain은 위 3-tuple로 분리해야 한다.
- **판매·매매 계열 컬럼은 21,882행 중 634행에만 존재한다(2.9%).**
  `trade_price`, `buy_yield`, `after_tax_yield`, `corp_pretax_yield`,
  `corp_after_tax_yield`, `pref_tax_yield`, `depo_equiv_yield_154`,
  `depo_equiv_yield_495`, `buyable_quantity`, `bdbns_abl_chnl_*`,
  `sale_yield_base_dt`가 모두 같은 634행이다.
  `CONTEXT.md`가 `buyable_quantity`를 쓰지 않기로 한 것과 별개로, **매수수익률·매매단가
  기반 질의의 모집단도 634개다.**
- `avg_annual_tax_yield`(세후 연평균수익률)는 634행 전부 0이다.
- `exg_close_price`/`exg_close_yield`는 nonblank 17,746이지만 그중 16,476이 0이다.
  실제 universe는 1,270이고, 이는 `exg_close_price_base_dt`의 nonblank 1,270과
  정확히 일치한다.
- `exrt_grte_ern_r`(만기보장수익률)는 21,882행 중 21,626이 0 → universe 256.
- `crd_grd`(적용신용등급)는 17,862/21,882 → 4,020행 결측.
- as-of는 단일하다: `info_base_dt`, `pd_std_info_update`, `sale_yield_base_dt`가
  모두 단일값 `20260821`. `crd_grd_dt`는 2,151개 값으로 분산되며 코멘트가
  "등급 미변경 시 과거 일자로 유지될 수 있음"이라고 명시한다.

### 4.4 공모펀드 (`PRFD01N001`)

- **이 테이블은 공모 전용이 아니다.** `prvo_pbff_desc`가 공모 14,716 / 사모 8,960이다.
- `sale_yn`은 판매중 10,962 / 판매완료 12,714. 공모 ∧ 판매중 = **8,969행**.
  `CONTEXT.md`가 지적한 대로 `sale_yn='판매중'`은 의미 검증 전까지 eligibility가 아니라
  collection scope다. 8,859(감사 보고서의 class 수)는 이 8,969 중
  `ksd_itm_no`가 있는 행 수다.
- 식별자(공모∧판매중 8,969 기준):

| 컬럼 | nonblank | `'0'` 제외 | distinct |
|---|---:|---:|---:|
| `itm_no` (종목번호) | 8,969 | 8,969 | 8,969 |
| `std_itm_no` (표준종목번호) | 8,969 | 8,969 | 8,966 |
| `ksd_itm_no` (예탁원종목번호) | 8,859 | 8,859 | 8,859 |
| `rptt_ksd_itm_no` (대표예탁원종목번호) | 8,859 | 8,859 | **1,809** |
| `fss_itm_no` (금감원종목번호) | 8,931 | 8,931 | 7,661 |
| `mtco_itm_no` (운용사종목번호) | 8,859 | 8,859 | 2,944 |

  class:portfolio = 8,859:1,809 ≈ 4.9:1. `mtco_itm_no`가 2,944로 또 다른 중간 grain을
  만든다. `fss_itm_no`, `rptt_ksd_itm_no`, `kofia_fd_ccd`, `fd_estb_ctry_cd`는
  전체 테이블 기준으로 값 `'0'`을 sentinel로 쓴다(각각 11,611 / 1,653 / 11,431 / 23,055행).
- **단일 총보수 컬럼이 없다.** 보수는 `or_co_rwrd_r`(집합투자업자),
  `sale_co_rwrd_r`(판매회사), `trusc_rwrd_r`(신탁업자),
  `ofwk_trus_rwrd_r`(일반사무관리) 4개로 나뉜다. "총보수"는 field가 아니라
  **파생 지표**이며 합산 규칙은 승인 대상이다.
- 지표 coverage(공모∧판매중 8,969):

| field | 0 제외 후 | 비율 |
|---|---:|---:|
| `or_co_rwrd_r` | 8,873 | 98.9% |
| `trusc_rwrd_r` | 8,859 | 98.8% |
| `sale_co_rwrd_r` | 8,575 | 95.6% |
| `fd_nast_suma` (순자산) | 8,340 | 93.0% |
| `ofwk_trus_rwrd_r` | 7,927 | 88.4% |
| `fd_mm3_ern_r` | 7,182 | 80.1% |
| `fd_yr1_ern_r` | 6,913 | 77.1% |
| `fd_last_dstb_r` | 3,946 | 44.0% |

- `fd_wk1_ern_r`(1주일수익률)는 23,676행 전부 결측이다.
- **freshness가 심각하게 분산돼 있다.** 공모∧판매중 8,969 중
  `fd_price_bas_dt`가 있는 8,340행에 **709개의 서로 다른 기준일**이 있고,
  최신 20260821은 7,316행뿐이며 최고령은 **20181011**이다. 결측이 629행이다.
  즉 8,969 중 1,653행(18.4%)이 최신 기준일을 갖지 않는다.
- 통화가 7종이다: KRW 23,147 / USD 453 / EUR 56 / JPY 15 / AUD 2 / GBP 2 / SEK 1.

## 5. 상품군 간 비교 가능성

| 의미 | 국내 ETF | 해외 ETF | 공모펀드 | 국내채권 |
|---|---|---|---|---|
| 1년 수익률 | `du_er_1y` 964/1,161 | **없음**(1D만) | `fd_yr1_ern_r` 6,913/8,969 | 없음(만기수익률 계열) |
| 총보수 | `cu_charge_rt` 67/1,161, text·percent | `cu_charge_rt` 5,618/6,037, numeric | 단일 컬럼 없음, 4개 구성요소 | 없음 |
| 순자산 | `pd_net_tamt` KRW 1,161/1,161 | `du_last_aum` USD 5,821/6,037 | `fd_nast_suma` 8,340/8,969 | 없음 |
| as-of | field 단위 4개 날짜, 균일 | 행 단위 109개 값 | 행 단위 709개 값 | 단일 20260821 |

세 지표 모두 상품군 통합 ranking·count·extrema를 지금 데이터로 정당화할 수 없다.
`ARCHITECTURE.md`가 금지하는 "incomplete coverage에서 global top-k"에 정확히 해당한다.

## 6. 일반화된 위험 분류

개별 컬럼 목록이 아니라 규칙으로 다뤄야 할 종류다.

1. **sentinel이 결측도 0도 아닌 형태로 존재한다.**
   `99991231`(미종료), `10001231`, `CURR_CD_000`, 텍스트 ID의 `'0'`,
   holdings의 `000000000`·`N/A`. 결측·0 제외 규칙만으로는 걸러지지 않는다.
2. **0 제외 규칙의 적용 범위를 field 종류별로 나눠야 한다.**
   `CONTEXT.md`의 규칙은 "조건·정렬·비교·집계에 사용하는 수치"가 대상이다.
   그러나 `pd_tr_yn='0'`(정상거래), `pd_sale_yn`, `fd_set_pcd='00'`처럼 코드·flag의 0은
   의미 있는 값이다. Registry가 measure와 code/flag를 구분하지 않으면 이 규칙이
   정상 상품을 모집단에서 지운다.
3. **Y/blank flag의 blank 의미가 검증되지 않았다.**
   `cu_etn_yn`(Y 65행), `cu_index_tracking_yn`(Y 2,407행),
   `cu_inverse_short_yn`(Y 183행), `wu_core_yn`, `thco_sale_yn`(Y 10,597행)은
   값이 한 종류뿐이고 나머지가 결측이다.
   blank를 N으로 읽는 것은 추측이며 `CONTEXT.md`가 금지한다.
4. **완전히 빈 컬럼이 5개 있다.** `PREF01N001`의 `fn_average_maturity`,
   `fn_effective_duration`, `fn_modified_duration`, `pd_dvid_inc_dist`와
   `PRFD01N001`의 `fd_wk1_ern_r`. schema에는 존재하므로 Registry가 "field 존재"만으로
   capability를 노출하면 실행 불가능한 요구를 mapped로 받아들인다.
5. **"field가 있다"와 "field에 답할 모집단이 있다"는 다른 문제다.**
   해외 ETF `du_diff_rt`는 컬럼이 존재하고 값이 3개다. Runtime View 후보에는
   ref·meaning뿐 아니라 **현재 queryable universe**가 함께 실려야 판단이 가능하다.
   (0-A 실험의 `vf_dataset_ownership_absent_001`은 해외 ETF 괴리율을 '없음'으로
   가정했는데, 실제로는 '있으나 3행'이다. 합성 catalog와 실제 데이터의 차이가
   이미 여기서 드러난다.)
6. **이름이 비슷한 인접 field의 universe가 크게 다르다.**
   순자산총액 1,161 대 유통순자산총액 669, 수익률 1M 1,144 대 1Y 964.
   field 선택 오류는 "비슷한 답"이 아니라 다른 모집단의 답을 낸다.
7. **같은 컬럼명이 상품군마다 다른 의미·타입·단위를 갖는다.**
   `cu_charge_rt`는 국내 ETF에서 text·총보수요율, 해외 ETF에서 numeric·연간보수율.
   `du_last_aum`은 국내 ETF "최종AUM"·KRW, 해외 ETF "일간 순자산총액"·USD.
8. **모집단 정의가 상품군마다 다른 컬럼에서 나온다.**
   국내 ETF는 `pd_grp_no`+`pd_lste_dt`, 해외 ETF는 flag에 구분력이 없고,
   공모펀드는 `prvo_pbff_desc`+`sale_yn`, 국내채권은 판매 계열 컬럼의 존재 여부다.

## 7. holdings normalized v1

### 7.1 coverage 테이블 (원문 그대로)

| family | eligible | attempted | success | failed | exact | ambiguous | unresolved | full | unknown | as_of 범위 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| domestic_etf | 1,164 | 1,161 | 1,160 | 4 | 1,161 | 0 | 3 | 1,160 | 0 | 2026-08-22 ~ 2026-08-22 |
| overseas_etf | 5,958 | 5,527 | 4,964 | 994 | 5,527 | 0 | 431 | 4,964 | 0 | 2025-04-30 ~ 2026-06-30 |
| public_fund | 8,859 | 8,859 | 8,064 | 795 | 8,415 | 292 | 152 | 0 | 8,064 | 2014-12-19 ~ 2026-07-31 |

`failed = (attempted - success) + unresolved`로 세 행 모두 정합한다.
domestic_etf의 `eligible=1,164`는 4.1의 "ETF ∧ (종료 sentinel ∨ 종료일 결측)"과 같다.

### 7.2 holdings 본문

| family | rows | products | portfolios | as_of 값 수 | sec_id 결측 | ISIN 결측 | ticker 결측 | weight 결측 | weight=0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| domestic_etf | 75,856 | 1,160 | 1,160 | 1 | 0 | 75,856 | 0 | 0 | 75,438 |
| overseas_etf | 1,397,455 | 4,964 | 4,944 | 19 | 0 | 49,242 | 1,159,168 | 0 | 2,869 |
| public_fund | 48,201 | 1,616 | 1,616 | **430** | 48,201 | 48,201 | 48,201 | 48,201 | 0 |

- **국내 ETF weight는 "대부분 0"이 아니라 "0 또는 100"이다.** 0이 아닌 행은 418개이고
  **418개 전부 값이 정확히 100.0**, 상품당 1행이다. 비중 filter·ranking·집계에
  쓸 수 있는 값이 아니다. `CONTEXT.md` 5절 8항의 판단을 더 강한 근거로 뒷받침한다.
- 국내 ETF holdings에 ISIN이 전혀 없고 `held_security_id`는 6자리 KRX 종목코드
  형태다. 해외 ETF의 `held_security_id`는 ISIN 형태다. **scheme이 family마다 다르고
  컬럼으로 표기돼 있지 않다.**
- 공모펀드 holdings는 `held_security_id`·ISIN·ticker·weight가 **전부 결측**이고
  `security_name` 17,449종만 있다. `snapshot_scope`도 전부 `unknown`이다.
- 공모펀드 holdings의 `holding_as_of`는 **430개 값, 2014-12-19 ~ 2026-07-31**이다.
- 해외 ETF는 `quantity_unit`이 `PA/NS/NC/OU` 코드이고 의미가 확인되지 않았다.
  `value_amount_unit`과 `currency`가 USD인 행과 비어 있는 행이 섞여 있으며
  `currency='N/A'`인 행도 1,135개 있다.

### 7.3 product ↔ portfolio 관계

| family | mapping rows | products | portfolios | 상품당 최대 portfolio | portfolio당 최대 상품 |
|---|---:|---:|---:|---:|---:|
| domestic_etf | 1,161 | 1,161 | 1,161 | 1 | 1 |
| overseas_etf | 5,527 | 5,527 | 5,506 | 1 | 2 |
| public_fund | 8,859 | 8,859 | 1,809 | 1 | **15** |

공모펀드는 최대 15개 class가 하나의 portfolio를 공유한다.

### 7.4 단순 JOIN의 팽창과 논리 중복

| family | JOIN 행 | distinct (product, security) | products |
|---|---:|---:|---:|
| domestic_etf | 75,856 | 75,249 | 1,160 |
| overseas_etf | 1,402,333 | 1,366,984 | 4,964 |
| public_fund | 161,888 | 150,530 | 8,064 |

**dedup을 (product, security)까지 해도 중복이 남는다.**
holdings 자체 안에서 같은 (product, held_security_id, security_name) 조합이
domestic_etf 123그룹(최대 53행), overseas_etf 6,478그룹(**최대 662행**),
public_fund 2,334그룹(최대 46행)이다.

해외 ETF 최악 사례는 `held_security_id`가 `000000000` 또는 `N/A`인 행들이다.
서로 다른 포지션이 placeholder ID 때문에 한 그룹으로 뭉친다.
**따라서 관계 검색은 `EXISTS` 또는 product grain `DISTINCT`가 필수이고, 동시에
placeholder ID를 실제 security ID로 취급하면 안 된다.**

### 7.5 실제 역방향 조회 실측 — 삼성전자

| 접근 | domestic_etf | public_fund |
|---|---|---|
| `held_security_id='005930'` | 239행 / **239개 상품** | 0 (ID 없음) |
| `security_name LIKE '%삼성전자%'` | 279행 / **246개 상품** | 207행 / **139개 상품** |

이름 기반이 ID 기반보다 국내 ETF에서 7개 상품 더 잡는다. 그 차이의 내용:

- `삼성전자우` (우선주) — 국내 ETF 20개, 공모펀드 30개
- `삼성전자   F 202609 (  10)`, `삼성전자F202511(10)`, `삼성전자선물2601`,
  `2023-01삼성전자개별선물` 등 **선물**
- `RISE 삼성전자단일종목레버리지`, `TIGER 삼성전자단일종목레버리지` —
  **다른 ETF를 보유한 것**이지 주식을 보유한 것이 아님
- `교보악사삼성전자투게더증권투자신탁[채권혼합](운용)`,
  `삼성전자알파자1호[채권혼합]` — **펀드명에 삼성전자가 들어간 것**

공모펀드는 security ID가 없으므로 이름 매칭 외에 방법이 없고, 위 15종 이름 변형이
전부 섞여 있다. **공모펀드의 역방향 종목 관계 검색은 entity resolution 없이는
보통주·우선주·선물·재간접·상품명 오탐을 구분하지 못한다.**

### 7.5.1 이름 매칭 정확도 측정

국내 ETF holdings는 `held_security_id`와 `security_name`을 **둘 다** 갖고 있어
ID 기반 결과를 정답으로 쓸 수 있다. KRX 형태 숫자 ID 3,857개 중 canonical 이름이
다른 ID와 겹치지 않는 3,844개를 대상으로 측정했다.

| 방식 | precision 평균 | precision 중앙값 | recall 평균 | precision<1.0 | precision<0.5 |
|---|---:|---:|---:|---:|---:|
| 정확 일치 (`=`) | **1.0000** | 1.0000 | 0.8911 | **0 (0.0%)** | 0 (0.0%) |
| 부분 문자열 (`LIKE`) | 0.9845 | 1.0000 | 0.8975 | 221 (5.7%) | 45 (1.2%) |

- **정확 일치는 3,844개 전부에서 precision 1.0이다. 예외가 없다.**
- 부분 문자열의 위험은 **이름 길이에 강하게 의존한다.**

| canonical 이름 길이 | 대상 수 | precision 평균 | 최솟값 |
|---|---:|---:|---:|
| 2자 | 108 | 0.7917 | 0.0194 |
| 3자 | 180 | 0.9330 | 0.0238 |
| 4자 | 398 | 0.9730 | 0.1111 |
| 5자 | 278 | 0.9955 | 0.8000 |
| 8자 이상 | 2,495 | 0.9956 | 0.1481 |

  최악 사례: `스맥`(정답 2개 → 103개 매칭, p=0.019), `DB`(10 → 245, p=0.041),
  `디오`, `하림`, `나노`, `STX`, `코텍`, `BGF`, `한진`.
  **짧은 한글·영문 종목명이 정확히 한국어 질문이 지목하는 대상이다.**
- 두 방식 모두 recall이 0.89 수준이다. 손실은 **같은 ID에 이름 표기가 여러 개**여서
  생긴다(ID의 32.9%가 2개 이상의 이름 표기를 갖는다).
- 공모펀드 security 이름 17,449종을 국내 ETF의 이름→ID 사전에 대조하면
  **유일한 ID로 정확 일치하는 것은 2,139종(12.3%)뿐이고 15,288종(87.6%)은
  정확 일치가 아예 없다.** 즉 국내 ETF를 사전으로 써도 공모펀드 entity resolution의
  대부분은 해결되지 않는다.

### 7.5.2 국내 ETF holdings에도 placeholder security ID가 있다

한 ID에 5개 이상의 서로 다른 이름이 달린 ID가 **302개**다.

| ID | 서로 다른 이름 수 | 행 수 |
|---|---:|---:|
| `100000` | 222 | 532 |
| `000001` | 175 | 368 |
| `000000` | 137 | 278 |
| `100001` | 109 | 263 |
| `100003` | 88 | 214 |

`ZTRSG6` 같은 ID에는 서로 다른 스왑·TRS 계약 17종이 한 ID 아래 들어 있다.
**해외 ETF의 `000000000`·`N/A`와 같은 문제가 국내 ETF에도 있다.**
`005930` 같은 실제 KRX 코드는 신뢰할 수 있지만, ID 하나가 곧 security 하나라는
가정은 성립하지 않는다.

### 7.6 실패 사유

| family | stage | code | 건수 |
|---|---|---|---:|
| overseas_etf | select_filing | NO_PUBLIC_NPORT_FOUND | 560 |
| overseas_etf | identify | UNRESOLVED_MAPPING | 431 |
| overseas_etf | parse_holdings / parse_xml | COLLECTED_EMPTY / XML_PARSE_ERROR | 5 |
| public_fund | fetch_holdings | NO_SETTLEMENT_REPORT | 642 |
| public_fund | lookthrough | PARENT_NOT_DISCLOSED | 479 |
| public_fund | resolve_company | NO_COMPANY_CODE | 152 |
| public_fund | lookthrough | 기타 | 20 |
| domestic_etf | identify / fetch_holdings | UNRESOLVED_TICKER / EMPTY_DATAFRAME | 4 |

해외 ETF unresolved 431과 filing 미발견 560은 원인이 다르다.
`CONTEXT.md`가 요구한 "unresolved 원인 분리"는 이 두 코드로 이미 구분돼 있다.

## 8. 이 관측이 만드는 결정 사항

사용자와 Codex의 결정이 필요하며, 이 문서는 어느 쪽도 채택하지 않았다.

1. 상품군별 Target 모집단 정의. 특히 국내 ETF에서 ETN 545행과 종료 상품,
   거래정지 1건, 손상 레코드 1건의 처리.
2. 0 제외 규칙을 measure에만 적용하고 code/flag에는 적용하지 않는 구분을
   Registry가 소유할지.
3. sentinel(`99991231`, `'0'` ID, `000000000`, `N/A`)을 결측과 같은 범주로 볼지
   별도 상태로 볼지.
4. Y/blank flag의 blank를 미확인으로 둘지, 근거를 확보해 N으로 확정할지.
5. 공모펀드 "총보수"를 4개 보수 컬럼의 합으로 정의할지, 아니면 지원하지 않을지.
6. 해외 ETF에 1D 외 수익률이 없다는 사실을 capability 수준에서 어떻게 표현할지
   (unsupported / refused / 외부 데이터 수집).
7. 통화가 다른 순자산을 상품군 통합 비교에서 어떻게 처리할지(환율 source 필요).
8. 공모펀드 as-of 709종·최고령 2018년, holdings 430종·최고령 2014년을
   freshness 상태로 어떻게 표현할지.
9. holdings의 `held_security_id` scheme을 family별로 표기하는 방법과,
   placeholder ID(302개, 해외 `000000000`·`N/A` 포함)를 security로 취급하지 않는 규칙.
10. 공모펀드 관계 검색을 이름 기반으로 열지, entity resolution 전까지 닫을지.
    7.5.1의 측정이 이 결정에 직접 붙는다. 정확 일치는 precision 1.0이지만
    공모펀드 이름의 87.6%가 정확 일치 대상을 갖지 못한다. 부분 문자열은 짧은
    이름에서 precision이 0.02까지 떨어진다.
11. 부분 문자열 매칭을 쓴다면 이름 길이·후보 수에 따른 precision 위험을
    build time에 계산해 capability로 노출할지(고정 임계값이 아니라 산출값).

## 9. 이 관측의 한계

- 컬럼 코멘트 외의 제공자 데이터 사전이 저장소에 없어 단위·코드 의미를 확정하지
  못했다. 퍼센트/원/USD 판단은 값의 범위와 코멘트에서 읽은 것이며 공식 근거가 아니다.
- 국내 ETF holdings의 실효일은 원본으로 검증할 수 없다. `2026-08-22`는 요청일이다.
- 공모펀드 결산 부속명세서가 full snapshot인지 판단할 근거가 없다
  (`snapshot_scope='unknown'`이 그대로 남아 있다).
- 7.5.1의 정확도는 **국내 ETF holdings 안에서** 측정한 값이다. 사용자가 질문에
  쓰는 표현이 holdings의 `security_name`과 같은 표기라는 가정이 들어 있다.
  질문 표현 → 종목 매칭은 별도 문제이며 측정하지 않았다.
- recall 0.89의 손실분이 어떤 이름 표기 차이에서 오는지 유형별로 분류하지 않았다.
- 실행 슬라이스(적재·compiler·Evidence)는 구현하지 않았다.

## 10. 재현 방법

세 단계로 실행했다.

1. `openpyxl` `read_only=True, data_only=True` 스트리밍으로 네 data workbook을
   한 행씩 집계(컬럼명·타입·코멘트는 각 schema workbook에서 읽음).
2. 모집단 정의별로 지표 nonblank / 0 제외 후 universe를 재계산.
3. holdings ZIP의 normalized parquet 4개를 임시 디렉터리로 복사해 DuckDB
   메모리 DB에서 grain·JOIN·역방향 조회 질의.

스크립트는 세션 임시 디렉터리에서 실행했고 저장소에 두지 않았다.
필요하면 `scripts/`에 승인된 형태로 다시 작성해야 한다.
원본 Excel과 ZIP은 열기만 했고 수정하지 않았다. 임시 parquet 복사본은 삭제했다.
