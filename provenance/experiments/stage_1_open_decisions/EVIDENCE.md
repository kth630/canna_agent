# Stage 1 미결 결정 3건 — 오프라인 증거

## 0. 이 문서의 지위와 경계

`FINDINGS_REVISED.md` 9절이 1단계로 넘긴 항목 중 세 가지에 대한 **증거**다.
어느 쪽도 채택하지 않았고 계약·아키텍처·계획을 바꾸지 않았다. 정본 문서와
0-A 산출물은 변경하지 않았다.

- 대상 결정 (2), (3), (5)에 해당:
  - **C1** span을 원문에 정렬할지, 문자 위치를 요구할지
  - **C2** 관계 방향을 모델에게 맡길지, 서버가 결정할지
  - **C3** 비교 요구를 강제할지, 서버가 승격할지
- HCX 호출 0회. 이미 보존된 0-A transcript와 fixture만 **데이터로** 읽었다.
  0-A의 실험 모듈을 import하지 않았고 1-A의 파일도 건드리지 않았다.

**표본 한계를 먼저 밝힌다.** 아래 수치는 합성 Runtime View 위의 fixture 31개,
transcript 674 레코드(채점 가능 613), requirement span 814개에서 나온다.
관계 방향은 서로 다른 질문 7개, 비교는 2개뿐이다. 방향과 비교의 결론은
**표본이 작다.** 실제 Registry가 생기면 다시 측정해야 한다.

---

## C1. span — 정렬 가능한가, 문자 위치가 필요한가

### 측정

모델이 낸 `text_span` 814개를 각 질문 원문에 결정적으로 정렬했다.
단계는 exact substring → 최소창 토큰 정렬(공백 무시, span의 모든 토큰을 포함하는
가장 짧은 구간) → 문자 블록 fuzzy 순이다.

| 정렬 단계 | 건수 | 비율 |
|---|---:|---:|
| exact substring | 694 | 85.3% |
| 최소창 토큰 정렬 | 106 | 13.0% |
| 문자 블록 fuzzy | 14 | 1.7% |
| **정렬 실패** | **0** | **0.0%** |

- **span이 질문 안 두 곳 이상에 나타난 경우는 0건이다.** 위치 자체가 모호했던
  사례가 없다.
- 최소창 정렬만으로 98.3%가 복구되고, 나머지 1.7%는 fuzzy로 전부 복구된다.
- encoding별 exact 비율: `nested` 82.3%, `grouped_flat` 82.3%, `delimited` 93.2%.

### 정렬 실패 1.7%의 정체는 오탈자다

`fuzzy` 단계로 넘어간 14건은 패러프레이즈가 아니라 **모델의 한글 문자 손상**이다.

```
Q   : 신용등급이 AA 이상인 국내채권의 개수와 평균 만기수익률, 최대 만기수익률을 알려줘
span: 신용등급이 AA 이상인 국내채의 개수          <- '국내채권' -> '국내채'
span: 신용등급이 AA 이상인 국내채관의 개수        <- '국내채권' -> '국내채관'
algn: 신용등급이 AA 이상인 국내채권의 개수        <- 정렬로 정확히 복원됨
```

### 결정적 관측: 위치는 원래 병목이 아니었다

| 지표 | 정렬 전(모델 원본 span) | 정렬 후 |
|---|---:|---:|
| gold `span_anchor` 회수율 (`nested`) | 94.6% | 94.6% |
| gold `span_anchor` 회수율 (`grouped_flat`) | 97.5% | 97.8% |
| 복수 requirement 레코드에서 span이 서로 구별됨 | 95.4% (125/131) | 92.4% (121/131) |

- **정렬은 anchor 회수율을 올리지 못한다.** 모델의 원본 span은 이미 gold anchor를
  94.6% 담고 있었다.
- **정렬은 오히려 구별성을 낮춘다.** 최소창은 인접 요구의 텍스트까지 삼켜서
  10개 레코드에서 창이 겹친다. 원본 span은 95.4%가 이미 서로 달랐다.
  복구된 창의 평균 길이는 질문 전체의 74%다.

즉 0-A가 "span 때문에만 실패했다"고 기록한 사례들은 **정보 손실이 아니라
채점 기준(exact verbatim + 상호 구별) 위반**이다. 요구가 원문의 어디에서 왔는지는
모델 출력에 이미 들어 있다.

### 이 증거가 지지하는 것과 지지하지 않는 것

- **지지함**: 문자 위치(offset)를 모델에게 요구할 근거가 이 데이터에는 없다.
  위치 모호성 0건, 정렬 실패 0건이므로 offset이 해결할 문제가 존재하지 않는다.
  offset은 모델이 인덱스를 세는 새 실패 모드를 추가한다.
