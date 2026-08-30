# 현재 상태와 다음 설계 게이트 — 2026-08-30

## 문서 지위

이 문서는 0-D 전수 감사 완료 직후의 최신 상태를 보존한다. 기존 정본을 자동으로 바꾸지
않으며, 기술세션 원본에서 새로 확인한 요구 방향은 사용자와 Codex가 아키텍처 변경을
승인하기 전까지 `pending reconciliation`로 둔다.

## 완료된 작업

- 공식 네 상품군 Excel 8개와 holdings ZIP 원본 hash가 기준 manifest와 일치한다.
- 공식 schema field 280개를 data header와 순서까지 대조했다.
- legacy Ontology 5개의 named declaration 298개를 전수 목록화하고 각 term에
  `유지 | 수정 | 제외 | 추가/미확정 관련 사유`를 기록했다.
- holdings ZIP member 29개, normalized field 51개와 coverage/failure 구조를 기록했다.
- product, product class, portfolio, security, raw holding observation, metric observation을
  분리했다.
- 기존 7개 미결정 항목을 아키텍처 확정 사항과 구현 중 evidence 사항으로 재분류했다.
  현재 0-D 범위에 남은 사용자 결정은 없다.

재현 명령:

```powershell
uv run python scripts/audit_0d_inventory.py --verify
```

확인 결과:

```json
{"holdings_manifest_mismatches":0,"holdings_member_rows":29,"holdings_normalized_field_rows":51,"official_field_rows":280,"status":"ok","ttl_term_rows":298}
```

## 기술세션 원본에서 새로 확인한 설계 방향

검토 source:

- 파일: `AI페스티벌_기술세션_금융상품Agent_참여자공유용.pdf`
- SHA-256: `7a62878f7a2c2f2c431381320430c36bbb9d4f9f866565c338c57152385cb064`
- 위치: 현재 사용자 Downloads. 저장소로 복사하지 않았으며 source fingerprint만 기록한다.

핵심 관측:

1. Ontology는 개념·규칙의 TBox이고 Knowledge Graph는 실제 인스턴스·관계의 ABox로
   명시적으로 구분된다.
2. 질문을 RDB, Graph, Vector로 routing하고 결과를 검증·통합하는 Federated Query 구조를
   제시한다.
3. Ontology를 설명문이 아니라 runtime grounding과 통제 계층으로 사용한다.
4. Vector 문서 검색은 실제 문서 근거를 찾는 경로다. Semantic Registry 후보 embedding과
   같은 책임으로 합치면 안 된다.

## 현재 아키텍처와의 관계

이미 정렬된 부분:

- HCX가 의미를 구조화하고 서버가 검증·결정적으로 실행한다.
- Ontology/SHACL에서 Semantic Registry를 생성한다.
- 조회용 DB가 수치·필터·집계와 관계 evidence의 source provenance를 보존한다.
- exact/rule 검색과 embedding 검색을 결합한다.
- 실행 결과를 Evidence로 제한해 최종 답변을 생성한다.

보강 검토가 필요한 부분:

- Ontology와 별개로 실제 entity/relation 인스턴스를 가진 Knowledge Graph/ABox 생성
- 공식 상품 문서를 Markdown으로 파싱하고 source/page/product binding을 보존하는 문서
  Vector evidence 경로
- 질문 requirement를 RDB/Graph/Vector executor로 나누고 결과를 합치는 deterministic
  federated routing
- Execution Registry가 semantic ID뿐 아니라 executor와 physical binding을 안전하게
  연결하는 방식

별도 Graph DB 제품 도입은 원본 자료가 직접 요구하지 않는다. 실제 ABox와 관계 순회가
검증되면 물리 구현은 승인된 아키텍처 안에서 결정할 수 있다.

## 다음 순서

1. 완료된 0-D 산출물은 다시 조사하지 않고 동결한다.
2. 사용자와 Codex가 아래 논리 구조를 아키텍처에 반영할지 승인한다.

```text
Ontology/SHACL (TBox)
  -> Semantic Registry

official/external structured data
  -> query RDB
  -> Knowledge Graph instances/relations (ABox)

official product documents
  -> parsed Markdown
  -> document Vector evidence index

validated semantic query
  -> deterministic RDB / Graph / Vector routing
  -> evidence merge and validation
  -> HCX answer
```

3. 승인 후 `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, shared Registry interface와 A~F
   workstream prompt를 한 번에 정렬한다.
4. 그 뒤 조회 DB, Knowledge Graph, Ontology/Semantic Registry, 문서 Vector 경로를 병렬
   구축하고 Execution Registry와 evidence merger에서 통합한다.

## 현재 중단점

- 0-D: 완료
- DB/Registry 본 구축: 아직 시작하지 않음
- Knowledge Graph/문서 Vector/Federated Query 반영: 설계 승인 대기
- 공식 상품 문서 corpus의 source·coverage·수집 범위: 아직 미확정
