r"""The same grouped-flat records, written as lines instead of as JSON.

Twelve live calls on 2026-08-31 walked the failure down one axis at a time:
``40009`` on the declaration, then argument pollution, then object-versus-string,
then code fences, then broken ``\uXXXX`` escapes, then an unterminated document.
The last two then began alternating. With both instructions in the prompt the
model kept the escapes and left a brace open on one call, then closed every
brace and escaped the Korean on the next, at three percent of the token budget
either way. Nothing about that is a space problem; it is the cost of writing
JSON *inside* a JSON string, where escaped quotes, unescaped Korean and brace
balance compete for the same attention.

So the notation inside the envelope stops being JSON. A record is a header line,
some ``key value`` lines, and an ``END`` line. There is no quoting, so an escape
cannot be malformed; there is no nesting, so nothing can be left unbalanced; and
a value is simply the rest of its line, so a span arrives with its whitespace
exactly as the question had it.

Nothing behind the notation moves. This module reads lines into precisely the
grouped-flat object ``parse_grouped_flat`` already takes, which assembles the
canonical submission ``parse_submission`` already decides. The record names and
the keys each record may carry are taken from ``grouped_flat``'s own property
tables rather than retyped, so this file cannot drift into being a second,
looser opinion about what a record is. The enums, the reference kinds, the
required spans and the three requirement statuses are all decided where they
were already decided.

What this module does own is the notation's own failure modes, and it refuses
every one of them rather than repairing it: a header nobody defined, a line
loose between records, a record with no ``END``, a key repeated inside one
record, a key line with no key, and any line-break character other than the line
ending itself. A span cannot contain a newline in this notation, so the encoder
refuses to write one instead of quietly flattening it — a span that cannot be
carried honestly is not carried at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contract import REQUIREMENT_KINDS, REQUIREMENT_STATUSES
from .grouped_flat import (
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
from .query import (
    CODE_MALFORMED_SUBMISSION,
    CODE_MISSING_REQUIRED_SPAN,
    CODE_UNKNOWN_PROPERTY,
    CODE_WRONG_TYPE,
    ShapeProblem,
    Submission,
)

__all__ = [
    "CLASS_COUNTS",
    "CODE_DUPLICATE_KEY",
    "CODE_MALFORMED_KEY_LINE",
    "CODE_STRAY_LINE",
    "CODE_UNKNOWN_RECORD",
    "CODE_UNSUPPORTED_LINE_BREAK",
    "CODE_UNTERMINATED_RECORD",
    "DIAGNOSTIC_FIELDS",
    "END",
    "ENVELOPE_PROPERTY",
    "LINE_BREAK_CHARACTERS",
    "LINE_CLASSES",
    "RECORD_KEYS",
    "RECORD_PROPERTIES",
    "RECORD_TOKENS",
    "LineFormatError",
    "classify_line",
    "grouped_flat_record_properties",
    "line_envelope_diagnostics",
    "line_parameters_schema",
    "line_record_keys",
    "line_shape_classes",
    "line_submission_guidance",
    "parse_line_submission",
    "parse_tool_arguments",
    "read_line_records",
    "render_line_records",
]

# ------------------------------------------------------------------- notation

RECORD_REQUIREMENT = "REQ"
RECORD_REFERENCE = "REF"
RECORD_DETAIL = "DETAIL"
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
# An unaccounted span is a bare string in the grouped-flat object, so it is the
# one record whose single key this notation has to name for itself.
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

# One space between the key and the value, and everything after it is the value:
# no trimming, no collapsing, no normalisation of any kind.
SEPARATOR = " "

# ``\r\n`` and ``\n`` end a line. Every other character a reader somewhere might
# treat as a line break is refused, because it would either split a span
# invisibly or ride inside one as a control character nobody wrote.
LINE_ENDING = "\n"
LINE_BREAK_CHARACTERS: tuple[str, ...] = (
    "\r",
    "\v",
    "\f",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x85",
    "\u2028",
    "\u2029",
)

# Problems only this notation can have. Everything else is reported with the
# code the canonical parser already publishes for it, so the same bad submission
# is refused under the same name whether it arrived as JSON or as lines.
CODE_UNKNOWN_RECORD = "unknown_record"
CODE_STRAY_LINE = "stray_line"
CODE_UNTERMINATED_RECORD = "unterminated_record"
CODE_DUPLICATE_KEY = "duplicate_record_key"
CODE_MALFORMED_KEY_LINE = "malformed_key_line"
CODE_UNSUPPORTED_LINE_BREAK = "unsupported_line_break"


class LineFormatError(ValueError):
    """A value cannot be written in this notation without being altered."""


# --------------------------------------------------------------------- reading


def _line_break_in(line: str) -> str:
    for character in LINE_BREAK_CHARACTERS:
        if character in line:
            return character
    return ""


def read_line_records(text: Any) -> tuple[dict[str, Any] | None, tuple[ShapeProblem, ...]]:
    """Read the notation into a grouped-flat object, refusing what it cannot read.

    Returns ``(None, problems)`` when the line structure itself is untrustworthy
    — a stray line break, or a record that was never closed — because the rest of
    the document says nothing reliable once record boundaries are in doubt.
    Otherwise the object is returned together with whatever problems were found,
    the way ``assemble_submission_payload`` does, so that the caller sees these
    problems and the parser's own.
    """
    if not isinstance(text, str):
        return None, (ShapeProblem(CODE_MALFORMED_SUBMISSION, "the submission is not text"),)

    problems: list[ShapeProblem] = []
    lines = text.replace("\r\n", LINE_ENDING).split(LINE_ENDING)
    for number, line in enumerate(lines, 1):
        found = _line_break_in(line)
        if found:
            problems.append(
                ShapeProblem(
                    CODE_UNSUPPORTED_LINE_BREAK,
                    f"line {number} contains {found!r}, which is not a line ending here",
                )
            )
            return None, tuple(problems)

    collected: dict[str, list[dict[str, str]]] = {token: [] for token in RECORD_TOKENS}
    open_token = ""
    open_line = 0
    open_keys: dict[str, str] = {}
    keep_open_record = True

    for number, line in enumerate(lines, 1):
        # A structural line carries no value, so trailing whitespace on it is
        # not span content and reading past it alters nothing.
        marker = line.rstrip()
        if not marker:
            continue
        if not open_token:
            if marker in RECORD_KEYS:
                open_token, open_line, open_keys, keep_open_record = marker, number, {}, True
                continue
            problems.append(
                ShapeProblem(
                    CODE_STRAY_LINE if marker == END else CODE_UNKNOWN_RECORD,
                    f"line {number} is not a record header",
                )
            )
            continue
        if marker == END:
            if keep_open_record:
                collected[open_token].append(open_keys)
            open_token = ""
            continue
        if marker in RECORD_KEYS:
            problems.append(
                ShapeProblem(
                    CODE_UNTERMINATED_RECORD,
                    f"the record opened on line {open_line} was never closed",
                )
            )
            return None, tuple(problems)
        key, _, value = line.partition(SEPARATOR)
        if not key:
            problems.append(
                ShapeProblem(CODE_MALFORMED_KEY_LINE, f"line {number} begins with no key")
            )
            keep_open_record = False
            continue
        if key not in RECORD_KEYS[open_token]:
            problems.append(
                ShapeProblem(
                    CODE_UNKNOWN_PROPERTY,
                    f"{open_token} on line {open_line} has unknown ['{key}']",
                )
            )
            keep_open_record = False
            continue
        if key in open_keys:
            problems.append(
                ShapeProblem(
                    CODE_DUPLICATE_KEY, f"{open_token} on line {open_line} repeats {key}"
                )
            )
            keep_open_record = False
            continue
        open_keys[key] = value

    if open_token:
        problems.append(
            ShapeProblem(
                CODE_UNTERMINATED_RECORD,
                f"the record opened on line {open_line} was never closed",
            )
        )
        return None, tuple(problems)

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


def parse_line_submission(text: Any) -> Submission:
    """Read the notation and hand the result to the parsers that already exist."""
    payload, problems = read_line_records(text)
    if payload is None:
        return Submission(None, problems)
    parsed = parse_grouped_flat(payload)
    return Submission(parsed.query, (*problems, *parsed.problems))


# --------------------------------------------------------------------- writing


def _value(record_token: str, key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise LineFormatError(f"{record_token}.{key} is {type(value).__name__}, not text")
    found = _line_break_in(value) or (LINE_ENDING if LINE_ENDING in value else "")
    if found:
        raise LineFormatError(
            f"{record_token}.{key} contains {found!r} and cannot be written on one line"
        )
    return value


def _record_lines(record_token: str, record: Mapping[str, Any]) -> list[str]:
    unknown = sorted(set(record) - set(RECORD_KEYS[record_token]))
    if unknown:
        raise LineFormatError(f"{record_token} has unknown {unknown}")
    lines = [record_token]
    lines += [
        f"{key}{SEPARATOR}{_value(record_token, key, record[key])}"
        for key in RECORD_KEYS[record_token]
        if key in record
    ]
    lines.append(END)
    return lines


def render_line_records(wire: Mapping[str, Any]) -> str:
    """Write a grouped-flat object in this notation, or refuse to write it.

    The inverse of the reader, used to show the two notations carry the same
    object and to build wire text in tests without hand-writing records. A value
    that cannot survive the round-trip — anything that is not text, anything
    holding a line break — raises rather than being flattened into something the
    question never said.
    """
    if not isinstance(wire, Mapping):
        raise LineFormatError("the grouped-flat payload is not an object")
    unknown = sorted(set(wire) - GROUPED_FLAT_PROPERTIES)
    if unknown:
        raise LineFormatError(f"the grouped-flat payload has unknown {unknown}")

    lines: list[str] = []
    for token in (RECORD_REQUIREMENT, RECORD_REFERENCE, RECORD_DETAIL):
        for record in wire.get(RECORD_PROPERTIES[token], ()) or ():
            if not isinstance(record, Mapping):
                raise LineFormatError(f"a {token} record is not an object")
            lines += _record_lines(token, record)
    for span in wire.get(P_UNACCOUNTED_SPANS, ()) or ():
        lines += _record_lines(RECORD_UNACCOUNTED, {P_SPAN: span})
    return LINE_ENDING.join([*lines, ""])


# -------------------------------------------------------------------- envelope

ENVELOPE_PROPERTY = "submission_text"

ENVELOPE_DESCRIPTION = "The accounting as record lines."
FUNCTION_DESCRIPTION = "Account for the question's explicit requirements."


def line_parameters_schema() -> dict[str, Any]:
    """One object, one required string — the declaration the provider accepted.

    Identical in shape to the JSON bridge's, because that shape is the one the
    provider took on 2026-08-31; what changes is only what the string holds. A
    fresh object each call.
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
    text. There is no decode step left to fail — that was the point.
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
            None, (ShapeProblem(CODE_WRONG_TYPE, f"{ENVELOPE_PROPERTY} must be text"),)
        )
    return parse_line_submission(raw)


