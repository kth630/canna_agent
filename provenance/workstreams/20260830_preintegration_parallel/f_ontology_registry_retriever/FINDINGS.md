# Semantic Registry hybrid Retriever 구현 기록

상태: **F 내부 구현과 로컬 검증 완료, F→B 후보 계약은 제안 상태**.
기준 HEAD는 `dc25ca7b60a5a08e40f53a14b41935f618dec9e3`이며 커밋·푸시는 하지 않았다.

## 1. 이어받은 Claude 변경

Codex가 이어받을 때 다음 파일은 모두 untracked 상태였다.

- `src/canna/retrieval/`: vocabulary, normalization, rule retrieval, CLOVA provider,
  embedding index, candidate/result 계약, merger와 설정
- `scripts/build_retrieval_index.py`
- `tests/retrieval/`: 79개 offline test
- `GATE_RETRIEVER.md`

Claude가 이미 만든 실제 로컬 산출물은 Git에서 제외된
`data/processed/semantic_retrieval_index.json`과 2,125,824-byte float32 sidecar다.
Semantic Registry 331개 중 검색 가능한 313개 용어의 label 313개, alias 145개,
definition 61개를 각각 embed한 519-entry index다. SHACL shape 18개는 검색 가능한 텍스트가
없으며 manifest에 누락 상태로 명시돼 있다.

초기 targeted test는 79개가 통과했지만 ruff 10건이 남아 있었다. 구현 감사에서 다음
미완성 또는 문제를 확인했다.

1. exact가 전체 문자열 일치가 아니라 문장 안 포함으로 구현돼 exact/normalized/phrase/
   substring 책임이 섞였다.
2. 모든 문장부호를 제거해 `15.4`와 `154`, 부호·percent 같은 의미가 다른 표기를 같은 key로
   만들 수 있었다.
3. provider 장애가 embedding path만 unavailable로 남지 않고 전체 retrieval을 예외로
   중단했다.
4. embedding top-k가 stable semantic ID dedup 전 surface-form entry에 적용돼 한 용어의
   여러 alias가 후보 budget을 독점할 수 있었다.
5. 고정 이름 vector sidecar를 먼저 교체한 뒤 manifest 교체가 실패하면 이전 generation을
   잃을 수 있었다.
6. build의 existing-index 검사가 model name과 Registry hash만 보고 dimension, metric,
   API contract, provider/base URL과 실제 form coverage를 확인하지 않았다.
7. live marker와 Registry 전체 threshold/top-k 실험 경로가 없었고 config가 존재하지 않는
   실험 script를 가리켰다.

## 2. Codex 보완

- rule tier를 `exact → normalized → phrase → substring`으로 분리했다. 앞의 세 단계는 승인된
  전체 surface form을 찾은 경우만 grounding 가능하고 substring은 후보 확장만 한다.
- NFKC, casefold, whitespace와 명시된 typographic separator만 공통 정규화한다. decimal,
  sign, percent, slash와 그 밖의 증명되지 않은 기호는 보존한다.
- 같은 위치에서 긴 Registry 표현이 함께 발견되면 짧은 표현을 vocabulary-driven maximal
  match로 substring에 내린다. 금융 동의어나 한국어 조사 목록은 코드에 넣지 않았다.
- embedding 장애는 rule 결과를 보존한 채 path의 `availability=unavailable`과
  `unavailable_reason`으로 남긴다. index build 실패는 여전히 예외이며 부분 index를 publish하지
  않는다.
- embedding 검색은 전체 entry cosine scan 후 stable semantic ID별 최고 점수를 선택하고,
  그 뒤 설정의 top-k를 적용한다.
- 후보마다 Registry hash를 넣고 label/alias/definition 및 semantic discriminator를 Registry
  evidence로 전달한다. normalized-equivalent 동명 표현도 competing meaning으로 묶는다.
- future index publish는 content-addressed float32 sidecar와 manifest generation으로 바꿨다.
  manifest 교체 실패 시 이전 manifest/sidecar가 그대로 usable하다. 기존 Claude index 형식은
  읽을 수 있다.
- index load/use 시 index kind, schema, 생성 시각, dtype/byte order/normalization, vector hash,
  entry count/중복, Registry hash와 전체 embeddable form, provider ID/model/dimension/metric/
  API contract/base URL을 fail-closed로 검증한다.
