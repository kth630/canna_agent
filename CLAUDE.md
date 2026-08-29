# CLAUDE.md

Claude는 이 저장소의 주 구현자다. 설계와 범위는 사용자와 Codex가 결정하며,
`ARCHITECTURE.md`가 아키텍처 정본이다.

## 작업 전 필수 절차

다음 순서로 읽는다.

1. `CONTEXT.md`
2. `QUESTION_STRUCTURE.md`
3. `ARCHITECTURE.md`
4. `IMPLEMENTATION_PLAN.md`의 현재 단계
5. 관련 `contracts/` 문서
6. `AGENTS.md`

그 뒤 코드에 손대기 전에 아래 형식으로 구현 경계를 보고한다.

```text
목적:
일반 capability:
변경 계층/계약:
data grain·coverage·failure 의미:
금지할 하드코딩:
수용 기준과 unseen variants:
```

## 구현 책임

- 승인된 계약을 가장 작은 수직 슬라이스로 구현한다.
- semantic ID, physical binding, dynamic coverage/freshness의 소유권을 분리한다.
- 검증 실패, unresolved, ambiguous, incomplete coverage를 명시적 결과로 보존한다.
- 서버 불변식과 Evidence를 같은 규칙 정의에서 생성해 서로 어긋나지 않게 한다.
- 변경에 비례한 단위·계약·통합 테스트를 추가한다.

## 임의 판단 금지

다음 상황에서는 멈추고 사용자와 Codex에 보고한다.

- 아키텍처나 공개 계약 변경이 필요함
- 데이터 grain, 식별자 scheme, 기준일 또는 coverage 의미가 불명확함
- HCX provider schema 제약 때문에 semantic 계약 변경이 필요함
- 현재 단계의 acceptance criteria를 우회해야 함
- 특정 평가 질문 전용 분기 없이는 통과하지 못함

보고에는 관측 사실, 가능한 선택지, 각 선택지의 영향, 추천안을 구분해 쓴다.

## 하드코딩 방지

다음을 런타임 코드에 넣지 않는다.

- CQ ID, exact question text, question별 expected plan/answer
- 고정 상품명, 고정 날짜, 고정 row count 또는 현재 coverage 수치
- Registry 밖의 field/predicate/alias/join allowlist
- 평가 fixture import
- 이전 저장소 import 또는 경로 fallback

공식 API field, 공식 table ID, 검증된 hash, 테스트 안의 expected value,
Registry-generated stable enum은 근거를 주석 또는 registry metadata로 남기고 사용할 수 있다.

## 테스트 작성

각 질문 기반 테스트 fixture에는 `test_purpose`, `capability_under_test`, 질문 구조,
명시 requirement, expected decision, falsification condition을 포함한다. 일반 기능을 시험하는
질문은 모호하지 않게 작성한다. 모호성 거부 테스트만 `ambiguity_intentional: true`를 쓴다.

테스트는 CQ별 회귀보다 구조 조합과 unseen paraphrase/field-neighbor/coverage boundary를
우선한다. 실패한 테스트를 통과시키기 위해 질문 문자열을 분기 조건으로 추가하지 않는다.

## 완료 보고

- 변경 전후 책임 차이
- 변경 파일
- 계약과 데이터 의미의 변경 여부
- 실행한 검증의 실제 출력
- 일반화 검증과 unseen variants
- 추가한 상수와 허용 근거
- 남은 결정·위험·범위 밖 문제
