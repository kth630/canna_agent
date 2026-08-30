# Stage 0-A — HCX opaque ref와 requirement accounting 반증 실험

## 1. 이 실험이 확인한 것

`IMPLEMENTATION_PLAN.md`의 0-A 단계다. 나머지 계약의 전제인 두 가지를 반증하려 했다.

1. HCX가 요청 단위 opaque ref만으로 질문의 명시 요구를 회계할 수 있는가.
2. provider schema 제약과 모델의 의미 판단 실패를 분리해 관측할 수 있는가.

공식 데이터는 쓰지 않았다. Runtime View는 서로 매우 비슷한 후보로만 구성한 합성
catalog(`tests/fixtures/semantic_probe_catalog.json`)이며, ref는 요청마다 새로 발급하는
8자 opaque token이라 이전 요청의 ref를 기억해도 통과할 수 없다. catalog key는 채점
전용이고 prompt payload에 들어가지 않는다(`test_catalog_key_never_reaches_the_provider_payload`).

## 2. 실행 구성

| 항목 | 값 |
|---|---|
| provider | NCP HyperCLOVA X, model `HCX-007`, `reasoning_effort="none"` |
| 호출 방식 | 단일 function을 `tool_choice`로 강제 |
| encoding | `nested`, `grouped_flat`, `delimited` 3종 |
| primary fixture | 13개, `tests/fixtures/semantic_grounding.jsonl` |
| holdout fixture | 8개, `tests/fixtures/semantic_grounding_holdout.jsonl` |
| 채점 | 결정적. ref 정체성·status·kind·요구 개수만 비교하며 질문 문자열로 분기하지 않는다 |

`case_pass`는 ref integrity(발명·변형 0), target dataset 일치, expected requirement
recall 1.0, 그리고 남은 record가 이 질문에 필요 없는 후보를 건드리지 않았을 때만 참이다.
요구를 더 잘게 쪼갠 것 자체는 실패로 보지 않는다.

## 3. 실행 기록

| run | 목적 |
|---|---|
| `20260829T170357Z_primary_smoke` | 최초 1건. nested schema 수용 여부와 회계 입도 관측 |
| `20260829T170508Z_primary_smoke2` | prompt에 요구 입도 규칙과 kind 정의를 넣은 뒤 재확인 |
| `20260829T170539Z_primary_full` | primary 13개 × 3 encoding |
| `20260829T171026Z_primary_final` | delimited 어휘 표기와 빈 ref 처리 수정 후 최종 primary |
| `20260829T171359Z_holdout_holdout1` | holdout 8개 × 3 encoding, prompt 고정 후 1회만 실행 |

prompt와 encoding 조정은 primary split에서만 했다. holdout은 조정이 끝난 뒤 한 번만
실행했고 그 결과를 보고 다시 조정하지 않았다.

## 4. 결과

### 4.1 encoding별 집계

primary(13개, `20260829T171026Z_primary_final`):

| encoding | provider 실패 | 모델 응답 실패 | case pass | ref integrity | 평균 recall | 평균 latency | 최대 latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| `nested` | 0 | 0 | 0.769 (10/13) | 1.000 | 0.808 | 4,724 ms | 6,610 ms |
| `grouped_flat` | 1 (`40009`) | 0 | 0.667 (8/12) | 1.000 | 0.708 | 5,506 ms | 7,653 ms |
| `delimited` | 0 | 0 | 0.385 (5/13) | 1.000 | 0.500 | 5,315 ms | 13,802 ms |

holdout(8개, `20260829T171359Z_holdout_holdout1`):

| encoding | provider 실패 | 모델 응답 실패 | case pass | ref integrity | 평균 recall | 평균 latency | 최대 latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| `nested` | 0 | 0 | 0.750 (6/8) | 1.000 | 0.750 | 4,419 ms | 6,590 ms |
| `grouped_flat` | 0 | 0 | 0.500 (4/8) | 1.000 | 0.594 | 5,405 ms | 8,821 ms |
| `delimited` | 0 | 0 | 0.500 (4/8) | 1.000 | 0.500 | 4,772 ms | 9,543 ms |

요청 payload는 평균 약 2.0–2.1 KB다. 후보가 6개 수준인 합성 view 기준이므로 실제
Runtime View에서는 더 커진다.

### 4.2 capability별 결과 (`nested`, primary+holdout 합산)

