"""One record per line, written the way the provider actually writes them.

Two live calls, 2026-08-31 and 2026-09-01, both refused at the multiline reader
with the same three codes. The second one carried the shape classes added after
the first, and they say what the codes could not: three header lines each
carrying something else, no free-standing key line at all, one ``END`` for the
whole document. The model was writing a record on a line.

So this module reads that. It is a second notation, not a loosening of the
first: ``line_records`` is untouched and still refuses everything it refused.
This is the Runtime's selected wire notation as of 2026-09-01. A line is a record — the token, then
``key=value`` segments separated by ``|`` — and the document may close with one
``END`` line, which is the one thing both notations spell the same way.

Nothing behind the notation moves. The keys come from ``grouped_flat``'s own
property constants rather than being retyped, the reader produces exactly the
grouped-flat object ``parse_grouped_flat`` already takes, and every decision
after that — reference kinds, required spans, the three statuses, orphan and
conflicting records, duplicate requirements — is made where it was already made.
This file owns the notation's own failures and refuses them rather than
repairing them: a first segment nobody defined, a segment with no ``=``, a
segment with no key, a key repeated in one record, and an ``END`` anywhere but
alone at the end.

The separator is the cost of the notation. A value is everything after its first
``=``, so ``=`` inside a value is safe, but ``|`` is not, and neither is a line
break: a value holding either cannot be written honestly, so the encoder refuses
it as ``unrepresentable_value`` instead of trimming, escaping or flattening it.
A span that cannot be carried exactly is not carried at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contract import REQUIREMENT_KINDS, REQUIREMENT_STATUSES
from .grouped_flat import (
    CODE_CONFLICTING_RECORD,
    CODE_DUPLICATE_RECORD,
    CODE_ORPHAN_RECORD,
    CODE_UNKNOWN_DETAIL_KIND,
    CODE_UNKNOWN_ROLE,
    DETAIL_CONDITION,
    DETAIL_KINDS,
    DETAIL_RECORD_PROPERTIES,
    GROUPED_FLAT_PROPERTIES,
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
    REF_RECORD_PROPERTIES,
    REF_ROLES,
    RELATION_ROLES,
    REQUIREMENT_RECORD_PROPERTIES,
    parse_grouped_flat,
)
from .hcx_bridge import CODE_ENVELOPE_NOT_AN_OBJECT, CODE_UNKNOWN_ENVELOPE_PROPERTY

# The faults both notations can have are named once, in the notation that named
# them first: the refusal codes, the line-break characters it will not read, and
# the three shapes — a bullet, JSON punctuation, a line break written as two
# characters — that are the same mistake whichever notation was asked for.
# Reusing them keeps one vocabulary rather than a second set of names for the
# same things; if the multiline notation is ever retired, they move somewhere
# shared rather than being renamed.
from .line_records import (
    CODE_DUPLICATE_KEY,
    CODE_MALFORMED_KEY_LINE,
    CODE_STRAY_LINE,
    CODE_UNKNOWN_RECORD,
    CODE_UNSUPPORTED_LINE_BREAK,
    LINE_BREAK_CHARACTERS,
    LINE_CLASS_BULLET,
    LINE_CLASS_JSON,
    LITERAL_BACKSLASH_N,
    classify_line,
)
from .query import (
    CODE_DUPLICATE_REQUIREMENT_ID,
    CODE_EMPTY_SUBMISSION,
    CODE_MALFORMED_REF,
    CODE_MALFORMED_REQUIREMENT,
    CODE_MALFORMED_SUBMISSION,
    CODE_MISSING_REQUIRED_SPAN,
    CODE_MISSING_REQUIREMENT_ID,
    CODE_UNKNOWN_KIND,
    CODE_UNKNOWN_PROPERTY,
    CODE_UNKNOWN_STATUS,
    CODE_WRONG_REF_KIND,
    CODE_WRONG_TYPE,
    ShapeProblem,
    Submission,
)

__all__ = [
    "ASSIGN",
    "CODE_UNREPRESENTABLE_VALUE",
    "END",
    "ENVELOPE_PROPERTY",
    "ONE_LINE_CLASSES",
    "ONE_LINE_DIAGNOSTIC_FIELDS",
    "RECORD_KEYS",
    "RECORD_PROPERTIES",
    "RECORD_TOKENS",
    "SEGMENT",
    "OneLineFormatError",
    "classify_one_line",
    "one_line_envelope_diagnostics",
    "one_line_grouped_flat_record_properties",
    "one_line_parameters_schema",
    "one_line_record_keys",
    "one_line_submission_guidance",
    "parse_one_line_submission",
    "parse_tool_arguments",
    "read_one_line_records",
    "render_one_line_records",
]

# ------------------------------------------------------------------- notation

RECORD_REQUIREMENT = "REQ"
RECORD_REFERENCE = "REF"
RECORD_DETAIL = "DETAIL"
# The grouped-flat object carries the spans a submission did not account for,
# and dropping them would be a quieter submission than the one that was written.
# It is a record here for the same reason it is one in the multiline notation:
# an unaccounted span is a bare string with nowhere else to go.
RECORD_UNACCOUNTED = "UNACCOUNTED"
END = "END"

# The keys each record may carry, in the order they are written. The names are
# ``grouped_flat``'s own property constants: this table decides the order and
# nothing else, and a test holds it against that module's property sets so a key
# cannot be added here without being a real property there.
REQUIREMENT_KEYS: tuple[str, ...] = (
    P_REQUIREMENT_ID,
    P_KIND,
    P_STATUS,
    P_SOURCE_SPAN,
    P_LIMIT_SPAN,
)
REFERENCE_KEYS: tuple[str, ...] = (P_REQUIREMENT_ID, P_ROLE, P_REF)
DETAIL_KEYS: tuple[str, ...] = (
    P_REQUIREMENT_ID,
    P_DETAIL_KIND,
    P_REF,
    P_SPAN,
    P_VALUE_SPAN,
)
UNACCOUNTED_KEYS: tuple[str, ...] = (P_SPAN,)

RECORD_KEYS: dict[str, tuple[str, ...]] = {
    RECORD_REQUIREMENT: REQUIREMENT_KEYS,
    RECORD_REFERENCE: REFERENCE_KEYS,
    RECORD_DETAIL: DETAIL_KEYS,
    RECORD_UNACCOUNTED: UNACCOUNTED_KEYS,
}
RECORD_TOKENS: tuple[str, ...] = tuple(RECORD_KEYS)

# Which grouped-flat property each record fills.
RECORD_PROPERTIES: dict[str, str] = {
    RECORD_REQUIREMENT: P_REQUIREMENT_RECORDS,
    RECORD_REFERENCE: P_REF_RECORDS,
    RECORD_DETAIL: P_DETAIL_RECORDS,
    RECORD_UNACCOUNTED: P_UNACCOUNTED_SPANS,
}

# Between segments, and between a key and its value. Only the first ``=`` on a
# segment separates: everything after it is the value, exactly as written.
SEGMENT = "|"
ASSIGN = "="
LINE_ENDING = "\n"

# A value that cannot be written in this notation without being altered. The
# only new code this notation needs; every other refusal reuses one that exists.
CODE_UNREPRESENTABLE_VALUE = "unrepresentable_value"


class OneLineFormatError(ValueError):
    """A value cannot be written in this notation without being altered."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


