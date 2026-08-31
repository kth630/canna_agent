"""What the model is told about its own submission, and nothing more.

The server's plan is a different document from the model's answer. The plan
holds stable semantic IDs, the verified entity key and the traversal the server
chose, because the next layer needs all of that to execute. The model needs
none of it, and handing it over would leak the Registry one refusal at a time —
a model that submits a wrong reference and reads back the real identifier of the
right one has been given a lookup table.

So this is an explicit projection rather than a serialisation of the internal
result. It is built by naming the safe fields, not by removing the unsafe ones,
because an allow-list stays correct when someone adds a field to the plan and a
deny-list does not.

Refusal reasons are included, in the model's own vocabulary of references: the
model has to be able to tell a wrong family from a missing canonicaliser to
account for its requirement honestly. The reason text is written for that and
carries no identifiers.
"""

from __future__ import annotations

from typing import Any

from .contract import CONTRACT_STATUS
from .validate import CanonicalRequirement, ValidationResult
from .view import RuntimeView

AUDIENCE = "model_facing"

# What a refusal means, in the model's terms. Written so that no code needs the
# server's identifiers to be understood.
SAFE_REASONS: dict[str, str] = {
    "unknown_ref": "a reference in this requirement is not one of the candidates offered",
    "ref_kind_mismatch": "a reference was used in a slot of a different kind",
    "missing_target_dataset": "the requirement does not say which population it applies to",
    "cross_family_field": (
        "the chosen measure belongs to a different product than the target; no measure "
        "of the target was substituted for it"
    ),
    "cross_family_predicate": "the chosen relationship belongs to a different product",
    "field_scope_unproven": (
        "it is not established which products this measure applies to, so it cannot be "
        "used for the chosen target"
    ),
    "field_grain_mismatch": (
        "the chosen measure is reported at a different unit of result than the target"
    ),
    "requirement_unresolved": "the requirement was submitted unresolved",
    "requirement_ambiguous": "the requirement was submitted as ambiguous",
    "requirement_incomplete": "the requirement is missing something it needs to be carried out",
    "empty_requirement": "the requirement names nothing to act on",
    "missing_source_span": "the requirement does not quote the part of the question it came from",
    "span_alignment_failed": "a quoted fragment does not appear in the question",
    "unaccounted_explicit_span": "part of the question was reported as unaccounted for",
    "entity_unresolved": "the named product or security could not be identified",
    "relation_direction_undecidable": "the direction of the relationship is not determined",
    "relation_target_mismatch": "the relationship does not return the kind of thing asked for",
    "canonicalizer_unavailable": "this operation cannot yet be carried out deterministically",
}

UNKNOWN_REASON = "the requirement was refused"


def _requirement_payload(
    view: RuntimeView, requirement: CanonicalRequirement
) -> dict[str, Any]:
    targets = [
        ref
        for ref in (view.ref_for(value) for value in requirement.target_dataset_ids)
        if ref
    ]
    fields = [
        ref
        for ref in (
            view.ref_for(binding.field_id) for binding in requirement.field_bindings
        )
        if ref
    ]
    relation_ref = (
        view.ref_for(requirement.relation.submitted_predicate_id)
        if requirement.relation
        else None
    )
    return {
        "requirement_id": requirement.requirement_id,
        "kind": requirement.kind,
        "submitted_status": requirement.submitted_status,
        "server_decision": requirement.server_decision,
        "semantic_valid": requirement.semantic_valid,
        "accepted_target_dataset_refs": sorted(set(targets)),
        "accepted_field_refs": sorted(set(fields)),
        "accepted_relationship_ref": relation_ref,
        "reasons": [
            {"code": code, "meaning": SAFE_REASONS.get(code, UNKNOWN_REASON)}
            for code in requirement.blocking_codes
        ],
    }


def model_response(view: RuntimeView, result: ValidationResult) -> dict[str, Any]:
    """Project a validation result down to what the model may be told."""
    requirements = result.plan.requirements if result.plan else ()
    return {
        "contract_status": CONTRACT_STATUS,
        "audience": AUDIENCE,
        "semantic_valid": result.semantic_valid,
        "execution_readiness": result.execution_readiness,
        "execution_readiness_note": (
            "semantic validation only; whether the data can answer this is decided "
            "elsewhere and is not asserted here"
        ),
        "requirements": [
            _requirement_payload(view, requirement) for requirement in requirements
        ],
        "unresolved_requirement_ids": list(result.unresolved_requirement_ids),
        "submission_level_reasons": [
            {"code": issue.code, "meaning": SAFE_REASONS.get(issue.code, UNKNOWN_REASON)}
            for issue in result.issues
            if not issue.requirement_id
        ],
    }
