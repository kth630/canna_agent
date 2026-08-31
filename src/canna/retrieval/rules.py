"""Rule-based retrieval over the approved vocabulary.

Four tiers, tried in order, each weaker than the last:

``exact``
    The complete question equals the registry surface form verbatim.
``normalized``
    The complete question equals the surface form after safe normalization.
``phrase``
    The complete surface form appears inside a larger sentence.
``substring``
    Only a bounded fragment of the form appears, or a shorter registered form
    is swallowed by a longer registered expression at the same position.

The first three are evidence that a complete approved form was named and may
ground a mention.  The last is not, and this module is where that boundary is
enforced: a substring is emitted as a proposal with ``grounding_eligible``
false, so no downstream ranking can turn a coincidence into a decision.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

from .normalize import normalize
from .settings import RuleSettings
from .vocabulary import (
    TIER_EXACT,
    TIER_NORMALIZED,
    TIER_PHRASE,
    TIER_SUBSTRING,
    SurfaceForm,
    Vocabulary,
)

GROUNDING_TIERS = frozenset({TIER_EXACT, TIER_NORMALIZED, TIER_PHRASE})
TIER_RANK = {TIER_EXACT: 0, TIER_NORMALIZED: 1, TIER_PHRASE: 2, TIER_SUBSTRING: 3}


@dataclass(frozen=True)
class RuleMatch:
    """One surface form found in one question."""

    form: SurfaceForm
    tier: str
    matched_span: str
    overlap_characters: int
    occurrences: tuple[tuple[int, int], ...] = ()

    @property
    def semantic_id(self) -> str:
        return self.form.semantic_id

    @property
    def score(self) -> float:
        """Share of the registry form the question actually covered."""
        length = len(self.form.normalized)
        if length == 0:
            return 0.0
        return min(1.0, self.overlap_characters / length)

    @property
    def grounding_eligible(self) -> bool:
        return self.tier in GROUNDING_TIERS

    @property
    def sort_key(self) -> tuple[int, float, int, str]:
        return (
            TIER_RANK[self.tier],
            -self.score,
            -len(self.form.normalized),
            self.form.form_id,
        )


def _occurrences(text: str, expression: str) -> tuple[tuple[int, int], ...]:
    """All possibly-overlapping locations of ``expression`` in ``text``."""
    if not expression:
        return ()
    found: list[tuple[int, int]] = []
    start = 0
    while True:
        position = text.find(expression, start)
        if position < 0:
            return tuple(found)
        found.append((position, position + len(expression)))
        start = position + 1


def _substring_span(
    form_normalized: str, question_normalized: str, settings: RuleSettings
) -> str:
    """Longest fragment of the form the question contains, if it is long enough.

    Fragments are looked for with ordinary substring search from the longest
    downwards, so the reported span is the strongest fragment available rather
    than the first one stumbled upon.
    """
    length = len(form_normalized)
    required = max(
        settings.min_substring_characters,
        math.ceil(settings.substring_overlap_ratio * length),
    )
    if required >= length or required < 1:
        return ""
    for size in range(length - 1, required - 1, -1):
        for start in range(length - size + 1):
            fragment = form_normalized[start : start + size]
            if fragment in question_normalized:
                return fragment
    return ""


def match_form(
    form: SurfaceForm,
    question: str,
    question_normalized: str,
    settings: RuleSettings,
) -> RuleMatch | None:
    """Strongest tier at which ``form`` is present, honouring its role contract."""
    stripped = question.strip()
    if form.allows(TIER_EXACT) and form.text and stripped == form.text:
        return RuleMatch(
            form,
            TIER_EXACT,
            stripped,
            len(form.normalized),
            ((0, len(question_normalized)),),
        )
    if form.allows(TIER_NORMALIZED) and form.normalized == question_normalized:
        return RuleMatch(
            form,
            TIER_NORMALIZED,
            question_normalized,
            len(form.normalized),
            ((0, len(question_normalized)),),
        )
    occurrences = _occurrences(question_normalized, form.normalized)
    if form.allows(TIER_PHRASE) and occurrences:
        return RuleMatch(
            form,
            TIER_PHRASE,
            form.normalized,
            len(form.normalized),
            occurrences,
        )
    if form.allows(TIER_SUBSTRING):
        span = _substring_span(form.normalized, question_normalized, settings)
        if span:
            return RuleMatch(
                form,
                TIER_SUBSTRING,
                span,
                len(span),
                _occurrences(question_normalized, span),
            )
    return None


def _downgrade_shadowed_phrases(matches: Sequence[RuleMatch]) -> list[RuleMatch]:
    """Keep maximal registered expressions as phrases at overlapping positions.

    If both ``보수`` and a longer registered expression match exactly the same
    position, the shorter form is substring evidence rather than independent
    grounding.  This is vocabulary-driven maximal matching; it contains no
    financial synonym or language-specific suffix list.
    """
    grounded = [match for match in matches if match.grounding_eligible]
    result: list[RuleMatch] = []
    for match in matches:
        if match.tier != TIER_PHRASE:
            result.append(match)
            continue
        longer = [
            other
            for other in grounded
            if len(other.form.normalized) > len(match.form.normalized)
        ]
        every_occurrence_is_shadowed = bool(match.occurrences) and all(
            any(
                other_start <= start and end <= other_end
                for other in longer
                for other_start, other_end in other.occurrences
            )
            for start, end in match.occurrences
        )
        result.append(
            replace(match, tier=TIER_SUBSTRING)
            if every_occurrence_is_shadowed
            else match
        )
    return result


def search(
    vocabulary: Vocabulary,
    question: str,
    settings: RuleSettings,
) -> tuple[list[RuleMatch], int]:
    """Best match per term, ranked. Returns ``(matches, truncated_count)``.

    A term is kept once, at its strongest tier: a label that matched exactly and
    an alias that matched partially describe the same term, and reporting both
    would inflate a candidate list without adding a meaning.
    """
    question_normalized = normalize(question)
    if not question_normalized:
        return [], 0
    raw_matches: list[RuleMatch] = []
    for form in vocabulary.rule_forms():
        match = match_form(form, question, question_normalized, settings)
        if match is not None:
            raw_matches.append(match)
    best: dict[str, RuleMatch] = {}
    for match in _downgrade_shadowed_phrases(raw_matches):
        current = best.get(match.semantic_id)
        if current is None or match.sort_key < current.sort_key:
            best[match.semantic_id] = match
    ranked = sorted(best.values(), key=lambda match: match.sort_key)
    truncated = max(0, len(ranked) - settings.max_candidates)
    return ranked[: settings.max_candidates], truncated


def grounding_matches(matches: Sequence[RuleMatch]) -> tuple[RuleMatch, ...]:
    return tuple(match for match in matches if match.grounding_eligible)
