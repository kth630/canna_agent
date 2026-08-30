# Claude parallel work prompts

이 디렉터리는 2026-08-30 방향 회의와 이후 데이터·Ontology 정렬 결정에서 승인된 A~F
병렬 작업을 Claude에 맡길 때
사용하는 실행 프롬프트다. 각 Claude 세션은 독립 worktree에서 실행하며 자기 프롬프트와
`COMMON.md`를 함께 따른다.

최신 실행 정본은
`../DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md`다. 기존 A~E 세션을 재개할 때도 최신
프롬프트를 다시 전달하고, worktree에 남은 untracked 작업을 삭제하거나 다시 만들지 않는다.

## 실행 순서

### Batch 0-D — 전체 데이터·Ontology 정렬

- F가 기존 Ontology 5개를 읽기 전용으로 감사한다.
- A와 D가 공식 네 상품군과 현재 외부 holdings 관측을 제공한다.
- 의미·지표·관계별 `유지 | 수정 | 제외 | 추가`와 조회 grain을 사용자·Codex가 승인한다.
- 승인 전에도 각 worktree의 로컬 관측·초안 검증은 계속하되 공유 schema와 stable ID를
  독자 확정하지 않는다.

### Batch 1 — 병렬 구축

- A: 공식 네 상품군의 재현 가능한 조회 store와 Execution Registry 공식 데이터 부분
- B: F Retriever 이후 Runtime View/semantic validation/logical compiler
- C: 전체 상품군 Product query와 Evidence core. 승인 전 physical schema를 추측하지 않음
- D: ETF 중심 holdings v2와 관계 실행 기반. 공모펀드 security relation은 unresolved로 분리
- E: transport-only API의 로컬 배포·검증 기반. 원격 변경과 A~F 통합은 승인 전 수행하지 않음
- F: 새 Ontology/SHACL, Semantic Registry generator, 규칙+embedding Retriever

### Batch 2 — freeze된 handoff를 이용한 통합

1. A/D Execution Registry와 F Semantic Registry의 stable ID·grain 일치를 검증한다.
2. F Retriever output을 B Runtime View/검증에 연결한다.
3. B logical plan을 C/D Tool adapter에 연결한다.
4. C/D Evidence를 E의 `Responder` seam에 연결한다.

Batch 2는 각 owner의 `FINDINGS.md`와 `HANDOFF.md`를 Codex가 감사하고 integration window를
승인한 뒤 별도 프롬프트로 수행한다.

## 공유면 단일 소유

| 공유면 | owner |
|---|---|
| 정본 문서, `contracts/`, `AGENTS.md`, `CLAUDE.md` | 사용자 + 메인 Codex |
| 공식 데이터 Execution Registry 생성 | A |
| 외부 holdings relation/coverage Registry fragment | D |
| Ontology/SHACL, Semantic Registry, Retriever | F |
| Retriever 이후 Runtime View, semantic validation, logical plan | B |
| Product execution, Evidence/claim assembly | C |
| Holdings relation observation/catalog fragment | D |
| 외부 API envelope, packaging, 배포·통합 | E |

다른 owner의 공유면이 필요하면 직접 수정하지 않고 `HANDOFF.md` 또는
`INTERFACE_REQUEST.md`로 관측·선택지·영향·추천을 반환한다.

## 프롬프트 파일

- `A_OFFICIAL_DATA.md`
- `B_SEMANTIC_COMPILER.md`
- `C_PRODUCT_EVIDENCE.md`
- `D_HOLDINGS_RELATIONS.md`
- `E_DEPLOYMENT_INTEGRATION.md`
- `F_ONTOLOGY_REGISTRY_RETRIEVER.md`
