"""Text normalization shared by every retrieval path.

One normalizer, used on both sides of every comparison: the question and the
registry surface form. If the two sides were normalized differently a match
would mean nothing.

The rules are deliberately language-neutral. Korean questions inflect around a
noun phrase and space it inconsistently ("1년 수익률", "1년수익률"), so folding
away whitespace and purely typographic separators lets a registry label be
looked for inside the question without a per-language particle list, which
would be exactly the kind of vocabulary this repository keeps in the Registry
rather than in code.

Not every symbol is typographic.  A decimal point, minus sign, percent sign or
slash can change a financial expression, so this normalizer deliberately keeps
them.  The old draft dropped every non-alphanumeric character and therefore
collapsed ``15.4`` into ``154``; that is not meaning-preserving normalization.
"""

from __future__ import annotations

import unicodedata

NORMALIZATION_FORM = "NFKC"

# These characters conventionally separate words without changing the words'
# identity.  Domain vocabulary does not live here: approved financial synonyms
# still come exclusively from the Semantic Registry.
IGNORABLE_SEPARATORS = frozenset({"_", "·", "ㆍ", "・"})


def normalize(text: str) -> str:
    """Case/width-folded projection with only safe separators removed.

    Whitespace and a small set of typographic separators are ignored.  All
    other punctuation and symbols are retained because the normalizer cannot
    prove they are semantically inert.  The result is a comparison key only;
    it is never shown as an answer and never used to reconstruct wording.
    """
    folded = unicodedata.normalize(NORMALIZATION_FORM, text).casefold()
    return "".join(
        character
        for character in folded
        if not character.isspace() and character not in IGNORABLE_SEPARATORS
    )


def normalization_contract() -> dict[str, object]:
    """The normalization rules, recorded into artifacts for reproducibility."""
    return {
        "unicode_form": NORMALIZATION_FORM,
        "case": "casefold",
        "dropped_characters": {
            "whitespace": True,
            "typographic_separators": sorted(IGNORABLE_SEPARATORS),
        },
        "retained_characters": "all_other_characters_including_semantic_symbols",
    }
