# Workstream C Execution Registry 확장 제안

상태: 제안 전용. 현재 `execution_registry.json`, generator, shared schema는 수정하지 않는다.

## 목적

Product execution이 물리 이름 추론이나 Registry summary의 row 값 전용 없이 실제 observation
row에서 provenance와 effective snapshot을 검증하게 한다. 이 선언이 없는 binding은
`provenance_binding_unavailable` 또는 `selection_policy_unavailable`로 실행을 막는다.

## Field binding 확장

각 executable field binding에 다음 구조가 필요하다.

```json
{
  "row_binding": {
    "subject_column": "<registry-allow-listed identifier>",
    "source_id_column": "<registry-allow-listed identifier>",
    "source_row_id_column": "<registry-allow-listed identifier>",
    "effective_as_of_column": "<registry-allow-listed identifier>",
    "value_status_column": "<registry-allow-listed identifier>",
    "valid_value_status": "<parameter-bound value>"
  },
  "selection_policy": {
    "kind": "unique_per_subject | latest_effective_as_of",
    "snapshot_policy": "single_effective_date"
  }
}
```

- `max_observations_per_subject=1`이면 `unique_per_subject`를 선언하고 실행 결과에서도 실제
  subject 중복이 없는지 검증한다.
- 1보다 크면 `latest_effective_as_of`처럼 Registry가 승인한 결정적 선택 정책과
  `source_row_id_column` tie-break를 사용한다.
- display와 order field 모두 동일 계약을 가져야 한다. `requested_as_of`는 두 observation
  CTE에 각각 parameter binding한다.
- 실제 row의 `source_id`, `source_row_id`, `effective_as_of`를 typed result에 보존한다.
- source ID는 `data_catalog.sources`의 명시적 ID와 연결하고 hash 존재 및 일치를 검증한다.
  physical source table 이름에서는 source ID를 추론하지 않는다.

## Dataset population binding 확장

field family 일치와 별도로 family/grain의 실제 모집단 binding이 하나 존재해야 한다.

```json
{
  "dataset_bindings": [
    {
      "family_id": "<stable family id>",
      "subject_grain": "product | product_class",
      "population": {
        "subject_total": 0,
        "coverage_status": "full | partial",
        "unknown_coverage": false,
        "missing_subjects": 0,
        "parse_failed_subjects": 0,
        "collection_failure_count": 0,
        "unknown_coverage_count": 0
      }
    }
  ]
}
```

`FULL`은 dataset population과 field coverage가 모두 `full`을 명시하고, unknown 상태가
false이며, 누락·parse failure·collection failure·unknown coverage가 명시적 0이고,
실제 observed subject count가 검증된 subject total과 같을 때만 허용한다. metadata 부재는
0으로 간주하지 않는다.

## 현재 readiness

현재 실제 Registry에는 위 row-level provenance/as-of, selection policy와 dataset population
binding이 없다. 기존 Registry와 DuckDB의 물리 queryability는 diagnostic으로 확인할 수 있지만,
Workstream C production execution은 `unavailable`이 정답이다.
