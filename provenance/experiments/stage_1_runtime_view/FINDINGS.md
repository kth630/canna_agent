# Stage 1-A Runtime View retrieval — 결과

이 문서는 `IMPLEMENTATION_PLAN.md` 1단계 중 "1-A. Runtime View contract와
deterministic retrieval 기반"의 실험 기록이다. 실험 계약이며 `ARCHITECTURE.md`의
Confirmed 결정을 바꾸지 않는다. `contracts/`와 정본 문서는 수정하지 않았다.

## 1. 이 실험이 측정한 것

0-A는 모델이 무엇을 못 하는지를 측정했다. 1-A는 그 앞 단계를 측정한다:
**질문에 필요한 후보가 애초에 모델에게 도달하는가.** 도달하지 않은 의미는 모델이
아무리 잘해도 복구할 수 없으므로, 이 recall이 뒤 단계 정확도의 천장이다.

측정 대상은 모델이 아니라 회수 계층이므로 이 실험에는 HCX 호출이 없다. 전부 offline이고
재현에 network, 자격증명, 원본 데이터가 필요하지 않다.

## 2. 구현하지 않은 것

승인된 경계대로 다음은 만들지 않았다: HCX 호출, semantic query 생성, span alignment와
문자 offset, comparison requirement의 서버 승격, 관계 방향 자동 보정, 조건 값·연산자·정렬
방향의 semantic validation, SQL/compiler/DuckDB/Evidence, 실제 Excel·holdings 적재,
NCP 배포와 40009 재시도, 운영 API 연결.

## 3. 산출물

| 경로 | 책임 |
|---|---|
| `tests/fixtures/runtime_view_registry.json` | 합성 Registry. 의미 metadata의 **유일한** source of truth |
| `src/canna/experiments/runtime_view_probe/registry.py` | Registry 적재와 build-time 검증 |
| `src/canna/experiments/runtime_view_probe/retrieval.py` | 결정적 후보 회수와 예산 적용 |
| `src/canna/experiments/runtime_view_probe/view.py` | 요청 단위 opaque ref, 모델용 payload, 크기 측정 |
| `src/canna/experiments/runtime_view_probe/diagnostics.py` | gold 없이 판정하는 구조화된 retrieval failure |
| `src/canna/experiments/runtime_view_probe/measurement.py` | gold 기반 required-candidate recall (harness 전용) |
| `src/canna/experiments/runtime_view_probe/probe.py` | 한 요청의 실행·측정·transcript |
| `tests/fixtures/runtime_view_probe.jsonl` | primary 11문항 |
| `tests/fixtures/runtime_view_probe_unseen.jsonl` | unseen 7문항 |
| `tests/test_runtime_view_probe.py` | offline 테스트 128개 |
| `scripts/run_runtime_view_probe.py` | 실행과 transcript 보존 |

## 4. Runtime View가 후보마다 보존하는 것

`QUESTION_STRUCTURE.md` 6절이 요구하는 구별자를 후보 종류별로 싣는다.

- dataset: label, meaning, grain, **capability coverage**(supported/unsupported 완전 분할),
  coverage grain, observed/universe, requested/effective as-of와 as-of status
- field: meaning, 소속 상품군 ref, period, unit, currency, grain, source, allowed operations
- predicate: meaning, domain/range, subject_role/object_role, relation_mode(direct 또는
  look-through), grain, source, evidence requirements, 적용 가능한 상품군 ref 목록
- entity: meaning, entity type, identifier scheme, grain, 소속 상품군 ref(있을 때)

모델에게 나가는 payload에는 stable ID가 하나도 없다. semantic ID, capability ID, dataset ID는
전부 서버 측에 남고, 소속은 그 요청에서 새로 발급한 `belongs_to_dataset_ref`로만 전달된다.
테스트가 직렬화 문자열에 어떤 semantic/capability ID도 나타나지 않음을 확인한다.

## 5. 회수 규칙

Python 코드에는 alias, field 이름, predicate 이름, 상품군 이름, dataset binding이 없다.
코드가 아는 것은 구조뿐이다.

1. **표면형 매칭** — Registry가 선언한 surface form을 정규화된 질문 문자열 안에서 찾는다.
   정규화 규칙(casefold, 제거 문자)도 Registry가 소유한다. 한국어는 명사구 뒤에 조사가
   붙으므로 토큰 분리가 아니라 부분문자열 포함으로 찾는다.
2. **한 홉 이웃 확장** — Registry가 켠 규칙만 적용한다.
   `same_neighbor_group`(같은 계열의 인접 기간·단위 field, 인접 종목·상품),
   `cross_family_homonym`(같은 label, 다른 상품군), `predicate_sibling`(direct ↔ look-through).
   Registry가 구현되지 않은 규칙 이름을 선언하면 적재가 실패한다.
