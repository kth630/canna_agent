# Question Structure

## 1. 목적

이 문서는 Canna가 질문을 어떤 의미 단위로 회계하는지와 테스트 질문을 어떤 원칙으로
만드는지 정의한다. 특정 평가문항의 답, 지원 상태, DB column, SQL, Tool 계획을 정의하지
않는다.

예시는 구조를 설명하기 위한 비권위 자료다. 예시 문자열이나 ID를 런타임 분기와 고정
계획에 사용하지 않는다.

## 2. 기본 의미 단위

### Target

조건 적용과 요구 수행의 대상 또는 대상 집합이다. Target은 table, column, row 같은
물리 DB 단위가 아니다. 하나의 질문에는 하나 이상의 상품군, 상품, security 또는
계산된 집합이 Target이 될 수 있다.

### Condition

Target에 포함될 대상을 선별하는 제약이다. 수치 비교, 범위, 포함, 관계, 기간,
status 등이 될 수 있다. 관계 조건의 예는 “삼성전자를 직접 보유한 국내 ETF”다.

### Requirement

선별된 Target으로 사용자가 만들어 달라고 한 결과 단위다. 목록, 속성 조회, count,
aggregation, ranking, grouping, comparison, explanation 등이 될 수 있다.

한 목록에서 상품명·수익률·순자산을 함께 보여 달라는 것은 보통 하나의 Requirement와
여러 output field다. “상위 10개 목록과 전체 평균”은 서로 다른 두 Requirement다.

### Relationship

서로 다른 entity type 사이의 의미 관계다. `Product directly holds Security`,
`Fund class maps to Portfolio`, `Portfolio has look-through exposure to Security`처럼 관계의
방향과 grain이 명확해야 한다. 문자열 포함이나 물리 join 자체는 관계 의미가 아니다.

## 3. 확장 구조

### Nested Structure

내부 결과가 바깥 단계의 대상이나 판단 기준으로 다시 쓰이는 구조다. 예를 들어
“1년 수익률 상위 10개 국내 ETF의 평균 총보수”는 먼저 상위 집합을 만든 뒤 그 집합의
평균을 계산한다. 단순 filter 후 aggregation이나 내부 SQL CTE 사용만으로 Nested가 되지는
않는다.

### Comparison Structure

둘 이상의 Target 또는 계산 결과를 공통 기준으로 대조해 차이·우열·동일성을 판단하는
구조다. 여러 값을 나란히 보여 주는 것만으로는 Comparison이 아니다.

### Multiple Targets and Requirements

질문은 다음 네 기본 조합을 가질 수 있다.

1. 단일 Target + 단일 Requirement
2. 복수 Target + 단일 Requirement
3. 단일 Target + 복수 Requirement
4. 복수 Target + 복수 Requirement

Condition, Relationship, Nested, Comparison은 이 조합과 별도로 내용을 기록한다.

## 4. 명시 requirement와 서버 불변식의 경계

HCX requirement accounting은 질문에 실제로 표현된 요구만 다룬다. 각 explicit
requirement는 원문의 `text_span` 또는 위치 정보와 Runtime View ref에 연결한다.

질문에 text span이 없지만 모든 실행에 필요한 규칙은 서버가 소유한다. 예:

- 상장폐지 또는 listing 종료 대상 제외
- 조건·정렬·비교·집계 지표의 0/결측 제외
- 허용되는 최신 유효 snapshot 선택
- unit, currency, period compatibility 검사
- entity와 relation grain 보존

서버는 이를 항상 적용하고 Evidence의 `applied_rules`에 기록한다. HCX prompt와 서버 양쪽에
같은 규칙을 중복 구현하지 않는다.

## 5. Requirement accounting

각 명시 requirement는 다음 중 하나로 끝나야 한다.

- `mapped`: 허용된 ref와 operation에 연결됨
- `unresolved`: Runtime View에 연결할 후보가 없거나 의미를 지원하지 못함
- `ambiguous`: 서로 다른 의미 후보 중 하나로 결정할 근거가 없음

HCX가 requirement 자체를 누락할 수 있으므로 `unresolved_requirements` 배열만으로 충분하지
않다. 질문의 명시 요구 span 전체가 requirement record 또는 명시적인 non-requirement
판정으로 덮였는지 평가한다. 실행기는 누락·unresolved·ambiguous를 조용히 버리지 않는다.

## 6. 의미가 유일하지 않은 표현

운영 평가 질문은 애매하지 않다는 공식 안내를 기본 전제로 한다. 따라서 일반 기능
테스트도 필요한 기간·단위·대상·관계 방향을 명시해 하나의 의미로 결정되게 작성한다.

field gold label은 다음을 구분한다.

- `unique`: 의미상 필요한 field/predicate가 하나로 결정됨
- `equivalent_alternatives`: 의미는 같고 허용되는 물리/semantic 표현이 여러 개임
- `materially_ambiguous`: 서로 다른 사용자 의미가 가능해 결정하면 안 됨

`materially_ambiguous` 질문은 정상 capability 테스트에 넣지 않는다. ambiguity
detection/refusal을 의도적으로 시험할 때만 사용한다.

Runtime View의 인접 field 후보에는 이름만이 아니라 각각의 ref, meaning, period, unit,
currency, grain, source와 적용 가능한 operation을 함께 제공한다.

## 7. 테스트 질문 계약

모든 질문 fixture는 최소한 다음을 포함한다.

```yaml
test_id: runtime_view_field_001
test_purpose: 1년 수익률과 인접 수익률 필드의 구별 확인
capability_under_test: field_grounding
question: 국내 ETF 중 1년 수익률이 높은 상품 10개를 보여줘
question_structure:
  targets: [domestic_etf]
  conditions: []
  requirements:
    - kind: ranking
      metric: return_1y
      direction: descending
      limit: 10
expected_decision: return_1y ref를 선택하고 모든 requirement를 mapped 처리
falsifies_if: 인접 기간 field 선택, requirement 누락 또는 ref 발명
ambiguity_intentional: false
```

의도적 모호성 테스트는 다음처럼 목적과 거부 기대를 명시한다.

```yaml
test_id: ambiguity_period_001
test_purpose: 기간 없는 수익률 요청을 임의 확정하지 않는지 확인
capability_under_test: ambiguity_refusal
question: 국내 ETF 중 수익률이 높은 상품을 보여줘
expected_decision: refused
expected_reason: ambiguous
ambiguity_intentional: true
falsifies_if: 특정 수익률 기간을 임의 선택해 실행
```

35개 평가 예상 질문을 가져올 때도 ID와 질문 문자열만 복사하지 않는다. 각 질문의
`test_purpose`, 구조, capability, expected invariant와 falsification condition을 사람이
검토해 붙인 뒤 `non_authoritative_test_example`로만 등록한다. 같은 구조의 paraphrase,
인접 field, 관계 방향, coverage boundary를 추가 생성해 특정 문장 암기를 막는다.

## 8. 분류 순서

1. explicit text span을 식별한다.
2. Target과 단일/복수를 기록한다.
3. Condition과 Relationship을 내용 단위로 기록한다.
4. Requirement와 output field를 구분한다.
5. Nested 결과 재사용을 기록한다.
6. Comparison 대상·공통 기준·판단을 기록한다.
7. 의미가 `unique`, `equivalent_alternatives`, `materially_ambiguous` 중 무엇인지 표시한다.
8. 서버가 별도로 적용할 implicit invariant를 구분한다.
