# Claude prompt — E: deployment, integration, and verification foundation

`COMMON.md`의 모든 지시를 적용하라. 당신은 workstream E 담당자다.

## 목표와 권한 경계

현재 transport-only `/answer` slice를 로컬에서 재현 가능하게 검증하고 NCP 배포·통합을 위한
비파괴 harness를 만든다. 이 프롬프트는 SSH, 원격 설치·업로드, service restart, 방화벽/ACG
변경, secret 주입을 승인하지 않는다. 원격 변경 전에는 사용자에게 정확한 명령과 상태 변경을
제시하고 별도 승인을 받아야 한다.

추가로 읽을 문서:

- `provenance/workstreams/20260830_preintegration_parallel/evaluation_api_skeleton/GATE.md`
- `provenance/workstreams/20260830_preintegration_parallel/evaluation_api_skeleton/FINDINGS.md`
- `provenance/infrastructure/servers/mirae-agent-api/SERVER.md`
- `provenance/MIGRATION_CHECKLIST.md`

## Owned paths

- `deploy/ncp/**`
- `scripts/deployment/**`
- `tests/deployment/**`
- `tests/integration/**`
- `provenance/workstreams/20260830_preintegration_parallel/e_deployment_integration/**`

외부 envelope owner 후보로서 `src/canna/api.py`, `src/canna/answer_envelope.py`,
`tests/test_api.py`, `pyproject.toml`, `uv.lock`은 읽을 수 있으나 Batch 1에서는 수정하지 않는다.
필요한 변경은 `INTEGRATION_REQUEST.md`로 반환한다.

## Batch 1 구현

1. 현재 API 회귀 테스트를 실행해 transport baseline을 기록한다.
2. endpoint를 환경으로 받는 strategy-neutral deployment probe를 만든다.
3. probe는 200, 정확한 media type, 5개 문자열 key, echo, parseable retrieved_context,
   unknown query parameter 안전성, 비ASCII 보존을 검증한다.
4. bounded cold/warm latency와 낮은 기본 동시성 probe를 만든다.
5. timeout, connection refusal, invalid JSON, schema drift, application no-data를 서로 다른
   실패로 기록한다.
6. memory/restart/availability 관측 명령과 deployment 선택지(systemd/container/reverse proxy)를
   기록하되 하나를 정본으로 확정하거나 원격 실행하지 않는다.
7. 실제 값이 없는 secret-free configuration template와 archive/image exclusion 검사를 만든다.
8. 로컬 API를 대상으로 probe를 검증한다.
9. A~F freeze 후 필요한 integration checklist와 최소 seam 변경을 제안한다.
10. validation error envelope, retrieved_context size, health endpoint, timeout/concurrency 정책은
    pending 계약이므로 임의 구현하지 않는다.

## Secret·원격 규칙

- IP, username, password, private key, NCP/HCX key를 source, prompt, command argument, log,
  provenance, image/archive에 기록하지 않는다.
- `.env` 내용을 출력하거나 hash하지 않는다.
- SSH agent 또는 interactive credential 주입을 우선하며 `sshpass`, URL credential,
  command-line secret을 쓰지 않는다.
- 원격 작업 전 host/user 전달 방법, 인증, 전송, install, process manager, exposure 범위,
  restart 허용 여부를 사용자에게 각각 확인한다.
- `0.0.0.0/0` 공개나 SSH/API ACG rule 결합을 임의 수행하지 않는다.

## 수용 기준

- probe가 endpoint/credential을 하드코딩하지 않는다.
- 외부 계약 drift와 network/timeout/schema/no-data 실패를 구분한다.
- latency/concurrency probe가 bounded이고 재현 가능하다.
- secret 값이 source/template/output/provenance에 없다.
- 원격에서 관측하지 않은 성능·복구·상시성을 성공으로 보고하지 않는다.
- A~D와 외부 API/packaging shared file을 변경하지 않는다.

## 검증

- `uv run pytest -q tests/test_api.py tests/deployment tests/integration`
- `uv run ruff check scripts/deployment tests/deployment tests/integration`
- `uv run pytest -q tests/test_architecture_guards.py`
- `git diff --check`
- `git status --short`

원격 변경, packaging, health/validation 계약, public exposure 또는 A~F integration이 필요하면
즉시 중단해 `INTEGRATION_REQUEST.md`로 보고하라.