- 외부 호출 없는 Registry cross-form sweep과 opt-in `embedding_live` test marker를 추가했다.

## 3. 후보 출력 제안 계약

`RetrievalResult`는 질문과 normalized key, `candidates | ambiguous | unresolved`, 구조화 reason,
path별 availability/latency/count, 설정 근거, Registry hash와 index manifest summary를 가진다.

각 `RetrievalCandidate`는 다음을 보존한다.

- `semantic_id`, semantic `kind`, `preferred_label`, `registry_content_hash`
- label/alias/definition과 family, grain, period, unit, currency, operation, comparison group,
  meaning status, evidence requirement, domain/range/inverse의 Registry evidence
- rule/embedding별 `matched_expression`, role, tier, score, rank, matched span과 path detail
- merged rank와 `grounding_eligible`

출력 구조에는 physical table/column, SQL, JOIN, Execution Registry binding, execution plan이
없다. 이 계약은 F→B handoff 제안이며 공유 계약으로 확정하지 않았다.

## 4. rule과 embedding 책임 경계

- rule은 stable ID, label, approved alias, definition만 읽는다. whole-form tier만 grounding
  가능하다. `수익률`은 실제 Registry에서 11개 substring 후보, `보수`는 2개 후보이며 둘 다
  grounding 후보 0개와 `ambiguous(no_grounding_evidence)`로 확인했다.
- embedding은 같은 Registry의 label/alias/definition만 search proposal로 사용한다.
  embedding score가 1위여도 `grounding_eligible=false`다.
- 두 경로는 독립 실행되고 stable semantic ID로만 합쳐진다. provider 장애는 rule을 없애지
  않으며 embedding 성공으로 위장하지 않는다.
- Retriever는 최종 의미 선택, HCX planning, 서버 validation, DB/Tool 실행을 하지 않는다.

## 5. index와 stale 검증

manifest에는 다음이 기록된다.

- `index_kind=semantic_registry_terms`, schema version, UTC 생성 시각
- provider/model/API contract/base URL, 1024 dimension, 모델별 distance metric과 normalization
  (`clir-sts-dolphin`/`bge-m3`: cosine + L2, `clir-emb-dolphin`: inner product + raw)
- Semantic Registry content hash, term/searchable/unsearchable count
- entry count와 role별 count, sidecar path/hash/bytes
- build/API 호출 수, provider token, retry, API elapsed/throttled time, 주입된 단가와 예상 비용

Registry hash, form coverage 또는 provider contract가 다르면 use와 no-op build 검사가 모두
거부한다. `dart_documents` 같은 다른 `index_kind`도 거부해 문서 index와 섞이지 않는다.

## 6. threshold/top-k 구조 실험

명령:

```powershell
uv run python scripts/evaluate_retrieval_index.py
```

519개 entry 중 같은 semantic ID에 다른 surface form이 있는 333개 entry(127개 semantic term)를
leave-one-form-out query로 사용했다. 자기 vector를 제외하고 stable ID로 합친 뒤 6개 threshold와
6개 top-k를 전수 sweep했다. 외부 API 호출이나 새 자연어 질문 fixture는 없다.

| cosine threshold | semantic top-k | same-ID recall | mean candidates | mean competing IDs |
|---:|---:|---:|---:|---:|
| 0.3 | 20 | 0.648649 | 19.630631 | 18.981982 |
| 0.5 | 20 | 0.576577 | 11.960961 | 11.384384 |
| 0.7 | 20 | 0.327327 | 2.330330 | 2.003003 |

이는 recall/budget trade-off의 구조적 근거지만 승인된 자연어 질문의 unrelated false-positive를
측정하지 않는다. 따라서 config의 0.5/20은 `provisional_registry_wide_structural_sweep`으로
명시하며 제품 threshold로 확정하지 않는다.

## 7. live API와 비용·latency

Claude의 실제 index build manifest:

- model: `clir-sts-dolphin`, 1024d, cosine
- 519 calls / 519 texts / 2,996 prompt·total tokens
- provider API elapsed 620,941.586 ms, build elapsed 624,889.470 ms
- pacing 273,742 ms, rate-limit retry 32회
- token 단가를 주입하지 않아 예상 비용은 `null`이며 공개 단가를 추측하지 않았다.

