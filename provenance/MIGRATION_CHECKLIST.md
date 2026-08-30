# 단계별 이사 체크리스트

## 목적

이 문서는 `C:\Users\user\asset_agent\canna`의 파일을 새 저장소에서 어떻게 취급할지
기록한다. 이전 저장소는 읽기 전용 참고 자료이며, 현재 단계에 필요한 항목만 이 표의
판정에 따라 다룬다.

이 문서는 아키텍처를 결정하지 않는다. `ARCHITECTURE.md`와 현재
`IMPLEMENTATION_PLAN.md`가 항상 우선한다.

## 판정

- **A**: 그대로 사용할 수 있음. 이미 새 저장소에 있으면 다시 복사하지 않음.
- **B**: 필요한 책임이나 검증 경험만 현재 설계에 맞게 다시 작성함. 원본 파일 전체를
  복사하지 않음.
- **C**: 가져오지 않음.
- **D**: 관련 계약이나 데이터 의미가 확정될 때까지 보류함.

## 공통 규칙

1. 단계가 시작될 때 그 단계에 필요한 A/B 항목만 확인한다.
2. B는 파일 복사가 아니라 현재 정본에 맞춘 재작성이다.
3. C는 코드, 테스트, fixture 또는 문서 정본으로 사용하지 않는다.
4. D는 사용자와 Codex가 선행 결정을 마치기 전에는 구현에 사용하지 않는다.
5. 이전 저장소의 CQ ID, 고정 질문, 고정 답, 고정 상품명·날짜·행 수는 가져오지 않는다.
6. 이전 저장소의 현재 작업공간은 dirty 상태다. 아래 지문은 감사 당시 읽은 파일을
   식별하기 위한 provenance이며 실행 규칙이 아니다.

## 지금 단계: 질문 이해 확인과 빈 평가 서비스

| source | 판정 | source 상태 / SHA-256 | 허용 범위 | 금지 범위 |
|---|---|---|---|---|
| `.python-version` | A | committed / `7b55f8e67b5623c4bef3fa691288da9437d79d3aba156de48d481db32ac7d16d` | Python 3.12 확인. 새 저장소에 이미 있으므로 복사 없음 | 없음 |
| `pyproject.toml` | B | modified / `66387d42e5431bc80c5fbc78c475ab3231a11b4e94529f6496d9cebe84a27c6d` | 필요한 패키지와 설치 설정을 새 `pyproject.toml`에 개별 반영 | 기존 파일·명령·개인 정보·lock 복사 |
| `src/canna/planning.py` | B | modified / `093b4560d92c9173d8f889aeb8a9360dcc8e1adb7d7984233ef1a2b33794a880` | HCX 호출 방식, 강제 Tool 선택, provider 오류 관측을 질문 이해 실험의 참고로 사용 | `plan_lines`, 질문 문자열 정책, CQ fixture, 기존 planner 전체 |
| `src/canna/runtime.py` | B | modified / `76889cde6b680ac566300b2531c5d41f79a91a5752056053a05e2304c2f6cac7` | HCX 최종 호출 경험, 시간 계측, 실패 시 동일 응답 형식 유지 패턴 참고 | CQ별 답변, 고정 상품명, template 답변기, 기존 runtime 전체 |
| `src/canna/api.py` | B | committed / `269db8cf210d488d6a3b562fa41dcb342bab2016e6c638a8e8d8b473c6c3cc8a` | `GET /answer`, UTF-8 JSON, 비어 있지 않은 입력, 5개 문자열 응답 골격 | `/health`, import 시 서비스 생성, 기존 runtime/settings 의존 |
| `tests/test_api.py` | B | committed / `4399c446d544958782c16015be32ead3817c3616c401668fde61dbee11e77814` | HTTP 200, UTF-8, 정확한 5개 field, 입력 echo, 미정의 parameter 안전성 | `H01`, `4,450`, 고정 문구, RulePlanner·TemplateAnswerGenerator 의존 |

위 여섯 항목 외의 이전 파일은 지금 단계에서 사용하지 않는다.

