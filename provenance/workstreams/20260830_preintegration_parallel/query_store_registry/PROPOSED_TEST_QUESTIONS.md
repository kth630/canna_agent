# 검수 대기 중인 제안 질문

상태: **미승인 제안**. 어떤 테스트도 이 파일을 읽지 않는다. `AGENTS.md`에 따라 사용자
검수를 통과한 질문만 `tests/fixtures/`에 등록한다.

## 왜 여기에 있나

구현이 구조 검증용으로 초안 12개를 만들었으나, 미승인 질문을 제품 fixture처럼 쓰지
않기 위해 `tests/fixtures/store_query_variants.jsonl`에서 제거하고 provenance로 옮겼다.
구조 불변식 검증은 질문 문자열 없이 `tests/test_store_queries.py`의 직접 테스트가
수행한다.

## 제외한 초안 5개

| 초안 | 제외 사유 |
|---|---|
| `store_relation_forward_005` | 대상 상품을 지목하지 않아 "한 상품"이 모호하다 |
| `store_relation_inverse_006` | 대상 종목을 지목하지 않아 "특정 종목"이 모호하다 |
| `store_lookthrough_separation_007` | 대상 클래스를 지목하지 않아 모호하다 |
| `store_source_row_vs_product_grain_010` | 사용자 질문이 아니라 내부 grain 불변조건이다 |
| `store_class_group_not_portfolio_011` | 사용자 질문이 아니라 내부 단위 분리 불변조건이다 |

제외한 다섯 항목이 지키려던 성질은 모두 직접 테스트로 남아 있다. 관계 정·역방향과
look-through 분리는 `test_relation_forward_and_inverse_agree_on_a_product_grain_answer`,
`test_logical_duplicates_do_not_inflate_a_relation_count`,
`test_direct_and_look_through_relations_stay_separate`가, grain과 단위 분리는
`test_source_rows_never_become_product_counts`,
`test_class_groups_and_portfolios_stay_different_units`가 검증한다.

## 남긴 초안 7개 (`PROPOSED_TEST_QUESTIONS.jsonl`)

| 초안 | 질문 요지 | 구현 의견 |
|---|---|---|
| `..._001` | 국내 ETF·ETN 1년 수익률 상위 10개 | 사용자 질문으로 자연스럽다 |
| `..._002` | 공모펀드 판매회사보수 낮은 순 10개 | 사용자 질문으로 자연스럽다 |
| `..._003` | 국내 ETF·ETN 1개월·1년 수익률 상위 목록 | 사용자 질문으로 자연스럽다 |
| `..._004` | 해외 ETF·ETN 연간보수율 평균 | 사용자 질문으로 자연스럽다 |
| `..._008` | 종목 식별자가 확인된 관측만 연결 | **내부 상태 질문에 가깝다. 제외 또는 재작성 권고** |
| `..._009` | 보유내역 기준일이 요청일인지 실효일인지 | **내부 상태 질문에 가깝다. 제외 또는 재작성 권고** |
| `..._012` | 보유내역 수집에 실패한 클래스가 있는지 | **내부 상태 질문에 가깝다. 제외 또는 재작성 권고** |

001~004는 승인 여부만 결정하면 되고, 008·009·012는 Codex가 지적한 10·11번과 같은 성격
(사용자 의도가 아니라 내부 상태 확인)으로 보여 함께 판단을 요청한다.

구현이 임의로 새 자연어 질문을 만들지 않는다. 위 목록을 승인·수정·기각해 주면 그
결과만 등록한다.