Codex의 별도 live marker 1회 결과:

- 1 call, 7 prompt·total tokens, 1024d vector와 기존 index 호환 통과
- provider elapsed 1,484.535 ms, retry 0
- 단가 미주입으로 예상 비용 `null`
- API key 값과 query text는 출력·문서·Git에 기록하지 않았다.

## 8. 검증과 남은 한계

실제 검증 결과:

- retrieval offline: `91 passed, 1 deselected` (`embedding_live`만 제외)
- 전체 offline: 한 직렬 실행에서 `429 passed, 4 deselected`; 최종 분리 재검증은
  atomicity 외 `409 passed, 4 deselected`, atomicity 20개 중 19개 통과 후 기존
  `store.publish` rollback 1개가 Windows `WinError 5`로 간헐 실패했다. 실패 case를 즉시
  고유 basetemp에서 단독 재실행하면 통과했다. 반복 전체 실행에서도 서로 다른 atomicity
  case가 같은 방식으로 한 번씩 실패·단독 통과해 Retriever 회귀가 아닌 파일 잠금 간헐성으로
  분리했다.
- live embedding marker: `1 passed`, 1 external call
- scoped ruff(`src/canna/retrieval`, 두 retrieval script, `tests/retrieval`):
  `All checks passed!`
- 전체 repository ruff는 이번 변경 밖의 `scripts/audit_0d_inventory.py`에 기존 import order와
  `datetime.UTC` 스타일 2건을 보고했다. 범위 밖 파일은 수정하지 않았다.
- existing index no-op validation: Registry 331 / searchable 313 / surface forms 519, hash와
  전체 provider contract 일치
- `git diff --check`: whitespace error 없음. Windows LF→CRLF 안내만 출력됨.

현재 확인된 한계는 다음과 같다.

- 자연어 gold 기반 threshold/recall/false-positive 평가는 B와 사용자 승인 질문이 준비된 뒤
  필요하다. 이번 구조 sweep으로 이를 대체하지 않는다.
- definition이 있는 용어는 61개뿐이고 18개 shape는 검색 텍스트가 없다. 이는 index가
  숨기지 않고 manifest에 기록한다.
- rule phrase boundary는 Registry의 긴 표현을 이용한 maximal match를 사용한다. 형태소 분석이나
  금융 동의어를 코드에 넣지 않았으므로, Registry에 없는 매우 짧은 동형 표현의 경계 문제는
  HCX 선택과 서버 검증 전까지 후보 수준에 남는다.
- 후보가 있다는 사실은 실제 데이터 coverage나 freshness, 실행 지원을 뜻하지 않는다.
- 계약·아키텍처·coverage 정책 변경은 없고 F→B 출력 승격 결정은 남아 있다.

## 9. 2026-08-31 후보 품질 평가 준비

사용자 승인 전 live 모델 비교는 실행하지 않았다. 기존 구현을 세 모델 비교 관점에서 다시
감사해 다음 두 문제를 확인했다.

1. build script의 기본 output이 모델과 무관한 단일 manifest라 `--model`만 바꿔 실행하면
   다른 모델 generation을 같은 경로에 publish할 수 있었다.
2. index가 cosine/L2로 고정되어 bge-m3에는 맞지만, provider가 inner product를 권장하는
   `clir-emb-dolphin`의 별도 metric 계약을 표현하지 못했다.

보완 결과:

- 세 approved model profile을 만들고 model, transport API contract, service contract,
  1024 dimension, metric과 normalization을 하나의 fail-closed identity로 관리한다.
- comparison index는
  `data/processed/semantic_retrieval_indexes/<model>/manifest.json`과 같은 디렉터리의
  content-addressed sidecar로 격리한다. 기존 단일 clir-sts index는 삭제·재생성하지 않고
  legacy generation으로 보존했다.
- cosine 모델(`clir-sts-dolphin`, `bge-m3`)은 실제 vector width/finite 값을 확인한 뒤 L2
  normalize하고, inner-product 모델(`clir-emb-dolphin`)은 finite raw vector를 보존한다.
