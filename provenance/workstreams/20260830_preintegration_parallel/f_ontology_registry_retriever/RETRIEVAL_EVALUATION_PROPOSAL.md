# Semantic Retriever 평가 질문 제안 v1

상태: **미승인 제안**

작성일: 2026-08-31

기준 Semantic Registry hash:
`afb7f0c827495dcdd52c972d77c934c380a661c9ccf6e5b5b590b31e8dad6757`

이 문서는 사용자 검수용 provenance다. `tests/fixtures`나 runtime 입력이 아니며, 사용자 승인
전에는 이 질문으로 모델 성능을 확정하거나 threshold를 바꾸거나 대규모 live 호출을 하지
않는다. 기계 판독 정본은 같은 디렉터리의
`RETRIEVAL_EVALUATION_PROPOSAL.jsonl`이다.

## 1. 큰그림 GATE

1. **시스템 목적**: HCX 선택 전에 명확한 지원 질문의 올바른 stable semantic ID가 후보군에
   포함되는지를 재현 가능하게 비교한다. 후보 수 최소화는 1차 목적이 아니다.
2. **일반화 capability**: 자연어 표현 하나와 Registry term 하나의 대응을 rule, embedding,
   stable-ID merge 단계별로 측정한다.
3. **영향 계층**: F 내부 Retriever index와 평가 harness, 미승인 provenance만 변경한다.
   HCX, Tool, Execution Registry, SQL, DART, 문서 Vector index는 건드리지 않는다.
4. **계약**: 공개/공유 계약은 변경하지 않는다. 평가 입력 JSONL과 모델별 report는 F 내부
   실험 계약이다.
5. **grain/coverage/freshness/실패**: grain은 semantic term과 evaluation case다. 후보 존재는
   데이터 coverage나 실행 가능성을 뜻하지 않는다. Registry hash, model/API contract,
   dimension, metric이 다르면 index 사용을 거부한다. provider 실패는 성공으로 위장하지 않는다.
6. **하드코딩**: 질문 문자열, case ID, 기대 ID는 provenance 평가 입력에만 있으며 runtime에
   import하지 않는다. 모델명·dimension·metric은 provider contract다. threshold는 모델별
   실험값 또는 관측 score quantile이며 제품 상수가 아니다.
7. **수용 기준**: 같은 승인 질문과 Registry로 세 모델을 분리 실행하고, 요청된 recall·후보 수·
   모호성 보존·무관 grounding 오탐·latency·실패 원인을 case ID 기준으로 산출한다.

아키텍처나 shared contract 변경은 필요하지 않다.

## 2. 제안 규모와 분포

총 44개다.

| 구역 | 개수 | 모델 선택 recall 분모 |
|---|---:|---|
| 명확한 지원 질문 | 35 | 포함 |
| 무관 질문 | 3 | recall 제외, grounding 오탐 측정 |
| 의도적 모호성 진단 | 6 | recall 제외, 필요 후보 set 보존 측정 |

명확 질문의 capability 분포는 국내채권 7, 국내 ETF·ETN 7, 해외 ETF·ETN 6,
공모펀드 8, 상품/보유 관계 4, 보유 관측 지표 3이다. 표현 축은 서로 겹치며 정확 label,
승인 alias, Registry에 없는 의역, 인접 기간, 상품군이 다른 동명 표현을 모두 포함한다.

각 JSONL case에는 다음을 빠짐없이 기록했다.

- `test_purpose`, `capability_under_test`
- `question_structure`, `explicit_requirements`
- 명확/무관 질문의 `semantic_clarity: explicit`
- `expected_semantic_ids`, `expected_status`
- `failure_falsifies`
- label/alias/definition/family/period/domain/range를 포함한 `registry_evidence`
- 실패 분석 때 검토할 허용 taxonomy인 `failure_analysis_hints`

`questions_sha256`는 순서가 보존된 `[case_id, question]` 배열을 UTF-8 compact JSON으로 만든
뒤 SHA-256한 값이다. 승인 후 질문이 한 글자라도 바뀌면 새 proposal version과 승인이 필요하다.

## 3. 명확한 지원 질문