# ------------------------------------------------ shape classes for a refusal

# The 13th live call refused here with three codes and nothing that said which
# malformation produced them: no header was ever opened, an ``END`` arrived with
# no record open, so nothing was collected. Those same three codes come out
# whether the model wrote ``REQ:``, ``req``, an indented ``REQ``, a bulleted
# list, ``requirement_id: v1``, a literal backslash-n or a JSON object. This
# section tells those apart.
#
# Every name below is decided in this file. A line is only ever compared
# against this module's own tokens and keys and then reported as one of these
# fixed class names, so nothing a line contains — no reference, no span, no
# identifier, not the unknown token itself, not a hash of it — can reach the
# record. A class that no counter names is visible only through the first and
# last line class and the JSON boolean, which is deliberate: the point is to
# know which shape arrived, never what it said.
LINE_CLASS_ABSENT = "absent"
LINE_CLASS_EXACT_HEADER = "exact_record_header"
LINE_CLASS_INDENTED_HEADER = "indented_record_header"
LINE_CLASS_CASEFOLD_HEADER = "casefold_record_header"
LINE_CLASS_HEADER_WITH_SUFFIX = "record_header_with_suffix"
LINE_CLASS_EXACT_END = "exact_end"
LINE_CLASS_INDENTED_END = "indented_end"
LINE_CLASS_KNOWN_KEY_SPACE = "known_key_space"
LINE_CLASS_KNOWN_KEY_COLON = "known_key_colon"
LINE_CLASS_BULLET = "bullet_prefixed"
LINE_CLASS_JSON = "json_punctuation"
LINE_CLASS_UNKNOWN = "unknown"