- 미승인 평가 제안은 명확 질문 35, unrelated 3, ambiguous diagnostic 6으로 작성했다.
  모든 clear case는 Registry stable ID와 label/alias/definition/family/period/관계 방향 근거를
  가진다. diagnostic은 명확 질문 recall에서 제외된다.
- evaluator는 approval reference와 proposal Registry hash를 검증하고, report에서 질문 원문을
  제외한다. rule-only, embedding/merged recall@1/3/5/10/20, 후보 수 분포, competing ID,
  ambiguous set 보존, unrelated grounding 오탐, latency p50/p95와 threshold/top-k sweep을
  생성한다.
- threshold는 모델별 관측 score quantile을 기본 실험 grid로 사용하고 모델별 explicit grid를
  선택적으로 받는다. runtime config와 기존 0.5/20은 변경하지 않았고 모델 자동 선택도 하지
  않는다.
- 실패 taxonomy는 Registry alias, label/definition, family, period, embedding similarity,
  threshold, top-k, merge/dedup을 보존한다. Registry 관련 원인은 사람 검토 hypothesis이며
  evaluator가 TTL/Registry를 수정하지 않는다.

최종 offline 검증은 고유 Windows basetemp에서 `435 passed, 4 deselected`였다. Retriever
범위 ruff는 통과했다. 전체 저장소 ruff의 유일한 2건은 이번 변경 밖의 기존
`scripts/audit_0d_inventory.py` import order와 `datetime.UTC` 스타일이다. `git diff --check`와
untracked 파일별 `git diff --no-index --check`는 whitespace error 없이 LF→CRLF 안내만 냈다.
live embedding 호출은 0회다.

승인 후 exact command는 `RETRIEVAL_EVALUATION_PROPOSAL.md` 8절에 기록했다.

## 10. Easy baseline live evaluation — 2026-08-31

사용자 승인 reference
`user_approval_2026-08-31_retrieval-evaluation-v1-easy-baseline`로만 실행했다. proposal
version, 질문 hash `90de44eff9dd5b4672ae9aee926ad3f6c37ce5ad4933396dcfcbe6449491668f`, Registry
hash `afb7f0c827495dcdd52c972d77c934c380a661c9ccf6e5b5b590b31e8dad6757`가 세 report에서
일치한다. 질문 원문은 report에 쓰지 않았다.

### Recall (35 clear cases, threshold 없는 ranking top-k)

| 모델 | embedding @1/@3/@5/@10/@20 | merged @1/@3/@5/@10/@20 | rule-only |
|---|---|---|---:|
| `clir-sts-dolphin` | 0.200000 / 0.285714 / 0.371429 / 0.514286 / 0.571429 | 0.342857 / 0.857143 / 0.885714 / 0.914286 / 0.914286 | 0.857143 |
| `clir-emb-dolphin` | 0.085714 / 0.085714 / 0.114286 / 0.171429 / 0.314286 | 0.342857 / 0.857143 / 0.857143 / 0.914286 / 0.914286 | 0.857143 |
| `bge-m3` | 0.514286 / 0.885714 / 0.914286 / 0.914286 / 0.971429 | 0.342857 / 0.857143 / 0.885714 / 0.942857 / 0.971429 | 0.857143 |

여기서 `rule-only` 0.857143은 rule **후보**가 기대 ID를 회수한 30/35다. 즉시
`grounding_eligible`인 `rule_grounding_ids`만 세면 28/35, 0.800000이다. `REL-01`의
`cnn:mapsToPortfolio`와 `REL-02`의 `cnn:directlyHoldsSecurity`는 rule 후보에는 있지만
grounding 후보에는 없다. 후보 회수와 실행 전 grounding 가능성을 같은 지표로 해석하지 않는다.

### 명확 질문 누락

merged top-20 기준 누락은 다음과 같다.

- `clir-sts-dolphin`: `DB-03 → bdkr:Duration`, `DE-03 → etkr:TrackingErrorRate`,
  `OE-03 → etgl:RealtimeMarketPrice`
- `clir-emb-dolphin`: `DB-03 → bdkr:Duration`, `DE-03 → etkr:TrackingErrorRate`,
  `OE-03 → etgl:RealtimeMarketPrice`
- `bge-m3`: `DB-03 → bdkr:Duration`

