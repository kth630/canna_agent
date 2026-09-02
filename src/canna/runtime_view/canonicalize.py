"""Turning a quoted question span into an executable value, or refusing to.

The 0-A re-verification measured the failure this module exists to remove. The
model copies opaque references reliably and does not preserve normalised
execution values: "1조원" came back as 10000, "이하" as ``lt``, sort directions
and relation directions were lost. So the wire carries spans, and the
derivation happens here, once, deterministically, on the server.

Four derivations live here and nothing else does. A sort direction, a row
limit, a comparison operator with its typed value, and an aggregation function.
Each one answers a question about *grammar* — what does this Korean or English
expression say — and then asks the Registry whether the field it applies to is
allowed to be used that way. Neither half is enough alone: "이상" means ``gte``
no matter which product family is being asked about, and a field the Registry
never authorised for filtering may not be filtered however clear the wording is.

Three refusals are deliberate and are not gaps to be closed by guessing.

A value whose magnitude the Registry does not fix cannot be canonicalised. The
ontology declares that ``percent_observed`` values are stored in percent
notation, so "3%" is 3 and never 0.03; it declares nothing of the kind for
``currency_amount`` or ``price``, whose stored scale and whose currency are not
knowable from a term's metadata, and it says ``number`` means the source
declared no unit at all. Reading "1조원" against a column that might be held in
억원 would be a silent factual error, so those units are refused by name.

An expression that could mean two things is refused rather than resolved. Two
opposing direction words, two comparison operators, a negation, a range, a
compound magnitude: each returns a code saying which, and none picks a winner.

An expression nobody has taught this module is refused rather than approximated.
The lexicons below are grammar tables, not a list of the questions anyone
expects; they contain no product name, no measure, no family and no identifier,
and every entry is checked by a test that asks the table itself what it claims.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .contract import (
    CANONICALIZER_AGGREGATION,
    CANONICALIZER_COMPARISON,
    CANONICALIZER_LIMIT,
    CANONICALIZER_ORDERING,
)
from .query import SubmittedRequirement
from .spans import CODE_SPAN_ALIGNMENT_FAILED, aligned, normalize_for_alignment

__all__ = [
    "AGGREGATION_FUNCTIONS",
    "COMPARISON_OPERATORS",
    "DIRECTIONS",
    "IMPLEMENTED_CANONICALIZERS",
    "UNIT_PROFILES",
    "AggregationResult",
    "ComparisonResult",
    "DirectionResult",
    "Failure",
    "FieldMetadata",
    "LimitResult",
    "RequirementCanonicalization",
    "TypedValue",
    "canonicalize_aggregation",
    "canonicalize_comparison",
    "canonicalize_direction",
    "canonicalize_limit",
    "canonicalize_ordering",
    "canonicalize_requirement",
    "field_metadata",
]

# ---------------------------------------------------------------------------
# Vocabularies borrowed from documents that own them
# ---------------------------------------------------------------------------

# Sort directions. Named by the 2026-08-31 scope decision recorded in
# IMPLEMENTATION_PLAN.md ("정렬 방향 ... asc | desc"); the Registry declares that
# a field may be ordered, never in which direction, so this pair is owned here.
DIRECTION_ASC = "asc"
DIRECTION_DESC = "desc"
DIRECTIONS = (DIRECTION_ASC, DIRECTION_DESC)

# Comparison operators and aggregation functions. These names are not invented:
# they are the values the Execution Registry already publishes for every bound
# measure under ``physical_operations``. Using the same spelling keeps one
# vocabulary between what this layer decides and what a compiler will execute.
OPERATOR_VOCABULARY_SOURCE = "execution_registry.json#bindings[].physical_operations"
OPERATOR_EQ = "eq"
OPERATOR_NE = "ne"
OPERATOR_GT = "gt"
OPERATOR_GTE = "gte"
OPERATOR_LT = "lt"
OPERATOR_LTE = "lte"
COMPARISON_OPERATORS = (
    OPERATOR_EQ,
    OPERATOR_NE,
    OPERATOR_GT,
    OPERATOR_GTE,
    OPERATOR_LT,
    OPERATOR_LTE,
)

AGGREGATION_COUNT = "count"
AGGREGATION_SUM = "sum"
AGGREGATION_AVG = "avg"
AGGREGATION_MIN = "min"
AGGREGATION_MAX = "max"
AGGREGATION_FUNCTIONS = (
    AGGREGATION_COUNT,
    AGGREGATION_SUM,
    AGGREGATION_AVG,
    AGGREGATION_MIN,
    AGGREGATION_MAX,
)

# Registry operation codes, declared in ontology/core.ttl as cnn:Operation
# instances and carried onto every term as ``allowed_operations``. A
# canonicalisation is only offered when the Registry authorised the operation
# it would produce.
OPERATION_CODES_SOURCE = "ontology/core.ttl#cnn:Operation/cnn:operationCode"
OPERATION_FILTER = "filter"
OPERATION_ORDER = "order"
OPERATION_AGGREGATE = "aggregate"
OPERATION_COUNT = "count"

# Which Registry operation each aggregation function needs. Counting rows and
# aggregating a measure are separate authorisations in the ontology, so they
# are kept separate here too.
AGGREGATION_OPERATIONS: Mapping[str, str] = {
    AGGREGATION_COUNT: OPERATION_COUNT,
    AGGREGATION_SUM: OPERATION_AGGREGATE,
    AGGREGATION_AVG: OPERATION_AGGREGATE,
    AGGREGATION_MIN: OPERATION_AGGREGATE,
    AGGREGATION_MAX: OPERATION_AGGREGATE,
}

# Unit codes, declared in ontology/core.ttl as cnn:Unit instances.
UNIT_CODES_SOURCE = "ontology/core.ttl#cnn:Unit/cnn:unitCode"
UNIT_PERCENT_OBSERVED = "percent_observed"
UNIT_CURRENCY_AMOUNT = "currency_amount"
UNIT_PRICE = "price"
UNIT_COUNT = "count"
UNIT_DAYS = "days"
UNIT_MULTIPLIER = "multiplier"
UNIT_NUMBER = "number"
UNIT_NONE = "none"

# The canonicaliser names ``contract.py`` uses to gate execution. This set is
# what a wiring change would assign to ``AVAILABLE_CANONICALIZERS``; grouping,
# whole-comparison requirements and explanations are absent because they are
# not implemented and must stay refused.
IMPLEMENTED_CANONICALIZERS = frozenset(
    {
        CANONICALIZER_ORDERING,
        CANONICALIZER_LIMIT,
        CANONICALIZER_COMPARISON,
        CANONICALIZER_AGGREGATION,
    }
)

# ---------------------------------------------------------------------------
# Reason codes (provisional internal, like the rest of this package)
# ---------------------------------------------------------------------------

CODE_DIRECTION_UNSUPPORTED = "direction_expression_unsupported"
CODE_DIRECTION_AMBIGUOUS = "direction_expression_ambiguous"
CODE_LIMIT_UNSUPPORTED = "limit_expression_unsupported"
CODE_LIMIT_AMBIGUOUS = "limit_expression_ambiguous"
CODE_LIMIT_NOT_POSITIVE = "limit_not_a_positive_integer"
CODE_LIMIT_IS_PROPORTION = "limit_is_a_proportion"
CODE_COMPARISON_UNSUPPORTED = "comparison_expression_unsupported"
CODE_COMPARISON_AMBIGUOUS = "comparison_expression_ambiguous"
CODE_VALUE_UNSUPPORTED = "value_expression_unsupported"
CODE_VALUE_UNIT_MISMATCH = "value_unit_mismatch"
CODE_UNIT_NOT_CANONICALIZABLE = "unit_not_canonicalizable"
CODE_AGGREGATION_UNSUPPORTED = "aggregation_function_unsupported"
CODE_AGGREGATION_AMBIGUOUS = "aggregation_function_ambiguous"
CODE_NEGATED = "negated_expression_unsupported"
CODE_OPERATION_NOT_ALLOWED = "operation_not_allowed_by_registry"
CODE_FIELD_METADATA_UNAVAILABLE = "field_metadata_unavailable"

SLOT_ORDERING = "ordering.direction_span"
SLOT_LIMIT = "limit_span"
SLOT_COMPARISON = "condition.comparison_span"
SLOT_VALUE = "condition.value_span"
SLOT_AGGREGATION = "aggregation.function_span"


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Failure:
    """Why a span could not become an execution value."""

    code: str
    slot: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "slot": self.slot, "detail": self.detail}


@dataclass(frozen=True)
class DirectionResult:
    direction: str = ""
    matched_forms: tuple[str, ...] = ()
    failure: Failure | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None and self.direction in DIRECTIONS


@dataclass(frozen=True)
class LimitResult:
    limit: int = 0
    failure: Failure | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None and self.limit > 0


@dataclass(frozen=True)
class TypedValue:
    """A number with the unit the Registry declared for the field it compares to."""

    number: Decimal
    unit_code: str
    magnitude_word: str = ""
    marker: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "number": str(self.number),
            "unit_code": self.unit_code,
            "magnitude_word": self.magnitude_word,
            "marker": self.marker,
        }


@dataclass(frozen=True)
class ComparisonResult:
    operator: str = ""
    value: TypedValue | None = None
    matched_forms: tuple[str, ...] = ()
    failure: Failure | None = None

    @property
    def ok(self) -> bool:
        return (
            self.failure is None
            and self.operator in COMPARISON_OPERATORS
            and self.value is not None
        )


@dataclass(frozen=True)
class AggregationResult:
    function: str = ""
    required_operation: str = ""
    matched_forms: tuple[str, ...] = ()
    failure: Failure | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None and self.function in AGGREGATION_FUNCTIONS


@dataclass(frozen=True)
class RequirementCanonicalization:
    """Every derivation one requirement needs, or the reasons it has none."""

    conditions: tuple[ComparisonResult, ...] = ()
    ordering: DirectionResult | None = None
    limit: LimitResult | None = None
    aggregation: AggregationResult | None = None
    failures: tuple[Failure, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failures


# ---------------------------------------------------------------------------
# Field metadata, read from the Registry and never invented
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldMetadata:
    """What the Semantic Registry says about the field a span applies to."""

    semantic_id: str = ""
    unit_code: str = ""
    period_code: str = ""
    currency_policy: str = ""
    allowed_operations: tuple[str, ...] = ()

    def allows(self, operation: str) -> bool:
        return operation in self.allowed_operations


def field_metadata(term: object) -> FieldMetadata:
    """Project a vocabulary ``Term`` onto the facts a canonicalisation needs."""
    evidence: Mapping[str, object] = getattr(term, "evidence", {}) or {}
    return FieldMetadata(
        semantic_id=str(getattr(term, "semantic_id", "")),
        unit_code=str(evidence.get("unit_code", "") or ""),
        period_code=str(evidence.get("period_code", "") or ""),
        currency_policy=str(evidence.get("currency_policy", "") or ""),
        allowed_operations=tuple(
            str(value) for value in (evidence.get("allowed_operations") or ())
        ),
    )


@dataclass(frozen=True)
class UnitProfile:
    """Whether a declared unit fixes what a written number means, and how."""

    unit_code: str
    canonicalizable: bool
    markers: tuple[str, ...]
    basis: str
    refusal_code: str = ""


# Every unit the ontology declares, and what a value span may say against it.
# ``basis`` records why, quoting the declaration rather than a habit. A unit
# that is missing here is refused loudly by ``_profile`` rather than defaulting.
UNIT_PROFILES: Mapping[str, UnitProfile] = {
    UNIT_PERCENT_OBSERVED: UnitProfile(
        unit_code=UNIT_PERCENT_OBSERVED,
        canonicalizable=True,
        markers=("%", "퍼센트"),
        basis=(
            "core.ttl declares the observed magnitude matches percent notation, so a "
            "percentage is carried as written and never divided by a hundred"
        ),
    ),
    UNIT_COUNT: UnitProfile(
        unit_code=UNIT_COUNT,
        canonicalizable=True,
        markers=("개", "건"),
        basis="core.ttl declares a quantity; a counted number needs no conversion",
    ),
    UNIT_DAYS: UnitProfile(
        unit_code=UNIT_DAYS,
        canonicalizable=True,
        markers=("일",),
        basis="core.ttl declares a number of days; a written day count needs no conversion",
    ),
    UNIT_MULTIPLIER: UnitProfile(
        unit_code=UNIT_MULTIPLIER,
        canonicalizable=True,
        markers=("배",),
        basis="core.ttl declares a multiple; a written multiple needs no conversion",
    ),
    UNIT_CURRENCY_AMOUNT: UnitProfile(
        unit_code=UNIT_CURRENCY_AMOUNT,
        canonicalizable=False,
        markers=(),
        basis=(
            "the stored magnitude is not declared and the currency comes from a per-row "
            "policy, so a written amount cannot be placed on the same scale"
        ),
        refusal_code=CODE_UNIT_NOT_CANONICALIZABLE,
    ),
    UNIT_PRICE: UnitProfile(
        unit_code=UNIT_PRICE,
        canonicalizable=False,
        markers=(),
        basis=(
            "a unit price carries a currency and a scale that a term's metadata does not "
            "fix, so a written price cannot be compared without assuming both"
        ),
        refusal_code=CODE_UNIT_NOT_CANONICALIZABLE,
    ),
    UNIT_NUMBER: UnitProfile(
        unit_code=UNIT_NUMBER,
        canonicalizable=False,
        markers=(),
        basis=(
            "core.ttl declares this unit means the source stated no unit at all; treating "
            "the reader's number as the same unit would be the assumption this layer refuses"
        ),
        refusal_code=CODE_UNIT_NOT_CANONICALIZABLE,
    ),
    UNIT_NONE: UnitProfile(
        unit_code=UNIT_NONE,
        canonicalizable=False,
        markers=(),
        basis=(
            "the field carries no numeric unit, so a comparison would be against a code, a "
            "label or a date, and resolving a written value to those is a separate layer"
        ),
        refusal_code=CODE_UNIT_NOT_CANONICALIZABLE,
    ),
}

# Markers that belong to some unit, used to tell "wrong unit" from "not a unit".
_ALL_MARKERS = frozenset(
    marker for profile in UNIT_PROFILES.values() for marker in profile.markers
)


# ---------------------------------------------------------------------------
# Grammar tables
# ---------------------------------------------------------------------------
#
# These are language, not domain. Korean conjugates, so a stem is not a
# substring of its inflected form ("크" is not inside "큰"); the inflected forms
# are therefore listed. ASCII forms are matched on word boundaries so that
# "desc" does not fire inside "descending", and every form is checked by a test
# that feeds it back in and demands the meaning it claims here.

DIRECTION_FORMS: tuple[tuple[str, str], ...] = (
    ("높은", DIRECTION_DESC),
    ("높다", DIRECTION_DESC),
    ("높은순", DIRECTION_DESC),
    ("높은 순", DIRECTION_DESC),
    ("큰", DIRECTION_DESC),
    ("많은", DIRECTION_DESC),
    ("상위", DIRECTION_DESC),
    ("내림차순", DIRECTION_DESC),
    ("최고", DIRECTION_DESC),
    ("최대", DIRECTION_DESC),
    ("가장 높은", DIRECTION_DESC),
    ("가장 큰", DIRECTION_DESC),
    ("descending", DIRECTION_DESC),
    ("desc", DIRECTION_DESC),
    ("highest", DIRECTION_DESC),
    ("largest", DIRECTION_DESC),
    ("top", DIRECTION_DESC),
    ("낮은", DIRECTION_ASC),
    ("낮다", DIRECTION_ASC),
    ("낮은순", DIRECTION_ASC),
    ("낮은 순", DIRECTION_ASC),
    ("작은", DIRECTION_ASC),
    ("적은", DIRECTION_ASC),
    ("하위", DIRECTION_ASC),
    ("오름차순", DIRECTION_ASC),
    ("최저", DIRECTION_ASC),
    ("최소", DIRECTION_ASC),
    ("가장 낮은", DIRECTION_ASC),
    ("가장 작은", DIRECTION_ASC),
    ("ascending", DIRECTION_ASC),
    ("asc", DIRECTION_ASC),
    ("lowest", DIRECTION_ASC),
    ("smallest", DIRECTION_ASC),
    ("bottom", DIRECTION_ASC),
)

COMPARISON_FORMS: tuple[tuple[str, str], ...] = (
    ("이상", OPERATOR_GTE),
    ("이상인", OPERATOR_GTE),
    (">=", OPERATOR_GTE),
    ("≥", OPERATOR_GTE),
    ("at least", OPERATOR_GTE),
    ("or more", OPERATOR_GTE),
    ("이하", OPERATOR_LTE),
    ("이하인", OPERATOR_LTE),
    ("<=", OPERATOR_LTE),
    ("≤", OPERATOR_LTE),
    ("at most", OPERATOR_LTE),
    ("or less", OPERATOR_LTE),
    ("초과", OPERATOR_GT),
    ("넘는", OPERATOR_GT),
    ("넘게", OPERATOR_GT),
    ("보다 큰", OPERATOR_GT),
    ("보다 높은", OPERATOR_GT),
    ("보다 많은", OPERATOR_GT),
    ("greater than", OPERATOR_GT),
    ("more than", OPERATOR_GT),
    ("above", OPERATOR_GT),
    (">", OPERATOR_GT),
    ("미만", OPERATOR_LT),
    ("보다 작은", OPERATOR_LT),
    ("보다 낮은", OPERATOR_LT),
    ("보다 적은", OPERATOR_LT),
    ("less than", OPERATOR_LT),
    ("below", OPERATOR_LT),
    ("under", OPERATOR_LT),
    ("<", OPERATOR_LT),
    ("같은", OPERATOR_EQ),
    ("같다", OPERATOR_EQ),
    ("동일", OPERATOR_EQ),
    ("equal to", OPERATOR_EQ),
    ("equals", OPERATOR_EQ),
    ("=", OPERATOR_EQ),
    ("아닌", OPERATOR_NE),
    ("아니", OPERATOR_NE),
    ("제외", OPERATOR_NE),
    ("!=", OPERATOR_NE),
    ("≠", OPERATOR_NE),
    ("other than", OPERATOR_NE),
)

AGGREGATION_FORMS: tuple[tuple[str, str], ...] = (
    ("개수", AGGREGATION_COUNT),
    ("갯수", AGGREGATION_COUNT),
    ("건수", AGGREGATION_COUNT),
    ("몇 개", AGGREGATION_COUNT),
    ("몇개", AGGREGATION_COUNT),
    ("수", AGGREGATION_COUNT),
    ("count", AGGREGATION_COUNT),
    ("합계", AGGREGATION_SUM),
    ("총합", AGGREGATION_SUM),
    ("합", AGGREGATION_SUM),
    ("sum", AGGREGATION_SUM),
    ("total", AGGREGATION_SUM),
    ("평균", AGGREGATION_AVG),
    ("average", AGGREGATION_AVG),
    ("avg", AGGREGATION_AVG),
    ("mean", AGGREGATION_AVG),
    ("최소", AGGREGATION_MIN),
    ("최저", AGGREGATION_MIN),
    ("최솟값", AGGREGATION_MIN),
    ("최소값", AGGREGATION_MIN),
    ("가장 낮은", AGGREGATION_MIN),
    ("가장 작은", AGGREGATION_MIN),
    ("minimum", AGGREGATION_MIN),
    ("min", AGGREGATION_MIN),
    ("lowest", AGGREGATION_MIN),
    ("최대", AGGREGATION_MAX),
    ("최고", AGGREGATION_MAX),
    ("최댓값", AGGREGATION_MAX),
    ("최대값", AGGREGATION_MAX),
    ("가장 높은", AGGREGATION_MAX),
    ("가장 큰", AGGREGATION_MAX),
    ("maximum", AGGREGATION_MAX),
    ("max", AGGREGATION_MAX),
    ("highest", AGGREGATION_MAX),
)

# Words that change which function is meant. A weighted average, a moving
# average or an annualised average is not the average this module can produce,
# and each of them contains the word for the one it is not.
AGGREGATION_MODIFIERS = ("가중", "중앙", "누적", "이동", "연평균", "월평균", "일평균", "분기평균")

# A negated expression is refused outright: "높지 않은" contains the word for
# the direction it denies, and no table can be written that reads both.
NEGATION_MARKERS = ("않", "못")
NEGATION_ASCII = ("not", "no", "never")
_STANDALONE_NEGATION = re.compile(r"(?:^|\s)안(?:\s|$)")

# "아니" negates everywhere except in a comparison, where it *is* the operator
# ``ne``. A negation table that ignored the slot would either refuse every
# inequality or read "평균이 아니" as an average.
NEGATION_OUTSIDE_COMPARISON = ("아니", "아닌")

# Expressions that make a span something other than a plain row limit.
LIMIT_RANGE_MARKERS = ("이상", "이하", "초과", "미만", "~", "부터", "에서", "보다", "between")
LIMIT_PERIOD_MARKERS = (
    "개월",
    "년",
    "분기",
    "주일",
    "일간",
    "일",
    "시간",
    "month",
    "year",
    "quarter",
    "week",
    "day",
)

# Sino-Korean magnitudes. Language, not data: a single suffixed magnitude is
# read, a compound one ("1조 5000억") is refused as two numbers.
MAGNITUDES: Mapping[str, int] = {
    "천": 1_000,
    "만": 10_000,
    "억": 100_000_000,
    "조": 1_000_000_000_000,
}

# Explicit link words. A span may join approved expressions with one of these,
# and with nothing else. They are what makes "< 또는 <=" readable as two
# expressions rather than as unreadable text.
CONNECTIVES = ("또는", "그리고", "및", "혹은", "이거나", "or", "and", ",", "/")

# Numbers are read in one written form only. A group separator either is absent
# or splits the integer part into a leading group of one to three digits and
# then groups of exactly three; "1,00" and "12,34,567" are neither, and are
# refused rather than repaired by deleting the commas.
_INTEGER = r"\d{1,3}(?:,\d{3})+|\d+"
_DECIMAL = rf"(?:{_INTEGER})(?:\.\d+)?"
_NUMBER = re.compile(_DECIMAL)
# Any run of digits and separators, so a malformed one is caught whole rather
# than partially matched by the strict pattern above.
_NUMERIC_RUN = re.compile(r"[0-9][0-9,.]*|[0-9,.]*[0-9]")
_STRICT_NUMBER = re.compile(rf"^(?:{_DECIMAL})$")
_VALUE = re.compile(
    rf"^(?P<sign>[-+])?\s*(?P<digits>{_DECIMAL})\s*(?P<magnitude>[천만억조])?\s*(?P<marker>.*)$"
)

# A row count is written as an optional selection word, a number, and an
# optional counting noun. Anything else in the span — a product name, a code,
# an approximation — means the number in it was not a row count.
LIMIT_PREFIXES = ("상위", "하위", "top", "bottom", "first")
LIMIT_COUNTERS = ("개의", "개", "건", "종목", "곳", "가지", "위")
_LIMIT = re.compile(
    r"^(?:(?:" + "|".join(LIMIT_PREFIXES) + r")\s*)?"
    r"(?P<sign>[-+])?\s*(?P<digits>" + _DECIMAL + r")\s*"
    r"(?P<magnitude>[천만억조])?\s*"
    r"(?P<counter>" + "|".join(LIMIT_COUNTERS) + r")?$"
)

# A bare four-digit number is written the way a calendar year is written, and a
# limit span carrying one says nothing that tells the two apart. It is refused
# unless it carries a counting noun that makes it a count.
YEAR_SHAPED_DIGITS = 4


# ---------------------------------------------------------------------------
# Reading a span
# ---------------------------------------------------------------------------


def _normalize(span: str) -> str:
    """The approved span normalisation, plus case folding for ASCII forms."""
    return normalize_for_alignment(span).lower()


def _cover(text: str, forms: Sequence[tuple[str, str]]) -> tuple[str, ...] | None:
    """Consume the whole span with approved forms and connectives, or fail.

    Substring matching was the wrong tool. Korean writes "이상한",
    "최소가입금액", "평균적으로" and "상위험", each of which contains an
    approved expression without saying it, and reading them as ``gte``,
    ``asc``, ``avg`` and ``desc`` are four silent wrong answers. So a span is
    read only when every character of it is accounted for by an approved form,
    an explicit connective or whitespace; one unexplained syllable and the span
    is refused.

    Longest match wins at each position, with backtracking. That is what makes
    "<=" one expression rather than "<" followed by "=", while "< 또는 <=" is
    still two expressions at two positions and is refused as ambiguous.
    """
    vocabulary = sorted({form for form, _ in forms} | set(CONNECTIVES), key=len, reverse=True)
    consumed: list[str] = []
    dead: set[int] = set()

    def walk(position: int) -> bool:
        if position == len(text):
            return True
        if position in dead:
            return False
        if text[position] == " ":
            return walk(position + 1)
        for candidate in vocabulary:
            if text.startswith(candidate, position):
                consumed.append(candidate)
                if walk(position + len(candidate)):
                    return True
                consumed.pop()
        dead.add(position)
        return False

    return tuple(consumed) if walk(0) else None


def _read(
    text: str, forms: Sequence[tuple[str, str]]
) -> tuple[set[str], tuple[str, ...], bool]:
    """``(meanings, the forms said, whether the whole span was accounted for)``."""
    consumed = _cover(text, forms)
    if consumed is None:
        return set(), (), False
    known = {form for form, _ in forms}
    said = tuple(item for item in consumed if item in known)
    meanings = {meaning for form, meaning in forms if form in said}
    return meanings, said, True


def _negated(
    text: str, forms: Sequence[tuple[str, str]] = (), *, comparison_slot: bool = False
) -> bool:
    """Is this span denying what it otherwise says?

    "안" is written both attached and detached, so adjacency is what is checked:
    an "안" immediately before an approved expression negates it, space or no
    space. That deliberately leaves "안정적인" alone — nothing approved follows
    the "안" there, so the span is simply not one this layer reads.
    """
    markers = NEGATION_MARKERS
    if not comparison_slot:
        markers = markers + NEGATION_OUTSIDE_COMPARISON
    if any(marker in text for marker in markers):
        return True
    for match in re.finditer(r"안\s*", text):
        rest = text[match.end() :]
        if any(rest.startswith(form) for form, _ in forms):
            return True
    return any(
        re.search(r"(?<![0-9a-z])" + re.escape(word) + r"(?![0-9a-z])", text)
        for word in NEGATION_ASCII
    )


def _malformed_number(text: str) -> str:
    """The first numeric run that is not written the one approved way."""
    for run in _NUMERIC_RUN.findall(text):
        if run and not _STRICT_NUMBER.match(run):
            return run
    return ""


def _alignment_failure(question: str, span: str, slot: str) -> Failure | None:
    """No derivation happens on text the question does not contain."""
    if not span.strip():
        return Failure(
            code=CODE_SPAN_ALIGNMENT_FAILED,
            slot=slot,
            detail="an empty span cannot be read as an execution value",
        )
    if not aligned(question, span):
        return Failure(
            code=CODE_SPAN_ALIGNMENT_FAILED,
            slot=slot,
            detail=(
                "the span is not in the question, exactly or after the approved "
                "normalisation; nothing is derived from text nobody wrote"
            ),
        )
    return None


# ---------------------------------------------------------------------------
# 1. Ordering direction
# ---------------------------------------------------------------------------


def canonicalize_direction(question: str, span: str) -> DirectionResult:
    """A quoted direction expression, as ``asc`` or ``desc``, or a refusal."""
    failure = _alignment_failure(question, span, SLOT_ORDERING)
    if failure is not None:
        return DirectionResult(failure=failure)
    text = _normalize(span)
    if _negated(text, DIRECTION_FORMS):
        return DirectionResult(
            failure=Failure(
                code=CODE_NEGATED,
                slot=SLOT_ORDERING,
                detail=(
                    "a negated direction is not the opposite direction; it is refused "
                    f"rather than reversed ({span!r})"
                ),
            )
        )
    meanings, forms, covered = _read(text, DIRECTION_FORMS)
    if not covered or not meanings:
        return DirectionResult(
            failure=Failure(
                code=CODE_DIRECTION_UNSUPPORTED,
                slot=SLOT_ORDERING,
                detail=(
                    f"{span!r} is not an approved direction expression; a span is read "
                    "only when all of it is accounted for, so text that merely contains "
                    "a direction word is refused"
                ),
            )
        )
    if len(meanings) > 1:
        return DirectionResult(
            matched_forms=forms,
            failure=Failure(
                code=CODE_DIRECTION_AMBIGUOUS,
                slot=SLOT_ORDERING,
                detail=(
                    f"{span!r} says both directions; one is not chosen over the other"
                ),
            ),
        )
    return DirectionResult(direction=meanings.pop(), matched_forms=forms)


def canonicalize_ordering(
    question: str, span: str, metadata: FieldMetadata | None
) -> DirectionResult:
    """A direction, and the Registry's permission to order that field by it."""
    result = canonicalize_direction(question, span)
    if not result.ok:
        return result
    if metadata is None:
        return DirectionResult(
            matched_forms=result.matched_forms, failure=_no_metadata(SLOT_ORDERING)
        )
    if not metadata.allows(OPERATION_ORDER):
        return DirectionResult(
            matched_forms=result.matched_forms,
            failure=_not_allowed(SLOT_ORDERING, metadata, OPERATION_ORDER),
        )
    return result


