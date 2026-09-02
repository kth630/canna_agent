"""The envelope HCX-007 accepts, wrapped around the contract it refuses.

Five live calls on 2026-08-31 established two facts that have to be held
together. A declaration with one required string property was accepted and
emitted a tool call. Every declaration carrying the grouped-flat structure was
refused with ``40009`` before any tool was emitted — including one smaller than
a structurally identical declaration the same provider accepted 93 times out of
93 the day before. Size and structure were ruled out as the difference; what
remains was not worth more calls to isolate.

So the structure stops travelling as JSON Schema and starts travelling as a
string. The tool declares one required ``submission_json`` property, which is
the shape the provider accepted; the grouped-flat payload goes inside it, and
the fields, enums and rules the schema used to state are stated in the system
message instead — where they were always instruction rather than contract.

Nothing behind the envelope moves. What comes back is unwrapped, parsed as
JSON, and handed to ``parse_grouped_flat``, which assembles it into the
canonical submission and hands that to ``parse_submission``. The server's rules
are enforced exactly once, in the places they already lived. This module adds
four checks and only four, all of them about the envelope: the arguments are an
object, they carry ``submission_json`` and nothing else, the string is JSON, and
that JSON is an object. Everything else it refuses, it refuses by passing the
payload on to code that was already refusing it.

A string-typed payload is weaker on the wire than a schema — the provider will
not reject a malformed submission for us any more. That trade only costs
something if the server were relying on the provider to validate, and it never
was: the schema and the parser were kept in parity precisely so the parser
could stand alone.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .contract import REQUIREMENT_KINDS, REQUIREMENT_STATUSES
from .grouped_flat import (
    DETAIL_CONDITION,
    DETAIL_KINDS,
    LIST_ROLES,
    P_DETAIL_KIND,
    P_DETAIL_RECORDS,
    P_KIND,
    P_LIMIT_SPAN,
    P_REF,
    P_REF_RECORDS,
    P_REQUIREMENT_ID,
    P_REQUIREMENT_RECORDS,
    P_ROLE,
    P_SOURCE_SPAN,
    P_SPAN,
    P_STATUS,
    P_UNACCOUNTED_SPANS,
    P_VALUE_SPAN,
    REF_ROLES,
    RELATION_ROLES,
    parse_grouped_flat,
)
from .query import ShapeProblem, Submission

__all__ = [
    "CODE_ENVELOPE_NOT_AN_OBJECT",
    "CODE_MALFORMED_SUBMISSION_JSON",
    "CODE_SUBMISSION_JSON_NOT_AN_OBJECT",
    "CODE_UNKNOWN_ENVELOPE_PROPERTY",
    "ENVELOPE_DESCRIPTION",
    "ENVELOPE_PROPERTY",
    "FUNCTION_DESCRIPTION",
    "bridge_parameters_schema",
    "envelope_diagnostics",
    "parse_tool_arguments",
    "submission_guidance",
]

ENVELOPE_PROPERTY = "submission_json"

CODE_ENVELOPE_NOT_AN_OBJECT = "envelope_not_an_object"
CODE_UNKNOWN_ENVELOPE_PROPERTY = "unknown_envelope_property"
CODE_MALFORMED_SUBMISSION_JSON = "malformed_submission_json"
CODE_SUBMISSION_JSON_NOT_AN_OBJECT = "submission_json_not_an_object"

# Two short descriptions rather than one long one repeated: the function says
# what the call is for, the property says what the string holds.
FUNCTION_DESCRIPTION = "Account for the question's explicit requirements."
ENVELOPE_DESCRIPTION = "The accounting as a JSON object, serialised to a string."


def bridge_parameters_schema() -> dict[str, Any]:
    """One object, one required string. The shape the provider accepted.

    Deliberately as plain as the accepted declaration: no ``additionalProperties``,
    no ``enum``, no nesting. A fresh object each call.
    """
    return {
        "type": "object",
        "properties": {
            ENVELOPE_PROPERTY: {"type": "string", "description": ENVELOPE_DESCRIPTION}
        },
        "required": [ENVELOPE_PROPERTY],
    }


def submission_guidance() -> str:
    """What the grouped-flat schema used to say, for the system message.

    Rendered from the same tables the assembler routes by, so the instruction
    cannot drift away from what the server will accept.
    """
    roles = ", ".join(REF_ROLES)
    details = ", ".join(DETAIL_KINDS)
    relation_roles = " and ".join(RELATION_ROLES)
    list_roles = ", ".join(LIST_ROLES)
    return (
        f"Put a JSON object in {ENVELOPE_PROPERTY}, serialised as a string. "
        f"Its properties are {P_REQUIREMENT_RECORDS}, {P_REF_RECORDS}, "
        f"{P_DETAIL_RECORDS} and {P_UNACCOUNTED_SPANS}; use no others. "
        f"{P_REQUIREMENT_RECORDS} holds one object per requirement the question "
        f"states, with {P_REQUIREMENT_ID} (an id you choose), {P_KIND} (one of: "
        f"{', '.join(REQUIREMENT_KINDS)}), {P_STATUS} (one of: "
        f"{', '.join(REQUIREMENT_STATUSES)}), {P_SOURCE_SPAN} (the words asking for "
        f"it, copied from the question) and optionally {P_LIMIT_SPAN} (the words "
        "saying how many). "
        f"{P_REF_RECORDS} holds objects with {P_REQUIREMENT_ID}, {P_ROLE} (one of: "
        f"{roles}) and {P_REF} (an opaque reference this request offered). "
        f"{list_roles} may each appear more than once; {relation_roles} at most once. "
        f"{P_DETAIL_RECORDS} holds objects with {P_REQUIREMENT_ID}, {P_DETAIL_KIND} "
        f"(one of: {details}), {P_REF} (the field reference), {P_SPAN} (the "
        f"comparison, direction or function words) and, for {DETAIL_CONDITION} only, "
        f"{P_VALUE_SPAN} (the value words). One object is one condition: keep its "
        "comparison and its value together. A requirement may carry at most one "
        f"ordering and one aggregation. {P_UNACCOUNTED_SPANS} holds question text "
        "you did not account for. "
        f"Repeat {P_REQUIREMENT_ID} on every record so it is clear which requirement "
        "it belongs to, and never name a requirement you did not declare. "
        "Copy every span from the question exactly; do not normalise it into a value, "
        "an operator, a direction or a number. Use only references this request "
        "offered and never invent one. "
        "Set status to mapped when the offered references carry the meaning, "
        "unresolved when none do, and ambiguous when several meanings are possible "
        "and nothing decides between them. "
        "Do not produce SQL, tables, columns, joins, stable identifiers or any other "
        "physical execution detail. "
        # The 2026-08-31 bridge call was accepted and emitted a tool, then failed
        # to parse. What a model can get wrong here is the envelope rather than
        # the accounting, so the envelope's rules are stated last and plainly.
        f"The value of {ENVELOPE_PROPERTY} must itself be a string, not a JSON "
        f"object: serialise the object and send the resulting text. Decoding that "
        f"string with a JSON parser must yield the object described above, so it "
        f"must start with {{ and end with }}. Do not wrap it in a markdown code "
        f"fence, do not put a language tag, explanation, label or any other "
        f"character before or after it, and do not send it as several strings. "
        f"Give the tool no argument other than {ENVELOPE_PROPERTY}. "
        # The 2026-08-31 call failed on an "Invalid \\uXXXX escape" a fifth of
        # the way into the string, with no fence and an opening brace: the JSON
        # was being written with escape sequences rather than the characters
        # themselves, and one of them was malformed. Korean text has no reason to
        # be escaped at all, so the instruction is to stop escaping it.
        "Write Korean and other non-ASCII text as the characters themselves. Do "
        "not turn them into \\u escape sequences. The only backslashes in the "
        "JSON should be the ones JSON requires inside a string, and the document "
        "must be complete, ending with the closing brace. "
        # 2026-08-31: the model finished normally (finish_reason tool_calls, 269
        # of 8192 tokens) and still handed back an unterminated document. It was
        # not running out of room, so what is left to reduce is how much quoting
        # and structure it has to keep track of while writing.
        "Write it on one line, compact, with no line breaks and no indentation. "
        "Omit any property you have nothing to put in rather than sending it "
        "empty. Keep each requirement_id to one or two characters. Before you "
        "finish, make sure every brace and bracket you opened is closed."
    )


def _string_shape(value: str) -> dict[str, Any]:
    """Form, not content: how the string opens, how it closes, how long it is.

    Enough to tell a code fence from a preamble from a truncation without
    keeping a character of what the model wrote.
    """
    stripped = value.strip()
    return {
        "length": len(value),
        "starts_with_code_fence": stripped.startswith("```"),
        "first_char_is_open_brace": stripped[:1] == "{",
        "last_char_is_close_brace": stripped[-1:] == "}",
    }


def envelope_diagnostics(
    arguments: Any, parsed: Submission | None = None
) -> dict[str, Any]:
    """Shape metadata for a refused call. Never the content.

    Enough to say which stage refused and why without keeping what the model
    wrote: types, property names, whether the JSON decoded, and the problem
    codes the parsers produced. No span, no reference, no payload text.
    """
    diagnostics: dict[str, Any] = {
        "raw_args_type": type(arguments).__name__,
        "argument_keys": sorted(str(key) for key in arguments)
        if isinstance(arguments, Mapping)
        else [],
        "submission_json_value_type": "absent",
        "json_decoded": "not_attempted",
        "parser_problem_codes": [],
    }
    if isinstance(arguments, Mapping) and ENVELOPE_PROPERTY in arguments:
        value = arguments[ENVELOPE_PROPERTY]
        diagnostics["submission_json_value_type"] = type(value).__name__
        if isinstance(value, str):
            diagnostics.update(_string_shape(value))
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError as error:
                diagnostics["json_decoded"] = "no"
                # where and what kind, never the text: a failure at the very end
                # of the string reads as truncation, one at the start as a fence
                # or a preamble, one in the middle as a quoting or escape fault
                diagnostics["decode_error"] = error.msg
                diagnostics["decode_error_position_ratio"] = (
                    round(error.pos / len(value), 3) if value else 0.0
                )
            else:
                diagnostics["json_decoded"] = "yes"
                diagnostics["decoded_type"] = type(decoded).__name__
    if parsed is not None:
        diagnostics["parser_problem_codes"] = sorted(
            {problem.code for problem in parsed.problems}
        )
    return diagnostics


def parse_tool_arguments(arguments: Any) -> Submission:
    """Unwrap the envelope, then let the existing parsers decide.

    Fail-closed at every step, and every refusal below the envelope belongs to
    code this function only calls.
    """
    if not isinstance(arguments, Mapping):
        return Submission(
            None,
            (ShapeProblem(CODE_ENVELOPE_NOT_AN_OBJECT, "tool arguments are not an object"),),
        )
    unknown = sorted(set(arguments) - {ENVELOPE_PROPERTY})
    if unknown:
        return Submission(
            None,
            (
                ShapeProblem(
                    CODE_UNKNOWN_ENVELOPE_PROPERTY,
                    f"tool arguments carry unknown {unknown}",
                ),
            ),
        )
    raw = arguments.get(ENVELOPE_PROPERTY)
    if not isinstance(raw, str):
        return Submission(
            None,
            (
                ShapeProblem(
                    CODE_MALFORMED_SUBMISSION_JSON,
                    f"{ENVELOPE_PROPERTY} must be a JSON string",
                ),
            ),
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        return Submission(
            None,
            (
                ShapeProblem(
                    CODE_MALFORMED_SUBMISSION_JSON,
                    f"{ENVELOPE_PROPERTY} is not valid JSON: {error.msg}",
                ),
            ),
        )
    if not isinstance(payload, Mapping):
        return Submission(
            None,
            (
                ShapeProblem(
                    CODE_SUBMISSION_JSON_NOT_AN_OBJECT,
                    f"{ENVELOPE_PROPERTY} must hold a JSON object",
                ),
            ),
        )
    return parse_grouped_flat(payload)