LINE_CLASSES: tuple[str, ...] = (
    LINE_CLASS_ABSENT,
    LINE_CLASS_EXACT_HEADER,
    LINE_CLASS_INDENTED_HEADER,
    LINE_CLASS_CASEFOLD_HEADER,
    LINE_CLASS_HEADER_WITH_SUFFIX,
    LINE_CLASS_EXACT_END,
    LINE_CLASS_INDENTED_END,
    LINE_CLASS_KNOWN_KEY_SPACE,
    LINE_CLASS_KNOWN_KEY_COLON,
    LINE_CLASS_BULLET,
    LINE_CLASS_JSON,
    LINE_CLASS_UNKNOWN,
)

# Which counter each class is reported under. ``LINE_CLASS_JSON`` has none: a
# JSON document would otherwise be counted line by line, and one boolean says
# the same thing without measuring how much of it arrived.
CLASS_COUNTS: dict[str, str] = {
    LINE_CLASS_EXACT_HEADER: "exact_record_header_count",
    LINE_CLASS_CASEFOLD_HEADER: "casefold_record_header_count",
    LINE_CLASS_INDENTED_HEADER: "indented_record_header_count",
    LINE_CLASS_HEADER_WITH_SUFFIX: "record_header_with_suffix_count",
    LINE_CLASS_EXACT_END: "exact_end_count",
    LINE_CLASS_INDENTED_END: "indented_end_count",
    LINE_CLASS_KNOWN_KEY_SPACE: "known_key_space_count",
    LINE_CLASS_KNOWN_KEY_COLON: "known_key_colon_count",
    LINE_CLASS_BULLET: "bullet_prefixed_line_count",
    LINE_CLASS_UNKNOWN: "unknown_nonempty_line_count",
}