| ID | 영역/축 | 제안 질문 | 기대 stable semantic ID |
|---|---|---|---|
| DB-01 | 국내채권/정확 | 국내채권의 민평수익률을 보여줘. | `bdkr:AppliedYield` |
| DB-02 | 국내채권/alias | 국내채권의 쿠폰금리를 비교해 줘. | `bdkr:CouponRate` |
| DB-03 | 국내채권/의역 | 국내채권이 금리 변화에 얼마나 민감한지 나타내는 지표를 알려줘. | `bdkr:Duration` |
| DB-04 | 국내채권/현재 | 국내채권의 현재 듀레이션을 보여줘. | `bdkr:Duration` |
| DB-05 | 국내채권/익일 | 국내채권의 익일 듀레이션을 알려줘. | `bdkr:NextDayDuration` |
| DB-06 | 국내채권/속성 | 이 국내채권의 발행사를 알려줘. | `bdkr:IssuerNameRaw` |
| DB-07 | 국내채권/속성 | 이 국내채권의 상환일자를 확인해 줘. | `bdkr:MaturityDate` |
| DE-01 | 국내 ETP/정확 | 국내 ETF·ETN의 3개월 수익률을 보여줘. | `etkr:Return3M` |
| DE-02 | 국내 ETP/alias | 국내 ETF·ETN의 1년 성과를 비교해 줘. | `etkr:Return1Y` |
| DE-03 | 국내 ETP/의역 | 국내 ETF·ETN이 추종 지수를 얼마나 정확히 따라가는지 보여주는 오차 지표를 알려줘. | `etkr:TrackingErrorRate` |
| DE-04 | 국내 ETP/P1D | 국내 ETF·ETN의 1일 수익률을 알려줘. | `etkr:Return1D` |
| DE-05 | 국내 ETP/P1M | 국내 ETF·ETN의 1개월 수익률을 알려줘. | `etkr:Return1M` |
| DE-06 | 국내 ETP/동명 | 국내 ETF·ETN의 운용규모를 알려줘. | `etkr:AssetsUnderManagement` |
| DE-07 | 국내 ETP/속성 | 국내 ETF·ETN이 어떤 추종지수를 따르는지 알려줘. | `etkr:BaseIndexNameRaw` |
| OE-01 | 해외 ETP/정확 | 해외 ETF·ETN의 연간보수율을 보여줘. | `etgl:AnnualExpenseRate` |
| OE-02 | 해외 ETP/동명 | 해외 ETF·ETN의 AUM을 비교해 줘. | `etgl:AssetsUnderManagement` |
| OE-03 | 해외 ETP/의역 | 해외 ETF·ETN이 지금 시장에서 거래되는 가격을 알려줘. | `etgl:RealtimeMarketPrice` |
| OE-04 | 해외 ETP/속성 | 해외 ETF·ETN의 거래통화를 알려줘. | `etgl:TradingCurrency` |
| OE-05 | 해외 ETP/alias | 해외 ETF·ETN의 일간 수익률을 보여줘. | `etgl:Return1D` |
| OE-06 | 해외 ETP/동명 | 해외 ETF·ETN의 기초지수를 알려줘. | `etgl:BaseIndexNameRaw` |
| PF-01 | 공모펀드/정확 | 공모펀드의 18개월 수익률을 보여줘. | `fdpb:Return18M` |
| PF-02 | 공모펀드/동명 alias | 공모펀드의 연간 수익률을 비교해 줘. | `fdpb:Return1Y` |
| PF-03 | 공모펀드/의역 | 공모펀드에서 운용사가 가져가는 연간 보수 항목을 알려줘. | `fdpb:ManagementFeeRate` |
| PF-04 | 공모펀드/속성 | 공모펀드의 위험등급을 알려줘. | `fdpb:InvestmentRiskGrade` |
| PF-05 | 공모펀드/P1Y | 공모펀드의 1년 수익률을 보여줘. | `fdpb:Return1Y` |
| PF-06 | 공모펀드/P2Y | 공모펀드의 2년 수익률을 보여줘. | `fdpb:Return2Y` |
| PF-07 | 공모펀드/alias | 공모펀드의 설정액을 알려줘. | `fdpb:FundNetAssets` |
| PF-08 | 공모펀드/클래스 속성 | 공모펀드 클래스의 판매채널을 알려줘. | `fdpb:ShareClassSalesChannelRaw` |
| REL-01 | 상품 관계 | 이 상품이 어느 운용 포트폴리오에 연결되는지 알려줘. | `cnn:mapsToPortfolio` |
| REL-02 | 직접 보유 정방향 | 이 ETF가 구성종목으로 직접 담고 있는 종목을 알려줘. | `cnn:directlyHoldsSecurity` |
| REL-03 | 직접 보유 역방향 | 이 종목을 직접 담은 상품을 찾아줘. | `cnn:isDirectlyHeldBy` |
| REL-04 | look-through | 이 공모펀드가 모펀드를 통해 보유한 종목을 알려줘. | `cnn:hasLookThroughExposureTo` |
| HOLD-01 | 보유 비중 | 이 상품에서 각 보유종목의 비중을 알려줘. | `cnn:HoldingWeightType` |
| HOLD-02 | 보유 수량 | 이 상품이 각 종목을 몇 개씩 보유하는지 수량을 알려줘. | `cnn:HoldingQuantityType` |
| HOLD-03 | 보유 평가금액 | 이 상품의 보유종목별 평가금액을 알려줘. | `cnn:HoldingValueAmountType` |

