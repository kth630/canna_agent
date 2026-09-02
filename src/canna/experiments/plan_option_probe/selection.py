"""Request-scoped plan references, and what makes one executable.

Section 8 of the proposal gives a reference no authority of its own: it is an
opaque token whose only power comes from being a key in *this* request's map.
Shape is a diagnostic; membership is the permission. This module implements that
so the experiment can show, rather than assert, that an arbitrary reference, a
reference minted by another request, an expired one and a consumed one all fail
for their own distinct reasons.

The preview is re-derived on selection from the stored option and compared with
the preview taken at generation time. If they differ the selection is refused,
which is the only way a plan that changed underneath a model can be caught.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field

from .options import PlanOption, PlanOptionSet

REF_PREFIX = "pl_"
REF_BYTES = 16

REJECT_SHAPE = "selected_plan_ref_malformed"
REJECT_NOT_IN_REQUEST = "selected_plan_ref_not_in_request"
REJECT_CONSUMED = "selected_plan_ref_consumed"
REJECT_EXPIRED = "selected_plan_ref_expired"
REJECT_NOT_SELECTABLE = "selected_plan_is_not_selectable"
REJECT_MISMATCH = "option_revalidation_mismatch"


class SelectionRejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def canonical_plan_preview(plan: PlanOption) -> str:
    """A deterministic fingerprint of what this plan would execute."""
    payload = [
        {
            "requirement": option.requirement_id,
            "kind": option.kind,
            "targets": sorted(option.target_keys),
            "outputs": sorted(option.output_field_keys),
            "conditions": sorted(
                (item.field_key, item.operator, item.value)
                for item in option.conditions
            ),
            "ordering": [option.ordering_field_key, option.ordering_direction],
            "limit": option.limit,
            "aggregation": [
                option.aggregation_field_key,
                option.aggregation_function,
            ],
            "relationship": [
                option.relationship_key,
                option.relationship_anchor_key,
                option.relationship_direction,
            ],
            "reuse": bool(option.result_reuse_of),
        }
        for option in sorted(
            plan.requirement_options, key=lambda item: item.requirement_id
        )
    ]
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


@dataclass
class PlanOptionStore:
    """One request's plan references. Nothing outside it can be selected."""

    request_scope_id: str
    by_ref: dict[str, PlanOption] = field(default_factory=dict)
    previews: dict[str, str] = field(default_factory=dict)
    consumed: set[str] = field(default_factory=set)
    open_for_selection: bool = True

    @classmethod
    def for_request(cls, result: PlanOptionSet) -> PlanOptionStore:
        store = cls(request_scope_id=secrets.token_hex(REF_BYTES))
        for plan in result.plan_options:
            ref = REF_PREFIX + secrets.token_hex(REF_BYTES)
            while ref in store.by_ref:  # pragma: no cover - collision guard
                ref = REF_PREFIX + secrets.token_hex(REF_BYTES)
            stored = PlanOption(
                plan_ref=ref,
                requirement_options=plan.requirement_options,
                plan_status=plan.plan_status,
                equivalence_key=plan.equivalence_key,
                execution_constraints=plan.execution_constraints,
                blocking_reasons=plan.blocking_reasons,
            )
            store.by_ref[ref] = stored
            store.previews[ref] = canonical_plan_preview(stored)
        return store

    @property
    def offered(self) -> tuple[PlanOption, ...]:
        return tuple(self.by_ref.values())

    def expire(self) -> None:
        self.open_for_selection = False

    def select(self, ref: str) -> PlanOption:
        """Exact membership, single use, and a preview that still matches."""
        if not isinstance(ref, str) or not ref.startswith(REF_PREFIX) or len(ref) < 8:
            raise SelectionRejected(REJECT_SHAPE)
        if not self.open_for_selection:
            raise SelectionRejected(REJECT_EXPIRED)
        if ref in self.consumed:
            raise SelectionRejected(REJECT_CONSUMED)
        plan = self.by_ref.get(ref)
        if plan is None:
            raise SelectionRejected(REJECT_NOT_IN_REQUEST)
        self.consumed.add(ref)
        if not plan.selectable:
            raise SelectionRejected(REJECT_NOT_SELECTABLE)
        if canonical_plan_preview(plan) != self.previews[ref]:
            raise SelectionRejected(REJECT_MISMATCH)
        return plan
