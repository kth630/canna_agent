# Canna Agent

Canna는 제공 데이터와 검증된 외부 데이터를 바탕으로 금융상품을 조회·비교·설명하는
근거 기반 Agent다. 이 저장소는 이전 구현을 복제하지 않고, 현재 승인된 아키텍처와
데이터 의미를 기준으로 새로 구축한다.

## 읽는 순서

1. `CONTEXT.md`
2. `QUESTION_STRUCTURE.md`
3. `ARCHITECTURE.md`
4. `IMPLEMENTATION_PLAN.md`의 현재 단계
5. 해당 단계가 참조하는 `contracts/` 문서

작업 규칙과 역할은 `AGENTS.md`, Claude의 구현 규칙은 `CLAUDE.md`를 따른다.

## 현재 상태

- 아키텍처와 이행 계획을 확정한 초기 이사 단계다.
- 애플리케이션 런타임 코드는 아직 이식하지 않았다.
- 공식 Excel과 holdings ZIP은 로컬에만 두며 Git으로 추적하지 않는다.
- 첫 구현은 HCX opaque ref 및 requirement accounting 반증 실험이다.
- NCP 최소 수직 슬라이스 배포는 첫 실험과 병행한다.

## 로컬 데이터 위치

```text
data/
├─ official_raw/   주최 측 제공 Excel 8개, 읽기 전용
└─ incoming/       holdings_20260829.zip 원본 번들
```

파일별 SHA-256과 출처는 `provenance/MIGRATION_MANIFEST.json`에 기록한다.