# ---------------------------------------------------------------------------
# 2. Limit
# ---------------------------------------------------------------------------


def canonicalize_limit(question: str, span: str) -> LimitResult:
    """A quoted count expression, as a positive integer, or a refusal.

    The span has to *be* a row count, not merely contain a number. "KODEX 200",
    "상품코드 123" and "ETF 10" all carry an integer and none of them says how
    many rows to return, so the whole span is matched against the grammar of a
    written count — an optional selection word, one number, an optional
    counting noun — and anything left over is a refusal.
    """
    failure = _alignment_failure(question, span, SLOT_LIMIT)
    if failure is not None:
        return LimitResult(failure=failure)
    text = _normalize(span)

    def refuse(code: str, detail: str) -> LimitResult:
        return LimitResult(failure=Failure(code=code, slot=SLOT_LIMIT, detail=detail))

    if _negated(text):
        return refuse(CODE_NEGATED, f"a negated count is not a row limit ({span!r})")
    if "%" in text or "퍼센트" in text:
        return refuse(
            CODE_LIMIT_IS_PROPORTION,
            "a share of the population is not a row count, and turning one into the "
            f"other needs a population this layer does not have ({span!r})",
        )
    if any(marker in text for marker in LIMIT_PERIOD_MARKERS):
        return refuse(
            CODE_LIMIT_UNSUPPORTED,
            f"{span!r} states a period rather than how many rows to return",
        )
    if any(marker in text for marker in LIMIT_RANGE_MARKERS):
        return refuse(
            CODE_LIMIT_UNSUPPORTED,
            f"{span!r} bounds a value rather than the number of rows",
        )
    malformed = _malformed_number(text)
    if malformed:
        return refuse(
            CODE_LIMIT_UNSUPPORTED,
            f"{malformed!r} is not a number as numbers are written; group separators are "
            "not deleted to make one readable",
        )
    numbers = _NUMBER.findall(text)
    if not numbers:
        return refuse(
            CODE_LIMIT_UNSUPPORTED,
            "no digits appear; a count written in words is not read, because a reading "
            f"would be a guess ({span!r})",
        )
    if len(numbers) > 1:
        return refuse(
            CODE_LIMIT_AMBIGUOUS,
            f"{span!r} contains more than one number; none of them is chosen",
        )
    match = _LIMIT.match(text)
    if match is None:
        return refuse(
            CODE_LIMIT_UNSUPPORTED,
            f"{span!r} is not written as a row count; a number inside other text — a "
            "product name, a code, an approximation — is not read as one",
        )
    if match.group("sign"):
        return refuse(
            CODE_LIMIT_NOT_POSITIVE,
            "a row count carries no sign; a signed number is refused rather than read "
            f"without it ({span!r})",
        )
    if match.group("magnitude"):
        return refuse(
            CODE_LIMIT_UNSUPPORTED,
            f"a row count written with a magnitude word is refused rather than expanded "
            f"({span!r})",
        )
    written = match.group("digits")
    if (
        not match.group("counter")
        and "." not in written
        and len(written.replace(",", "")) == YEAR_SHAPED_DIGITS
    ):
        return refuse(
            CODE_LIMIT_UNSUPPORTED,
            f"{span!r} is written the way a calendar year is written and carries no "
            "counting word; a bare four-digit number is not read as a row count",
        )
    try:
        number = Decimal(written.replace(",", ""))
    except InvalidOperation:
        return refuse(CODE_LIMIT_UNSUPPORTED, f"{span!r} does not contain a readable number")
    if number != number.to_integral_value():
        return refuse(
            CODE_LIMIT_NOT_POSITIVE, f"a row count has to be a whole number ({span!r})"
        )
    limit = int(number)
    if limit <= 0:
        return refuse(
            CODE_LIMIT_NOT_POSITIVE, f"a row count has to be greater than zero ({span!r})"
        )
    return LimitResult(limit=limit)