| capability | 통과 |
|---|---|
| `field_grounding` (기간·의미·상하위 개념 인접 후보 구별) | 6/6 |
| `requirement_accounting` (요구 1~4개, nested 재사용, 부분 unresolved) | 5/5 |
| `relationship_grounding` (관계 방향, 직접/간접, 유사 종목·상품 entity) | 3/3 |
| `comparison_grounding` | 0/1 |
| `dataset_and_field_grounding` (상품군 2개 + 요구 2개) | 0/1 |
| `absent_candidate_refusal` | 1/4 |

## 5. 사용자 확인 항목에 대한 답

- **비슷한 항목과 상품 후보를 구별하는가**: 구별한다. `nested`에서 1M/3M/1Y/3Y 수익률,
  순자산총액/시가총액, 총보수/운용보수, 잔존만기/발행만기, 표면금리/만기수익률,
  보통주/우선주, 지수형/선물형 상품, 직접 보유/간접 노출을 모두 요청된 쪽으로 골랐다.
  홀드아웃에서 앞선 시험과 반대쪽 후보를 지정한 3건도 모두 통과했다.
- **요구사항이 하나일 때 정확히 찾는가**: 찾는다. 단일 요구 fixture는 후보 부재 사례를
  제외하고 전부 통과했다.
- **요구사항이 여러 개일 때 빠뜨리지 않는가**: 같은 상품군 안에서는 빠뜨리지 않는다.
  요구 2·3·4개와 nested 재사용 모두 통과했다. 다만 상품군이 서로 다른 두 요구에서는
  두 번째 요구와 그 dataset ref를 통째로 잃었다(6.1).
- **적절한 후보가 없을 때 임의로 만들어내지 않는가**: **만들어낸다. 가장 큰 위험이다**(6.2).
- **제공된 식별값을 바꾸지 않고 그대로 사용하는가**: 그대로 쓴다. 최종 primary와 holdout의
  채점된 62회 호출 전부에서 ref integrity 1.000이었다. 전체 기록 105회 중 2회만 위반으로
  집계됐는데, 둘 다 `grouped_flat`이 "ref 없음"을 빈 문자열 row로 표현한 형식 artifact이며
  ref를 변형하거나 발명한 사례는 한 번도 없다.
- **요청 형식이 복잡할 때와 단순할 때 각각 작동하는가**: 세 형식 모두 provider가 수용했고
  모두 실행됐다. 다만 정확도는 형식이 복잡할수록 좋다(6.3).
- **처리시간**: 호출당 평균 4.4–5.5초, 최대 13.8초다. 의미 회계 1회에 이 정도가 든다는
  뜻이므로 `GET /answer` 전체 예산 설계에 그대로 반영해야 한다.

## 6. 관측된 실패

### 6.1 상품군이 다른 두 요구에서 두 번째 요구 손실

`sg_multi_target_two_requirements_001`은 국내 ETF 순위 요구와 해외 ETF 순위 요구를
함께 물었다. 세 encoding 모두 첫 요구만 남기고 두 번째 요구와 `ds.overseas_etf`를
버렸다. 같은 상품군 안의 요구 2~4개는 잃지 않았으므로, 손실은 요구 개수가 아니라
target 전환에서 발생한다.

`sg_comparison_two_entities_001`도 같은 계열이다. 비교 요구를 두 개의
`attribute_lookup`으로 분해하고 `comparison` record 자체를 남기지 않았다. 사용한 후보는
정확했다.

### 6.2 후보가 없을 때 유사 후보로 대체 — 가장 중요한 결과

`absent_candidate_refusal` 4건 중 3건이 실패했고 세 encoding에서 재현된다.

| 질문의 요구 | Runtime View 상태 | HCX 결정 |
|---|---|---|
| 보유 비중 상위 순위 | 비중 field 없음 | 직접 보유·간접 노출 predicate와 상품명으로 `mapped` |
| 향후 1년 예상 수익률 상위 | 전망 field 없음 | 과거 1년 수익률로 `mapped` |
| 해외 ETF 순자산총액 상위 | 해외 ETF에 해당 field 없음 | 국내 ETF 순자산총액으로 `mapped`, target은 해외 ETF |

세 번째는 dataset 경계를 넘어 다른 상품군의 field를 끌어왔다. 두 번째는
`CONTEXT.md` 2절의 "근거 없는 수익률 전망 금지"와 직접 충돌한다.