# Longest first, so no key can be read as the head of another one.
KNOWN_KEYS: tuple[str, ...] = tuple(
    sorted({key for keys in RECORD_KEYS.values() for key in keys}, key=lambda key: -len(key))
)
BULLET_MARKERS: tuple[str, ...] = ("-", "*", "+", "•", "·", "–", "●")
JSON_OPENERS = "{[\""
JSON_PUNCTUATION = "{}[],:"
# A backslash followed by the letter n, written the way the rest of this
# tree writes it, so no editor or transport can turn it into a real newline.
LITERAL_BACKSLASH_N = chr(92) + "n"
COLON = ":"


def _is_bullet(text: str) -> bool:
    """A list marker where a record header should be: ``- REQ``, ``1. REQ``."""
    if text[0] in BULLET_MARKERS:
        return len(text) == 1 or text[1] in " \t"
    marker, _, _rest = text.partition(SEPARATOR)
    return len(marker) > 1 and marker[:-1].isdigit() and marker[-1] in ".)"


def _is_json(text: str) -> bool:
    """A line that opens a JSON value, or one made of nothing but its punctuation."""
    return text[0] in JSON_OPENERS or set(text) <= set(JSON_PUNCTUATION + " \t")


def _is_token_with_suffix(text: str, token: str) -> bool:
    """The header is there, and something else is on the line with it.

    The character after the token has to be a boundary, so a key that merely
    begins with the same letters is not read as a header wearing a suffix.
    """
    if text[: len(token)].casefold() != token.casefold():
        return False
    rest = text[len(token) :]
    return bool(rest) and not (rest[0].isalnum() or rest[0] == "_")


def classify_line(line: str) -> str:
    """Name the shape of one line. Never returns any part of the line itself."""
    body = line.rstrip()
    text = body.strip()
    if not text:
        return LINE_CLASS_ABSENT
    if _is_bullet(text):
        return LINE_CLASS_BULLET
    if _is_json(text):
        return LINE_CLASS_JSON
    if text == END:
        return LINE_CLASS_EXACT_END if body == END else LINE_CLASS_INDENTED_END
    for token in RECORD_TOKENS:
        if text == token:
            return LINE_CLASS_EXACT_HEADER if body == token else LINE_CLASS_INDENTED_HEADER
        if text.casefold() == token.casefold():
            return LINE_CLASS_CASEFOLD_HEADER
    # Before the loose header test, because a key line the reader reads exactly
    # as written is not a mangled header: ``ref`` would otherwise be read as
    # ``REF`` wearing a suffix, and every well-formed reference would be
    # reported as a malformation.
    for key in KNOWN_KEYS:
        if text.startswith(key + COLON):
            return LINE_CLASS_KNOWN_KEY_COLON
        if text.startswith(key + SEPARATOR):
            return LINE_CLASS_KNOWN_KEY_SPACE
    for token in RECORD_TOKENS:
        if _is_token_with_suffix(text, token):
            return LINE_CLASS_HEADER_WITH_SUFFIX
    return LINE_CLASS_UNKNOWN