# ---------------------------------------------------------------------------
# 3. Comparison operator and typed value
# ---------------------------------------------------------------------------


def canonicalize_comparison(
    question: str,
    comparison_span: str,
    value_span: str,
    metadata: FieldMetadata | None,
) -> ComparisonResult:
    """An operator and a typed value, or the reason neither could be derived."""
    failure = _alignment_failure(question, comparison_span, SLOT_COMPARISON)
    if failure is not None:
        return ComparisonResult(failure=failure)
    failure = _alignment_failure(question, value_span, SLOT_VALUE)
    if failure is not None:
        return ComparisonResult(failure=failure)
    if metadata is None:
        return ComparisonResult(failure=_no_metadata(SLOT_COMPARISON))

    comparison_text = _normalize(comparison_span)
    meanings, forms, covered = _read(comparison_text, COMPARISON_FORMS)
    if _negated(comparison_text, COMPARISON_FORMS, comparison_slot=True):
        return ComparisonResult(
            matched_forms=forms,
            failure=Failure(
                code=CODE_NEGATED,
                slot=SLOT_COMPARISON,
                detail=(
                    "a negated comparison is not the opposite comparison; it is refused "
                    f"rather than inverted ({comparison_span!r})"
                ),
            ),
        )
    if not covered or not meanings:
        return ComparisonResult(
            failure=Failure(
                code=CODE_COMPARISON_UNSUPPORTED,
                slot=SLOT_COMPARISON,
                detail=(
                    f"{comparison_span!r} is not an approved comparison expression; a span "
                    "that merely contains one is refused rather than read"
                ),
            )
        )
    if len(meanings) > 1:
        return ComparisonResult(
            matched_forms=forms,
            failure=Failure(
                code=CODE_COMPARISON_AMBIGUOUS,
                slot=SLOT_COMPARISON,
                detail=(
                    f"{comparison_span!r} says more than one comparison; none is chosen"
                ),
            ),
        )
    operator = meanings.pop()

    if not metadata.allows(OPERATION_FILTER):
        return ComparisonResult(
            matched_forms=forms,
            failure=_not_allowed(SLOT_COMPARISON, metadata, OPERATION_FILTER),
        )

    value, value_failure = _typed_value(value_span, metadata)
    if value_failure is not None:
        return ComparisonResult(matched_forms=forms, failure=value_failure)
    return ComparisonResult(operator=operator, value=value, matched_forms=forms)