3. **소속 폐포** — 회수된 후보의 소속 상품군은 아무도 지목하지 않아도 view에 들어온다.
   소속을 모르는 field 후보는 의미가 없기 때문이다.
4. **결정적 순위** — `(tier, -최장 매칭 길이, -매칭 개수, semantic_id)`. tier는
   dataset < 직접 매칭 < 이웃. semantic_id tie-break가 있어 순서는 전순서다.
5. **예산** — 순위대로 admit하고, 넘치면 잘라 내되 잘린 후보와 사유를 전부 기록한다.

테스트로 확인한 성질: Registry의 선언 **순서를 뒤집어도 view 순서가 같다**. 즉 순서는 파일
편집 순서가 아니라 규칙에서 나온다.

## 6. 실패 의미

`AGENTS.md`는 unresolved requirement를 버리고 실행하는 것을 금지한다. 같은 규칙을 한 계층
앞에 적용했다. gold 없이 요청 시점에 판정 가능한 실패는 세 가지다.

| kind | 조건 | 결과 |
|---|---|---|
| `no_dataset_match` | 상품군 후보가 하나도 없음 | `executable=false` |
| `budget_truncated` | 질문이 **직접 지목한** 후보가 예산에 잘림 | `executable=false` |
| `capability_unsupported` | 요청된 capability를 회수된 어느 상품군도 지원하지 않음 | `executable=false` |

**이 실험 안에서 내린 판단 하나**: confusion neighbor만 잘린 경우는 실패로 보지 않는다.
이웃은 대조용이고 요구 자체가 아니기 때문이다. 다만 잘렸다는 사실과 사유는
`truncated`에 그대로 남고 harness가 `neighbors_missing`으로 따로 센다.
`rv_budget_boundary_neighbor_loss_001`이 이 구별을 고정한다. 이 판단은 실험 범위 안의
결정이며 아키텍처 변경이 아니다.

## 7. 실제 측정 결과

실행: `python scripts/run_runtime_view_probe.py --split {primary,unseen} --repeats 3 --label baseline`
기록: `20260829T194042Z_primary_baseline/`, `20260829T194044Z_unseen_baseline/`

| split | 문항 | 순서가 3회 모두 같은 문항 | ref 재사용 | micro recall | recall 완전 문항 | 실행 가능 |
|---|---:|---:|---|---:|---:|---:|
| primary | 11 | 11/11 | 없음 | 0.964 (27/28) | 10/11 | 8/11 |
| unseen | 7 | 7/7 | 없음 | **1.000 (20/20)** | 7/7 | 5/7 |

상품군별 required-candidate recall (primary / unseen):

| 상품군 | required | recall |
|---|---:|---:|
| `ds.domestic_etf` | 17 / 8 | 0.941 / 1.000 |
| `ds.public_fund` | 7 / 7 | 1.000 / 1.000 |
| `ds.domestic_bond` | 2 / 4 | 1.000 / 1.000 |
| `ds.overseas_etf` | 2 / 1 | 1.000 / 1.000 |
| 상품군 없는 종목 entity | 1 / 2 | 1.000 / 1.000 |

primary의 유일한 손실은 의도적으로 예산을 4로 조인 `rv_budget_boundary_required_loss_001`
한 건이고, 그 손실은 `budget_truncated` 실패와 `missing.reason=budget_truncated`로 남았다.
조용히 사라진 후보는 없다.

view 크기와 latency (첫 반복 기준):

| split | 후보 수 min/median/max | 직렬화 byte min/median/max | 총 latency ms min/median/max |
|---|---|---|---|
| primary | 1 / 8 / 15 | 776 / 3,666 / 5,908 | 0.43 / 1.40 / 2.13 |
| unseen | 1 / 6 / 21 | 300 / 2,975 / 7,786 | 0.47 / 1.03 / 3.70 |

가장 큰 view는 unseen의 관계+복수 요구 질문으로 후보 21개, 7,786 byte였다. 0-A에서 관측한
호출당 4.4~6.2초 latency에 비하면 회수 비용은 무시할 수 있는 수준이다. 즉 **후보를 넉넉히
싣는 비용은 latency가 아니라 prompt 크기와 모델의 순서 민감도로 지불된다.**

## 8. unseen 결과의 의미와 한계

unseen 7문항은 Registry와 회수 코드를 다 쓴 뒤, 실행 결과를 보기 **전에** 작성했고 작성
후 회수 규칙을 고치지 않았다. 첫 실행에서 7/7 통과했다.

과대 해석하면 안 되는 이유가 있다.