## 이후 단계에서 사용할 B 항목

| source | 사용 시점 | 허용 범위 | 선행 조건 |
|---|---|---|---|
| `src/canna/settings.py` | 실제 경로·환경 설정이 필요할 때 | 저장소 자체 `.env`, `data/official_raw` 기본 경로를 사용하는 새 설정 작성 | 현재 단계의 실제 설정 요구 확정 |
| `src/canna/data.py`의 Excel 적재 부분 | 공식 Excel 적재 단계 | schema/data 일치 검증, 원자적 DB 교체, 실패 정리 패턴 | 적재 산출물과 metadata 계약 |
| `tests/test_loader.py` | 공식 Excel 적재 단계 | 임시 합성 workbook 기반 자족 테스트 | 새 ingest 경로 확정 |
| `tests/test_ontology.py` | Registry·Ontology 단계 | 5개 Turtle parse와 SHACL 자기 검증 | 새 Ontology와 Registry generator |
| `scripts/collect_pykrx_pdf.py` | holdings v2 수집 단계 | 호출 간격, 성공·빈 결과·예외 구분, 읽기 전용 수집 패턴 | requested/effective as-of 계약 |
| `scripts/collect_kofia_holdings.py` | holdings v2 수집 단계 | KOFIA 3단계 호출 절차와 실패 사유 보존 | product/class/portfolio grain, direct/look-through 계약 |
| `docs/PYKRX_PDF_FINDINGS.md` | holdings v2 수집 단계 | 2026-08-29 수집 관측을 provenance 연구 기록으로 재작성 | source snapshot과 한계 표기 |

## C — 가져오지 않는 파일

- `README.md`, `uv.lock`
- `src/canna/__init__.py`, `cli.py`, `contracts.py`, `evaluation.py`, `priority.py`
- `src/canna/catalog.py`를 실행 정본으로 사용하는 방식
- `src/canna/planning.py`와 `runtime.py`의 기존 전체 구현
- `tests/test_contracts.py`, `test_evaluation_35.py`, `test_priority_13_real_data.py`,
  `test_hcx_live.py`
- `tests/test_paraphrases.py`의 기존 실행 방식
- `scripts/verify_pykrx_pdf.py`
- `docs/API_CONTRACT.md`, `BASELINE_AUTHORITY.md`, `CANNA_FOUNDATION.md`,
  `COMPETITION_CONTEXT.md`, `DOCUMENT_CONTROL.md`, `OPERATING_STATE.md`,
  `QUESTION_STRUCTURE.md`
- `docs/baseline/` 전체
- 과거 package wrapper, 과거 validation 결과, 생성된 Stage 4 output

## D — 선행 결정까지 보류하는 파일·자료

- `src/canna/catalog.py`의 physical field binding 자료
- `src/canna/data.py`의 QueryCompiler, Repository와 네 개 entity view
- `scripts/build_holdings_bundle.py`
- `ontology/common.ttl`, `bond_kr.ttl`, `etf_kr.ttl`, `etf_gl.ttl`, `fund_pub.ttl`
- `tests/test_catalog_bindings.py`, `tests/golden_15.json`
- `tests/test_paraphrases.py`의 질문 문자열과 기존 35개 질문 문자열
- `docs/COLUMN_REGISTRATION_PLAN.md`
- `docs/ontology/FIBO_ALIGNMENT.md`, `NAMESPACE_IRI_RULES.md`, `ONTOLOGY_DESIGN.md`,
  `RDB_ONTOLOGY_MAPPING.md`
- `docs/reference/gptwork_20260827/data_assessment/`의 분석 결과
- `docs/reference/gptwork_20260827/project_questions/`의 질문·요구 매핑
- `docs/reference/gptwork_20260827/reproducibility/stage4/`의 분석 코드

## 단계 시작 시 확인 양식

```text
현재 단계:
이번 단계에서 확인할 A/B source:
새 저장소에서 새로 작성할 destination:
가져오지 않을 과거 책임:
선행 계약이 없어 계속 D로 둘 항목:
source 상태와 SHA-256 확인:
```