def _profile(metadata: FieldMetadata) -> UnitProfile | None:
    return UNIT_PROFILES.get(metadata.unit_code)


def _typed_value(
    value_span: str, metadata: FieldMetadata
) -> tuple[TypedValue | None, Failure | None]:
    """Read the written number in the unit the Registry declared, or refuse."""
    if not metadata.unit_code:
        return None, Failure(
            code=CODE_UNIT_NOT_CANONICALIZABLE,
            slot=SLOT_VALUE,
            detail=(
                "the Registry declares no unit for this field, so a written number has no "
                "stated meaning against it"
            ),
        )
    profile = _profile(metadata)
    if profile is None:
        return None, Failure(
            code=CODE_UNIT_NOT_CANONICALIZABLE,
            slot=SLOT_VALUE,
            detail=(
                f"unit {metadata.unit_code!r} has no declared reading in this layer; a new "
                "unit is refused rather than assumed to behave like a known one"
            ),
        )
    if not profile.canonicalizable:
        return None, Failure(
            code=profile.refusal_code or CODE_UNIT_NOT_CANONICALIZABLE,
            slot=SLOT_VALUE,
            detail=profile.basis,
        )
    if metadata.currency_policy:
        return None, Failure(
            code=CODE_UNIT_NOT_CANONICALIZABLE,
            slot=SLOT_VALUE,
            detail=(
                "the field's currency comes from a per-row policy, so a written amount is "
                "not on one fixed scale"
            ),
        )

    text = _normalize(value_span)
    if _negated(text):
        return None, Failure(
            code=CODE_NEGATED,
            slot=SLOT_VALUE,
            detail=f"a negated value is refused rather than interpreted ({value_span!r})",
        )
    malformed = _malformed_number(text)
    if malformed:
        return None, Failure(
            code=CODE_VALUE_UNSUPPORTED,
            slot=SLOT_VALUE,
            detail=(
                f"{malformed!r} is not a number as numbers are written; group separators "
                "are not deleted to make one readable"
            ),
        )
    if len(_NUMBER.findall(text)) != 1:
        return None, Failure(
            code=CODE_VALUE_UNSUPPORTED,
            slot=SLOT_VALUE,
            detail=(
                "a value has to be exactly one number; none and several are both refused "
                f"rather than reduced to one ({value_span!r})"
            ),
        )
    match = _VALUE.match(text)
    if match is None:
        return None, Failure(
            code=CODE_VALUE_UNSUPPORTED,
            slot=SLOT_VALUE,
            detail=f"{value_span!r} is not a number with an optional unit",
        )
    marker = match.group("marker").strip()
    if marker and marker not in profile.markers:
        code = (
            CODE_VALUE_UNIT_MISMATCH if marker in _ALL_MARKERS else CODE_VALUE_UNSUPPORTED
        )
        return None, Failure(
            code=code,
            slot=SLOT_VALUE,
            detail=(
                f"{value_span!r} is written in {marker!r}, which is not how this field's "
                f"declared unit {metadata.unit_code!r} is written"
            ),
        )
    try:
        number = Decimal(match.group("digits").replace(",", ""))
    except InvalidOperation:
        return None, Failure(
            code=CODE_VALUE_UNSUPPORTED,
            slot=SLOT_VALUE,
            detail=f"{value_span!r} does not contain a readable number",
        )
    magnitude = match.group("magnitude") or ""
    if magnitude:
        number = number * MAGNITUDES[magnitude]
    if match.group("sign") == "-":
        number = -number
    return (
        TypedValue(
            number=number,
            unit_code=metadata.unit_code,
            magnitude_word=magnitude,
            marker=marker,
        ),
        None,
    )