prompt는 9번 규칙으로 대체 금지와 `unresolved` 사용을 명시하고 있고, 후보가 완전히 없는
`sg_absent_field_unresolved_001`과 `sg_partial_unresolved_mix_001`은 통과했다. 즉 HCX는
"의미가 아예 없는 요구"는 거절하지만 "의미가 그럴듯하게 인접한 요구"는 거절하지 않는다.

이것은 아키텍처 변경 사유가 아니라 `ARCHITECTURE.md` 3절의 서버 검증 책임이 왜 필요한지에
대한 증거다. 서버는 HCX의 `mapped` 상태를 신뢰하면 안 되고, 최소한 다음을 독립적으로
검증해야 한다.

- field가 요구된 dataset에 속하는지
- 요구된 시점 의미(과거/전망)와 field의 period 의미가 호환되는지
- 요구된 연산이 field의 `allowed_operations`에 있는지

### 6.3 encoding별 형식 제한과 판단 실패의 분리

- provider가 세 schema를 모두 수용했다. **nested object array가 거부된다는 전제는 성립하지
  않았다.** 이전 저장소가 문자열 line 문법을 쓴 이유는 이 실험 범위에서 재현되지 않았다.
- `40009`는 최종 primary 실행 39회 중 1회 발생했고, 같은 schema가 나머지 12건에서 성공했다. 따라서 이 code는
  결정적 schema 거부가 아니라 간헐적 provider 오류로 취급한다. 현재 코드는 이 code에
  재시도를 걸지 않아 관측이 남도록 했다.
- `delimited`는 문자열 배열이라 JSON Schema enum을 실을 수 없다. 첫 실행에서 모델이
  `resolved`, `requested` 같은 임의 status를 만들었다. 배열 description에 허용 어휘를
  적어 준 뒤 정확도가 0.077 → 0.385로 올랐지만 여전히 세 형식 중 가장 낮다.
- `grouped_flat`은 `ref` 문자열이 필수라 "ref 없는 요구"를 빈 문자열 row로 표현했다.
  빈 ref를 발명으로 채점하지 않도록 decoder에서 공백을 버린다.
- HCX는 JSON Schema `enum`을 강제하지 않는다. `output`, `filter` 같은 목록 밖 `kind` 값이
  관측됐다. 서버는 enum 준수를 스스로 검증해야 한다.

### 6.4 요구 입도

첫 실행에서 HCX는 "1년 수익률 상위 10개"를 listing + attribute_lookup + count 3개로
쪼갰다. prompt에 "결과 단위마다 record 하나, 조건·정렬·개수 제한·출력 항목은 그 요구에
포함"이라는 일반 규칙과 kind 정의를 넣자 해결됐다. 질문별 규칙이 아니라
`QUESTION_STRUCTURE.md` 2절의 정의를 그대로 옮긴 것이다.

## 7. 판정

- 0-A의 전제는 유지된다. bounded opaque ref 계약은 provider가 수용하고, 모델은 ref를
  변형하지 않으며, 유사 후보 구별과 같은 상품군 안의 복수 요구 회계는 동작한다.
- 논리 계약을 포기할 이유는 없다. `nested` encoding이 세 형식 중 가장 정확하고 가장 빠르다.
  grouped flat fallback도 요구별 grouping을 보존하며 동작하므로 예비 경로로 남길 수 있다.
- 다만 HCX의 `mapped` 판정 자체는 근거로 쓸 수 없다. requirement status는 서버 검증을
  통과한 뒤에만 실행 근거가 된다.

## 8. 다음 단계로 넘기는 항목

1. Runtime View 계약(1단계)에 dataset↔field 소유 관계와 period 의미를 후보 metadata로
   명시하고, 서버가 이를 독립 검증한다.
2. target 전환이 있는 질문에서 요구 손실을 막을 방법을 1단계에서 측정한다. 상품군별로
   회계를 분리해 호출할지, 한 번에 회계할지는 아직 결정하지 않았다.
3. `comparison`을 별도 요구로 남기지 않는 경향을 1단계 gold annotation에서 다시 측정한다.
4. 의미 회계 1회에 4~6초가 드는 점을 0-B의 배포 latency 예산과 합쳐 본다.
5. 이 실험의 합성 catalog는 실제 Registry가 아니다. 4단계 Registry 생성 후 같은 fixture
   구조로 실제 후보에 대해 다시 측정한다.
