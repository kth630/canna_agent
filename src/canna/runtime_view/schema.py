"""A provisional JSON Schema for the ``submit_semantic_query`` tool.

The schema and the parser have to agree, or the boundary has two different
opinions about what a valid submission is — and the one that matters would be
whichever the provider happened to enforce. So the reference patterns and the
required spans are derived from the parser's own tables rather than retyped, and
a parity test asserts that what one accepts the other accepts too.

References are typed by slot. A target slot takes only a dataset reference, a
field slot only a field reference, and so on, so a model cannot put a
relationship where a measure belongs and have the mistake surface later as a
puzzling refusal. Spans that carry meaning are required and non-empty: a
condition without a comparison is not a looser condition, it is an unreadable
one, and the same goes for an ordering with no direction or an aggregation with
no function.

``additionalProperties`` is false everywhere on purpose. A model that invents a
property is reaching for something this contract does not offer, and the useful
response is a rejection at the boundary rather than a field silently dropped.

What the schema cannot express is as telling as what it can: there is no slot
for a table, a column, a join, a SQL fragment, a traversal or any identifier
that would survive outside this request.

This is a draft, which is what ``CONTRACT_STATUS`` records. It is also the
declaration HyperCLOVA X refused on 2026-08-31 with API error ``40009`` before
emitting any tool — three times, once as written, once with its keywords
projected onto the vocabulary an accepted request had used, and once more under
the function name that accepted request carried.

So this schema is no longer what the provider is sent. ``grouped_flat.py``
carries the same contract as flat records grouped by a repeated
``requirement_id``, the fallback ``RUNTIME_VIEW_TOOL_DECISION_20260831.md``
section 5 approved in advance, and assembles what comes back into the shape
this schema describes so that ``query.parse_submission`` decides it. The
encoding moved; nothing the server enforces did.
"""

from __future__ import annotations

from typing import Any

from .contract import CONTRACT_STATUS, REQUIREMENT_KINDS, REQUIREMENT_STATUSES
from .one_line_records import FUNCTION_DESCRIPTION as BRIDGE_DESCRIPTION
from .one_line_records import one_line_parameters_schema
from .query import (
    AGGREGATION_PROPERTIES,
    CONDITION_PROPERTIES,
    ORDERING_PROPERTIES,
    RELATIONSHIP_PROPERTIES,
    REQUIRED_SPANS,
    REQUIREMENT_PROPERTIES,
    SLOT_KINDS,
    SLOT_PREFIXES,
    SUBMISSION_PROPERTIES,
)
from .refs import reference_pattern

SCHEMA_ID = "https://canna.local/contracts/submit_semantic_query/provisional-1"

FUNCTION_NAME = "submit_semantic_query"

DESCRIPTION = (
    "Account for the question's explicit requirements using only the references this "
    "request offered. Values, comparisons, directions and limits are submitted as spans "
    "copied from the question; the server derives their executable form."
)


def ref_schema(slot: str) -> dict[str, Any]:
    """A reference of exactly the kind this slot accepts."""
    prefix = SLOT_PREFIXES[slot]
    return {
        "type": "string",
        "pattern": reference_pattern(SLOT_KINDS[slot]),
        "description": f"an opaque {prefix}_ reference offered by this request",
    }


def _ref_array(slot: str) -> dict[str, Any]:
    return {"type": "array", "items": ref_schema(slot)}


def _span(required: bool) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "string",
        "description": "text copied from the question, not a normalised value",
    }
    if required:
        schema["minLength"] = 1
    return schema


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


CONDITION_SCHEMA = _object(
    {
        "field_ref": ref_schema("condition.field_ref"),
        "comparison_span": _span(True),
        "value_span": _span(True),
    },
    ["field_ref", *REQUIRED_SPANS["condition"]],
)
ORDERING_SCHEMA = _object(
    {"field_ref": ref_schema("ordering.field_ref"), "direction_span": _span(True)},
    ["field_ref", *REQUIRED_SPANS["ordering"]],
)
AGGREGATION_SCHEMA = _object(
    {"field_ref": ref_schema("aggregation.field_ref"), "function_span": _span(True)},
    ["field_ref", *REQUIRED_SPANS["aggregation"]],
)
RELATIONSHIP_SCHEMA = _object(
    {
        "predicate_ref": ref_schema("relationship.predicate_ref"),
        "anchor_entity_ref": ref_schema("relationship.anchor_entity_ref"),
    },
    ["predicate_ref", "anchor_entity_ref"],
)

REQUIREMENT_SCHEMA = _object(
    {
        "requirement_id": {"type": "string", "minLength": 1},
        "kind": {"type": "string", "enum": list(REQUIREMENT_KINDS)},
        "status": {"type": "string", "enum": list(REQUIREMENT_STATUSES)},
        "source_span": _span(True),
        "target_dataset_refs": _ref_array("target_dataset_refs"),
        "field_refs": _ref_array("field_refs"),
        "output_field_refs": _ref_array("output_field_refs"),
        "conditions": {"type": "array", "items": CONDITION_SCHEMA},
        "ordering": ORDERING_SCHEMA,
        "limit_span": _span(False),
        "aggregation": AGGREGATION_SCHEMA,
        "grouping_field_refs": _ref_array("grouping_field_refs"),
        "relationship": RELATIONSHIP_SCHEMA,
    },
    ["requirement_id", "kind", "status", *REQUIRED_SPANS["requirement"]],
)