# ---------------------------------------------------------------------------
# 4. Aggregation function
# ---------------------------------------------------------------------------


def canonicalize_aggregation(
    question: str, span: str, metadata: FieldMetadata | None
) -> AggregationResult:
    """An aggregation the Registry allows on this field, or a refusal."""
    failure = _alignment_failure(question, span, SLOT_AGGREGATION)
    if failure is not None:
        return AggregationResult(failure=failure)
    if metadata is None:
        return AggregationResult(failure=_no_metadata(SLOT_AGGREGATION))
    text = _normalize(span)
    if _negated(text, AGGREGATION_FORMS):
        return AggregationResult(
            failure=Failure(
                code=CODE_NEGATED,
                slot=SLOT_AGGREGATION,
                detail=f"a negated aggregation is refused rather than read ({span!r})",
            )
        )
    modifier = next((word for word in AGGREGATION_MODIFIERS if word in text), "")
    if modifier:
        return AggregationResult(
            failure=Failure(
                code=CODE_AGGREGATION_UNSUPPORTED,
                slot=SLOT_AGGREGATION,
                detail=(
                    f"{span!r} asks for a modified aggregation ({modifier!r}), which is a "
                    "different function from the one it contains the name of"
                ),
            )
        )
    meanings, forms, covered = _read(text, AGGREGATION_FORMS)
    if not covered or not meanings:
        return AggregationResult(
            failure=Failure(
                code=CODE_AGGREGATION_UNSUPPORTED,
                slot=SLOT_AGGREGATION,
                detail=(
                    f"{span!r} is not an approved aggregation expression; a span that "
                    "merely contains one is refused rather than read"
                ),
            )
        )
    if len(meanings) > 1:
        return AggregationResult(
            matched_forms=forms,
            failure=Failure(
                code=CODE_AGGREGATION_AMBIGUOUS,
                slot=SLOT_AGGREGATION,
                detail=f"{span!r} names more than one aggregation; none is chosen",
            ),
        )
    function = meanings.pop()
    operation = AGGREGATION_OPERATIONS[function]
    if not metadata.allows(operation):
        return AggregationResult(
            matched_forms=forms,
            failure=_not_allowed(SLOT_AGGREGATION, metadata, operation),
        )
    return AggregationResult(
        function=function, required_operation=operation, matched_forms=forms
    )


