# 0-D 실제 데이터 × 기존 Ontology 정렬 감사

## 상태와 목적

- 상태: **전수 감사 완료·Codex 재검증 완료(2026-08-30)**. 이 경로는 현재 실제 데이터와
  이전 저장소 Ontology의 차이를 기록하는 provenance이며, 새 Ontology·SHACL·Registry·DB
  계약은 바꾸지 않는다. `uv run python scripts/audit_0d_inventory.py --verify`가
  `status=ok`로 종료했다.
- 목적: 이후 조회 저장소와 두 Registry가 상품, 클래스, 포트폴리오, 종목, 관측을 서로
  다른 단위로 구현하지 않도록 실제 근거와 legacy TBox의 차이를 드러낸다.
- 비목적: 질문 목록을 정하거나, 어떤 질문을 미리 허용·금지하거나, 물리 binding·SQL·Tool을
  구현하는 일. 데이터가 어떤 주장에 충분한지는 실행 시 source·grain·coverage·freshness로
  판정한다.

## 큰그림 게이트

| 항목 | 이번 감사의 답 |
|---|---|
| 시스템 수준 목적 | 근거 기반 상품 조회·비교·설명에서 의미와 결과 grain의 불일치를 막는다. |
| 일반화 capability | source-to-semantic alignment: 실제 source의 entity, metric, relation, observation을 semantic 모델에 안전하게 연결할 수 있는지 감사한다. |
| 영향 계층 | provenance와 향후 Data Catalog/Semantic Registry 설계 입력. Runtime, API, DB, Retriever, Tool, 배포는 변경하지 않는다. |
| 변경 계약 | 없음. `GRAIN_AND_OPEN_DECISIONS.md`의 내용은 사용자·Codex 승인 전 제안이다. |
| grain·coverage·freshness·실패 | 각 대조 행에 source row/result grain, identifier 상태, requested/effective as-of, coverage/failure 근거를 기록한다. |
| 금지 하드코딩 | 현재 상품명·행 수·날짜·coverage, 평가 질문 문자열, legacy physical binding을 runtime 규칙으로 만들지 않는다. |
| 수용 기준 | 네 공식 상품군·세 holdings 상품군·legacy TTL 5개가 대조에 포함되고, 근거 없는 의미는 `unresolved`로 남으며, 질문 제약 없이 grain 결정 후보를 검토 가능하다. |

## 입력과 우선순위

| 입력 | 용도 | 취급 |
|---|---|---|
| `data/official_raw/*_{data,schema}.xlsx` 8개 | 공식 4개 상품군의 field, schema comment, source row, 실제 값 관측 | 읽기 전용 공식 기준선 |
| `data/incoming/holdings_20260829.zip` | holdings mapping/observation/coverage/failure와 raw provenance | 읽기 전용 외부 기준선 |
| `provenance/MIGRATION_MANIFEST.json` | 위 9개 원본의 hash·byte-size 확인 | immutable custody 근거 |
| `provenance/experiments/stage_0c_data_discovery/FINDINGS.md` | 현재 배포본에 대한 read-only profile 및 holdings 관계 관측 | 재현된 관측 근거, 계약 아님 |
| 이전 `ontology/{common,bond_kr,etf_kr,etf_gl,fund_pub}.ttl` | class/property/MetricType/SHACL inventory | B: 읽기 전용 감사만 허용 |
| 이전 `docs/ontology/{FIBO_ALIGNMENT,NAMESPACE_IRI_RULES,ONTOLOGY_DESIGN,RDB_ONTOLOGY_MAPPING}.md` | 이전 의미 선택과 field mapping의 출발점 | B: 자동 승격·복사 금지 |

`DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md`와 현재 `ARCHITECTURE.md`가 위 모든
이전 자료보다 우선한다. 공식 데이터와 외부 데이터가 충돌하면 공식 데이터를 우선하되
충돌을 기록한다.

## 산출물

1. `CROSSWALK.md` — 의미·지표·관계별 legacy 표현과 실제 source 관측의 대조.
2. `GRAIN_AND_OPEN_DECISIONS.md` — 승인할 조회 단위 후보, 식별자/as-of/coverage 상태와
   아키텍처 확정·구현 증거·사용자 결정 항목의 구분.
3. `generated/` — 원본에서 재생성하는 TTL term 전수 목록, 공식 field 전수 catalog, ZIP
   member/normalized-field 목록 및 hash evidence. 생성 명령과 결과는
   `COMPLETENESS_EVIDENCE.md`에 기록한다.

## 판정어의 의미

| 판정 | 뜻 |
|---|---|
| 유지 | legacy 의미가 실제 source와 grain 수준에서 계속 맞는다. 실제 binding은 별도 Registry 단계에서 결정한다. |
| 수정 | 의미 자체는 유효하지만 domain/range/grain/as-of/identifier/shape를 고쳐야 한다. |
| 추가 | 실제 source에 필요한 의미·상태가 legacy TBox에 없다. |
| 제외 | 현재 source binding 또는 이번 제출 범위의 근거가 없다. Ontology에서 즉시 삭제하거나 미래 질문을 금지한다는 뜻은 아니다. |
| 미확정 | source가 의미·단위·식별자·coverage를 충분히 증명하지 않는다. 임의 mapping을 만들지 않는다. |

## 다음 게이트

`ARCHITECTURE.md`가 이미 확정한 product/class–portfolio 분리, requested/effective as-of
분리, direct/look-through 분리, coverage/failure의 독립 상태는 다시 사용자 결정으로 올리지
않는다. 다음 단계의 전제는 이 전수 catalog의 증거 검토이며, 실제 binding·identifier
검증·unit/freshness 관측은 A/D/F가 구현 중 evidence로 확정한다. 현재 alignment에 남은
사용자 결정은 없다.