평가기가 자동 분류한 이 누락은 모두 `top_k_exclusion`이다. 이는 Registry 부족을 확정하는
판정이 아니다. 의역·label/definition 정보 부족 가능성은 별도 human-review hypothesis로
남겼다.

### 관계·보유 후보

세 모델 모두 `REL-01`~`REL-04`, `HOLD-01`~`HOLD-03`의 기대 ID를 merged top-20에 포함했다.
괄호는 merged rank이며, embedding top-5에 기대 ID가 없더라도 rule 후보로 보완될 수 있다.

| case | 기대 ID | STS rank | EMB rank | BGE rank |
|---|---|---:|---:|---:|
| REL-01 | `cnn:mapsToPortfolio` | 3 | 3 | 3 |
| REL-02 | `cnn:directlyHoldsSecurity` | 3 | 3 | 3 |
| REL-03 | `cnn:isDirectlyHeldBy` | 5 | 8 | 5 |
| REL-04 | `cnn:hasLookThroughExposureTo` | 1 | 1 | 1 |
| HOLD-01 | `cnn:HoldingWeightType` | 2 | 2 | 2 |
| HOLD-02 | `cnn:HoldingQuantityType` | 1 | 1 | 1 |
| HOLD-03 | `cnn:HoldingValueAmountType` | 1 | 1 | 1 |

특히 역방향 관계 `REL-03`와 보유 관계는 embedding-only 순위가 모델별로 달라도 rule path가
정답을 후보에 남겼다. 이는 실행 허가나 관계 방향 검증을 의미하지 않는다.

### Ambiguous / unrelated

- `DIAG-01`~`DIAG-06`: 세 모델 모두 required semantic ID set 6/6 보존(merged top-20).
  threshold sweep에서는 세 모델 모두 top-k=1일 때 모든 threshold에서 0.0이고,
  top-k=3/5/10/20일 때 모든 threshold에서 1.0이다.
- `UNR-01`~`UNR-03`: 세 모델 모두 `grounding_eligible` 오탐 0건이다. 다만 threshold 없는
  embedding top-20은 각 질문마다 20개 후보를 냈다. 따라서 이 결과는 rule grounding을 통한
  실행 안전장치 검증이지 candidate precision이나 abstention 검증이 아니다.

### 후보 수와 latency

아래 후보 수는 35 clear case, merged, top-k=20이며 각 모델 score-quantile sweep의 범위를
기록한다. 괄호 끝은 가장 높은 관측 threshold row다.

| 모델 | 평균 후보 수 범위 (최고 threshold) | 중앙값 범위 (최고 threshold) | 최댓값 | latency p50/p95 ms |
|---|---|---|---:|---:|
| `clir-sts-dolphin` | 16.657–20.000 (16.657) | 20 (20) | 20 | 596.365 / 650.609 |
| `clir-emb-dolphin` | 16.200–20.000 (16.200) | 20 (20) | 20 | 597.103 / 935.257 |
| `bge-m3` | 14.114–20.000 (14.114) | 14–20 (14) | 20 | 595.607 / 661.555 |

### 모델별 threshold sweep (top-k=20)

threshold는 모델별 score scale에서 독립 관측 quantile이다. 따라서 숫자를 모델 간 직접
비교하거나 runtime 값으로 승격하지 않는다. 표기는 `threshold → merged recall / 평균 후보 / 중앙값 후보 / 최대 후보`다.

- `clir-sts-dolphin`: `-0.107489→0.914286/20.00/20/20`,
  `0.187079→0.914286/20.00/20/20`, `0.263283→0.914286/20.00/20/20`,
  `0.356641→0.914286/19.86/20/20`, `0.460783→0.914286/18.29/20/20`,
  `0.537949→0.914286/16.66/20/20`
- `clir-emb-dolphin`: `807.851198→0.914286/20.00/20/20`,
  `821.398881→0.914286/20.00/20/20`, `825.646275→0.914286/20.00/20/20`,
  `831.079488→0.914286/20.00/20/20`, `836.491067→0.914286/19.57/20/20`,
  `838.689114→0.914286/16.20/20/20`
- `bge-m3`: `0.242228→0.971429/20.00/20/20`, `0.397044→0.971429/20.00/20/20`,
  `0.440283→0.971429/20.00/20/20`, `0.484247→0.971429/20.00/20/20`,
  `0.530878→0.942857/17.89/20/20`, `0.564640→0.942857/14.11/14/20`