# ---------------------------------------------------------------------------
# Shared refusals and the requirement-level entry point
# ---------------------------------------------------------------------------


def _no_metadata(slot: str) -> Failure:
    return Failure(
        code=CODE_FIELD_METADATA_UNAVAILABLE,
        slot=slot,
        detail=(
            "the field this span applies to was not resolved to a Registry term, so its "
            "unit and its permitted operations are unknown"
        ),
    )


def _not_allowed(slot: str, metadata: FieldMetadata, operation: str) -> Failure:
    return Failure(
        code=CODE_OPERATION_NOT_ALLOWED,
        slot=slot,
        detail=(
            f"the Registry does not list {operation!r} among this field's allowed "
            "operations, so the expression is not executed however clearly it reads"
        ),
    )


def canonicalize_requirement(
    question: str,
    requirement: SubmittedRequirement,
    metadata_for: Callable[[str], FieldMetadata | None],
) -> RequirementCanonicalization:
    """Every derivation one requirement needs, refusing each one independently.

    ``metadata_for`` maps a submitted field reference to what the Registry says
    about it, and returns ``None`` for a reference that did not resolve. A slot
    that fails does not silence the others: the caller gets one reason per slot
    so that a plan is refused for everything actually wrong with it.
    """
    failures: list[Failure] = []

    conditions: list[ComparisonResult] = []
    for condition in requirement.conditions:
        result = canonicalize_comparison(
            question,
            condition.comparison_span,
            condition.value_span,
            metadata_for(condition.field_ref),
        )
        conditions.append(result)
        if result.failure is not None:
            failures.append(result.failure)

    ordering: DirectionResult | None = None
    if requirement.ordering is not None:
        ordering = canonicalize_ordering(
            question,
            requirement.ordering.direction_span,
            metadata_for(requirement.ordering.field_ref),
        )
        if ordering.failure is not None:
            failures.append(ordering.failure)

    limit: LimitResult | None = None
    if requirement.limit_span:
        limit = canonicalize_limit(question, requirement.limit_span)
        if limit.failure is not None:
            failures.append(limit.failure)

    aggregation: AggregationResult | None = None
    if requirement.aggregation is not None:
        aggregation = canonicalize_aggregation(
            question,
            requirement.aggregation.function_span,
            metadata_for(requirement.aggregation.field_ref),
        )
        if aggregation.failure is not None:
            failures.append(aggregation.failure)

    return RequirementCanonicalization(
        conditions=tuple(conditions),
        ordering=ordering,
        limit=limit,
        aggregation=aggregation,
        failures=tuple(failures),
    )
