"""The vocabulary this experiment adds, and where every item of it comes from.

Three of the four groups below are *borrowed*, not written: the direction,
comparison, aggregation, limit and magnitude tables are imported from
``canna.runtime_view.canonicalize``, which owns them, so that what this
experiment measures is the grammar the server already has rather than a second
copy of it that could disagree.

What is genuinely new is the Korean function-word vocabulary the proposal's
``non_requirement_reason`` allow-list requires but no production module owns
yet: particles, connectives, politeness endings, discourse markers and
demonstratives. It is language, not domain, in exactly the sense
``canonicalize.py`` already argues for its own tables -- no product, no metric,
no date and no identifier appears here. Any noun that carries domain meaning is
deliberately absent, because classifying one as a function word is the failure
this experiment is built to detect.

The requirement-kind markers (listing, comparison, explanation) are the one
group that is neither borrowed nor purely functional. They are recorded here as
an explicit new constant so that the findings can name them, and they are
listed in the hard-coding audit rather than hidden.

The two adapter tables at the bottom translate the approved *synthetic* view
sources' vocabulary into the codes the ontology owns. They exist because those
fixtures predate the ontology's unit and operation codes; the real Registry
declares the ontology codes directly and needs no adapter.
"""

from __future__ import annotations

from canna.runtime_view.canonicalize import (
    AGGREGATION_FORMS,
    COMPARISON_FORMS,
    DIRECTION_FORMS,
    LIMIT_COUNTERS,
    LIMIT_PERIOD_MARKERS,
    LIMIT_PREFIXES,
    MAGNITUDES,
    OPERATION_AGGREGATE,
    OPERATION_COUNT,
    OPERATION_FILTER,
    OPERATION_ORDER,
    UNIT_PROFILES,
)

BORROWED_TABLES_SOURCE = "canna.runtime_view.canonicalize"

__all__ = [
    "AGGREGATION_FORMS",
    "ANAPHOR_MARKERS",
    "BORROWED_TABLES_SOURCE",
    "COMPARISON_FORMS",
    "COMPARISON_REQUIREMENT_MARKERS",
    "CONNECTIVES",
    "DIRECTION_FORMS",
    "DISCOURSE_MARKERS",
    "EXPLANATION_MARKERS",
    "INFLECTIONS",
    "LIMIT_COUNTERS",
    "LIMIT_PERIOD_MARKERS",
    "LIMIT_PREFIXES",
    "LISTING_MARKERS",
    "MAGNITUDES",
    "PARTICLES",
    "POLITENESS_FORMS",
    "PUNCTUATION",
    "UNIT_PROFILES",
    "fixture_operation_code",
    "fixture_unit_code",
]

# Korean bound particles. They attach to a noun and carry case or focus; none of
# them can head a requirement. Longest first is enforced at match time, not here.
PARTICLES: tuple[str, ...] = (
    "이라도",
    "에서는",
    "으로는",
    "에게서",
    "이라는",
    "이나마",
    "에서",
    "으로",
    "에게",
    "한테",
    "까지",
    "부터",
    "처럼",
    "같이",
    "마다",
    "조차",
    "밖에",
    "이나",
    "라도",
    "인지",
    "이며",
    "이고",
    "이란",
    "들의",
    "들을",
    "들이",
    "들은",
    "들",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "도",
    "만",
    "나",
    "라",
    "며",
    "고",
    "인",
    "한",
    "중",
    "께",
)

# Words that join two expressions. A connective may separate two requirements;
# it can never be one.
CONNECTIVES: tuple[str, ...] = (
    "그리고",
    "이거나",
    "또는",
    "혹은",
    "그리고는",
    "및",
    "와",
    "과",
)

# Request and politeness endings. They say the question is a request; they say
# nothing about what is being requested.
POLITENESS_FORMS: tuple[str, ...] = (
    "알려주세요",
    "보여주세요",
    "말씀해주세요",
    "부탁드립니다",
    "부탁드려요",
    "해주세요",
    "알려줘요",
    "보여줘요",
    "알려줘",
    "보여줘",
    "해주라",
    "주세요",
    "해줘",
    "부탁해",
    "줘",
    "요",
)

# Discourse and quantifier-scope markers. "각각" distributes a requirement over
# already-named targets; it does not introduce a new one.
DISCOURSE_MARKERS: tuple[str, ...] = (
    "각각",
    "전체",
    "모두",
    "그중",
    "그 중",
    "혹시",
    "좀",
    "각",
)

# Demonstratives. A limit or a noun immediately behind one of these refers back
# to a result already produced; that is the proposal's bounded nested reuse, not
# a second independent requirement.
ANAPHOR_MARKERS: tuple[str, ...] = (
    "해당",
    "위의",
    "그",
    "이",
    "저",
    "각",
)

# Verbal inflections that attach to a stem the Registry already named. Only
# affirmative endings are listed: a negative ending changes the meaning of what
# it attaches to, so "않는" and "없는" are deliberately absent and stay content.
INFLECTIONS: tuple[str, ...] = (
    "되는",
    "하는",
    "된",
    "함",
    "됨",
)

PUNCTUATION: str = " \t\n.,?!·:;()[]{}/~-'\"“”‘’"

# --- Requirement-kind markers -------------------------------------------------
#
# These three are new domain-adjacent vocabulary and are declared in the
# hard-coding audit as such. They exist because QUESTION_STRUCTURE.md section 2
# names listing, comparison and explanation as result units, and no production
# module recognises their surface expression: ``contract.py`` has no
# canonicaliser for any of them, so detecting one is exactly how a requirement
# that must end non-executable gets accounted for instead of disappearing.

LISTING_MARKERS: tuple[str, ...] = ("목록", "리스트", "list")

COMPARISON_REQUIREMENT_MARKERS: tuple[str, ...] = (
    "비교",
    "대비",
    "차이",
    "어느 쪽",
    "어느 것",
    "compare",
)

EXPLANATION_MARKERS: tuple[str, ...] = (
    "전망",
    "설명",
    "이유",
    "분석",
    "왜",
)

# --- Fixture adapters ---------------------------------------------------------
#
# The approved synthetic view sources were authored before the ontology fixed
# its unit and operation codes. Mapping their vocabulary onto the codes
# ``contract.py`` and ``canonicalize.py`` own is a fixture concern; the real
# Registry declares the ontology codes and is passed through untouched.

_FIXTURE_UNIT_CODES: dict[str, str] = {
    "percent": "percent_observed",
    "krw": "currency_amount",
    "usd": "currency_amount",
    "count": "count",
    "days": "days",
    "multiplier": "multiplier",
    "date": "none",
    "text": "none",
    "code": "none",
}

_FIXTURE_OPERATION_CODES: dict[str, str] = {
    "filter": OPERATION_FILTER,
    "sort": OPERATION_ORDER,
    "order": OPERATION_ORDER,
    "aggregate": OPERATION_AGGREGATE,
    "count": OPERATION_COUNT,
    "output": "output",
    "relation_filter": "relation_filter",
    "relation_output": "relation_output",
}


def fixture_unit_code(declared: str) -> str:
    """The ontology unit code a fixture's unit name stands for, or the name."""
    if not declared:
        return ""
    lowered = declared.strip().lower()
    if lowered in UNIT_PROFILES:
        return lowered
    return _FIXTURE_UNIT_CODES.get(lowered, lowered)


def fixture_operation_code(declared: str) -> str:
    """The ontology operation code a fixture's operation name stands for."""
    lowered = declared.strip().lower()
    return _FIXTURE_OPERATION_CODES.get(lowered, lowered)