### 쉬운 기본선에서의 열세

`clir-emb-dolphin`은 embedding-only recall 전 구간에서 명백한 열세다(`@20 0.314286`,
STS 0.571429, BGE 0.971429). 그러나 동일한 rule path가 merged 후보를 보완해 merged
top-20은 STS와 같고, production 제외를 아키텍처 확정사항으로 만들지 않는다.

`bge-m3`는 다음 hard evaluation의 provisional primary model이다. clear 35개 중 merged
top-20으로 34/35를 회수했다. rule 후보가 놓친 5개(`DB-03`, `DE-03`, `OE-03`, `PF-03`,
`REL-03`) 중 BGE는 4개, STS와 EMB는 각각 2개를 embedding으로 보완했다. 모든 모델이 놓친
`DB-03 → bdkr:Duration`은 BGE embedding rank 287이므로 top-k 확대만으로 해결하지 않는다.
production 모델·threshold·top-k는 여전히 미확정이다.

build는 세 모델 각각 519 calls로 순차 실행했고, provider/API 오류 없이 모두 publish됐다.
처음 일반 샌드박스에서 발생한 `WinError 10013`은 API 응답 오류가 아니라 네트워크 권한
거부였으며, 권한 상승 재시도에서 성공했다. 모델 build 중 rate-limit retry는 STS 32회,
EMB 31회, BGE 31회였다. 세 모델 query 평가도 모두 성공했고, 비교기는 공통 proposal/
Registry/question hash가 일치할 때만 report를 결합했다. runtime threshold, Registry, 제품
fixture, 공유 계약은 변경하지 않았다.

### Cleanup 재검수와 재현 산출물

proposal은 clear 35 / unrelated 3 / ambiguous diagnostic 6, 총 44개로 다시 확인했다.
세 개별 report는 다음 값을 모두 동일하게 기록한다.

- proposal ID: `semantic-retrieval-evaluation-proposal-20260831-v1`
- approval reference: `user_approval_2026-08-31_retrieval-evaluation-v1-easy-baseline`
- questions SHA-256: `90de44eff9dd5b4672ae9aee926ad3f6c37ce5ad4933396dcfcbe6449491668f`
- Registry SHA-256: `afb7f0c827495dcdd52c972d77c934c380a661c9ccf6e5b5b590b31e8dad6757`
- Registry term/searchable/form count: 331 / 313 / 519

`proposal_status_at_run=unapproved`는 proposal artifact 자체를 product fixture로 승인·승격하지
않았다는 상태이고, `approval_reference`는 그 고정 hash의 44개 질문으로 easy baseline을 한 번
실행하도록 사용자가 별도로 허가한 근거다. 두 필드가 함께 있는 것은 의도된 분리지만 이름만
보면 실행 승인도 없었던 것처럼 오해할 수 있다. 이번 cleanup에서는 승인 계약이나 wire schema를
임의 변경하지 않고 이 해석을 provenance에 남긴다.

`.gitignore`의 `data/processed/` 정책에 따라 아래 생성물은 force-add하지 않는다. 파일 bytes를
직접 다시 읽어 기록한 SHA-256과 byte count다.

