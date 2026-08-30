# Claude prompt — D: holdings and relationship execution

`COMMON.md`의 모든 지시를 적용하라. 당신은 workstream D 담당자다.

## 목표와 경계

Product/class→Portfolio→Portfolio Observation→Security grain을 보존하는 holdings v2와,
데이터가 허용하는 ETF 양방향 관계 실행 기반을 만든다. 공모펀드의 미확정 security relation을
억지로 완성하지 않는다. HCX, Runtime View, Product metric, 공개 API와 공유 Registry는
담당하지 않는다.

추가로 읽을 문서:

- `provenance/experiments/stage_0c_data_discovery/FINDINGS.md`
- `provenance/MIGRATION_CHECKLIST.md`
- `provenance/MIGRATION_MANIFEST.json`

## Owned paths

- `src/canna/holdings/**`
- `scripts/build_holdings_v2.py`
- `tests/holdings/**`
- `provenance/workstreams/20260830_preintegration_parallel/d_holdings_relations/**`
- 재현 가능한 생성물 `data/processed/holdings/**`

## Batch 1 구현

1. incoming ZIP hash와 내부 manifest 무결성을 검증하고 안전한 임시 디렉터리에서만 읽는다.
2. Product/class→Portfolio mapping, Portfolio Observation, held-security identifier+scheme/status,
   source call/failure, coverage observation grain을 분리한 deterministic v2 builder를 만든다.
3. requested/effective as-of와 as-of status를 분리한다. 요청일을 실효일로 바꾸지 않는다.
4. direct holding과 look-through exposure를 별도 predicate/status로 보존한다. 근거가 없으면
   unresolved다.
5. 검증된 domestic/overseas ETF 범위에서 product→observed holdings와 resolved
   security→distinct products를 지원한다.
6. 관계 filter가 product metric과 결합될 때 `EXISTS` 또는 product-grain distinct 불변식으로
   logical duplicate를 막는다.
7. placeholder/ambiguous/unresolved identifier는 Security relation으로 실행하지 않는다.
   identifier 모양만 보고 scheme을 확정하지 않는다.
8. 국내 ETF weight는 관계 존재 외 filter/ranking/aggregation capability로 노출하지 않는다.
9. 해외 ETF snapshot과 mapping/filing/parse 실패 원인을 분리한다.
10. 공모펀드는 class→portfolio mapping, source resolution, raw security-name observation,
    direct/look-through 상태를 보존하되 이름 exact/substring match를 검증된 Security relation으로
    승격하지 않는다.
11. D→A relation catalog fragment와 D→C/E relation result handoff를 제안하되 공유 파일은
    직접 수정하지 않는다.

## 수용 기준

- 원본 hash와 manifest 불일치는 fail closed한다.
- requested/effective as-of, identifier scheme/status, direct/look-through가 소실되지 않는다.
- ambiguous source/entity resolution은 구조화된 실패가 된다.
- JOIN 중복이 product count/ranking을 부풀리지 않는다.
- coverage 밖 대상은 false가 아니며 incomplete 결과는 full/current/global이 아니다.
- 공모펀드 이름과 요청일을 검증된 Security/as-of로 변환하지 않는다.

## 검증

- `uv run pytest -q tests/holdings`
- `uv run pytest -q -m real_data tests/holdings`
- `uv run ruff check src/canna/holdings scripts/build_holdings_v2.py tests/holdings`
- `uv run pytest -q tests/test_architecture_guards.py`
- `git diff --check`
- `git status --short`

identifier scheme, source completeness, 공모펀드 entity resolution, 외부 데이터 또는 공유
Registry/Evidence 변경이 필요하면 즉시 중단·보고하라.
