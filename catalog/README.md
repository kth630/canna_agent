# Data Catalog 입력

이 디렉터리는 조회용 DB build와 Execution Registry가 읽는 **데이터 파일**이다. alias,
field, predicate, join 정보를 Python 상수로 중복 정의하지 않기 위해 여기에만 둔다.
의미(semantic) 자체는 `ontology/`가 소유하고, 이 파일들은 semantic ID를 참조만 한다.

| 파일 | 소유하는 결정 |
|---|---|
| `product_families.csv` | 상품군 ↔ 공식 table ↔ 외부 holdings 상품군, 결과 grain, 공식 key, 외부 조인 key, portfolio 식별자 scheme, 보유내역 기준일의 역할(요청/실효)과 그 근거 |
| `official_field_bindings.csv` | 공식 field 280개 전수의 역할(identity/identifier/metric/attribute/as_of/unbound), semantic ID, 값 slot, subject grain, 단위·통화·기간, as-of field, 0-D 판정, 충돌 그룹, 사유 |
| `holdings_bindings.csv` | 외부 번들 normalized field 51개의 목적지 table·column과 semantic ID |
| `holdings_relation_rules.csv` | 보유 관측의 관계 종류 판정 규칙과 상위 포트폴리오 추출 위치, 각 규칙의 근거 |
| `identifier_rules.csv` | 식별자 형식 → scheme·해석 상태·Security 승격 여부·검사 알고리즘 |
| `relation_bindings.csv` | 관계 종류 ↔ 정·역방향 semantic predicate, 결과 grain 중복 제거 요구, 사용할 join 경로 |
| `conflict_groups.csv` | 같은 의미의 서로 다른 출처를 비교할 그룹과 충돌 처리 정책 |

## 규칙

- 공식 field는 하나도 빠뜨리지 않는다. 지원하지 않는 field도 `unbound` 역할과 사유를
  남긴다. `tests/test_catalog_contract.py`가 0-D field 전수 목록과 대조한다.
- `semantic_id`가 온톨로지에 없거나 grain·단위·기간·연산·통화 정책이 어긋나면
  Execution Registry build가 실패한다.
- 값 의미가 확인되지 않은 코드(여부 flag의 극성, text 보수율의 단위 등)는 원문을
  보존하고 `meaning_status`로 표시하되, 그 값을 근거로 서버 invariant를 만들지 않는다.
- 특정 상품명·날짜·행 수·현재 coverage 수치는 이 디렉터리에 쓰지 않는다. 관측값은
  build가 측정해 `data/processed/data_catalog.json`에 기록한다.

## 산출물

build는 물리 table 26개(원본 mirror 8 + 파생 18)를 가진 store와 Data Catalog를 만든다.
기존 산출물 위에 바로 쓰지 않고 같은 디렉터리의 임시 파일에 만든 뒤 검증을 통과한
경우에만 교체하므로, 실패한 build는 직전 산출물을 훼손하지 않는다. store와 catalog는
같은 `build_id`를 가진 하나의 generation으로 함께 교체되며, Registry build는 두 값이
어긋나면 거부한다.

## 재생성

```powershell
uv run python scripts/build_query_store.py
uv run python scripts/build_registries.py
```