- **지지함**: 서버 정렬을 넣는다면 그 목적은 "위치 찾기"가 아니라
  **표면형 정규화(공백·오탈자)** 로 한정된다.
- **지지하지 않음**: 정렬이 requirement 회계 정확도를 올린다는 주장.
  올리지 못했다. 요구 누락·과잉·slot 오용은 span과 무관한 실패다.
- **미측정**: 실제 평가 질문의 길이·구조에서도 위치 모호성이 0인지.
  fixture 질문은 대체로 한 문장이다.

---

## C2. 관계 방향 — 모델인가 서버인가

### 모델이 쓴 값

관측된 relationship detail 64건 중 모델이 적은 방향값:

| 값 | 건수 |
|---|---:|
| `subject_to_object` | 61 |
| `object_to_subject` | 1 |
| 빈 값 | 2 |

**사실상 상수다.** predicate 후보에 `subject_role`/`object_role`을 명시하고
중복 `direction` 표기를 제거한 뒤에도 그대로다.

### 서버 파생 규칙

규칙: *질문이 지목한 entity의 grain을 predicate의 subject/object role grain과
대조해 방향을 정한다.* 지목된 entity는 Runtime View의 entity label을 질문 원문에서
최장 일치로 찾는다(모델 출력을 쓰지 않는다).

fixture가 선언한 gold `traversal`과 대조한 결과:

| test_id | gold | 서버 규칙 | 일치 |
|---|---|---|:--:|
| `ho_entity_preferred_share_001` | object_to_subject | object_to_subject | OK |
| `ho_predicate_lookthrough_001` | object_to_subject | object_to_subject | OK |
| `sg_absent_metric_on_relation_001` | object_to_subject | object_to_subject | OK |
| `sg_relationship_product_to_security_001` | subject_to_object | subject_to_object | OK |
| `sg_relationship_security_to_product_001` | object_to_subject | object_to_subject | OK |
| `vf_relationship_lookthrough_forward_001` | subject_to_object | subject_to_object | OK |
| `vf_relationship_with_metric_ranking_001` | object_to_subject | object_to_subject | OK |

**7/7.** `ho_entity_preferred_share_001`은 질문에 `가온전자`와 `가온전자우` 두 label이
모두 부분 일치하지만 최장 일치가 `가온전자우`를 고르고 방향이 맞는다.

### 모델 대 서버

| | 건수 |
|---|---:|
| 서버 규칙으로 결정 가능 | **64 / 64** |
| 결정 불가 | 0 |
| 모델 = 서버 (일치) | 30 |
| 모델 ≠ 서버 (불일치) | 34 |

불일치 34건은 전부 `named=security, subject=상품, object=종목`인데 모델이
`subject_to_object`라고 쓴 경우다. 서로 다른 질문 5개에서 재현된다.

### 규칙이 깨지는 조건

지목된 entity가 여러 grain에 걸치면 규칙이 모호해진다. 이번 데이터에서는
**0건**이다(security만 35건, product만 30건, entity 미지목 2건).
다만 이는 fixture가 그런 질문을 담고 있지 않기 때문이며 반증이 아니다.

깨질 수 있는 실제 형태는 다음과 같고 아직 시험되지 않았다.

1. predicate의 양 끝 grain이 같은 경우(상품이 상품을 보유 — 재간접·ETF-of-ETF).
   이번 실험의 두 predicate는 모두 상품→종목이라 이 경우가 없다.
   **실제 데이터에는 존재한다**(discovery 기록의 `RISE 삼성전자단일종목레버리지`가
   국내 ETF holdings에 나타난다).
2. 질문이 상품과 종목을 동시에 지목하는 경우("이 ETF가 삼성전자를 보유하는가").
3. entity label이 질문에 문자 그대로 나타나지 않는 경우(별칭·축약).

### 이 증거가 지지하는 것

- 방향을 모델 출력에서 읽는 것은 이 표본에서 **정확도 30/64**다. 서버 파생은 7/7이다.
- 서버 파생은 모델 출력에 의존하지 않으므로 encoding·후보 순서·provider 오류에
  영향을 받지 않는다.
- 규칙은 predicate의 role grain과 entity grain을 Registry가 소유할 때만 성립한다.
  양 끝 grain이 같은 predicate가 생기면 이 규칙만으로는 부족하고 별도 판정이 필요하다.

---

## C3. 비교 요구 — 강제인가 승격인가

### 비교 보존율은 encoding에 따라 갈린다

comparison fixture 2개(`sg_comparison_two_entities_001`, `vf_comparison_on_fee_001`)의
채점 가능한 모든 실행:

