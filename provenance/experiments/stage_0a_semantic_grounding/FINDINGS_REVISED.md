# Stage 0-A 검증 보완 — 결과

`FINDINGS.md`는 1차 실행 기록이다. 이 문서는 그 실행의 다섯 가지 결함을 고친 뒤
다시 측정한 결과이며, 0-A의 최종 판정 근거다. 1차 기록과 실행 transcript는 지우지
않았고 새 실행은 별도 디렉터리로 남겼다.

## 1. 무엇을 고쳤나

| # | 1차의 문제 | 보완 |
|---|---|---|
| 1 | Runtime View가 field의 소속 상품군을 알려주지 않았다 | 후보마다 `belongs_to_dataset_ref`를 붙였다. 값은 그 요청에서 새로 발급한 dataset ref이고 `catalog_key`·`dataset_key`는 여전히 모델에게 가지 않는다. 소속 dataset이 view에 없으면 view 생성 자체가 실패한다 |
| 2 | 합격 기준이 요구 과잉·span 미검사·요구 수 불일치를 통과시켰다 | 합격 조건을 재정의했다(2절) |
| 3 | 조건 대상·연산자·값, 관계 방향, 정렬, 개수, 비교 대상이 채점 대상이 아니었다 | 세 encoding 모두에 공통 detail slot(`condition`, `relationship`, `aggregation`, `order`, `limit`, `comparison_subject`)을 추가하고 채점했다 |
| 4 | 후보 순서를 고정한 1회 실행이었다 | 질문마다 순서를 3번 바꿔 실행했다(4절) |
| 5 | holdout 결과를 보고 수정했다 | 그 split을 `regression`으로 강등하고, 새 `verification` split 10문항을 따로 만들어 모든 수정이 끝난 뒤 1회만 실행했다 |

실험 코드는 `src/canna/experiments/semantic_probe/`로 옮겼다. 이 package는 운영 계약이
아니며, 서빙 코드가 import하면 `tests/test_architecture_guards.py`가 실패한다.

## 2. 합격 기준: 수정 전과 후

| 항목 | 1차 기준 | 보완 기준 |
|---|---|---|
| ref 무결성 | 필수 | 필수. detail 안의 ref와 관계 anchor ref까지 포함 |
| target dataset | 일치 필요 | 동일 |
| 요구 누락 | recall 1.0 필요 | 동일 |
| 요구 과잉 | 기대 후보 밖 ref를 건드릴 때만 실패 | **선언된 동등 표현이 아니면 요구 수가 다른 순간 실패** |
| 원문 span | 비율만 기록 | **모든 요구가 질문의 부분문자열인 span을 갖고, 요구별로 선언된 anchor를 포함하며, 요구가 여러 개면 span이 서로 달라야 한다** |
| 조건·관계·정렬·개수·비교 | 채점하지 않음 | **필수 slot은 모두 있어야 하고, 허용 slot은 있으면 검사하며, 그 밖의 slot이 남으면 실패** |

동등 표현은 fixture의 `requirement_sets`에 명시한 것만 인정한다. 예를 들어 비교 질문은
"comparison 요구 하나" 또는 "두 조회 + comparison 하나" 둘 다 인정하지만, 어느 쪽이든
comparison 요구 자체가 없으면 실패다.

집계 함수와 metric ref가 붙은 `limit`은 `optional_details`로 허용한다. 없어도 통과하고
있으면 검사한다. 잘못된 집계 함수는 여전히 실패다.

## 3. 결과: 수정 전과 후

### 3.1 기준만 바꾼 효과 (같은 1차 실행 데이터를 재채점)

`scripts/rescore_archived_runs.py`로 1차 transcript를 보완 기준으로 다시 채점했다.
1차 wire에는 detail slot이 없었으므로 detail 검사만 끄고 나머지는 그대로 적용했다.
기록은 `rescore_archived_under_revised_criteria.json`이다.

| 실행 / encoding | 1차 기준 | 보완 기준(detail 제외) |
|---|---:|---:|
| primary / `nested` | 0.769 (10/13) | **0.538 (7/13)** |
| primary / `grouped_flat` | 0.667 (8/12) | **0.333 (4/12)** |
| primary / `delimited` | 0.385 (5/13) | **0.385 (5/13)** |
| 구 holdout / `nested` | 0.750 (6/8) | **0.750 (6/8)** |
| 구 holdout / `grouped_flat` | 0.500 (4/8) | **0.375 (3/8)** |
| 구 holdout / `delimited` | 0.500 (4/8) | **0.500 (4/8)** |

primary의 성공률 하락분은 전부 요구 과잉과 span 규칙에서 나왔다. 1차 보고의 성공률은
기준이 느슨해서 나온 값이다.

### 3.2 보완 계약으로 다시 실행 (순서 3회 반복)

`20260829T181613Z_primary_revised2`, `20260829T182756Z_regression_revised2`,
`20260829T183449Z_verification_final`. 집계는 각 디렉터리의 `summary_recomputed.json`이다.