질문의 실행 가능성이나 실제 상품 coverage는 이 평가의 gold가 아니다. 여기서는 올바른
semantic ID가 후보에 포함되는지만 검증한다.

## 4. 무관 질문

| ID | 질문 | 기대 |
|---|---|---|
| UNR-01 | 오늘 서울의 시간대별 날씨를 알려줘. | expected ID 없음, `unresolved` |
| UNR-02 | 노트북 배터리를 오래 쓰는 방법을 알려줘. | expected ID 없음, `unresolved` |
| UNR-03 | 다음 주 팀 회의 일정을 정리해 줘. | expected ID 없음, `unresolved` |

embedding 후보는 실행 근거가 아니므로, 무관 질문 평가는 두 값을 구분한다. threshold를 넘은
embedding 후보 수는 candidate-noise이고, whole-form rule match로 `grounding_eligible`가 된
경우만 grounding 오탐이다.

## 5. 별도 ambiguous diagnostic

아래 6개는 의미가 유일하지 않으므로 제품 fixture와 명확 질문 recall 분모에 넣지 않는다.
Retriever가 임의로 하나를 확정하지 않고 필요한 set을 보존하는지만 진단한다.

| ID | 질문 | 보존해야 할 semantic ID set |
|---|---|---|
| DIAG-01 | AUM을 알려줘. | `etkr:AssetsUnderManagement`, `etgl:AssetsUnderManagement` |
| DIAG-02 | 1년 수익률을 알려줘. | `etkr:Return1Y`, `fdpb:Return1Y` |
| DIAG-03 | 기초지수를 알려줘. | `etkr:BaseIndexNameRaw`, `etgl:BaseIndexNameRaw` |
| DIAG-04 | NAV를 알려줘. | `etkr:NetAssetValuePerShare`, `etgl:EstimatedNetAssetValuePerShare` |
| DIAG-05 | 보유 비중을 알려줘. | `cnn:HoldingWeightType`, `cnn:weightValue` |
| DIAG-06 | 보수율을 알려줘. | `etkr:TotalExpenseRate`, `etgl:AnnualExpenseRate` |

## 6. 세 모델 index 분리 계약

비교 index는 아래 디렉터리를 사용한다. manifest와 content-addressed float32 sidecar가
모델 디렉터리 안에 함께 있으므로 다른 모델의 벡터를 참조할 수 없다.

```text
data/processed/semantic_retrieval_indexes/
  clir-sts-dolphin/manifest.json + *.vectors.f32
  clir-emb-dolphin/manifest.json + *.vectors.f32
  bge-m3/manifest.json + *.vectors.f32
```

| 모델 | service contract | dimension | metric | 저장/검색 전 처리 |
|---|---|---:|---|---|
| `clir-sts-dolphin` | CLOVA Embedding v1 | 1024 | cosine | finite/width 검증 후 L2 normalize |
| `clir-emb-dolphin` | CLOVA Embedding v1 | 1024 | inner product | finite/width 검증, 원 벡터 유지 |
| `bge-m3` | CLOVA Embedding v2 dense | 1024 | cosine | dense finite/width 검증 후 L2 normalize |

