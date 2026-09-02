"""Aligning what the model said against what the question actually contains.

The 0-A re-verification found the model composing spans rather than quoting
them: text that reads like the question but is not in it. A composed span is
indistinguishable from a quoted one by eye, and every downstream derivation —
the comparison operator, the value, the sort direction, the limit — would be
read out of text nobody wrote. So every span is checked against the question
before it is allowed to mean anything.

Alignment is exact, or exact after one fixed normalisation: Unicode NFKC, then
whitespace collapsed to single spaces, then trimmed. That handles a full-width
digit or a doubled space without ever letting a paraphrase through. It is
deliberately not fuzzy matching, and it is deliberately not value
canonicalisation: this decides whether the model quoted the question, not what
the quoted text means.
"""

from __future__ import annotations

import re
import unicodedata

ALIGNMENT_EXACT = "exact"
ALIGNMENT_NORMALIZED = "normalized_exact"
ALIGNMENT_FAILED = "not_in_question"

# The one reason code for "the model did not quote the question". It lives here
# rather than in a caller because every reader of a span has to refuse the same
# thing for the same stated reason; two copies of the string would be two
# contracts. Provisional internal, like every other code in this package.
CODE_SPAN_ALIGNMENT_FAILED = "span_alignment_failed"

NORMALIZATION_RULE = "unicode_nfkc_then_collapse_whitespace_then_strip"

_WHITESPACE = re.compile(r"\s+")


def normalize_for_alignment(text: str) -> str:
    """The one approved deterministic normalisation, applied to both sides."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()


def align(question: str, span: str) -> str:
    """Return how this span matches the question, or that it does not."""
    if not span:
        return ALIGNMENT_FAILED
    if span in question:
        return ALIGNMENT_EXACT
    if normalize_for_alignment(span) and normalize_for_alignment(span) in (
        normalize_for_alignment(question)
    ):
        return ALIGNMENT_NORMALIZED
    return ALIGNMENT_FAILED


def aligned(question: str, span: str) -> bool:
    return align(question, span) != ALIGNMENT_FAILED
