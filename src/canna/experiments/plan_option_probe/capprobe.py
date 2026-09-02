"""What the provisional caps would actually bind, measured at their edges.

The approved corpus never approaches 8/8/32/16, which is itself a result but
not an answer: a cap has to be checked where it bites. This module builds
synthetic view sources whose only purpose is to put the option count exactly one
below a cap, exactly on it and one above it, and records what the generator does
at each point.

Nothing here is a question fixture. The surface forms are placeholders, the
candidates describe no real product, and none of it is registered as test
material. It exists to measure a boundary, not to assert a meaning.

This module is experiment-only. It is not imported by any serving path,
it calls no provider, index or database, and nothing it produces is a
product contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ledger import build_ledger
from .options import (
    GENERATION_TRUNCATED,
    OptionGenerationPolicy,
    PlanOptionSet,
    generate,
)
from .sources import (
    KIND_DATASET,
    KIND_FIELD,
    ViewCandidate,
    ViewSource,
)

TARGET_FORM = "표적집합"
METRIC_FORM = "측정값"
_AXES = frozenset({"type", "family", "grain", "operation", "period", "unit"})


@dataclass(frozen=True)
class CapObservation:
    cap_name: str
    cap_value: int
    position: str
    requested: int
    requirement_options: tuple[int, ...]
    plan_options: int
    plans_before_cap: int
    lossy_discards: int
    generation_status: str
    blocked: bool


def _source(target_count: int) -> ViewSource:
    """One measure served by N targets: the only way N options can coexist.

    With exact-surface matching a slot has one candidate per name, so a second
    option for one requirement can only come from a second target the same
    measure belongs to. That is worth stating plainly, because it is why the
    per-requirement cap is so hard to reach on real questions.
    """
    candidates: list[ViewCandidate] = []
    keys: list[str] = []
    for index in range(target_count):
        key = f"probe.dataset.{index}"
        keys.append(key)
        candidates.append(
            ViewCandidate(
                key=key,
                kind=KIND_DATASET,
                meaning=f"probe target {index}",
                surface_forms=(TARGET_FORM,),
                dataset_keys=(),
                grains=("product",),
                period="",
                unit="",
                currency="",
                allowed_operations=(),
                subject_class="",
                object_class="",
                relation_mode="",
                entity_class="",
                role_nouns=(),
                declared_axes=frozenset({"type", "family", "grain"}),
            )
        )
    candidates.append(
        ViewCandidate(
            key="probe.field.shared",
            kind=KIND_FIELD,
            meaning="probe measure",
            surface_forms=(METRIC_FORM,),
            dataset_keys=tuple(keys),
            grains=("product",),
            period="1Y",
            unit="percent",
            currency="",
            allowed_operations=("filter", "sort", "aggregate", "count", "output"),
            subject_class="",
            object_class="",
            relation_mode="",
            entity_class="",
            role_nouns=(),
            declared_axes=_AXES,
        )
    )
    return ViewSource(
        source_id="cap_probe", authority="experiment_only", candidates=tuple(candidates)
    )


def _question(requirement_count: int) -> str:
    """A frame per aggregation head, coordinated so the ledger splits them."""
    # Nine distinct approved aggregation expressions, so a probe with N
    # requirements uses N different heads rather than repeating one.
    heads = [
        "평균", "최대", "최소", "합계", "개수",
        "총합", "갯수", "최댓값", "최솟값",
    ]
    parts = [f"{heads[index % len(heads)]} {METRIC_FORM}" for index in range(requirement_count)]
    return f"{TARGET_FORM}의 " + "와 ".join(parts) + "을 알려줘"


def _run(target_count: int, requirement_count: int, policy: OptionGenerationPolicy):
    source = _source(target_count)
    question = _question(requirement_count)
    ledger = build_ledger(question, source)
    return ledger, generate(question, ledger, source, policy)


def _observe(
    cap_name: str,
    cap_value: int,
    position: str,
    requested: int,
    result: PlanOptionSet,
) -> CapObservation:
    return CapObservation(
        cap_name=cap_name,
        cap_value=cap_value,
        position=position,
        requested=requested,
        requirement_options=tuple(
            len(options) for options in result.requirement_options.values()
        ),
        plan_options=len(result.plan_options),
        plans_before_cap=result.plan_options_before_cap,
        lossy_discards=result.lossy_discards,
        generation_status=result.generation_status,
        blocked=not result.selectable_plans,
    )


def observations(
    policy: OptionGenerationPolicy | None = None,
) -> tuple[CapObservation, ...]:
    """Each cap at one below, exactly on, and one above."""
    policy = policy or OptionGenerationPolicy()
    rows: list[CapObservation] = []

    for offset, position in ((-1, "below"), (0, "at"), (1, "above")):
        count = policy.max_options_per_requirement + offset
        _ledger, result = _run(count, 1, policy)
        rows.append(
            _observe("max_options_per_requirement", policy.max_options_per_requirement,
                     position, count, result)
        )

    for offset, position in ((-1, "below"), (0, "at"), (1, "above")):
        count = policy.max_requirements + offset
        _ledger, result = _run(1, count, policy)
        rows.append(
            _observe("max_requirements", policy.max_requirements, position, count, result)
        )

    # The plan cap and the join beam are reached by multiplying targets across
    # requirements, so they are approached from the product rather than a count.
    for targets, requirements, position in (
        (2, 3, "below"),
        (2, 4, "at"),
        (2, 5, "above"),
    ):
        _ledger, result = _run(targets, requirements, policy)
        rows.append(
            _observe(
                "max_plan_options",
                policy.max_plan_options,
                position,
                targets**requirements,
                result,
            )
        )
    return tuple(rows)


def to_rows(items: tuple[CapObservation, ...]) -> list[dict[str, object]]:
    return [
        {
            "cap": item.cap_name,
            "cap_value": item.cap_value,
            "position": item.position,
            "requested": item.requested,
            "requirement_options": list(item.requirement_options),
            "plan_options": item.plan_options,
            "plans_before_cap": item.plans_before_cap,
            "lossy_discards": item.lossy_discards,
            "generation_status": item.generation_status,
            "blocked": item.blocked,
            "truncated": item.generation_status == GENERATION_TRUNCATED,
        }
        for item in items
    ]