# --------------------------------------------------------------------- reading


def _line_break_in(line: str) -> str:
    for character in LINE_BREAK_CHARACTERS:
        if character in line:
            return character
    return ""


def _end_problem(lines: list[str]) -> ShapeProblem | None:
    """``END`` is optional, singular, and last. Anything else is refused.

    Not repaired and not ignored: an ``END`` in the middle says the document
    was assembled from parts, and a second one says the same thing louder.
    """
    populated = [(number, line.rstrip()) for number, line in enumerate(lines, 1) if line.strip()]
    ends = [number for number, marker in populated if marker == END]
    if not ends:
        return None
    if len(ends) > 1:
        return ShapeProblem(CODE_STRAY_LINE, f"{END} appears {len(ends)} times")
    if ends[0] != populated[-1][0]:
        return ShapeProblem(CODE_STRAY_LINE, f"{END} is not the last line")
    return None


def read_one_line_records(text: Any) -> tuple[dict[str, Any] | None, tuple[ShapeProblem, ...]]:
    """Read the notation into a grouped-flat object, refusing what it cannot read.

    Returns ``(None, problems)`` when the document's own structure is
    untrustworthy — a stray line break, or an ``END`` that is not alone at the
    end — because nothing after that says anything reliable. Otherwise the
    object is returned together with whatever problems were found, so the caller
    sees these and the parser's own.
    """
    if not isinstance(text, str):
        return None, (ShapeProblem(CODE_MALFORMED_SUBMISSION, "the submission is not text"),)

    lines = text.replace("\r\n", LINE_ENDING).split(LINE_ENDING)
    for number, line in enumerate(lines, 1):
        found = _line_break_in(line)
        if found:
            return None, (
                ShapeProblem(
                    CODE_UNSUPPORTED_LINE_BREAK,
                    f"line {number} contains {found!r}, which is not a line ending here",
                ),
            )
    misplaced = _end_problem(lines)
    if misplaced is not None:
        return None, (misplaced,)

    problems: list[ShapeProblem] = []
    collected: dict[str, list[dict[str, str]]] = {token: [] for token in RECORD_TOKENS}

    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if line.rstrip() == END:
            continue
        # No normalisation anywhere on this line: the first segment is the token
        # exactly as written, and the last segment's trailing spaces are span
        # content, not layout.
        segments = line.split(SEGMENT)
        token = segments[0]
        if token not in RECORD_KEYS:
            problems.append(
                ShapeProblem(CODE_UNKNOWN_RECORD, f"line {number} opens with no record token")
            )
            continue
        record: dict[str, str] = {}
        keep = True
        for position, segment in enumerate(segments[1:], 2):
            key, separator, value = segment.partition(ASSIGN)
            if not separator or not key:
                problems.append(
                    ShapeProblem(
                        CODE_MALFORMED_KEY_LINE,
                        f"line {number} segment {position} carries no key and {ASSIGN}",
                    )
                )
                keep = False
                continue
            if key not in RECORD_KEYS[token]:
                problems.append(
                    ShapeProblem(
                        CODE_UNKNOWN_PROPERTY, f"{token} on line {number} has unknown ['{key}']"
                    )
                )
                keep = False
                continue
            if key in record:
                problems.append(
                    ShapeProblem(CODE_DUPLICATE_KEY, f"{token} on line {number} repeats {key}")
                )
                keep = False
                continue
            record[key] = value
        if keep:
            collected[token].append(record)

    return _payload(collected, problems), tuple(problems)


