# AGENTS.md

이 저장소의 아키텍처 정본은 `ARCHITECTURE.md`다. 모든 작업자는 아래 순서로 필요한
문서를 읽은 뒤 작업한다.

1. `CONTEXT.md`
2. `QUESTION_STRUCTURE.md`
3. `ARCHITECTURE.md`
4. `IMPLEMENTATION_PLAN.md`의 현재 단계
5. 관련 `contracts/` 문서

이전 저장소 `C:\Users\user\asset_agent`의 문서나 코드는 참고 자료일 뿐 이 저장소의
결정을 덮어쓸 수 없다.

## 역할

- 사용자: 목표·범위·아키텍처의 최종 결정자다.
- Codex: 사용자와 함께 아키텍처를 정리하고, 작업을 분해·조율하며, 구현 결과의
  일반화·계약·하드코딩·아키텍처 이탈을 검수한다.
- Claude: 승인된 계약과 단계에 따라 주로 코드를 작성한다. 아키텍처, 데이터 의미,
  coverage 정책 또는 계약을 임의로 바꾸지 않는다.

결정이 필요한 경우 Claude는 구현을 멈추고 사용자와 Codex에 선택지·영향·근거를
보고한다. Codex도 승인된 큰그림 없이 국소 구현부터 시작하지 않는다.

## 구현 전 큰그림 게이트

코드를 수정하기 전에 다음을 짧게라도 명시한다.

1. 시스템 수준 목적
2. 문항이 아닌 일반화된 capability
3. 영향을 받는 아키텍처 계층
4. 변경되는 계약
5. 데이터 grain·coverage·freshness·실패 의미
6. 금지할 하드코딩과 허용할 안정 상수
7. 수용 기준과 보지 않은 변형 질문

이 항목이 답해지지 않으면 구현하지 않는다. 사용자는 언제든
`구현 전에 큰그림 게이트부터`라고 요구해 구현을 중단시킬 수 있다.

## 금지 사항

- CQ ID, `question_id`, case ID 또는 정확한 평가 질문 문자열로 런타임 분기
- 평가 fixture, expected answer, 현재 35문항 상태를 런타임에서 import
- 특정 상품명·날짜·행 수·현재 coverage를 일반 규칙으로 고정
- Registry가 소유해야 할 alias, field, predicate, join binding을 Python 상수로 중복 정의
- HCX가 물리 컬럼명, SQL, JOIN 또는 임의 ID를 생성하게 하는 계약
- unresolved/ambiguous requirement를 버리고 실행
- incomplete coverage에서 global top-k, count, max/min 또는 부정·보편 명제를 완전한
  결과처럼 주장
- 이전 저장소를 import, symlink, fallback path 또는 상대 경로로 런타임 연결
- 원본 Excel이나 수집 ZIP 내부 파일 수정

허용되는 안정 상수는 공식 API field, 공식 table ID, 검증된 source hash, 격리된 테스트의
expected value, Registry에서 생성된 stable enum뿐이다.

## 테스트 질문 규칙

테스트 질문은 답이나 제품 사양이 아니다. 모든 테스트 질문에는 최소한 다음이 있어야 한다.

- `test_purpose`
- `capability_under_test`
- 질문 구조와 명시 requirement
- `semantic_clarity: explicit`
- expected decision 또는 invariant
- 실패 시 무엇을 반증하는지

모든 테스트 질문은 의미가 유일하게 결정되도록 작성한다. 애매한 자연어 질문은 어떤
fixture에도 등록하지 않는다. `ambiguous`는 candidate grounding 또는 source resolution이
결정되지 않을 때 서버가 임의 실행을 막기 위한 런타임 상태다. 평가 질문 35개를 고정 답·고정
계획·런타임 분기의 근거로 쓰지 않는다.

## 데이터와 변경 규칙

- `data/official_raw/`와 `data/incoming/`은 읽기 전용 원본이다.
- 원본에서 파생한 데이터는 별도 경로에 재현 가능하게 생성한다.
- 확인되지 않은 의미·단위·코드값·source completeness는 추측하지 않는다.
- 기존 사용자 변경을 덮어쓰거나 삭제하지 않는다.
- 아키텍처 변경은 사용자와 Codex의 승인이 필요하다.
- 실험 결과는 `IMPLEMENTATION_PLAN.md`의 상태를 바꿀 수 있지만, 자동으로
  `ARCHITECTURE.md`의 확정 결정을 바꾸지 않는다.

## 구현 후 Codex 감사

완료 보고에는 다음을 포함한다.

- 일반화 단위
- 새 하드코딩과 허용 근거
- 보지 않은 변형 질문 테스트
- 계약 및 아키텍처 이탈 여부
- 실제 검증 명령과 결과
- 남은 결정과 데이터 한계