| split / encoding | 채점된 실행 | provider 실패 | 실행 단위 성공률 | 3회 모두 성공한 질문 비율 | ref 무결성 | 평균 latency |
|---|---:|---:|---:|---:|---:|---:|
| primary / `nested` | 27/39 | 12 (`40009`) | 0.333 | 0.250 | 1.000 | 5,584 ms |
| primary / `grouped_flat` | 39/39 | 0 | 0.333 | 0.154 | 0.974 | 6,121 ms |
| primary / `delimited` | 35/39 | 4 | 0.143 | 0.077 | 0.600 | 4,602 ms |
| regression / `nested` | 19/24 | 5 | 0.158 | 0.125 | 1.000 | 5,419 ms |
| regression / `grouped_flat` | 24/24 | 0 | 0.083 | 0.000 | 1.000 | 6,232 ms |
| regression / `delimited` | 24/24 | 0 | 0.125 | 0.000 | 0.583 | 4,976 ms |
| **verification** / `nested` | 23/30 | 7 | **0.609** | **0.400** | 1.000 | 5,401 ms |
| **verification** / `grouped_flat` | 30/30 | 0 | **0.500** | **0.300** | 1.000 | 6,148 ms |
| **verification** / `delimited` | 29/30 | 1 | **0.207** | **0.100** | 0.586 | 4,520 ms |

split 사이 성공률을 직접 비교하면 안 된다. primary와 regression에는 이미 실패가 확인된
어려운 질문이 모여 있고 verification은 단일 요구 질문 비중이 높다.

capability별(세 split 합산, `nested`, 채점된 실행 기준):

| capability | 통과 |
|---|---|
| `absent_candidate_refusal` | 9/17 = 0.529 |
| `dataset_and_field_grounding` | 2/3 = 0.667 |
| `field_grounding` | 6/12 = 0.500 |
| `relationship_grounding` | 6/16 = 0.375 |
| `comparison_grounding` | 1/6 = 0.167 |
| `requirement_accounting` | 2/15 = 0.133 |

## 4. 후보 순서의 영향

순서 생성 규칙은 실행마다 기록한다. 반복 0은 fixture가 쓴 순서를 그대로 쓰고, 반복 1과 2는
`(base_seed * 1000003 + crc32(test_id) + repeat_index) % 2**31`을 seed로 섞는다. base seed는
`20260830`이며 각 transcript record에 `order_seed`와 실제 순서가 들어 있다. 반복은 3회로
정했다. 한 번의 성공과 세 번 중 두 번의 성공을 구분하기에 충분한 최소값이고, 세 split ×
세 encoding × 3회가 약 280회 호출이라 이 실험의 비용 한계 안에 들어온다.

순서를 바꾸면 결과가 바뀐다. 채점된 실행만 세었을 때 순서에 따라 통과와 실패가 갈린 질문은
`nested` 기준 primary 1개, regression 2개, verification 5개다. verification `nested`에서는
실행 단위 성공률 0.609가 "3회 모두 성공" 기준으로는 0.400으로 떨어진다.

**한 가지 고정 순서에서 한 번 통과한 것은 기능 검증이 아니다.** 앞으로 이 실험의 성공률은
실행 단위와 반복 전체 단위를 함께 적어야 한다.

## 5. 사용자 확인 항목별 결과

- **상품군이 다른 질문**: 소속 정보를 넣은 뒤 개선됐지만 안정적이지 않다. 새 질문
  `vf_dataset_ownership_absent_001`(해외 ETF에 없는 괴리율)은 3회 모두 unresolved로 거절했고,
  `vf_dataset_ownership_positive_001`(공모펀드/국내 ETF에 같은 이름의 순자산총액)은 채점된
  1회만 통과했다. `vf_multi_target_bond_fund_001`은 두 상품군 요구를 모두 남겼다 — 1차에서
  두 번째 요구를 통째로 잃던 실패는 재현되지 않았다. 다만 요청 개수 5를 두 요구 모두에서
  잃어 실패했다.
- **후보가 없는 질문**: 절반만 거절한다(9/17). 새 질문 `vf_forward_default_rate_unresolved_001`
  (내년 예상 부도율)은 3회 모두 거절했지만, regression의 `ho_forward_looking_unresolved_001`
  (향후 1년 예상 수익률)은 여전히 과거 수익률로 `mapped` 판정한다. 같은 성격의 요구인데
  표현에 따라 갈린다.
- **비교 질문**: 1/6으로 가장 나쁘다. 두 비교 질문 모두 `attribute_lookup` 두 개로 분해하고
  `comparison` 요구 자체를 남기지 않는다. 사용한 후보는 정확하다.

## 6. 남은 실패의 종류

모두 `nested` 실행에서 재현된 것이다.

1. **제공된 값 변형** — "1조원" 조건을 `10000`으로 바꿔 기록한다. 1차의 ref 정확 복사와 달리
   **조건 값은 보존되지 않는다.**