def _payload(
    collected: Mapping[str, list[dict[str, str]]], problems: list[ShapeProblem]
) -> dict[str, Any]:
    """Assemble the grouped-flat object, keeping absent lists absent.

    ``requirement_records`` is always present, empty included: an empty
    submission has to reach the parser as an empty submission rather than as a
    missing property.
    """
    payload: dict[str, Any] = {P_REQUIREMENT_RECORDS: collected[RECORD_REQUIREMENT]}
    for token in (RECORD_REFERENCE, RECORD_DETAIL):
        if collected[token]:
            payload[RECORD_PROPERTIES[token]] = collected[token]
    spans: list[str] = []
    for index, record in enumerate(collected[RECORD_UNACCOUNTED], 1):
        span = record.get(P_SPAN, "")
        if not span.strip():
            # The only content check this module makes, because it is the only
            # record the grouped-flat object has no record for: an unaccounted
            # span arrives there as a bare string, so an empty one would arrive
            # as an empty string nobody would refuse.
            problems.append(
                ShapeProblem(
                    CODE_MISSING_REQUIRED_SPAN,
                    f"{RECORD_UNACCOUNTED} record {index} carries no {P_SPAN}",
                )
            )
            continue
        spans.append(span)
    if spans:
        payload[P_UNACCOUNTED_SPANS] = spans
    return payload


def parse_one_line_submission(text: Any) -> Submission:
    """Read the notation and hand the result to the parsers that already exist."""
    payload, problems = read_one_line_records(text)
    if payload is None:
        return Submission(None, problems)
    parsed = parse_grouped_flat(payload)
    return Submission(parsed.query, (*problems, *parsed.problems))


# --------------------------------------------------------------------- writing


