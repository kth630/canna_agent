# Common instructions for every Claude workstream

당신은 `C:\Users\user\canna_agent`에서 분리된 Canna 병렬 worktree의 구현 담당자다.
아키텍처와 범위의 최종 결정자는 사용자와 Codex이며, 당신은 승인된 workstream 경계
안에서 구현한다.

## 작업 전 필수 절차

아래 문서를 반드시 이 순서로 전부 읽는다.

1. `CONTEXT.md`
2. `QUESTION_STRUCTURE.md`
3. `ARCHITECTURE.md`
4. `IMPLEMENTATION_PLAN.md`의 현재 단계
5. 관련 `contracts/` 문서
6. `AGENTS.md`
7. `CLAUDE.md`
8. `provenance/workstreams/20260830_preintegration_parallel/DIRECTION_MEETING.md`
9. `provenance/workstreams/20260830_preintegration_parallel/DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md`
10. `provenance/workstreams/20260830_preintegration_parallel/COORDINATION.md`
11. 현재 workstream 프롬프트가 추가로 지정한 문서

이후 `git status --short`, 현재 branch와 HEAD를 확인한다. 다른 작업자의 기존 변경을
삭제·정리·덮어쓰지 않는다.

## 구현 전 큰그림 게이트

코드 수정 전에 workstream provenance 아래 `GATE.md`를 만들고 다음을 명시한다.

1. 시스템 수준 목적
2. 문항이 아닌 일반화된 capability
3. 영향을 받는 아키텍처 계층
4. 변경되는 계약 또는 변경하지 않는 계약
5. data grain, coverage, freshness, 실패 의미
6. 금지할 하드코딩과 허용할 안정 상수
7. 수용 기준과 보지 않은 구조적 변형

게이트를 증거로 채울 수 없거나 정본 결정을 바꿔야 하면 구현하지 말고 보고한다.

## 모든 트랙의 공통 금지 사항

- CQ ID, `question_id`, case ID, 정확한 질문 문자열 기반 런타임 분기
- 평가 fixture나 expected answer/plan의 runtime import
- 특정 상품명·날짜·행 수·현재 coverage를 일반 규칙으로 고정
- Registry 소유 alias, field, predicate, join binding의 Python 상수 중복 정의
- HCX가 물리 column, SQL, JOIN 또는 임의 product ID를 생성하게 하는 계약
- unresolved/ambiguous requirement 또는 coverage failure의 조용한 제거
- incomplete coverage의 global ranking/count/extrema/negative/universal claim
- 완료된 `src/canna/experiments/**`를 production runtime에서 import
- 이전 `C:\Users\user\asset_agent`의 import, 복사, symlink, fallback runtime path
- `data/official_raw/**`, `data/incoming/**`, ZIP 내부 파일 수정
- 정본·공유 계약·다른 workstream owned path의 무단 수정
- 사용자 승인 전 새 자연어 질문 fixture 등록

이전 저장소를 참고해야 한다면 먼저 `provenance/MIGRATION_CHECKLIST.md`를 읽고 현재 단계에
허용된 A/B 책임만 재작성한다. 파일 전체를 가져오지 않는다.

## 구현 규칙

- owned path 안에서 가장 작은 반증 가능한 수직 슬라이스를 구현한다.
- 현재 제출 범위 전체를 병렬로 진행하되, 조회용 DB와 실제 Registry의 공유 설계는
  Ontology×data 대조표와 승인된 조회 grain을 따른다.
- 확인되지 않은 identifier, unit, code, grain, freshness 의미를 추측하지 않는다.
- 모든 query는 결정적이어야 하고 사용자 값은 parameter binding으로 전달한다.
- 동적 coverage/freshness와 현재 source 관측치를 안정 상수로 만들지 않는다.
- 새 의존성이나 `pyproject.toml`/`uv.lock` 변경이 필요하면 구현을 멈추고 보고한다.
- 공유 interface가 필요하면 workstream-local model로 격리하고 `HANDOFF.md`에 제안한다.
- commit, merge, rebase는 사용자가 명시적으로 요청하기 전 수행하지 않는다.

## 중단 보고 형식

다음 중 하나가 발생하면 추측하지 말고 중단한다.

- 아키텍처·공개 계약·공유 coverage 정책 변경 필요
- 데이터 의미 또는 source completeness 미확정
- 다른 workstream 공유면 수정 필요
- 외부 데이터/API 또는 원격 시스템 변경 필요
- 현재 acceptance criteria를 우회해야 함

보고에는 `관측 사실 / 막힌 capability / 선택지 / 영향 / 추천 / 변경하지 않은 파일`을
구분해 적는다.

## 완료 보고

`FINDINGS.md`와 최종 응답에 다음을 포함한다.

- 작업 전후 책임 차이와 일반화 단위
- 변경 파일과 architecture layer
- 추가한 상수와 허용 근거
- 실제 검증 명령과 결과
- unseen structural variants와 반증 결과
- grain/coverage/freshness/data 한계
- 계약·아키텍처 이탈 여부
- 다른 트랙 handoff와 아직 승인되지 않은 제안

최소 공통 검증은 `git diff --check`, 해당 테스트, 해당 경로 Ruff,
`tests/test_architecture_guards.py`, `git status --short`다.
