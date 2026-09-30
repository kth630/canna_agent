# 포트폴리오 검증 기록

검증일: 2026-09-30 (Asia/Seoul). 코드 기준: `f1aa669`.

## 범위와 재현 조건

Git이 추적하는 HEAD 파일만 `git archive`로 별도 경로에 추출했습니다.
원본 데이터, `.env`, 생성 DB와 작업 중인 untracked `semantic_tool` 코드는 포함하지 않았습니다.
Windows / Python 3.12.13에서 기존 로컬 가상환경의 Python으로 실행했습니다.
따라서 데이터·자격증명 없이 동작하는 코드 경로는 확인했지만, 새 머신에서의 dependency 다운로드·설치는 검증하지 않았습니다.

## 실행 명령과 결과

저장소의 pytest 설정은 `.tmp/pytest`를 사용하므로 첫 실행 전에 부모 폴더를 생성합니다.
최초 실행에서는 이 폴더가 없어 29개 setup error가 발생했고, README에 준비 단계를 추가한 뒤 재검증했습니다.

```bash
python -c "from pathlib import Path; Path('.tmp').mkdir(exist_ok=True)"
python -m pytest tests/test_api.py tests/test_architecture_guards.py tests/test_semantic_registry.py tests/test_ontology_shacl.py tests/runtime_view/test_canonicalize.py tests/execution -q -m "not real_data and not hcx_live and not embedding_live"
```

결과: **332 passed, 6 skipped, 2 deselected** (30.24초).
6개 skip은 실제 조회 저장소·Registry가 필요한 offline integration 경로이며, 2개 deselection은 real-data 테스트입니다.
실제 데이터 E2E와 HCX 호출 성공률을 이 수치에 포함하지 않습니다.

```bash
python scripts/build_registries.py --semantic-only
```

결과: **status=ok**, 의미 Registry 331개 항목 생성.
이 수치는 해당 코드·Ontology snapshot의 관측값이며 런타임 상수가 아닙니다.

## 검증한 일반화 경계

- API: 기존의 복수 요구, 관계 조건, 비교, 특수문자 등 요청 변형에서도 같은 응답 계약을 유지.
- Runtime View: 기존 span canonicalization 테스트로 값·단위·연산 해석 및 실패 경계 확인.
- 실행: 합성 Registry에서 grain, source, coverage, as-of 및 binding 불일치 시 실행 제한 확인.
- Ontology: 유효 합성 ABox 수용과 grain 위반 거부, Registry 의미 선언 검사.
- 아키텍처 guard: 평가 ID 분기, fixture 질문 삽입, 이전 저장소 의존 등 검사.

새 질문 fixture는 추가하지 않았습니다. 기존 unseen-variant 테스트를 재실행했으며,
새로 확보한 holdout의 일반화 성능을 주장하지 않습니다.

## 변경과 한계

이번 변경은 README와 이 검증 기록입니다. 런타임·공유 계약·아키텍처·coverage 정책을 변경하지 않았고 새 런타임 상수도 없습니다.
미완성 API, production compiler 및 provenance binding, 모델 생성 안정성은 README에 명시했습니다.
기존 미추적 작업은 수정하거나 커밋에 포함하지 않았습니다.

원본 Excel·holdings ZIP·생성 DB·`.env`의 Git 제외를 확인했습니다.
공개 코드에도 공식 데이터의 스키마·의미 대조표와 대회 요구사항·실험 기록이 포함됩니다.
이 자료의 공개·재배포 권한은 기술 검증만으로 확인할 수 없으며, 저장소 공개 전환 전에 확인이 필요합니다.