def _value(record_token: str, key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise OneLineFormatError(
            CODE_WRONG_TYPE, f"{record_token}.{key} is {type(value).__name__}, not text"
        )
    found = (
        _line_break_in(value)
        or (LINE_ENDING if LINE_ENDING in value else "")
        or (SEGMENT if SEGMENT in value else "")
    )
    if found:
        raise OneLineFormatError(
            CODE_UNREPRESENTABLE_VALUE,
            f"{record_token}.{key} contains {found!r} and cannot be written on one line",
        )
    return value


def _record_line(record_token: str, record: Mapping[str, Any]) -> str:
    unknown = sorted(set(record) - set(RECORD_KEYS[record_token]))
    if unknown:
        raise OneLineFormatError(CODE_UNKNOWN_PROPERTY, f"{record_token} has unknown {unknown}")
    segments = [record_token]
    segments += [
        f"{key}{ASSIGN}{_value(record_token, key, record[key])}"
        for key in RECORD_KEYS[record_token]
        if key in record
    ]
    return SEGMENT.join(segments)


def render_one_line_records(wire: Mapping[str, Any]) -> str:
    """Write a grouped-flat object in this notation, or refuse to write it.

    The inverse of the reader, used to show the notations carry the same object
    and to build wire text in tests without hand-writing records. No ``END`` is
    written: the reader accepts one and does not need one, and the shorter
    document is the one this notation exists to produce. A value that cannot
    survive the round trip — anything that is not text, anything holding a line
    break or the segment separator — raises rather than being altered into
    something the question never said.
    """
    if not isinstance(wire, Mapping):
        raise OneLineFormatError(
            CODE_MALFORMED_SUBMISSION, "the grouped-flat payload is not an object"
        )
    unknown = sorted(set(wire) - GROUPED_FLAT_PROPERTIES)
    if unknown:
        raise OneLineFormatError(
            CODE_UNKNOWN_PROPERTY, f"the grouped-flat payload has unknown {unknown}"
        )

    lines: list[str] = []
    for token in (RECORD_REQUIREMENT, RECORD_REFERENCE, RECORD_DETAIL):
        for record in wire.get(RECORD_PROPERTIES[token], ()) or ():
            if not isinstance(record, Mapping):
                raise OneLineFormatError(CODE_WRONG_TYPE, f"a {token} record is not an object")
            lines.append(_record_line(token, record))
    for span in wire.get(P_UNACCOUNTED_SPANS, ()) or ():
        lines.append(_record_line(RECORD_UNACCOUNTED, {P_SPAN: span}))
    return LINE_ENDING.join([*lines, ""])


# -------------------------------------------------------------------- guidance


def one_line_submission_guidance() -> str:
    """How to write the notation, rendered from the tables the reader reads by.

    Every field name, role, detail kind, requirement kind and status comes from
    the server's own tables, so the instruction cannot drift from what the
    server will accept, and no question, product or reference is named anywhere
    in it. The Runtime system message uses this renderer directly.
    """
    keys = {token: SEGMENT.join(RECORD_KEYS[token]) for token in RECORD_TOKENS}
    return (
        "Write one record per line. Do not write JSON: no braces, no brackets, no "
        "quotation marks around anything, no backslash escapes. A record is the word "
        f"{RECORD_REQUIREMENT}, {RECORD_REFERENCE}, {RECORD_DETAIL} or "
        f"{RECORD_UNACCOUNTED}, then one {SEGMENT} before each field, each field "
        f"written as the field name, {ASSIGN}, and the value. Everything after the "
        f"first {ASSIGN} of a field is the value, exactly as you write it, so a value "
        f"must never contain {SEGMENT} or a line break and must not be wrapped in "
        "quotes. Write non-ASCII text as the characters themselves. Omit a field "
        "entirely rather than writing one you have nothing to put in. You may write "
        f"{END} on its own as the last line, once, or leave it out. "
        f"{RECORD_REQUIREMENT} is one line per requirement the question states, with "
        f"{keys[RECORD_REQUIREMENT]}; {P_LIMIT_SPAN} only when the question says how "
        f"many. {P_REQUIREMENT_ID} is an id you choose, one or two characters, and "
        f"every other line repeats it. {P_KIND} is one of: "
        f"{', '.join(REQUIREMENT_KINDS)}. {P_STATUS} is one of: "
        f"{', '.join(REQUIREMENT_STATUSES)}. "
        f"{RECORD_REFERENCE} is one line per reference, with {keys[RECORD_REFERENCE]}. "
        f"{P_ROLE} is one of: {', '.join(REF_ROLES)}. {', '.join(LIST_ROLES)} may each "
        f"appear more than once; {' and '.join(RELATION_ROLES)} at most once. {P_REF} "
        "is an opaque reference this request offered. "
        f"{RECORD_DETAIL} is one line per condition, ordering or aggregation, with "
        f"{keys[RECORD_DETAIL]}. {P_DETAIL_KIND} is one of: {', '.join(DETAIL_KINDS)}. "
        f"{P_REF} is the field reference, {P_SPAN} is the comparison, direction or "
        f"function words, and {P_VALUE_SPAN} is the value words, for {DETAIL_CONDITION} "
        "only. One line is one condition: keep its comparison and its value on the "
        "same line. A requirement may carry at most one ordering and one aggregation. "
        f"{RECORD_UNACCOUNTED} is one line per part of the question you did not "
        f"account for, with {keys[RECORD_UNACCOUNTED]}. "
        "Copy every span from the question exactly; do not normalise it into a value, "
        "an operator, a direction or a number. Use only references this request offered "
        "and never invent one. Never name a requirement you did not declare. "
        f"Set {P_STATUS} to {REQUIREMENT_STATUSES[0]} when the offered references carry "
        f"the meaning, {REQUIREMENT_STATUSES[1]} when none do, and "
        f"{REQUIREMENT_STATUSES[2]} when several meanings are possible and nothing "
        "decides between them. "
        "Do not produce SQL, tables, columns, joins, stable identifiers or any other "
        "physical execution detail."
    )


def one_line_record_keys() -> dict[str, tuple[str, ...]]:
    """Every record and the keys it accepts, published for parity checking."""
    return {token: RECORD_KEYS[token] for token in RECORD_TOKENS}


def one_line_grouped_flat_record_properties() -> dict[str, frozenset[str]]:
    """The same records as ``grouped_flat`` defines them, for the same check."""
    return {
        RECORD_REQUIREMENT: REQUIREMENT_RECORD_PROPERTIES,
        RECORD_REFERENCE: REF_RECORD_PROPERTIES,
        RECORD_DETAIL: DETAIL_RECORD_PROPERTIES,
    }


# -------------------------------------------------------------------- envelope

# The property name does not change with the notation. The provider accepted a
# declaration of exactly this shape on 2026-08-31 and emitted a call against it
# on 2026-09-01; what travels inside the string is the only thing being changed,
# so the declaration stays byte-identical in shape.
ENVELOPE_PROPERTY = "submission_text"

ENVELOPE_DESCRIPTION = "The accounting, one record per line."
FUNCTION_DESCRIPTION = "Account for the question's explicit requirements."


def one_line_parameters_schema() -> dict[str, Any]:
    """One object, one required string — the declaration the provider accepted.

    Identical in shape to the notations before it, because that shape is the one
    the provider took; what changes is only what the string holds. A fresh
    object each call.
    """
    return {
        "type": "object",
        "properties": {
            ENVELOPE_PROPERTY: {"type": "string", "description": ENVELOPE_DESCRIPTION}
        },
        "required": [ENVELOPE_PROPERTY],
    }


def parse_tool_arguments(arguments: Any) -> Submission:
    """Unwrap the envelope, then let the existing parsers decide.

    Three checks and only three, all of them about the envelope: the arguments
    are an object, they carry this property and nothing else, and its value is
    text. There is no decode step left to fail.
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
                    CODE_UNKNOWN_ENVELOPE_PROPERTY, f"tool arguments carry unknown {unknown}"
                ),
            ),
        )
    raw = arguments.get(ENVELOPE_PROPERTY)
    if not isinstance(raw, str):
        return Submission(
            None,
            (ShapeProblem(CODE_WRONG_TYPE, f"{ENVELOPE_PROPERTY} must be text"),),
        )
    return parse_one_line_submission(raw)


# ----------------------------------------------------- diagnosing a refusal

# What a refused call may be remembered by in this notation, approved on
# 2026-09-01. It is a different list from the multiline one because the shapes
# are different — there are no key lines here, and a segment is the unit that
# can be malformed — and it is held to the same rule: fixed names, counts and
# booleans decided in this file, and never a character the model wrote. No
# payload text, no span, no reference, no semantic or requirement identifier, no
# unrecognised token, no hash of any of them, no credential, no request id.
ONE_LINE_DIAGNOSTIC_FIELDS: tuple[str, ...] = (
    "raw_args_type",
    "envelope_property_present",
    "unknown_envelope_key_present",
    "submission_text_value_type",
    "length",
    "line_count",
    "record_line_counts",
    "unknown_record_line_count",
    "unknown_record_present",
    "unknown_key_present",
    "end_count",
    "end_position_valid",
    "pipe_present",
    "key_value_segment_count",
    "malformed_segment_count",
    "bullet_prefixed_line_count",
    "json_punctuation_present",
    "literal_backslash_n_present",
    "first_line_class",
    "last_line_class",
    "parser_problem_codes",
    "finish_reason",
    "output_tokens",
)

DIAGNOSTIC_VALUE_TYPES: tuple[str, ...] = (
    "absent",
    "array",
    "boolean",
    "null",
    "number",
    "object",
    "other",
    "string",
)
DIAGNOSTIC_FINISH_REASONS: tuple[str, ...] = (
    "content_filter",
    "length",
    "other",
    "stop",
    "tool_calls",
)
DIAGNOSTIC_PARSER_PROBLEM_CODES: frozenset[str] = frozenset(
    {
        CODE_CONFLICTING_RECORD,
        CODE_DUPLICATE_KEY,
        CODE_DUPLICATE_RECORD,
        CODE_DUPLICATE_REQUIREMENT_ID,
        CODE_EMPTY_SUBMISSION,
        CODE_ENVELOPE_NOT_AN_OBJECT,
        CODE_MALFORMED_KEY_LINE,
        CODE_MALFORMED_REF,
        CODE_MALFORMED_REQUIREMENT,
        CODE_MALFORMED_SUBMISSION,
        CODE_MISSING_REQUIRED_SPAN,
        CODE_MISSING_REQUIREMENT_ID,
        CODE_ORPHAN_RECORD,
        CODE_STRAY_LINE,
        CODE_UNKNOWN_DETAIL_KIND,
        CODE_UNKNOWN_ENVELOPE_PROPERTY,
        CODE_UNKNOWN_KIND,
        CODE_UNKNOWN_PROPERTY,
        CODE_UNKNOWN_RECORD,
        CODE_UNKNOWN_ROLE,
        CODE_UNKNOWN_STATUS,
        CODE_UNSUPPORTED_LINE_BREAK,
        CODE_WRONG_REF_KIND,
        CODE_WRONG_TYPE,
    }
)

# The classes this notation adds. ``LINE_CLASS_BULLET`` and ``LINE_CLASS_JSON``
# are the multiline notation's, imported rather than restated so the two
# notations cannot end up calling the same shape by two names.
LINE_CLASS_ABSENT = "absent"
LINE_CLASS_RECORD = "exact_record_line"
LINE_CLASS_END = "end"
LINE_CLASS_UNKNOWN_RECORD = "unknown_record_line"

ONE_LINE_CLASSES: tuple[str, ...] = (
    LINE_CLASS_ABSENT,
    LINE_CLASS_RECORD,
    LINE_CLASS_END,
    LINE_CLASS_BULLET,
    LINE_CLASS_JSON,
    LINE_CLASS_UNKNOWN_RECORD,
)


def classify_one_line(line: str) -> str:
    """Name the shape of one line. Never returns any part of the line itself.

    Bullets, JSON punctuation and the literal two-character line break are the
    same faults the multiline notation already named, so they are decided by its
    classifier rather than by a second opinion here.
    """
    text = line.strip()
    if not text:
        return LINE_CLASS_ABSENT
    borrowed = classify_line(line)
    if borrowed == LINE_CLASS_BULLET:
        return LINE_CLASS_BULLET
    if borrowed == LINE_CLASS_JSON:
        return LINE_CLASS_JSON
    if line.rstrip() == END:
        return LINE_CLASS_END
    if line.split(SEGMENT)[0] in RECORD_KEYS:
        return LINE_CLASS_RECORD
    return LINE_CLASS_UNKNOWN_RECORD


def _segment_shape(lines: list[str]) -> dict[str, Any]:
    """How many segments were written as ``key=value``, and how many were not.

    A segment is counted, never read: the key is compared against this module's
    own tables and then discarded, so an unknown key is a boolean and never a
    name.
    """
    key_value = 0
    malformed = 0
    unknown_key = False
    for line in lines:
        if classify_one_line(line) != LINE_CLASS_RECORD:
            continue
        segments = line.split(SEGMENT)
        token = segments[0]
        for segment in segments[1:]:
            key, separator, _value = segment.partition(ASSIGN)
            if not separator or not key:
                malformed += 1
                continue
            key_value += 1
            if key not in RECORD_KEYS[token]:
                unknown_key = True
    return {
        "key_value_segment_count": key_value,
        "malformed_segment_count": malformed,
        "unknown_key_present": unknown_key,
    }


def _text_shape(value: str) -> dict[str, Any]:
    """Form, not content: how the document is built, never what it says."""
    lines = value.replace("\r\n", LINE_ENDING).split(LINE_ENDING)
    classes = [classify_one_line(line) for line in lines]
    populated = [name for name in classes if name != LINE_CLASS_ABSENT]
    ends = [index for index, name in enumerate(classes) if name == LINE_CLASS_END]
    last_populated = max(
        (index for index, name in enumerate(classes) if name != LINE_CLASS_ABSENT),
        default=-1,
    )
    shape: dict[str, Any] = {
        "length": len(value),
        "line_count": len(lines),
        "record_line_counts": {
            token: sum(
                1
                for line, name in zip(lines, classes, strict=True)
                if name == LINE_CLASS_RECORD and line.split(SEGMENT)[0] == token
            )
            for token in RECORD_TOKENS
        },
        "unknown_record_line_count": populated.count(LINE_CLASS_UNKNOWN_RECORD),
        "end_count": len(ends),
        # Absent is valid, one at the end is valid, anything else is not.
        "end_position_valid": not ends or (len(ends) == 1 and ends[0] == last_populated),
        "pipe_present": SEGMENT in value,
        "bullet_prefixed_line_count": populated.count(LINE_CLASS_BULLET),
        "json_punctuation_present": (
            LINE_CLASS_JSON in populated
            or any(character in value for character in "{}[]")
            or '"' + ASSIGN in value
            or '":' in value
        ),
        "literal_backslash_n_present": LITERAL_BACKSLASH_N in value,
        "first_line_class": populated[0] if populated else LINE_CLASS_ABSENT,
        "last_line_class": populated[-1] if populated else LINE_CLASS_ABSENT,
    }
    shape.update(_segment_shape(lines))
    shape["unknown_record_present"] = shape["unknown_record_line_count"] > 0
    return shape


def _diagnostic_value_type(value: Any) -> str:
    """Reduce an arbitrary runtime type to a fixed diagnostic enum."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, (int, float)):
        return "number"
    return "other"


def _diagnostic_finish_reason(value: str) -> str:
    """Keep only provider stop categories approved for persisted diagnostics."""
    return value if value in DIAGNOSTIC_FINISH_REASONS else "other"


def one_line_envelope_diagnostics(
    arguments: Any,
    parsed: Submission | None = None,
    *,
    finish_reason: str | None = None,
    output_tokens: int | None = None,
) -> dict[str, Any]:
    """Shape metadata for a refused call. Never the content.

    Enough to say which stage refused and why: the argument types and names, how
    many lines of each record arrived, whether the document closed the way this
    notation closes, how many segments were written as ``key=value`` and how
    many were not, and the codes the parsers produced. The response metadata is
    passed in rather than read here, and is left out when the caller has none.
    """
    is_object = isinstance(arguments, Mapping)
    diagnostics: dict[str, Any] = {
        "raw_args_type": _diagnostic_value_type(arguments),
        "envelope_property_present": is_object and ENVELOPE_PROPERTY in arguments,
        "unknown_envelope_key_present": is_object
        and bool(set(arguments) - {ENVELOPE_PROPERTY}),
        "submission_text_value_type": "absent",
        "parser_problem_codes": [],
    }
    if is_object and ENVELOPE_PROPERTY in arguments:
        value = arguments[ENVELOPE_PROPERTY]
        diagnostics["submission_text_value_type"] = _diagnostic_value_type(value)
        if isinstance(value, str):
            diagnostics.update(_text_shape(value))
    if parsed is not None:
        diagnostics["parser_problem_codes"] = sorted(
            {
                problem.code
                if problem.code in DIAGNOSTIC_PARSER_PROBLEM_CODES
                else "other"
                for problem in parsed.problems
            }
        )
    if finish_reason is not None:
        diagnostics["finish_reason"] = _diagnostic_finish_reason(finish_reason)
    if isinstance(output_tokens, int) and not isinstance(output_tokens, bool) and output_tokens >= 0:
        diagnostics["output_tokens"] = output_tokens
    return diagnostics
