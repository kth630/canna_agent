"""What a model would be shown, and what showing it would cost.

Section 9 of the proposal allows a plan option to carry an opaque reference and
a summary built from a deterministic allow-list -- never a free sentence, never
a stable identifier, never a physical name. This module builds exactly that
summary and measures its size, so the prompt budget can be estimated without
calling a provider.

The allow-list is enforced by construction: the summary is assembled from named
fields, so a value that is not on the list has no way in. The leak check that
follows is therefore a regression guard rather than the only defence.

This module is experiment-only. It is not imported by any serving path,
it calls no provider, index or database, and nothing it produces is a
product contract.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .options import PlanOption, RequirementOption
from .sources import ViewSource

# The only per-requirement facts a summary may carry, from proposal section 9.
SUMMARY_FIELDS = (
    "requirement",
    "kind",
    "target_meaning",
    "field_meaning",
    "period",
    "unit",
    "relation_meaning",
    "relation_direction",
    "result_grain",
    "question_spans",
)

# A rough size model, stated rather than assumed. No provider was called, so
# this is an estimate: CJK characters are counted as one token each and ASCII
# runs at four characters per token, which is the usual order of magnitude for
# byte-pair vocabularies on Korean text.
_CJK = re.compile(r"[ㄱ-힝一-鿿]")


@dataclass(frozen=True)
class PayloadEstimate:
    option_count: int
    bytes_utf8: int
    estimated_tokens: int


def _estimate_tokens(text: str) -> int:
    cjk = len(_CJK.findall(text))
    other = len(text) - cjk
    return cjk + (other + 3) // 4


def requirement_summary(
    option: RequirementOption, source: ViewSource
) -> dict[str, object]:
    """One requirement, in meanings and the question's own words only."""
    targets = [source.get(key) for key in option.target_keys]
    fields = [source.get(key) for key in option.output_field_keys]
    relation = source.get(option.relationship_key) if option.relationship_key else None
    return {
        "requirement": option.requirement_id,
        "kind": option.kind,
        "target_meaning": [item.meaning for item in targets if item],
        "field_meaning": [item.meaning for item in fields if item],
        "period": [item.period for item in fields if item and item.period],
        "unit": [item.unit for item in fields if item and item.unit],
        "relation_meaning": relation.meaning if relation else "",
        "relation_direction": option.relationship_direction,
        "result_grain": sorted(
            {grain for item in targets if item for grain in item.grains}
        ),
        "question_spans": list(option.span_texts),
    }


def plan_summary(plan: PlanOption, source: ViewSource) -> dict[str, object]:
    return {
        "plan_ref": plan.plan_ref,
        "requirements": [
            requirement_summary(item, source) for item in plan.requirement_options
        ],
    }


def payload_for(plans: Sequence[PlanOption], source: ViewSource) -> str:
    return json.dumps(
        {"options": [plan_summary(item, source) for item in plans]},
        ensure_ascii=False,
    )


def estimate(payload: str, option_count: int) -> PayloadEstimate:
    return PayloadEstimate(
        option_count=option_count,
        bytes_utf8=len(payload.encode("utf-8")),
        estimated_tokens=_estimate_tokens(payload),
    )


def scale_estimates(
    plans: Sequence[PlanOption],
    source: ViewSource,
    counts: Sequence[int] = (2, 4, 8, 16),
) -> tuple[PayloadEstimate, ...]:
    """What the same options would cost if the server offered N of them.

    A request that produced one plan is scaled by repeating it, which is the
    honest lower bound: real alternatives differ, and differing text is longer
    than repeated text, never shorter.
    """
    if not plans:
        return ()
    estimates: list[PayloadEstimate] = []
    for count in counts:
        repeated = [plans[index % len(plans)] for index in range(count)]
        estimates.append(estimate(payload_for(repeated, source), count))
    return tuple(estimates)


def leaked_values(payload: str, source: ViewSource) -> tuple[str, ...]:
    """Anything in the payload that the allow-list forbids."""
    lowered = payload.lower()
    leaks: list[str] = []
    for candidate in source.candidates:
        if candidate.key.lower() in lowered:
            leaks.append("stable_semantic_id")
            break
    for word in ("select ", "join ", "src_", "table", "column", "sql"):
        if word in lowered:
            leaks.append(f"physical_term:{word.strip()}")
    return tuple(dict.fromkeys(leaks))


def unexpected_fields(summary: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(sorted(set(summary) - set(SUMMARY_FIELDS)))