| encoding | 실행 | `comparison` 요구 보존 | 보존율 |
|---|---:|---:|---:|
| `nested` | 13 | 5 | 38.5% |
| `grouped_flat` | 14 | 10 | 71.4% |
| `delimited` | 14 | 11 | 78.6% |

`FINDINGS_REVISED.md`는 "두 비교 질문 모두 `attribute_lookup` 두 개로 분해하고
comparison 요구 자체를 남기지 않는다"고 기록했다. 그 관찰은 **`nested`에 한정된다.**
`grouped_flat`과 `delimited`는 과반 이상 유지한다.

### 잃었을 때 서버가 복구할 수 있는가

비교를 잃은 실행을 분해 형태별로 나눴다.

| encoding | 잃음 | 지표 ref 공유 + entity ref 구별 (**승격 가능**) | entity ref만 구별 | **entity ref 없음 (승격 불가)** | 기타 불가 |
|---|---:|---:|---:|---:|---:|
| `nested` | 8 | **8** | 0 | 0 | 0 |
| `grouped_flat` | 4 | 0 | 2 | 2 | 0 |
| `delimited` | 3 | 0 | 0 | 1 | 2 |

`nested`가 비교를 잃을 때의 형태는 항상 이렇다.

```
r1: attribute_lookup  refs=[e.product_index_replication,   f.etf_kr.return_1y]
r2: attribute_lookup  refs=[e.product_futures_replication, f.etf_kr.return_1y]
```

**같은 지표 ref, 서로 다른 entity ref, 요구 2개.** 서버가 결정적으로 비교로
승격할 수 있는 형태다. 반면 `grouped_flat`·`delimited`의 손실분은 entity ref가
아예 없어(`refs=[f.etf_kr.total_expense_ratio]` 두 번) 무엇과 무엇을 비교하는지
복구할 수 없다.

### 보존 + 승격 가능성 합계

| encoding | 비교를 최종적으로 확보 가능 | |
|---|---:|---:|
| `nested` | 5 보존 + 8 승격 = **13 / 13** | **100.0%** |
| `grouped_flat` | 10 보존 + 2 승격 = 12 / 14 | 85.7% |
| `delimited` | 11 보존 + 0 승격 = 11 / 14 | 78.6% |

**순위가 뒤집힌다.** 모델 출력만 보면 `nested`가 최악(38.5%)이지만,
서버 승격을 허용하면 `nested`가 유일하게 100%다. `nested`는 실패할 때도
승격에 필요한 정보를 남기고, 나머지 둘은 성공률이 높은 대신 실패할 때
정보를 통째로 잃는다.

### 한계

- 비교 질문이 **2개**다. 이 결론은 방향성 신호이지 확정된 비율이 아니다.
- 두 질문 모두 "두 상품의 한 지표 비교"라는 같은 형태다. 세 대상 비교,
  집합 대 집합 비교, 서로 다른 지표 비교는 시험되지 않았다.
- 승격 규칙이 성립하려면 질문에 비교 anchor가 있다는 별도 판정이 필요하다.
  이 실험은 그 판정을 측정하지 않았다.

---

## 결정에 넘기는 요약

| 결정 | 이 데이터가 가리키는 방향 | 확신도 |
|---|---|---|
| span 정렬 vs 문자 위치 | 문자 위치를 요구할 근거 없음. 정렬은 표면형 정규화용으로만 | **높음** (814 span, 실패 0, 모호 0) |
| 관계 방향 | 모델에게 맡기지 않음. Registry의 role grain으로 서버 파생 | **중간** (규칙 7/7이지만 질문 7개, 양끝 동일 grain 미시험) |
| 비교 강제 vs 승격 | 승격을 허용하면 `nested` 유지가 정당화됨 | **낮음** (질문 2개) |

추가로 확인이 필요한 것:

1. 양 끝 grain이 같은 predicate(상품→상품)에서 방향 규칙이 어떻게 되는지.
   실제 holdings에 이 관계가 존재한다.
2. 질문이 상품과 종목을 동시에 지목하는 형태.
3. 세 대상 이상·집합 대 집합 비교.
4. entity label이 질문에 문자 그대로 없을 때의 anchor 탐지.
5. 실제 Registry 후보로 C1의 위치 모호성이 여전히 0인지.

## 재현

0-A transcript 15개 실행 디렉터리의 `transcript_*.jsonl`과 fixture 3종을 읽어
정렬 cascade, 방향 파생 규칙, 비교 분해 분류를 계산했다. 스크립트는 세션 임시
디렉터리에서 실행했고 저장소에 두지 않았다. 저장소 파일은 이 문서 외에
읽기만 했다.