1. catalog가 합성이다. 실제 Registry에서는 surface form이 훨씬 많고 서로 겹친다.
2. 질문이 전부 `semantic_clarity: explicit`이다. 애매한 질문에서의 회수는 측정하지 않았다.
3. 표면형 부분문자열 매칭은 Registry가 그 표현을 선언했을 때만 동작한다. 선언되지 않은
   패러프레이즈는 `not_matched`로 떨어진다. 이 실험은 **회수 장치가 결정적이고 측정
   가능하다**를 보였을 뿐, **실제 어휘 coverage가 충분하다**를 보이지 않았다.
4. 4단계에서 실제 Registry가 생성되면 같은 fixture로 다시 측정해야 한다.

## 9. 다음 단계로 남기는 결정 — 구현하지 않음

세 항목은 승인 경계에서 "구현하지 말고 선택지·영향·추천을 보고하라"고 지정된 것이다.

### 9.1 span alignment vs character offset

- **A. 모델이 문자 offset(start/end)을 낸다.** 장점: 검증이 정수 비교로 끝난다. 단점:
  0-A에서 모델은 부분문자열 span조차 원문에서 자르지 않고 합성했다(6절 6번). offset은
  더 어려운 요구이며 한글 인덱싱을 모델이 맞출 근거가 없다.
- **B. 모델은 span 문자열을 내고 서버가 원문에 정렬한다.** 장점: 모델 부담이 줄고,
  정렬 실패 자체가 신호가 된다. 단점: 근사 정렬이면 잘못된 구간에 붙을 수 있어
  정렬 규칙(정확 일치 → 정규화 후 일치 → 실패)을 계약으로 못 박아야 한다.
- **추천: B.** 단, 근사 매칭은 넣지 말고 "정확 일치 또는 정규화 후 정확 일치, 아니면
  `span_unaligned`로 실패"로 한정한다. 0-A 데이터가 모델의 span 신뢰도를 이미 반증했으므로
  서버가 정렬 책임을 갖되 정렬 실패를 숨기지 않는 쪽이 안전하다.

### 9.2 comparison requirement — 모델 강제 vs 서버 승격

- 0-A 관측: 비교 질문 6회 중 1회만 comparison 요구가 남았고, 나머지는 조회 두 개로
  분해됐다. 사용된 후보 자체는 정확했다.
- **A. 모델에 강제한다.** 장점: 의미가 모델 출력에 명시된다. 단점: 이미 6분의 5가 실패한
  지점을 더 강한 제약으로 요구하는 것이고, prompt/schema가 커지면 `40009`도 늘어난다.
- **B. 서버가 승격한다.** 같은 기준(field ref)으로 두 target을 조회한 결과가 나오면
  서버가 comparison 요구로 승격한다. 장점: 관측된 실패 모드에 정확히 대응한다. 단점:
  질문이 실제로 비교를 요구했는지 판단 근거가 필요하다.
- **추천: B + 최소 신호.** 서버 승격을 기본으로 하되, 승격 조건을 "동일 field ref, 서로
  다른 target, 같은 질문"으로 한정하고 승격 사실을 `applied_rules`에 남긴다. 승격했는데
  질문이 비교가 아니었을 위험은 출력에 비교 문장을 덧붙이지 않는 것으로 낮춘다.

### 9.3 관계 방향 — 모델 출력 vs 서버가 entity role로 결정

- 0-A 관측: 방향 반전이 3개 질문에서 일관되게 재현됐고, `subject_role`/`object_role`을
  명시한 뒤에도 남았다.
- 이번 실험이 더한 사실: Runtime View의 entity 후보는 `entity_type`(security / product /
  product_class)과 grain을 이미 싣고 있고, predicate는 `domain`/`range`를 싣고 있다.
  즉 **지목된 entity의 종류만으로 방향이 결정된다.** 질문이 종목을 지목했으면
  product→security 관계에서 object가 고정되고, 상품을 지목했으면 subject가 고정된다.
- **추천: 서버 결정.** 모델에게는 "어느 entity를 지목했는가"만 받고 방향은 받지 않는다.
  모델 출력에서 `traversal`/`direction` slot을 제거하면 반전 실패 모드가 구조적으로
  사라진다. 단, 지목된 entity가 domain/range 양쪽에 해당하는 경우(상품이 상품을 보유하는
  관계)는 서버가 `ambiguous`로 남기고 실행하지 않는다.

## 10. 이 실험이 세우지 못한 것

- 실제 데이터의 회수 성능. catalog가 합성이다.
- 모델이 이 view를 잘 읽는지. 이번 실험에 모델 호출이 없다.
- 후보 순서가 모델 정확도에 미치는 영향. 순서를 **고정**했을 뿐, 그 고정 순서가 좋은
  순서인지는 측정하지 않았다. 0-A의 순서 민감도는 여전히 열린 문제다.
- 실제 어휘 coverage. Registry가 선언하지 않은 표현은 회수되지 않는다.
- coverage/freshness 값의 진위. Registry의 모든 수치와 날짜는 합성이다.
