# 긴급회의 상태 보고 — Claude 병렬 작업 중단 시점

> **문서 상태:** 이 문서는 중단 시점 snapshot이며 현재 작업 지시가 아니다. 재개 시에는
> `DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md`와 갱신된 A~F 프롬프트를 우선한다.

## 보고 목적

Claude 세션이 중단된 시점의 A~E worktree를 읽기 전용으로 점검해, 9시 재개 전 현재
진척·검증 수준·즉시 조치·통합 금지선을 기록한다. 이 문서는 아키텍처 또는 계약을
변경하지 않는다.

## 한 줄 결론

다섯 트랙 모두 게이트와 상당한 초안 코드를 만들었으나, **어느 트랙도 완료·커밋·handoff
상태가 아니다.** 현재는 untracked 작업물로만 존재하므로 삭제·checkout·worktree 재생성 없이
그 worktree에서 이어서 작업해야 한다.

## 기준점과 보존 상태

- 공통 기준 commit: `c98e00e` (`docs: add Claude parallel work prompts`)
- A~E branch는 모두 아직 `c98e00e`에 머물러 있다. Claude 변경은 커밋되지 않았다.
- 각 worktree에는 해당 트랙의 새 파일만 untracked 상태다. tracked 파일 수정은 관측되지 않았다.
- 원본 대조:
  - A worktree의 `data/official_raw/` 8개 파일과 메인 원본의 SHA-256이 모두 일치한다.
  - D worktree의 `data/incoming/` ZIP 1개와 메인 원본의 SHA-256이 일치한다.
- 원격 NCP 접속·배포·파일 전송·서비스 재기동·ACG 변경은 수행되지 않았다.

## 트랙별 상태

| 트랙 | 중단 시점까지 만든 것 | 확인된 검증 | 9시 첫 작업 | 판단 |
|---|---|---|---|---|
| A — 공식 자료 준비 | 공식 Excel 검증·정리·저장 코드, 국내 ETF 정의 초안, Execution Catalog 초안, `GATE.md` | 새 모듈 import만 성공. 새 테스트 파일·실제 build·`FINDINGS.md`·`HANDOFF.md` 없음. 정적 검사 3건 실패. | 테스트를 먼저 추가하고, 공식 Excel build를 실제 실행해 hash·재현성·catalog를 확인한다. | 작성 중, 검증 전 |
| B — 질문 해석/검증 | 후보 화면, semantic query 구조, 검증·방향 판정·span 처리 코드, `GATE.md` | 새 모듈 import만 성공. 새 테스트·`FINDINGS.md`·`HANDOFF.md` 없음. `compiler/`에는 설명 파일만 있고 plan 생성 구현은 확인되지 않았다. 정적 검사 1건 실패. | logical plan 생성부와 구조 테스트를 완성한다. A/C와의 공유 형식은 제안만 남긴다. | 작성 중, 핵심 일부 미완성 |
| C — 상품 찾기/근거 | 주입형 상품 조회, DuckDB 실행, 근거 모델, synthetic 테스트, `GATE.md` | 28개 중 27개 통과, 1개 실패. 정적 검사 1건 실패. `FINDINGS.md`·`HANDOFF.md` 없음. | 테스트 fixture의 허용 작업과 ranking 기대가 어긋난 문제를 해결하고 전체 테스트를 통과시킨다. | 가장 가까운 기능 초안, 실패 수정 필요 |
| D — ETF 보유종목 | holdings v2 build·관계 조회·coverage/as-of/식별자 상태 코드, `GATE.md` | 새 모듈 import만 성공. script entrypoint·새 테스트·`FINDINGS.md`·`HANDOFF.md` 없음. 정적 검사 1건 실패. | 테스트와 builder 실행 경로를 추가하고, 실제 ZIP build를 실행해 ETF 관계 결과를 검증한다. | 작성 중, 검증·실행 진입점 미완성 |
| E — 배포 점검 | endpoint 계약 probe, latency/concurrency 도구, secret 검사, 배포 선택지 문서·template, 테스트, `GATE.md` | deployment 테스트 38개 통과. 정적 검사 오류 없음. 원격 실행 없음. `FINDINGS.md` 없음. | 로컬 API에 probe를 실제 실행하고 latency/concurrency 테스트를 보강한다. 원격 변경은 승인 전 금지. | 가장 안정적, 로컬 검증 마무리 단계 |

