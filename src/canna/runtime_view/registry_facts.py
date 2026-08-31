"""Registry structure this layer needs and the retrieval vocabulary does not carry.

``Vocabulary`` exists to answer "what text could name this term", so it keeps
labels, aliases and the metadata a candidate is judged by, and drops the class
hierarchy. Deciding which dataset a relation may traverse to needs exactly that
hierarchy, so it is read here from the same Semantic Registry document.

Two readers of one file can drift apart, which would be a silent correctness
bug rather than a loud one, so the payload's own content hash is checked against
the vocabulary's before either is used. Nothing here re-derives a meaning: the
Registry remains the single source of truth and this is a second projection of
it, not a second definition.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..retrieval.vocabulary import (
    Term,
    Vocabulary,
    build_vocabulary,
    content_hash,
    load_vocabulary,
)


class RegistryFactsError(ValueError):
    """The structural projection and the vocabulary disagree."""


@dataclass(frozen=True)
class RegistryFacts:
    """One Semantic Registry state, seen as vocabulary plus class hierarchy."""

    vocabulary: Vocabulary
    subclass_of: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], source_path: str = "") -> RegistryFacts:
        vocabulary = build_vocabulary(
            json.loads(json.dumps(payload, ensure_ascii=False)), source_path
        )
        return cls(vocabulary=vocabulary, subclass_of=_hierarchy(payload))

    @classmethod
    def load(cls, path: Path | None = None) -> RegistryFacts:
        vocabulary = load_vocabulary(path)
        payload = json.loads(Path(vocabulary.source_path).read_text(encoding="utf-8"))
        if content_hash(payload) != vocabulary.content_hash:
            raise RegistryFactsError(
                "the Semantic Registry changed between the two reads of it"
            )
        return cls(vocabulary=vocabulary, subclass_of=_hierarchy(payload))

    @property
    def content_hash(self) -> str:
        return self.vocabulary.content_hash

    @property
    def terms(self) -> tuple[Term, ...]:
        return self.vocabulary.terms

    def has(self, semantic_id: str) -> bool:
        return self.vocabulary.has(semantic_id)

    def term(self, semantic_id: str) -> Term:
        return self.vocabulary.term(semantic_id)

    def ancestors(self, semantic_id: str) -> frozenset[str]:
        """Transitive ``subclass_of`` closure, cycle-safe."""
        seen: set[str] = set()
        pending = [semantic_id]
        while pending:
            for parent in self.subclass_of.get(pending.pop(), ()):
                if parent not in seen:
                    seen.add(parent)
                    pending.append(parent)
        return frozenset(seen)

    def is_kind_of(self, semantic_id: str, expected: str) -> bool:
        if not semantic_id or not expected:
            return False
        return semantic_id == expected or expected in self.ancestors(semantic_id)


def _hierarchy(payload: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    rows = payload.get("terms", ())
    return {
        str(row["semantic_id"]): tuple(str(value) for value in row.get("subclass_of", ()) or ())
        for row in rows
        if isinstance(row, Mapping) and row.get("semantic_id")
    }
