# 제출용 Ontology와 SHACL

## 파일

| 파일 | 범위 |
|---|---|
| `core.ttl` | 공통 TBox: 상품·클래스·포트폴리오·종목·관측·식별자·출처·coverage·실패, 관계와 상태 값, 공통 지표·속성, 공통 SHACL shape |
| `bond_kr.ttl` | 국내채권 개체·속성·지표와 shape |
| `etf_kr.ttl` | 국내 ETF·ETN 개체·속성·지표와 shape |
| `etf_gl.ttl` | 해외 ETF·ETN 개체·속성·지표와 shape |
| `fund_pub.ttl` | 공모펀드 클래스·묶음·속성·지표와 shape |

SHACL NodeShape는 도메인별 파일 안에 함께 둔다. 제출 산출물은 이 5개 파일이다.

## namespace

`https://canna.local/ontology/{core,bond-kr,etf-kr,etf-gl,fund-pub}#`.
`canna.local`은 외부에 공개되지 않는 안정 식별자 접두사로만 쓰며 해석 가능한 주소가
아니다. Semantic Registry의 stable ID는 이 접두사에서 만든 CURIE(`etkr:Return1Y`)이고,
CURIE는 TTL의 `@prefix` 선언에서 그대로 생성한다.

## 이 온톨로지가 담는 것과 담지 않는 것

담는다.

- stable semantic ID와 의미, 한국어 label, 승인된 alias
- domain·range·inverse와 관계 방향
- semantic grain, 관측 기간, 단위 종류, 통화 결정 방식
- 의미상 허용되는 연산과 Evidence 요구
- 비교 가능 그룹과 의미 확정 상태
- 0-D 대조에서 기록한 `유지 | 수정 | 제외 | 추가 | 미확정` 판정

담지 않는다.

- 물리 table·column·SQL·join
- 실행 시점 coverage, freshness, 행 수
- 특정 상품명·날짜·질문 문자열

물리 binding은 `catalog/`와 `data/processed/data_catalog.json`이, 동적 coverage는
Execution Registry가 소유한다. 두 축은 stable semantic ID로만 연결한다.

## 생성과 검증

```powershell
uv run python scripts/build_registries.py
uv run python -m pytest tests/test_ontology_shacl.py tests/test_semantic_registry.py -q
```

`scripts/build_registries.py`는 이 디렉터리에서 Semantic Registry를 생성하고, 지표가
grain·단위·기간·연산·비교 그룹을 선언하지 않으면 실패한다. SHACL은 두 방향으로 시험한다.

1. 합성 ABox: 식별자 미해결 종목, 포트폴리오 없는 보유 관측, 값 상태 없는 지표 관측 등
   grain 위반이 실제로 거부되는지 확인한다.
2. 실제 store에서 투영한 ABox가 shape를 통과하는지 확인한다. 이 투영
   (`src/canna/graph/project.py`)은 전체 Knowledge Graph가 아니라 SHACL 검증용 bounded
   sample이다(상품군당 subject 8개, subject당 관측 6개 상한).

## 확장 지점

- 문서 근거(예: OpenDART 공시)는 `cnn:ProjectProduct`/`cnn:Portfolio`의 subject key를
  재사용해 붙인다. 지금은 문서 개념을 선언하지 않았다. 추가할 때 기존 semantic ID와 핵심
  DB를 갈아엎을 필요는 없지만, Document·Chunk·Evidence 개념과 Vector executor·index·
  filter binding은 새로 설계해야 하며 두 Registry가 함께 확장된다.
- 전체 Knowledge Graph 적재는 같은 투영 코드를 확장해 수행한다. 현재 산출물은 sample
  이며 별도 Graph DB 도입은 이번 범위가 아니다.