세 모델 모두 현재 공식 OpenAI-compatible embedding transport를 사용하지만 manifest는 model,
transport API contract, service contract, dimension, metric, Registry hash를 각각 기록한다.
query provider와 하나라도 다르면 fail-closed한다. 기존 단일
`data/processed/semantic_retrieval_index.json`은 이전 `clir-sts-dolphin` 구현을 보존하기 위한
legacy generation이며 세 모델 비교에는 사용하지 않는다.

근거 문서:

- Naver Cloud CLOVA Studio API Guide, Embedding v2
  (`https://api.ncloud-docs.com/docs/en/clovastudio-embeddingv2`)
- Naver Cloud CLOVA Studio Guide, API model table
  (`https://guide.ncloud-docs.com/docs/en/clovastudio-explorer03`)

## 7. 평가와 threshold sweep

명확 질문 35개에 대해 다음을 산출한다.

- rule-only recall
- embedding-only recall@1/@3/@5/@10/@20
- merged recall@1/@3/@5/@10/@20
- 정답 누락 case ID와 semantic ID
- merged 후보 수 평균/중앙값/최댓값
- 명확 질문의 competing ID 평균
- ambiguous diagnostic의 required set 보존율
- unrelated 질문의 grounding 오탐
- embedding query+local scan latency p50/p95

threshold 없는 순위 recall과 threshold sweep을 분리한다. 명시 threshold를 주지 않으면 각
모델에서 실제로 관측된 score 분포의 0/25/50/75/90/95 percentile을 그 모델만의 sweep으로
사용한다. 이는 서로 다른 score scale에 같은 숫자를 강요하지 않는다. 필요하면 한 모델 실행에만
`--thresholds`를 주어 별도 sweep할 수 있다. 어떤 경우에도 runtime config는 자동 변경하지
않으며 모델도 자동 선정하지 않는다.

누락은 자동으로 source-stage를 먼저 판정한다.

- `threshold_exclusion`
- `top_k_exclusion`
- `embedding_similarity_failure`
- `merge_deduplication_failure`

다음 네 항목은 결과만으로 확정할 수 없으므로 JSONL의 Registry 근거와 함께 사람 검토
hypothesis로 남긴다.

- `registry_alias_gap`
- `label_definition_gap`
- `product_family_information_gap`
- `period_disambiguation_failure`

Registry 부족으로 판단돼도 TTL/Registry를 평가기가 수정하지 않는다. 별도 변경 제안과 근거가
필요하다.

## 8. 승인 후 실행 명령

아래 명령은 승인 전 실행하지 않는다. 승인 reference는 이 proposal version에 대해
`user_approval_2026-08-31_retrieval-evaluation-v1`로 기록하는 예시다.

```powershell
uv run --cache-dir .tmp/uv-cache python scripts/build_retrieval_index.py --model clir-sts-dolphin
uv run --cache-dir .tmp/uv-cache python scripts/build_retrieval_index.py --model clir-emb-dolphin
uv run --cache-dir .tmp/uv-cache python scripts/build_retrieval_index.py --model bge-m3

uv run --cache-dir .tmp/uv-cache python scripts/run_retrieval_evaluation.py --model clir-sts-dolphin --approval-reference user_approval_2026-08-31_retrieval-evaluation-v1 --output data/processed/retrieval_evaluations/clir-sts-dolphin.json
uv run --cache-dir .tmp/uv-cache python scripts/run_retrieval_evaluation.py --model clir-emb-dolphin --approval-reference user_approval_2026-08-31_retrieval-evaluation-v1 --output data/processed/retrieval_evaluations/clir-emb-dolphin.json
uv run --cache-dir .tmp/uv-cache python scripts/run_retrieval_evaluation.py --model bge-m3 --approval-reference user_approval_2026-08-31_retrieval-evaluation-v1 --output data/processed/retrieval_evaluations/bge-m3.json

uv run --cache-dir .tmp/uv-cache python scripts/compare_retrieval_evaluations.py data/processed/retrieval_evaluations/clir-sts-dolphin.json data/processed/retrieval_evaluations/clir-emb-dolphin.json data/processed/retrieval_evaluations/bge-m3.json --output data/processed/retrieval_evaluations/three-model-comparison.json
```

report에는 질문 원문을 쓰지 않고 case ID만 남긴다. API key는 기존 환경변수에서만 읽으며
출력하지 않는다.