| 생성물 | SHA-256 | bytes |
|---|---|---:|
| `semantic_retrieval_indexes/clir-sts-dolphin/manifest.json` | `34af0889788fe516339971514f4eba80224df28c084a370e76a15857d12347cc` | 117512 |
| `semantic_retrieval_indexes/clir-sts-dolphin/manifest.5f693e9725f2619bdb7fd785c700946459309fe8973d5fa61f04e57e06bc6ec0.vectors.f32` | `5f693e9725f2619bdb7fd785c700946459309fe8973d5fa61f04e57e06bc6ec0` | 2125824 |
| `semantic_retrieval_indexes/clir-emb-dolphin/manifest.json` | `08ecd4cd9c4a99a53d5037728b0a12eac7ea5095f836ed4ebcbf42fe1ff93988` | 117521 |
| `semantic_retrieval_indexes/clir-emb-dolphin/manifest.2c0425298cbe9b5492a318ac7c30902bf2248264bf448b3ef85366e5546b5dcc.vectors.f32` | `2c0425298cbe9b5492a318ac7c30902bf2248264bf448b3ef85366e5546b5dcc` | 2125824 |
| `semantic_retrieval_indexes/bge-m3/manifest.json` | `9f37349db3a8bfb5c13b138039171a47d24884b615abfb1b4ec19e48725273ea` | 117508 |
| `semantic_retrieval_indexes/bge-m3/manifest.eaa466b3dda07a730c172c2c748ecd6a3b17bbc6e27e9c78e060d55382fcf8c7.vectors.f32` | `eaa466b3dda07a730c172c2c748ecd6a3b17bbc6e27e9c78e060d55382fcf8c7` | 2125824 |
| `retrieval_evaluations/clir-sts-dolphin.json` | `c91d86bc0dfeb62dbc75c4afbadc3de3d9dffe4e47dbd7b70aee60e2b1de9aae` | 316686 |
| `retrieval_evaluations/clir-emb-dolphin.json` | `10d749286e4dc54ab0452dacf521158a482ffd09399c9e333ad8e69825488b7f` | 319690 |
| `retrieval_evaluations/bge-m3.json` | `8c8e74c429ea7722847dcd64dba2373445571cefdd50311dd2163efd2c944e37` | 302347 |
| `retrieval_evaluations/three-model-comparison.json` | `39370d6f0e3f27c308433d6277fe03cbaa74a4998db1a9a998fc2d140565d569` | 404951 |

각 sidecar의 실제 hash와 byte count는 manifest 선언과 일치했다. model, service/API contract,
dimension, metric, Registry hash와 519개 form coverage도 모델별 manifest에서 다시 검증했다.
`case_results`에서 recall, merged top-20 누락, 관계·보유 rank, threshold top-20 후보 수와
ambiguous 보존율을 독립 재계산해 report 표와 일치함을 확인했다. report의 반올림된 case latency로
재구성하면 BGE p50/p95가 각각 0.001ms 높지만, 위 latency 표는 최종 report summary 값을 그대로
기록한다. 세 report에서 질문 원문, API key 이름과 현재 환경의 API key 값은 모두 0건이었다.

재현 명령은 다음과 같다. build 세 개는 rate limit 회피를 위해 표시 순서대로 직렬 실행한다.

```powershell
uv run --cache-dir .tmp/uv-cache python scripts/build_retrieval_index.py --model clir-sts-dolphin
uv run --cache-dir .tmp/uv-cache python scripts/build_retrieval_index.py --model clir-emb-dolphin
uv run --cache-dir .tmp/uv-cache python scripts/build_retrieval_index.py --model bge-m3
uv run --cache-dir .tmp/uv-cache python scripts/run_retrieval_evaluation.py --model clir-sts-dolphin --approval-reference user_approval_2026-08-31_retrieval-evaluation-v1-easy-baseline --output data/processed/retrieval_evaluations/clir-sts-dolphin.json
uv run --cache-dir .tmp/uv-cache python scripts/run_retrieval_evaluation.py --model clir-emb-dolphin --approval-reference user_approval_2026-08-31_retrieval-evaluation-v1-easy-baseline --output data/processed/retrieval_evaluations/clir-emb-dolphin.json
uv run --cache-dir .tmp/uv-cache python scripts/run_retrieval_evaluation.py --model bge-m3 --approval-reference user_approval_2026-08-31_retrieval-evaluation-v1-easy-baseline --output data/processed/retrieval_evaluations/bge-m3.json
uv run --cache-dir .tmp/uv-cache python scripts/compare_retrieval_evaluations.py data/processed/retrieval_evaluations/clir-sts-dolphin.json data/processed/retrieval_evaluations/clir-emb-dolphin.json data/processed/retrieval_evaluations/bge-m3.json --output data/processed/retrieval_evaluations/three-model-comparison.json
```

최초 생성물 세 개에는 사용자 승인 원문의 `_retrieval`이 `-retrieval`로 잘못 기록돼 있었다.
cleanup에서 성능 값·질문·기대 ID·hash는 바꾸지 않고 approval metadata만 승인 원문으로
정정한 뒤 comparison을 offline으로 다시 결합했다. live embedding/API는 다시 호출하지 않았다.