def line_shape_classes(text: str) -> dict[str, Any]:
    """How many lines of each fixed shape arrived, and which shape opened and closed.

    Counts and booleans only. This is what separates a header the reader would
    not recognise from one it would, without the record ever holding a character
    the model wrote.
    """
    classes = [
        classify_line(line)
        for line in text.replace("\r\n", LINE_ENDING).split(LINE_ENDING)
    ]
    populated = [name for name in classes if name != LINE_CLASS_ABSENT]
    shape: dict[str, Any] = {
        counter: populated.count(name) for name, counter in CLASS_COUNTS.items()
    }
    shape["literal_backslash_n_present"] = LITERAL_BACKSLASH_N in text
    # Punctuation anywhere, not only where a line opened with it: a document
    # that is JSON says so on the inside of its lines too.
    shape["json_punctuation_present"] = (
        LINE_CLASS_JSON in populated
        or any(character in text for character in "{}[]")
        or '"' + COLON in text
    )
    shape["first_line_class"] = populated[0] if populated else LINE_CLASS_ABSENT
    shape["last_line_class"] = populated[-1] if populated else LINE_CLASS_ABSENT
    return shape


# The complete list of what a refused call may be remembered by, approved on
# 2026-08-31. Nothing outside it is recorded, and a test holds the produced
# record to this list: no payload text, no span, no reference, no credential and
# no request or response identifier, ever.
DIAGNOSTIC_FIELDS: tuple[str, ...] = (
    "raw_args_type",
    "argument_keys",
    "submission_text_value_type",
    "length",
    "line_count",
    "first_line_is_record_header",
    "last_line_is_end",
    "starts_with_code_fence",
    "record_counts",
    # The line shapes, added on 2026-08-31 after the 13th call: fixed class
    # names, their counts, and two booleans. Every one of them is decided by
    # this module, so none of them can carry a reference, a span, an identifier
    # or an unrecognised token itself.
    "exact_record_header_count",
    "casefold_record_header_count",
    "indented_record_header_count",
    "record_header_with_suffix_count",
    "exact_end_count",
    "indented_end_count",
    "known_key_space_count",
    "known_key_colon_count",
    "bullet_prefixed_line_count",
    "unknown_nonempty_line_count",
    "literal_backslash_n_present",
    "json_punctuation_present",
    "first_line_class",
    "last_line_class",
    "parser_problem_codes",
    "finish_reason",
    "output_tokens",
)


def _text_shape(value: str) -> dict[str, Any]:
    """Form, not content: how long it is, how it opens, how it closes, how many.

    Enough to tell a code fence from a truncation from a document that never
    started, without keeping a character of what the model wrote. The record
    counts are counts of this module's own record names, so they say how much
    arrived and nothing about what it said.
    """
    lines = [line.rstrip() for line in value.replace("\r\n", LINE_ENDING).split(LINE_ENDING)]
    populated = [line for line in lines if line]
    return {
        "length": len(value),
        "line_count": len(lines),
        "first_line_is_record_header": bool(populated) and populated[0] in RECORD_KEYS,
        "last_line_is_end": bool(populated) and populated[-1] == END,
        "starts_with_code_fence": value.strip().startswith("```"),
        "record_counts": {token: populated.count(token) for token in RECORD_TOKENS},
    }


def line_envelope_diagnostics(
    arguments: Any,
    parsed: Submission | None = None,
    *,
    finish_reason: str | None = None,
    output_tokens: int | None = None,
) -> dict[str, Any]:
    """Shape metadata for a refused call. Never the content.

    Enough to say which stage refused and why: the argument types and names, the
    document's outline, how many records of each kind arrived, and the codes the
    parsers produced. The response metadata is passed in rather than read here,
    and is left out when the caller has none.
    """
    diagnostics: dict[str, Any] = {
        "raw_args_type": type(arguments).__name__,
        "argument_keys": sorted(str(key) for key in arguments)
        if isinstance(arguments, Mapping)
        else [],
        "submission_text_value_type": "absent",
        "parser_problem_codes": [],
    }
    if isinstance(arguments, Mapping) and ENVELOPE_PROPERTY in arguments:
        value = arguments[ENVELOPE_PROPERTY]
        diagnostics["submission_text_value_type"] = type(value).__name__
        if isinstance(value, str):
            diagnostics.update(_text_shape(value))
            diagnostics.update(line_shape_classes(value))
    if parsed is not None:
        diagnostics["parser_problem_codes"] = sorted(
            {problem.code for problem in parsed.problems}
        )
    if finish_reason is not None:
        diagnostics["finish_reason"] = finish_reason
    if output_tokens is not None:
        diagnostics["output_tokens"] = output_tokens
    return diagnostics


