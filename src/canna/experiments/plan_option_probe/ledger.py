"""The SpanLedger the proposal assumes the server can build.

Section 5.1 of the role-reduction proposal asks the server to cover every
identified explicit semantic anchor and requirement span exactly once, to
classify the residue only as a particle, a connective, politeness or
punctuation, and to block the whole option set if any content-bearing span is
left over. This module builds that ledger deterministically so the assumption
can be measured rather than assumed.

Two departures from the proposal are deliberate and are reported as findings
rather than hidden:

* A content span with no Runtime View candidate becomes an ``unresolved_anchor``
  and may head a requirement. Blocking on it, as the proposal's text says,
  would delete the ``unresolved`` accounting QUESTION_STRUCTURE.md section 5
  requires -- the question asked for something, and "we cannot map it" is an
  answer the ledger has to be able to carry.
* A residue token that the view source itself names as an entity role noun is
  classified as ``result_grain_noun``, a fifth reason outside the proposal's
  four-item allow-list. The vocabulary is read from the source's own role
  labels, never written here.

Nothing in this module reads a fixture's expected decision. It sees a question
and a candidate pool, and nothing else.

This module is experiment-only. It is not imported by any serving path,
it calls no provider, index or database, and nothing it produces is a
product contract.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from canna.runtime_view.contract import (
    REQUIREMENT_KIND_AGGREGATION,
    REQUIREMENT_KIND_ATTRIBUTE_LOOKUP,
    REQUIREMENT_KIND_COMPARISON,
    REQUIREMENT_KIND_COUNT,
    REQUIREMENT_KIND_EXPLANATION,
    REQUIREMENT_KIND_LISTING,
    REQUIREMENT_KIND_RANKING,
)

from .lexicon import (
    AGGREGATION_FORMS,
    ANAPHOR_MARKERS,
    COMPARISON_FORMS,
    COMPARISON_REQUIREMENT_MARKERS,
    CONNECTIVES,
    DIRECTION_FORMS,
    DISCOURSE_MARKERS,
    EXPLANATION_MARKERS,
    INFLECTIONS,
    LIMIT_COUNTERS,
    LIMIT_PERIOD_MARKERS,
    LIMIT_PREFIXES,
    LISTING_MARKERS,
    MAGNITUDES,
    PARTICLES,
    POLITENESS_FORMS,
    PUNCTUATION,
    UNIT_PROFILES,
)
from .sources import (
    KIND_DATASET,
    KIND_ENTITY,
    KIND_FIELD,
    KIND_PREDICATE,
    ViewCandidate,
    ViewSource,
)

ROLE_TARGET = "target"
ROLE_FIELD = "field"
ROLE_RELATIONSHIP = "relationship"
ROLE_ENTITY = "entity"
ROLE_CONDITION_FIELD = "condition_field"
ROLE_COMPARISON_OPERATOR = "comparison_operator"
ROLE_CONDITION_VALUE = "condition_value"
ROLE_ORDER_DIRECTION = "order_direction"
ROLE_LIMIT = "limit"
ROLE_AGGREGATION_FUNCTION = "aggregation_function"
ROLE_LISTING_MARKER = "listing_marker"
ROLE_COMPARISON_MARKER = "comparison_marker"
ROLE_EXPLANATION_MARKER = "explanation_marker"
ROLE_NESTED_REUSE = "nested_reuse"
ROLE_UNRESOLVED_ANCHOR = "unresolved_anchor"
ROLE_UNRESOLVED_MODIFIER = "unresolved_modifier"

SEMANTIC_ANCHOR_ROLES = (
    ROLE_TARGET,
    ROLE_FIELD,
    ROLE_RELATIONSHIP,
    ROLE_ENTITY,
    ROLE_CONDITION_FIELD,
)
OPERATION_ANCHOR_ROLES = (
    ROLE_COMPARISON_OPERATOR,
    ROLE_CONDITION_VALUE,
    ROLE_ORDER_DIRECTION,
    ROLE_LIMIT,
    ROLE_AGGREGATION_FUNCTION,
    ROLE_LISTING_MARKER,
    ROLE_COMPARISON_MARKER,
    ROLE_EXPLANATION_MARKER,
)

# The proposal's allow-list, plus the one this experiment had to add.
REASON_CONNECTIVE = "connective"
REASON_POLITENESS = "politeness"
REASON_DISCOURSE = "discourse"
REASON_PUNCTUATION = "punctuation"
REASON_PARTICLE = "particle"
REASON_GRAIN_NOUN = "result_grain_noun"
REASON_INFLECTION = "inflection"
PROPOSAL_ALLOWED_REASONS = (
    REASON_CONNECTIVE,
    REASON_POLITENESS,
    REASON_DISCOURSE,
    REASON_PUNCTUATION,
)
ADDED_REASONS = (REASON_PARTICLE, REASON_GRAIN_NOUN, REASON_INFLECTION)

_ROLE_BY_KIND = {
    KIND_DATASET: ROLE_TARGET,
    KIND_FIELD: ROLE_FIELD,
    KIND_PREDICATE: ROLE_RELATIONSHIP,
    KIND_ENTITY: ROLE_ENTITY,
}

_NUMBER = r"\d{1,3}(?:,\d{3})+|\d+"
_DECIMAL = rf"(?:{_NUMBER})(?:\.\d+)?"
_UNIT_MARKERS = tuple(
    sorted(
        {marker for profile in UNIT_PROFILES.values() for marker in profile.markers},
        key=len,
        reverse=True,
    )
)
# A value span carries its own unit marker so that the production comparison
# canonicaliser can refuse a mismatch rather than never seeing one. Period words
# are included for the same reason: "1년" against a day-count field has to reach
# the canonicaliser whole to be refused as a unit mismatch.
_VALUE_MARKERS = tuple(
    sorted({*_UNIT_MARKERS, *LIMIT_PERIOD_MARKERS, "원"}, key=len, reverse=True)
)
_VALUE_SCAN = re.compile(
    rf"(?P<digits>{_DECIMAL})\s*(?P<magnitude>[{''.join(MAGNITUDES)}]?)\s*"
    rf"(?P<marker>{'|'.join(re.escape(item) for item in _VALUE_MARKERS)})?"
)
_LIMIT_SCAN = re.compile(
    r"(?:(?:" + "|".join(re.escape(item) for item in LIMIT_PREFIXES) + r")\s*)?"
    rf"(?P<digits>{_DECIMAL})\s*"
    rf"(?P<magnitude>[{''.join(MAGNITUDES)}]?)\s*"
    r"(?P<counter>" + "|".join(re.escape(item) for item in LIMIT_COUNTERS) + r")"
)
_ASCII_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Span:
    """One stretch of the question, and every role it was recognised as.

    A span can honestly hold more than one role. "상위 5개" is a row limit and a
    sort direction at once, and "최대" is a direction and an aggregation
    function at once. Keeping only the longest match would delete the direction
    and turn a ranking into a listing, so a role a shorter or equal-length match
    found is carried here rather than discarded.
    """

    start: int
    end: int
    text: str
    role: str
    alternates: tuple[tuple[str, str], ...] = ()
    candidate_keys: tuple[str, ...] = ()
    payload: str = ""

    @property
    def candidate_key(self) -> str:
        return self.candidate_keys[0] if self.candidate_keys else ""

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def role_alternatives(self) -> tuple[str, ...]:
        return tuple(role for role, _payload in self.alternates)

    @property
    def roles(self) -> tuple[str, ...]:
        return (self.role, *self.role_alternatives)

    def payload_for(self, role: str) -> str:
        if role == self.role:
            return self.payload
        return next(
            (payload for name, payload in self.alternates if name == role), ""
        )

    def with_role(self, role: str) -> Span:
        """Re-head this span on one of its roles, keeping the others."""
        if role == self.role:
            return self
        remaining = tuple(
            (name, payload)
            for name, payload in ((self.role, self.payload), *self.alternates)
            if name != role
        )
        return Span(
            start=self.start,
            end=self.end,
            text=self.text,
            role=role,
            alternates=remaining,
            candidate_keys=self.candidate_keys,
            payload=self.payload_for(role),
        )


@dataclass(frozen=True)
class NonRequirementSpan:
    start: int
    end: int
    text: str
    reason: str


@dataclass(frozen=True)
class UnclassifiedSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class RequirementFrame:
    """One explicit requirement, and every span that belongs to it."""

    requirement_id: str
    kind: str
    kind_alternatives: tuple[str, ...]
    start: int
    end: int
    spans: tuple[Span, ...]

    def of_role(self, role: str) -> tuple[Span, ...]:
        return tuple(
            item
            for item in self.spans
            if item.role == role or role in item.role_alternatives
        )

    @property
    def source_text(self) -> str:
        return ""  # never reconstructed for diagnostics


@dataclass
class SpanLedger:
    question_length: int
    spans: tuple[Span, ...]
    frames: tuple[RequirementFrame, ...]
    non_requirement: tuple[NonRequirementSpan, ...]
    unclassified: tuple[UnclassifiedSpan, ...]
    subsumed: tuple[Span, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def blocked(self) -> bool:
        return not self.frames

    def anchor_texts(self, roles: Iterable[str]) -> tuple[str, ...]:
        wanted = set(roles)
        return tuple(
            item.text
            for item in self.spans
            if item.role in wanted or wanted & set(item.role_alternatives)
        )


def _lower(text: str) -> str:
    """Case folding that keeps every offset. Korean is unchanged by it."""
    folded = text.lower()
    if len(folded) != len(text):  # pragma: no cover - defensive
        return text
    return folded


def _occurrences(haystack: str, needle: str) -> list[tuple[int, int]]:
    if not needle:
        return []
    found: list[tuple[int, int]] = []
    start = haystack.find(needle)
    while start != -1:
        found.append((start, start + len(needle)))
        start = haystack.find(needle, start + 1)
    return found


def _ascii_boundary(lowered: str, start: int, end: int, form: str) -> bool:
    """An ASCII form must not fire inside a longer ASCII word."""
    if not form.isascii() or not any(ch.isalnum() for ch in form):
        return True
    before = lowered[start - 1] if start else ""
    after = lowered[end] if end < len(lowered) else ""
    return not (before.isascii() and before.isalnum()) and not (
        after.isascii() and after.isalnum()
    )


def _scan_forms(
    lowered: str, forms: Sequence[tuple[str, str]], role: str
) -> list[Span]:
    spans: list[Span] = []
    for form, payload in forms:
        needle = _lower(form)
        for start, end in _occurrences(lowered, needle):
            if not _ascii_boundary(lowered, start, end, needle):
                continue
            spans.append(
                Span(
                    start=start,
                    end=end,
                    text=lowered[start:end],
                    role=role,
                    payload=payload,
                )
            )
    return spans


def _scan_markers(lowered: str, markers: Sequence[str], role: str) -> list[Span]:
    return _scan_forms(lowered, tuple((item, "") for item in markers), role)


def _scan_candidates(lowered: str, source: ViewSource) -> list[Span]:
    spans: list[Span] = []
    for candidate in source.candidates:
        role = _ROLE_BY_KIND[candidate.kind]
        for form in candidate.surface_forms:
            needle = _lower(form)
            for start, end in _occurrences(lowered, needle):
                if not _ascii_boundary(lowered, start, end, needle):
                    continue
                spans.append(
                    Span(
                        start=start,
                        end=end,
                        text=lowered[start:end],
                        role=role,
                        candidate_keys=(candidate.key,),
                    )
                )
    return spans


def _scan_regex(lowered: str, pattern: re.Pattern[str], role: str) -> list[Span]:
    spans: list[Span] = []
    for match in pattern.finditer(lowered):
        text = match.group(0).strip()
        if not text:
            continue
        start = match.start() + match.group(0).index(text[0])
        spans.append(
            Span(start=start, end=start + len(text), text=text, role=role)
        )
    return spans


def _merge_roles(base: Span, *others: Span) -> Span:
    """Keep ``base``'s extent and primary role; add the others' roles to it."""
    seen: dict[str, str] = {}
    for item in (base, *others):
        for role, payload in ((item.role, item.payload), *item.alternates):
            if role not in seen or (payload and not seen[role]):
                seen[role] = payload
    primary_payload = seen.pop(base.role, base.payload)
    # A surface form can name more than one candidate: the very same words
    # spell a measure in several product families. Keeping only the first
    # would hide the family choice the server has to make and the homonymy
    # it has to refuse, so every key the extent matched is carried.
    keys: list[str] = []
    for item in (base, *others):
        for key in item.candidate_keys:
            if key not in keys:
                keys.append(key)
    return Span(
        start=base.start,
        end=base.end,
        text=base.text,
        role=base.role,
        alternates=tuple(sorted(seen.items())),
        candidate_keys=tuple(keys),
        payload=primary_payload,
    )


def _resolve_overlaps(spans: Sequence[Span]) -> tuple[list[Span], list[Span]]:
    """Longest wins the extent; a role it fully covers is absorbed, not lost."""
    by_extent: dict[tuple[int, int], list[Span]] = {}
    for span in spans:
        by_extent.setdefault((span.start, span.end), []).append(span)
    merged = [_merge_roles(group[0], *group[1:]) for group in by_extent.values()]
    merged.sort(key=lambda item: (-item.length, item.start, item.role))

    kept: list[Span] = []
    dropped: list[Span] = []
    for span in merged:
        overlapping = [
            index
            for index, item in enumerate(kept)
            if span.start < item.end and item.start < span.end
        ]
        if not overlapping:
            kept.append(span)
            continue
        # A grammar form that falls inside a Registry name is a coincidence of
        # spelling, not a second meaning: "총보수" ends in the character that
        # spells "count" and "합성..." starts with the one that spells "sum".
        # A grammar match inside a named candidate is therefore dropped.
        inside_a_name = any(
            kept[index].start <= span.start
            and span.end <= kept[index].end
            and kept[index].candidate_key
            and not span.candidate_key
            for index in overlapping
        )
        if inside_a_name:
            dropped.append(span)
            continue
        # Otherwise a shorter reading that adds a role is kept beside the longer
        # one rather than folded into it. "상위 5개" is a row limit whose extent
        # covers "상위", and the direction has to keep its own extent because
        # the production canonicaliser reads a direction span whole and refuses
        # anything with a number left in it.
        adds_a_role = any(
            role not in kept[index].roles
            for index in overlapping
            for role in span.roles
        )
        if adds_a_role:
            kept.append(span)
            continue
        dropped.append(span)
    kept.sort(key=lambda item: (item.start, -item.length))
    return kept, dropped


def _residue_runs(question_length: int, spans: Sequence[Span]) -> list[tuple[int, int]]:
    covered = [False] * question_length
    for span in spans:
        for index in range(span.start, min(span.end, question_length)):
            covered[index] = True
    runs: list[tuple[int, int]] = []
    index = 0
    while index < question_length:
        if covered[index]:
            index += 1
            continue
        start = index
        while index < question_length and not covered[index]:
            index += 1
        runs.append((start, index))
    return runs


def _classify_residue(
    lowered: str,
    runs: Sequence[tuple[int, int]],
    grain_nouns: Sequence[str],
) -> tuple[list[NonRequirementSpan], list[UnclassifiedSpan]]:
    """Peel function words off each run; whatever survives is content."""
    ordered = (
        [(item, REASON_POLITENESS) for item in POLITENESS_FORMS]
        + [(item, REASON_CONNECTIVE) for item in CONNECTIVES]
        + [(item, REASON_DISCOURSE) for item in DISCOURSE_MARKERS]
        + [(item, REASON_DISCOURSE) for item in ANAPHOR_MARKERS]
        + [(item, REASON_GRAIN_NOUN) for item in grain_nouns]
        + [(item, REASON_INFLECTION) for item in INFLECTIONS]
        + [(item, REASON_PARTICLE) for item in PARTICLES]
    )
    ordered.sort(key=lambda pair: len(pair[0]), reverse=True)

    classified: list[NonRequirementSpan] = []
    unclassified: list[UnclassifiedSpan] = []
    for start, end in runs:
        cursor = start
        pending = start
        while cursor < end:
            character = lowered[cursor]
            if character in PUNCTUATION:
                if pending < cursor:
                    unclassified.append(
                        UnclassifiedSpan(pending, cursor, lowered[pending:cursor])
                    )
                classified.append(
                    NonRequirementSpan(
                        cursor, cursor + 1, character, REASON_PUNCTUATION
                    )
                )
                cursor += 1
                pending = cursor
                continue
            match = next(
                (
                    (form, reason)
                    for form, reason in ordered
                    if form and lowered.startswith(form, cursor) and cursor + len(form) <= end
                ),
                None,
            )
            if match is not None:
                form, reason = match
                if pending < cursor:
                    unclassified.append(
                        UnclassifiedSpan(pending, cursor, lowered[pending:cursor])
                    )
                classified.append(
                    NonRequirementSpan(cursor, cursor + len(form), form, reason)
                )
                cursor += len(form)
                pending = cursor
                continue
            cursor += 1
        if pending < end:
            unclassified.append(UnclassifiedSpan(pending, end, lowered[pending:end]))
    return classified, unclassified


def _grain_nouns(source: ViewSource) -> tuple[str, ...]:
    """Result-grain nouns the view source itself writes as relation role labels.

    "상품" and "종목" are how a predicate's own subject and object roles are
    spelled in the approved sources, so the vocabulary is read from the data
    rather than written here. They are content-bearing nouns and so fall outside
    the proposal's four-reason allow-list; that gap is a reported finding, not a
    silent extension.
    """
    nouns: set[str] = set()
    for candidate in source.candidates:
        for text in candidate.role_nouns:
            tokens = str(text).split()
            if not tokens:
                continue
            # Korean puts the head noun last: "보유하는 상품" is a product, and
            # only "상품" is the grain noun. Taking every token would classify
            # the relation's own verb as a function word.
            token = tokens[-1].strip(PUNCTUATION)
            if token and not token.isascii():
                nouns.add(_lower(token))
    return tuple(sorted(nouns, key=len, reverse=True))


def _attach_conditions(spans: list[Span]) -> list[Span]:
    """A comparison operator makes the nearest field to its left a condition."""
    updated = list(spans)
    for index, span in enumerate(updated):
        if span.role != ROLE_COMPARISON_OPERATOR:
            continue
        for back in range(index - 1, -1, -1):
            if updated[back].role == ROLE_FIELD:
                field_span = updated[back]
                updated[back] = Span(
                    start=field_span.start,
                    end=field_span.end,
                    text=field_span.text,
                    role=ROLE_CONDITION_FIELD,
                    alternates=field_span.alternates,
                    candidate_keys=field_span.candidate_keys,
                    payload=field_span.payload,
                )
                break
            if updated[back].role in (
                ROLE_AGGREGATION_FUNCTION,
                ROLE_LISTING_MARKER,
                ROLE_COMPARISON_MARKER,
            ):
                break
    return updated


def _mark_nested_reuse(lowered: str, spans: list[Span]) -> list[Span]:
    """A limit right behind a demonstrative points back, it does not select."""
    updated = list(spans)
    for index, span in enumerate(updated):
        if span.role != ROLE_LIMIT:
            continue
        prefix = lowered[max(0, span.start - 6) : span.start]
        if not any(marker in prefix for marker in ANAPHOR_MARKERS):
            continue
        updated[index] = Span(
            start=span.start,
            end=span.end,
            text=span.text,
            role=ROLE_NESTED_REUSE,
            candidate_keys=span.candidate_keys,
            payload=span.payload,
        )
    return updated


_HEAD_ROLES = (
    ROLE_AGGREGATION_FUNCTION,
    ROLE_LISTING_MARKER,
    ROLE_COMPARISON_MARKER,
    ROLE_EXPLANATION_MARKER,
    ROLE_ORDER_DIRECTION,
    ROLE_LIMIT,
    ROLE_RELATIONSHIP,
    ROLE_FIELD,
    ROLE_UNRESOLVED_ANCHOR,
)


def _is_head(span: Span) -> bool:
    roles = (span.role, *span.role_alternatives)
    return any(role in _HEAD_ROLES for role in roles)


def _coordination_positions(lowered: str) -> list[int]:
    positions: list[int] = []
    for form in (*CONNECTIVES, ",", "·"):
        for start, _end in _occurrences(lowered, _lower(form)):
            positions.append(start)
    return sorted(set(positions))


def _frame_kind(spans: Sequence[Span]) -> tuple[str, tuple[str, ...]]:
    """Which result unit this frame asks for, by the roles it actually carries.

    Two of these rules were written after the first measurement contradicted a
    simpler one, and both are recorded in the findings. A direction word that is
    *only* a direction ("상위") heads a ranking even with no row limit -- the
    limit's absence makes the ranking incomplete, not absent. A word that is
    both a direction and an aggregation function ("최대") heads an aggregation
    unless a row limit is present, because otherwise every maximum would be read
    as a one-row sort.
    """
    roles = {role for span in spans for role in span.roles}
    if ROLE_COMPARISON_MARKER in roles:
        return REQUIREMENT_KIND_COMPARISON, ()
    if ROLE_EXPLANATION_MARKER in roles:
        return REQUIREMENT_KIND_EXPLANATION, ()
    aggregations = [
        span for span in spans if ROLE_AGGREGATION_FUNCTION in span.roles
    ]
    direction_only = [
        span
        for span in spans
        if ROLE_ORDER_DIRECTION in span.roles
        and ROLE_AGGREGATION_FUNCTION not in span.roles
    ]
    has_ranking = bool(direction_only) or (
        ROLE_ORDER_DIRECTION in roles and ROLE_LIMIT in roles
    )
    if aggregations and not has_ranking:
        functions = {
            span.payload_for(ROLE_AGGREGATION_FUNCTION) for span in aggregations
        }
        functions.discard("")
        if functions == {"count"}:
            return REQUIREMENT_KIND_COUNT, ()
        if "count" in functions:
            return REQUIREMENT_KIND_AGGREGATION, (REQUIREMENT_KIND_COUNT,)
        return REQUIREMENT_KIND_AGGREGATION, ()
    if has_ranking:
        return REQUIREMENT_KIND_RANKING, (REQUIREMENT_KIND_LISTING,)
    if ROLE_LISTING_MARKER in roles or ROLE_RELATIONSHIP in roles:
        return REQUIREMENT_KIND_LISTING, (REQUIREMENT_KIND_ATTRIBUTE_LOOKUP,)
    if ROLE_ENTITY in roles and ROLE_FIELD in roles:
        return REQUIREMENT_KIND_ATTRIBUTE_LOOKUP, ()
    if ROLE_FIELD in roles or ROLE_UNRESOLVED_ANCHOR in roles:
        return REQUIREMENT_KIND_ATTRIBUTE_LOOKUP, (REQUIREMENT_KIND_LISTING,)
    return REQUIREMENT_KIND_LISTING, ()


def _build_frames(
    lowered: str, spans: Sequence[Span]
) -> tuple[RequirementFrame, ...]:
    heads = [span for span in spans if _is_head(span)]
    if not heads:
        return ()
    coordination = _coordination_positions(lowered)
    groups: list[list[Span]] = [[heads[0]]]
    for previous, current in itertools.pairwise(heads):
        split = any(previous.end <= position < current.start for position in coordination)
        if split:
            groups.append([current])
        else:
            groups[-1].append(current)

    boundaries: list[tuple[int, int]] = []
    for index, group in enumerate(groups):
        start = 0 if index == 0 else groups[index - 1][-1].end
        end = len(lowered) if index == len(groups) - 1 else group[-1].end
        boundaries.append((start, end))

    frames: list[RequirementFrame] = []
    for index, (group, (start, end)) in enumerate(
        zip(groups, boundaries, strict=True), start=1
    ):
        owned = tuple(
            span for span in spans if start <= span.start and span.end <= end
        )
        if not owned:
            owned = tuple(group)
        kind, alternatives = _frame_kind(owned)
        frames.append(
            RequirementFrame(
                requirement_id=f"r{index}",
                kind=kind,
                kind_alternatives=alternatives,
                start=start,
                end=end,
                spans=owned,
            )
        )
    return tuple(frames)


def _promote_unresolved(
    lowered: str, unclassified: Sequence[UnclassifiedSpan], spans: Sequence[Span]
) -> list[Span]:
    """Content the Runtime View cannot name still asked for something.

    The proposal blocks the whole option set on any leftover content span. That
    deletes the ``unresolved`` accounting QUESTION_STRUCTURE.md section 5
    requires, so instead the leftover is carried, and split by what it is doing.
    A word standing on its own heads a requirement nobody can map. A word flush
    in front of a candidate the view *did* name is modifying that candidate, and
    the difference matters: "최근" narrows a period harmlessly while "향후" turns
    a past measure into a forecast. Neither can be discarded, and neither can be
    resolved here, so both are kept and told apart.
    """
    promoted: list[Span] = []
    for span in unclassified:
        text = span.text.strip()
        if not text:
            continue
        start = span.start + span.text.index(text[0])
        end = start + len(text)
        gap = lowered[end : end + 1]
        # Flush in front of something the ledger did recognise -- a candidate,
        # a value, an operator -- with at most one space between. A single
        # character counts: "연" in front of a percentage qualifies that
        # percentage, and dropping it for being short would be the silent
        # discard this whole ledger exists to prevent.
        modifies = any(
            item.start == end or (item.start == end + 1 and gap.isspace())
            for item in spans
        )
        promoted.append(
            Span(
                start=start,
                end=end,
                text=text,
                role=(
                    ROLE_UNRESOLVED_MODIFIER if modifies else ROLE_UNRESOLVED_ANCHOR
                ),
            )
        )
    return promoted


def build_ledger(question: str, source: ViewSource) -> SpanLedger:
    """Account for one question against one candidate pool, and nothing else."""
    normalized = unicodedata.normalize("NFKC", question)
    lowered = _lower(normalized)

    raw: list[Span] = []
    raw += _scan_candidates(lowered, source)
    raw += _scan_forms(lowered, DIRECTION_FORMS, ROLE_ORDER_DIRECTION)
    raw += _scan_forms(lowered, COMPARISON_FORMS, ROLE_COMPARISON_OPERATOR)
    raw += _scan_forms(lowered, AGGREGATION_FORMS, ROLE_AGGREGATION_FUNCTION)
    raw += _scan_markers(lowered, LISTING_MARKERS, ROLE_LISTING_MARKER)
    raw += _scan_markers(lowered, COMPARISON_REQUIREMENT_MARKERS, ROLE_COMPARISON_MARKER)
    raw += _scan_markers(lowered, EXPLANATION_MARKERS, ROLE_EXPLANATION_MARKER)
    raw += _scan_regex(lowered, _LIMIT_SCAN, ROLE_LIMIT)
    raw += _scan_regex(lowered, _VALUE_SCAN, ROLE_CONDITION_VALUE)

    kept, subsumed = _resolve_overlaps(raw)
    grain_nouns = _grain_nouns(source)
    kept = _drop_fragmenting_grammar(lowered, kept, grain_nouns)
    kept = _attach_conditions(kept)
    kept = _mark_nested_reuse(lowered, kept)

    runs = _residue_runs(len(lowered), kept)
    classified, unclassified = _classify_residue(lowered, runs, grain_nouns)

    promoted = _promote_unresolved(lowered, unclassified, kept)
    if promoted:
        kept = sorted([*kept, *promoted], key=lambda item: item.start)
        unclassified = []

    frames = _build_frames(lowered, kept)
    return SpanLedger(
        question_length=len(lowered),
        spans=tuple(kept),
        frames=frames,
        non_requirement=tuple(classified),
        unclassified=tuple(unclassified),
        subsumed=tuple(subsumed),
    )


def _drop_fragmenting_grammar(
    lowered: str, spans: Sequence[Span], grain_nouns: Sequence[str]
) -> list[Span]:
    """A grammar word touching unrecognised text was part of that text.

    "수" spells the aggregation function *count* and is also the first syllable
    of the word for *return*. Reading it as a function there would split a noun
    the Runtime View simply does not carry into a phantom count plus the
    fragment "익률". A grammar match with unclassified content flush against it,
    with no space or particle between, is therefore given back to that content.
    """
    grammar = [
        index
        for index, span in enumerate(spans)
        if not span.candidate_key and set(span.roles) <= set(OPERATION_ANCHOR_ROLES)
    ]
    if not grammar:
        return list(spans)
    runs = _residue_runs(len(lowered), spans)
    _classified, unclassified = _classify_residue(lowered, runs, grain_nouns)
    touching = {
        index
        for index in grammar
        for residue in unclassified
        if residue.end == spans[index].start or residue.start == spans[index].end
    }
    return [span for index, span in enumerate(spans) if index not in touching]


def candidate_for(source: ViewSource, span: Span) -> ViewCandidate | None:
    return source.get(span.candidate_key) if span.candidate_key else None
