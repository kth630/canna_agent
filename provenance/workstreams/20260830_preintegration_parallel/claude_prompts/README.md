# Claude parallel work prompts

이 디렉터리는 2026-08-30 방향 회의에서 승인된 A~E 병렬 작업을 Claude에 맡길 때
사용하는 실행 프롬프트다. 각 Claude 세션은 독립 worktree에서 실행하며 자기 프롬프트와
`COMMON.md`를 함께 따른다.

## 실행 순서

### Batch 1 — 독립 기반 작업

- A: 공식 데이터의 최소 파생 적재와 Execution Catalog slice
- B: 실제 field 상수에 의존하지 않는 Runtime View/semantic validation/logical compiler
- C: synthetic DuckDB 기반 Product query와 Evidence core. A의 실제 schema를 추측하지 않음
- D: ETF 중심 holdings v2와 관계 실행 기반. 공모펀드 security relation은 unresolved로 분리
- E: transport-only API의 로컬 배포·검증 기반. 원격 변경과 A~D 통합은 승인 전 수행하지 않음

### Batch 2 — freeze된 handoff를 이용한 첫 수직 슬라이스

1. A의 store/catalog handoff를 C와 B가 소비한다.
2. B의 logical plan handoff를 C adapter에 연결한다.
3. C의 Evidence handoff를 E의 `Responder` seam에 연결한다.
4. D의 ETF relation result를 C/E에 연결한다.

Batch 2는 각 owner의 `FINDINGS.md`와 `HANDOFF.md`를 Codex가 감사하고 integration window를
승인한 뒤 별도 프롬프트로 수행한다.

## 공유면 단일 소유

| 공유면 | owner |
|---|---|
| 정본 문서, `contracts/`, `AGENTS.md`, `CLAUDE.md` | 사용자 + 메인 Codex |
| Execution Catalog/Registry 생성 | A |
| Runtime View, semantic validation, logical plan | B |
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