SUBMISSION_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": SCHEMA_ID,
    "title": FUNCTION_NAME,
    "description": DESCRIPTION,
    "x-contract-status": CONTRACT_STATUS,
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "requirements": {"type": "array", "minItems": 1, "items": REQUIREMENT_SCHEMA},
        "unaccounted_spans": {
            "type": "array",
            "items": _span(True),
            "description": (
                "parts of the question this accounting did not cover; a non-empty list "
                "prevents execution"
            ),
        },
    },
    "required": ["requirements"],
}


def tool_definition() -> dict[str, Any]:
    """The provider-neutral declaration."""
    return {
        "name": FUNCTION_NAME,
        "description": DESCRIPTION,
        "x-contract-status": CONTRACT_STATUS,
        "input_schema": SUBMISSION_SCHEMA,
    }


def hcx_wire_schema() -> dict[str, Any]:
    """What HCX is actually sent: one object with one required string.

    Not this module's schema, and since 2026-08-31 not the grouped-flat schema
    either. Both were refused with ``40009`` before any tool was emitted, while
    a declaration of exactly this shape was accepted and emitted a call. The
    declaration shape is therefore unchanged; what travels inside the string is
    not. Writing JSON inside a JSON string cost the model quote escaping,
    non-ASCII escaping and brace balance at once, and it failed one of the three
    on every attempt. Record lines have no quotes to escape and no brackets to
    balance, so both defects are gone from the notation rather than argued about
    in the prompt.

    Since 2026-09-01 those lines are one record each. Two calls emitted a tool
    against this declaration and both wrote a record on a line — three of them,
    no free-standing key line, one closing line for the whole document — so the
    notation inside the string follows what was observed rather than arguing
    with it. ``one_line_records.parse_tool_arguments`` reads it and hands it to
    the parsers that already existed.

    A fresh object every call.
    """
    return one_line_parameters_schema()


def hcx_tool_definition() -> dict[str, Any]:
    """The same contract in the shape the existing HCX client binds tools in.

    The probe's provider passes one tool mapping straight through to
    ``bind_tools``, and that client expects the OpenAI-style function envelope.
    The name stays ``submit_semantic_query``: it is the logical tool's name and
    the server's, and the 2026-08-31 probes found no evidence that changing it
    helps. If a provider ever needs a different name on the wire, it belongs
    here in the adapter and nowhere behind it.
    """
    return {
        "type": "function",
        "function": {
            "name": FUNCTION_NAME,
            "description": BRIDGE_DESCRIPTION,
            "parameters": hcx_wire_schema(),
        },
    }


def schema_properties() -> dict[str, frozenset[str]]:
    """Every object in the schema and the properties it allows."""
    return {
        "submission": frozenset(SUBMISSION_SCHEMA["properties"]),
        "requirement": frozenset(REQUIREMENT_SCHEMA["properties"]),
        "condition": frozenset(CONDITION_SCHEMA["properties"]),
        "ordering": frozenset(ORDERING_SCHEMA["properties"]),
        "aggregation": frozenset(AGGREGATION_SCHEMA["properties"]),
        "relationship": frozenset(RELATIONSHIP_SCHEMA["properties"]),
    }


def parser_properties() -> dict[str, frozenset[str]]:
    """The same question, asked of the parser."""
    return {
        "submission": SUBMISSION_PROPERTIES,
        "requirement": REQUIREMENT_PROPERTIES,
        "condition": CONDITION_PROPERTIES,
        "ordering": ORDERING_PROPERTIES,
        "aggregation": AGGREGATION_PROPERTIES,
        "relationship": RELATIONSHIP_PROPERTIES,
    }


def _required_spans(schema: dict[str, Any]) -> frozenset[str]:
    """Span properties this object will not accept as empty.

    Only ``*_span`` names count. ``requirement_id`` is also non-empty, but it is
    an identifier rather than a quotation from the question, and the parser
    enforces it by a different rule.
    """
    return frozenset(
        name
        for name, node in schema["properties"].items()
        if name.endswith("_span")
        and node.get("minLength") == 1
        and name in schema["required"]
    )


def schema_required_spans() -> dict[str, frozenset[str]]:
    """The spans the schema will not accept as empty."""
    return {
        "requirement": _required_spans(REQUIREMENT_SCHEMA),
        "condition": _required_spans(CONDITION_SCHEMA),
        "ordering": _required_spans(ORDERING_SCHEMA),
        "aggregation": _required_spans(AGGREGATION_SCHEMA),
    }


def parser_required_spans() -> dict[str, frozenset[str]]:
    return {key: frozenset(value) for key, value in REQUIRED_SPANS.items()}


def schema_ref_patterns() -> dict[str, str]:
    """Each reference slot and the pattern the schema constrains it to."""
    return {slot: ref_schema(slot)["pattern"] for slot in SLOT_PREFIXES}
