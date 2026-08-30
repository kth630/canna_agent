# 0-D 전수성·무결성 증거

## 재현 명령

```powershell
uv run python scripts/audit_0d_inventory.py
```

2026-08-30 실행 결과:

```json
{
  "official_field_rows": 280,
  "official_source_rows": 4,
  "ttl_term_rows": 298,
  "holdings_member_rows": 29,
  "holdings_normalized_field_rows": 51,
  "holdings_coverage_rows": 3,
  "holdings_manifest_file_rows": 28,
  "holdings_manifest_mismatches": 0
}
```

스크립트는 공식 workbook을 `read_only=True, data_only=True`로 읽어 schema header와 data
header의 순서를 비교하고 모든 field의 nonblank/zero-like 관측을 기록한다. ZIP은 임시
디렉터리로 normalized parquet만 복사해 schema를 읽고 즉시 삭제한다. 원본 Excel·ZIP에는
write하지 않으며 DB·Registry·Ontology·runtime binding을 만들지 않는다.

## 생성물과 전수 조건

| 생성물 | 전수 조건 | 결과 |
|---|---|---|
| `generated/ttl_term_inventory.csv` | TTL 5개에서 선언된 모든 named Class, ObjectProperty, DatatypeProperty, MetricType, NodeShape. ValueStatus, IdentifierScheme, AnnotationProperty도 추가 포함 | 298 rows; 각 row에 `audit_status`, `evidence`, `unresolved_reason` 존재 |
| `generated/official_source_inventory.csv` | 공식 table ID 4개와 data/schema workbook 8개 | 4 rows; source-row grain, identifier 후보, as-of field와 hash 기록 |
| `generated/official_field_catalog.csv` | schema field와 data header가 같은 순서로 일치하는 모든 공식 field | 280 rows; 각 row에 schema type/comment, nonblank/zero-like 관측, legacy candidate 여부, semantic binding 상태 기록 |
| `generated/holdings_bundle_member_inventory.csv` | ZIP의 실제 file member 전부 | 29 rows. 내부 `MANIFEST.json`은 자기 자신을 제외한 28 파일 hash를 싣고, catalog는 MANIFEST 자체까지 hash 기록한다. |
| `generated/holdings_normalized_field_catalog.csv` | normalized parquet 4개의 모든 field | 51 rows; mapping/holding/coverage/failure의 source-row grain과 semantic binding 상태 기록 |
| `generated/holdings_coverage_rows.csv` | normalized coverage parquet의 모든 row | 3 rows |

`ttl_term_inventory.csv`의 298개 선언은 중복 0이며 `audit_status` 빈 값 0이다. `official_field_catalog.csv`의
280개 `(table_id, field)`는 중복 0이며 semantic binding 상태 빈 값 0이다. 이는 term과 field가
대표 표본만 기록된 것이 아니라 전수 record를 가진다는 검사다.

요청한 TTL 선언 유형의 분포는 Class 66, ObjectProperty 47, DatatypeProperty 47, MetricType
100, NodeShape 20으로 합계 280개다. 여기에 audit 누락을 막기 위해 IdentifierScheme 11,
ValueStatus 6, AnnotationProperty 1도 포함해 총 298개 row를 기록했다.

## 입력 hash

아래 값은 `generated/audit_evidence.json`에도 machine-readable로 기록되어 있다.

| 입력 | SHA-256 |
|---|---|
| `prbd01n001_data.xlsx` | `574ae5d6c1d98704712c256ed5352cbaed065ea9c3a6eb7b2a52adb305fa9001` |
| `prbd01n001_schema.xlsx` | `9965126695066f9dc07951a78054e9e7639b6863d1ad2a9616f7e2d8fcadbc4f` |
| `pref01n001_data.xlsx` | `18c4329d8fc8768d030316816f3e6e48226a3c217db3354245b766a2c6f6c592` |
| `pref01n001_schema.xlsx` | `2135081fd8107760d127915147032987ee1d9e7c2ed039665ae4214b96faec5a` |
| `pref02n001_data.xlsx` | `ca6a274aeaf3f884f2f7635d7802558bc6dabf408871ecb1f71e5a50d9d34067` |
| `pref02n001_schema.xlsx` | `32ac732f0501f4ab518682175fecc50756ee1eafde9296801f139d62559b5e64` |
| `prfd01n001_data.xlsx` | `81b3ce3f1d5042b32fd52a76acff094fc5b8dd9fa36289af2fb54c195eb5d94c` |
| `prfd01n001_schema.xlsx` | `cfe7be44cbcd9ce349206776a4eb46996162643acbf3ca5a4f74c2886394862b` |
| `holdings_20260829.zip` | `93fc5f2c4c4ee00fe3bf7ac74bade43beb546b7eb36df3cfce4d5cac3d247a29` |
| legacy `common.ttl` | `fecbda8a67b530c1b3bef71e05bc719554201e5410f3529f0850ff6f380570f6` |
| legacy `bond_kr.ttl` | `97035e2e0e8ff7873e25c3e3a4f08d69c7a7c460624b6255f8a8cdb709ede245` |
| legacy `etf_kr.ttl` | `1155718204de3e1cceceafc7418d4e83c72d4511c6b2c297a263b050b492dc66` |
| legacy `etf_gl.ttl` | `76f24892f74cddcc20cb59ed49cf80aa4f2409b1f6312c7ff948243b9cbfbeef` |
| legacy `fund_pub.ttl` | `2eaa80a3c83116615f79832e93214ed961a5537415089e8f15ece6cb5644f1d9` |
| legacy `RDB_ONTOLOGY_MAPPING.md` | `964d85c959810ee9fe7d4a958c7a824afb2c4a2839cf3c19555c42d5e811c53e` |

## 검증 명령

```powershell
# generated catalog 전수성·input hash·ZIP 내부 MANIFEST를 다시 읽기 전용으로 검증한다.
.\.venv\Scripts\python.exe scripts\audit_0d_inventory.py --verify

# provenance 문서의 trailing whitespace와 tracked diff 형식 점검
rg -n '[ \t]+$' provenance/workstreams/20260830_preintegration_parallel/ontology_data_alignment
git diff --check
```

검증 결과는 status/binding 공란 0, term 중복 0, official `(table_id, field)` 중복 0이었다.
`git diff --check`은 오류 없이 종료했다. 기존 사용자 변경 파일의 CRLF 경고는 이 감사가
수정하지 않은 파일에 대한 Git 경고이며 whitespace error가 아니다.