## 확인된 실패와 품질 이슈

### C의 테스트 실패

`tests/product/test_product_execution.py::test_ranking_over_complete_coverage_is_supported`가 실패했다.
테스트는 `field.flag`로 순위를 기대하지만, 그 테스트 binding은 `field.flag`에 `order`를
허용하지 않는다. 현재 실행기는 의도대로 이를 거부한다. 즉 실행기 오류인지 fixture 선언
오류인지 먼저 판정해 둘 중 하나를 일관되게 고쳐야 한다.

### 정적 검사 오류

- A: 불필요한 `noqa` 2건, 중첩 `if` 1건
- B: 오래된 `Union[...]` type annotation 1건
- C: 중첩 `if` 1건
- D: context manager 반환 type annotation 1건
- E: 없음

이 오류는 자동 형식 정리 수준이지만, 각 트랙의 수용 기준인 정적 검사를 통과하지 못하게 한다.

## 지금 하지 말아야 할 일

- untracked 파일을 정리하거나 새 worktree를 만들지 않는다.
- A~E 변경을 메인 branch에 부분 복사하거나 병합하지 않는다.
- B/C의 공유 요청 형식, C/E의 외부 응답 형식, A/D의 Registry 연결을 지금 확정하지 않는다.
- 공모펀드 보유종목을 이름만으로 확정하거나, 불완전한 자료에서 전체 순위·전체 개수·부정 답을 만들지 않는다.
- E가 사용자 승인 없이 원격 서버에 접속하거나 배포하지 않는다.

## 9시 재개 순서

### 1. 다섯 Claude 세션 모두 같은 worktree에서 재개

각 세션 첫 문장:

```text
이전 세션이 중단됐다. 현재 worktree의 untracked 작업물을 보존하고,
GATE.md와 이 파일을 읽은 뒤 아래 "9시 첫 작업"만 수행해라.
완료·커밋·병합을 주장하지 말고 실제 검사 결과와 FINDINGS.md/HANDOFF.md를 남겨라.
```

### 2. 우선순위

1. E: 로컬 probe와 38개 테스트를 다시 확인해 배포 전송 경계를 먼저 고정한다.
2. C: 단일 실패를 해결하고 synthetic query/Evidence core를 green으로 만든다.
3. A: 실제 공식 Excel build와 최소 Catalog를 검증해 C/B가 쓸 실제 자료 기반을 만든다.
4. B: logical plan 생성과 fail-closed 테스트를 완성한다.
5. D: actual holdings build와 ETF 양방향 관계 테스트를 완성한다.

이는 우선순위일 뿐 순차 작업 명령은 아니다. E/C/A/B/D는 서로 다른 worktree에서 동시에
재개한다. 다만 C의 실제 공식 자료 연결은 A의 `HANDOFF.md`가 freeze되기 전에는 시작하지 않는다.

### 3. 각 트랙의 완료 보고 최소 요건

- `FINDINGS.md`: 바뀐 책임, 일반화 단위, 실제 명령·결과, 남은 데이터 한계
- `HANDOFF.md`: 다른 트랙에 필요한 입력/출력 제안. 공유 계약으로 확정하지 않음
- 해당 새 코드의 unit/structural test
- 정적 검사, architecture guard, `git diff --check`
- worktree 안에서만 commit 후보를 제시. 병합은 Codex 감사 후 별도 결정

## 다음 통합 회의의 판정 기준

다음 네 가지가 모두 충족될 때에만 Batch 2 통합 논의를 시작한다.

1. A가 실제 공식 Excel에서 재현 가능한 최소 store와 Catalog를 만들고 검증했다.
2. B가 질문 해석 결과를 physical SQL 없이 logical plan으로 만들고 오류를 멈출 수 있다.
3. C가 그 plan과 binding을 받을 수 있는 query/Evidence core를 모든 자체 테스트 통과 상태로 만들었다.
4. D/E가 관계 결과와 서비스 점검 결과를 각각 독립적으로 검증했다.

현재는 이 기준을 충족하지 않았으므로, 9시 회의의 목표는 병합이 아니라 **각 트랙을
검증 가능한 완료 후보로 바꾸는 것**이다.
