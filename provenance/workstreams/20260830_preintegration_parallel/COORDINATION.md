# Parallel coordination — 2026-08-30

## Purpose and boundary

This record coordinates only pre-integration work. It does not approve a
product/fund/portfolio/security mapping, a common data table, a snapshot
reconciliation rule, or a holdings execution schema.

The approved parallel work is limited to immutable-source custody and
file-level observation, linkage-candidate research, the evaluation-service
transport boundary, and their provenance. Any result below is an observation
or a pending decision until the user and Codex approve an architectural or
contract change.

## Workstream status

| workstream | status | owned paths | boundary |
|---|---|---|---|
| 0-A — HCX opaque-ref and requirement-accounting experiment | complete / separately recorded | `src/canna/experiments/semantic_probe/`, `tests/fixtures/semantic_*`, `tests/test_semantic_probe*.py`, `provenance/experiments/stage_0a_semantic_grounding/` | Synthetic Runtime View experiment only; it is not the serving API or a data registry. |
| 0-B — evaluation API minimum vertical slice | local transport slice verified; deployment validation pending | `src/canna/api.py`, `src/canna/answer_envelope.py`, `tests/test_api.py`, `provenance/workstreams/20260830_preintegration_parallel/evaluation_api_skeleton/` | HTTP/JSON envelope only; no HCX invocation, Runtime View, Registry, DuckDB, source data, holdings, or joins. |
| 1-A — Runtime View retrieval foundation | active / assigned by user | `src/canna/experiments/runtime_view_probe/`, `tests/test_runtime_view_probe.py`, `tests/fixtures/runtime_view_*`, `scripts/run_runtime_view_probe.py`, `provenance/experiments/stage_1_runtime_view/` | Synthetic Registry and deterministic candidate retrieval only; no HCX invocation, semantic-query generation, compiler, DuckDB, source data, holdings, serving API, or NCP deployment. |

## Isolation rules

- 0-A and 0-B do not import one another's code or fixtures.
- 1-A does not modify or import the 0-A experiment, 0-B serving slice, or their
  fixtures. It may use only the approved logical conclusions in the canonical
  documents and the 0-A findings as design input.
- Neither workstream changes `CONTEXT.md`, `QUESTION_STRUCTURE.md`,
  `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, `contracts/`, immutable source
  data, or the migration manifest.
- `pyproject.toml` and `uv.lock` are shared configuration surfaces. They are
  not to be changed by either workstream while the other is active.
- API-only tests may run while 0-A changes fixtures. The full architecture
  guard runs once after both workstreams have stopped modifying their files.

### 1-A active boundary

- The work builds a synthetic, Registry-owned candidate source and a
  deterministic Runtime View retrieval experiment. It records candidate recall,
  candidate count, serialized size, and retrieval latency; a required candidate
  missing from a view is an explicit retrieval failure, never a silent execute.
- Opaque refs are request-scoped. Stable semantic IDs and all candidate aliases,
  meanings, and bindings remain inside the synthetic Registry fixture rather
  than Python branching constants.
- Span alignment versus character offsets, comparison-requirement enforcement
  versus server promotion, and relationship-direction derivation remain
  unresolved design decisions. 1-A must report options and evidence rather
  than implement any of them.
- 1-A must not modify `src/canna/api.py`, `src/canna/answer_envelope.py`,
  `tests/test_api.py`, `pyproject.toml`, `uv.lock`, canonical documents,
  `data/`, or any completed 0-A artifact.

## Evidence recorded so far

### 0-A completion

The user reports that 0-A has completed. Its experiment outputs and findings
remain the source of record under
`provenance/experiments/stage_0a_semantic_grounding/`. 0-B does not consume or
import those outputs at this stage.

### 0-B local verification

- `tests/test_api.py`: 50 parameterized test executions passed.
- Ruff check on the two API modules and API test passed.
- Five architecture guards that do not read mutable 0-A fixtures passed; two
  fixture-reading guards are intentionally deferred.
- The API implementation imports no 0-A module, legacy workspace path, source
  data, DuckDB, or holdings input.

This establishes only the local HTTP transport boundary. It does not establish
NCP deployment, public reachability, cold/warm latency, memory use, restart
recovery, concurrency behavior, or an answer capability.

### Deployment target

The deployment target is recorded at
`provenance/infrastructure/servers/mirae-agent-api/SERVER.md`: an NCP VPC
Ubuntu 24.04 server (2 vCPU / 4 GB / 10 GB) in a public subnet with a public IP
assigned, ACG configured, and user-reported SSH availability. The public IP,
credential material, individual ACG rules, deployment method, and remote
runtime facts remain unrecorded or unverified. No deployment action is
authorized by this record alone.

## Open decisions and blockers

1. The public handling of missing or blank `question_id` / `question` is not
   yet fixed. The contract requires non-empty inputs but does not yet define
   the status and response envelope for violations.
2. `retrieved_context` internal schema and size limit remain pending.
3. The test environment currently receives `httpx` transitively. Adding it as
   an explicit development dependency must wait until shared packaging changes
   are coordinated.
4. Deployment requires the user-provided server connection and deployment
   details before a worker can perform a real remote validation.

## Promotion rule

Do not mark implementation-plan stages complete from this coordination log.
After 0-A and 0-B have frozen their files, the coordinator will run the full
architecture guard, inspect the diffs, and write an integration review. Only
then may results be proposed for updates to the implementation plan or other
canonical documents.
