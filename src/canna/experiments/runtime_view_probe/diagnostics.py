"""Structured retrieval outcome for the stage 1-A Runtime View experiment.

Experiment only. ``AGENTS.md`` forbids dropping an unresolved requirement and
executing anyway; the same rule applies one layer earlier. When a view is known
to be incomplete, that has to be a recorded result, not a shorter candidate
list that nothing downstream can tell apart from a complete one.

Everything here is decided without gold labels, so it is available at request
time. Gold-based recall lives in ``measurement.py`` and is a harness measure.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .registry import Registry
from .retrieval import TRUNCATION_BUDGET, TRUNCATION_DEPENDENCY, RetrievalResult

# Failure kinds. Each names a different reason the view cannot be trusted to
# carry the meanings the question needs.
FAILURE_NO_DATASET_MATCH = "no_dataset_match"
FAILURE_BUDGET_TRUNCATED = "budget_truncated"
FAILURE_CAPABILITY_UNSUPPORTED = "capability_unsupported"
FAILURE_KINDS: tuple[str, ...] = (
    FAILURE_NO_DATASET_MATCH,
    FAILURE_BUDGET_TRUNCATED,
    FAILURE_CAPABILITY_UNSUPPORTED,
)

STATUS_COMPLETE = "complete"
STATUS_INCOMPLETE = "incomplete"


class RetrievalFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    detail: str
    semantic_ids: tuple[str, ...] = ()


class CapabilityRequest(BaseModel):
    """A capability the question named, checked against retrieved families."""

    model_config = ConfigDict(frozen=True)

    capability_id: str
    label: str
    supported_by: tuple[str, ...] = ()
    unsupported_by: tuple[str, ...] = ()

    def unsupported_everywhere(self) -> bool:
        return not self.supported_by


class RetrievalOutcome(BaseModel):
    """Whether this view may be treated as a basis for execution."""

    model_config = ConfigDict(frozen=True)

    status: str
    executable: bool
    failures: tuple[RetrievalFailure, ...] = ()
    capability_requests: tuple[CapabilityRequest, ...] = ()

    def failure_kinds(self) -> tuple[str, ...]:
        return tuple(sorted({failure.kind for failure in self.failures}))


def assess(registry: Registry, result: RetrievalResult) -> RetrievalOutcome:
    """Judge a retrieval result without consulting gold labels."""
    failures: list[RetrievalFailure] = []

    dataset_ids = tuple(
        candidate.semantic_id for candidate in result.admitted_of_kind("dataset")
    )
    if not dataset_ids:
        failures.append(
            RetrievalFailure(
                kind=FAILURE_NO_DATASET_MATCH,
                detail="no product family could be grounded from this question",
            )
        )

    dropped = tuple(
        candidate
        for candidate in result.truncated
        if candidate.reason in (TRUNCATION_BUDGET, TRUNCATION_DEPENDENCY)
        and candidate.directly_matched
    )
    if dropped:
        failures.append(
            RetrievalFailure(
                kind=FAILURE_BUDGET_TRUNCATED,
                detail=(
                    "the candidate budget dropped candidates the question named directly; "
                    "the view is smaller than the question's meaning"
                ),
                semantic_ids=tuple(sorted(candidate.semantic_id for candidate in dropped)),
            )
        )

    requests = tuple(
        _capability_request(registry, capability_id, dataset_ids)
        for capability_id in result.matched_capability_ids
    )
    unsupported = tuple(request for request in requests if request.unsupported_everywhere())
    if unsupported:
        failures.append(
            RetrievalFailure(
                kind=FAILURE_CAPABILITY_UNSUPPORTED,
                detail=(
                    "the question asks for a capability no retrieved product family declares "
                    "as supported"
                ),
                semantic_ids=tuple(sorted(request.capability_id for request in unsupported)),
            )
        )

    return RetrievalOutcome(
        status=STATUS_INCOMPLETE if failures else STATUS_COMPLETE,
        executable=not failures,
        failures=tuple(failures),
        capability_requests=requests,
    )


def _capability_request(
    registry: Registry,
    capability_id: str,
    dataset_ids: tuple[str, ...],
) -> CapabilityRequest:
    supported: list[str] = []
    unsupported: list[str] = []
    for dataset_id in dataset_ids:
        coverage = registry.entry(dataset_id).capability_coverage
        if coverage is None:
            continue
        if coverage.classification(capability_id) == "supported":
            supported.append(dataset_id)
        else:
            unsupported.append(dataset_id)
    return CapabilityRequest(
        capability_id=capability_id,
        label=registry.capability(capability_id).label,
        supported_by=tuple(sorted(supported)),
        unsupported_by=tuple(sorted(unsupported)),
    )