def line_submission_guidance() -> str:
    """How to write the notation, rendered from the tables the reader reads by.

    The same discipline the JSON bridge's guidance follows: every field name,
    role, detail kind, requirement kind and status comes from the server's own
    tables, so the instruction cannot drift from what the server will accept, and
    no question, product or reference is named anywhere in it.
    """
    keys = {token: SEPARATOR.join(RECORD_KEYS[token]) for token in RECORD_TOKENS}
    return (
        f"Put record lines in {ENVELOPE_PROPERTY}. Do not write JSON: no braces, no "
        "brackets, no quotation marks around anything, no backslash escapes. "
        f"A record is the line {RECORD_REQUIREMENT}, {RECORD_REFERENCE}, "
        f"{RECORD_DETAIL} or {RECORD_UNACCOUNTED} on its own, then one line per field "
        f"written as the field name, one space, and the value, then the line {END} on "
        "its own. Everything after that one space is the value, exactly as you write "
        "it, so a value must never contain a line break and must not be wrapped in "
        "quotes. Write non-ASCII text as the characters themselves. Omit a line "
        "entirely rather than writing a field you have nothing to put in. "
        f"{RECORD_REQUIREMENT} is one record per requirement the question states, with "
        f"{keys[RECORD_REQUIREMENT]}; {P_LIMIT_SPAN} only when the question says how "
        f"many. {P_REQUIREMENT_ID} is an id you choose, one or two characters, and "
        f"every other record repeats it. {P_KIND} is one of: "
        f"{', '.join(REQUIREMENT_KINDS)}. {P_STATUS} is one of: "
        f"{', '.join(REQUIREMENT_STATUSES)}. "
        f"{RECORD_REFERENCE} is one record per reference, with {keys[RECORD_REFERENCE]}. "
        f"{P_ROLE} is one of: {', '.join(REF_ROLES)}. {', '.join(LIST_ROLES)} may each "
        f"appear more than once; {' and '.join(RELATION_ROLES)} at most once. {P_REF} "
        "is an opaque reference this request offered. "
        f"{RECORD_DETAIL} is one record per condition, ordering or aggregation, with "
        f"{keys[RECORD_DETAIL]}. {P_DETAIL_KIND} is one of: {', '.join(DETAIL_KINDS)}. "
        f"{P_REF} is the field reference, {P_SPAN} is the comparison, direction or "
        f"function words, and {P_VALUE_SPAN} is the value words, for {DETAIL_CONDITION} "
        "only. One record is one condition: keep its comparison and its value in the "
        "same record. A requirement may carry at most one ordering and one aggregation. "
        f"{RECORD_UNACCOUNTED} is one record per part of the question you did not "
        f"account for, with {keys[RECORD_UNACCOUNTED]}. "
        "Copy every span from the question exactly; do not normalise it into a value, "
        "an operator, a direction or a number. Use only references this request offered "
        "and never invent one. Never name a requirement you did not declare. "
        f"Set {P_STATUS} to {REQUIREMENT_STATUSES[0]} when the offered references carry "
        f"the meaning, {REQUIREMENT_STATUSES[1]} when none do, and "
        f"{REQUIREMENT_STATUSES[2]} when several meanings are possible and nothing "
        "decides between them. "
        "Do not produce SQL, tables, columns, joins, stable identifiers or any other "
        "physical execution detail. Give the tool no argument other than "
        f"{ENVELOPE_PROPERTY}, and put nothing before the first record header or after "
        f"the last {END}."
    )


def line_record_keys() -> dict[str, tuple[str, ...]]:
    """Every record and the keys it accepts, published for parity checking."""
    return {token: RECORD_KEYS[token] for token in RECORD_TOKENS}


def grouped_flat_record_properties() -> dict[str, frozenset[str]]:
    """The same records as ``grouped_flat`` defines them, for the same check."""
    return {
        RECORD_REQUIREMENT: REQUIREMENT_RECORD_PROPERTIES,
        RECORD_REFERENCE: REF_RECORD_PROPERTIES,
        RECORD_DETAIL: DETAIL_RECORD_PROPERTIES,
    }