2. **연산자 변형** — "0.1% 이하"를 `lte`가 아니라 `lt`로 기록한다. 경계값이 달라진다.
3. **정렬 방향 반전** — "가장 낮은 7개"에 `descending`을 붙인다.
4. **관계 방향 반전** — 질문이 종목을 지목하고 상품을 찾는데 `subject_to_object`로 기록한다.
   predicate 후보에 `subject_role`/`object_role`을 명시하고 중복된 `direction` 표기를 없앤
   뒤에도 재현된다. 3개 질문에서 일관되게 나타난다.
5. **비교 요구 소실** — 6절 참조.
6. **span 합성** — 요구를 모두 정확히 회계하고도 span을 원문에서 자르지 않고 문장을 새로
   만든다. `ho_requirements_four_001`과 `vf_requirements_three_with_condition_001`은 요구
   누락도 과잉도 없이 span 때문에만 실패했다.
7. **slot 오용** — 관계를 `condition ... contains <entity ref>`로 적거나, `limit`의 개수를
   `value`가 아닌 `operator`에 넣거나, `relationship` slot에 방향을 비워 둔다.
8. **요구 과잉 사용 후보** — 개수 요구 record에 집계 대상 field까지 넣는 등 그 요구에 필요
   없는 후보를 끌어온다.
9. **요구 손실** — `sg_partial_unresolved_mix_001`에서 불가능한 두 번째 요구를 통째로 버린다.

## 7. provider 오류

`40009`가 1차의 39회 중 1회에서 이번 세 실행 합계 `nested` 93회 중 24회로 늘었다.
`grouped_flat`은 이번 93회에서 0회, `delimited`는 5회다. 같은 질문·같은 schema가 반복에 따라
성공하기도 실패하기도 한다. schema가 커지면서 발생률이 올라간 것으로 보이지만 크기만으로는
설명되지 않는다. `grouped_flat` schema가 `nested`보다 크고, 앞선 실행에서는
`grouped_flat`에서 6회 발생했다.

현재 코드는 이 code에 재시도를 걸지 않아 관측이 그대로 남는다. **정확도 수치를 안정적으로
얻으려면 backoff 재시도 정책이 먼저 필요하다.** 이번 `nested` 수치는 27/39, 19/24, 23/30만
채점된 값이다. 다만 `grouped_flat`은 provider 실패 0회로 93회를 모두 채점했고 같은 실패
종류를 같은 순서로 보여 주므로, 6절의 결론 자체는 표본 축소에 흔들리지 않는다.

## 8. 0-A를 완료로 판단하는 근거

- 보완 항목 다섯 가지가 모두 코드와 fixture에 반영됐고, harness가 각 실패를 실제로 잡는지
  offline 테스트 34개로 증명했다(잘못된 정렬 방향, 잃어버린 개수, 잃어버린 조건 값, 반전된
  관계 방향, 요구 과잉, 합성 span, 공유 span, detail 안의 발명 ref, 동등 표현 허용).
- 기준 변경 효과와 계약 변경 효과를 분리해 측정했다(3.1, 3.2).
- 순서 반복으로 "한 번 통과"와 "항상 통과"를 구분했다.
- 새 verification split을 만들어 모든 수정 뒤 1회만 실행했고, 그 결과를 보고 계약이나
  prompt를 다시 고치지 않았다.
- provider 형식 제한과 모델 판단 실패를 계속 분리해 기록했다.
- 인증정보 없는 raw request/response를 실행마다 보존했다.

즉 0-A는 "HCX가 잘한다"를 보인 것이 아니라 **무엇이 되고 무엇이 안 되는지를 신뢰할 수 있게
재현 가능하게 측정하는 장치를 갖췄고 그 측정을 마쳤다**는 뜻으로 완료다. 측정 결과 자체는
1차 보고보다 부정적이다.

## 9. 다음 단계로 넘기는 항목

1. HCX의 `mapped` 판정도, 조건 값도, 연산자도, 정렬 방향도, 관계 방향도 서버가 독립 검증해야
   한다. 특히 관계 방향은 지목된 entity의 종류로 서버가 결정할 수 있으므로 모델에게 맡기지
   않는 편이 낫다.
2. 비교 요구는 현재 계약에서 모델이 남기지 않는다. 1단계에서 비교를 별도 요구로 강제할지,
   두 조회 결과를 서버가 비교로 승격할지 결정해야 한다.
3. span 합성 때문에 "요구가 원문의 어느 부분에서 왔는지"를 모델 출력만으로 신뢰할 수 없다.
   1단계에서 서버가 span을 원문에 정렬(align)하거나, span 대신 문자 위치를 요구하는 방안을
   시험해야 한다.
4. `40009` 재시도·backoff 정책을 0-B 배포 실험과 함께 정해야 한다.
5. 순서 민감도가 남아 있으므로 1단계 Runtime View는 후보 제시 순서를 결정적으로 고정하고
   그 순서가 결과에 미치는 영향을 계속 측정해야 한다.
6. 이 실험의 catalog는 합성이다. 4단계 Registry 생성 뒤 실제 후보로 다시 측정해야 한다.
