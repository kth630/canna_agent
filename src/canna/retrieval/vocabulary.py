"""The searchable projection of the Semantic Registry.

Both retrieval paths read this module and nothing else for vocabulary. The rule
path and the embedding path therefore search exactly the same approved terms:
no synonym list, no field list and no per-family exception exists anywhere in
``canna.retrieval``. Adding a term to the ontology adds it here.

A surface form is one piece of registry text that a question could name. Which
forms exist for a term is a property of the registry data (does it carry a
label, an approved alias, a definition), never of the term's kind. Terms that
carry no searchable text at all — SHACL shapes do not — simply produce no forms
and are reported as such by the index manifest instead of disappearing.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .normalize import normalize

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = ROOT / "data" / "processed" / "semantic_registry.json"

ROLE_SEMANTIC_ID = "semantic_id"
ROLE_LABEL = "label"
ROLE_ALIAS = "alias"
ROLE_DEFINITION = "definition"

TIER_EXACT = "exact"
TIER_NORMALIZED = "normalized"
TIER_PHRASE = "phrase"
TIER_SUBSTRING = "substring"
TIER_ORDER = (TIER_EXACT, TIER_NORMALIZED, TIER_PHRASE, TIER_SUBSTRING)


@dataclass(frozen=True)
class RoleContract:
    """What a kind of registry text is allowed to do in retrieval.

    A stable id and a definition may confirm a mention when they appear whole,
    but neither may produce a partial match: half of an opaque id, or a phrase
    lifted out of a sentence, is not evidence that a term was named. Only the
    names of a term — its label and its approved aliases — carry meaning in
    fragments, and even then only as a proposal.
    """

    role: str
    rule_tiers: tuple[str, ...]
    embedded: bool


ROLE_CONTRACTS: Mapping[str, RoleContract] = {
    ROLE_SEMANTIC_ID: RoleContract(
        ROLE_SEMANTIC_ID, (TIER_EXACT, TIER_NORMALIZED, TIER_PHRASE), False
    ),
    ROLE_LABEL: RoleContract(
        ROLE_LABEL, (TIER_EXACT, TIER_NORMALIZED, TIER_PHRASE, TIER_SUBSTRING), True
    ),
    ROLE_ALIAS: RoleContract(
        ROLE_ALIAS, (TIER_EXACT, TIER_NORMALIZED, TIER_PHRASE, TIER_SUBSTRING), True
    ),
    ROLE_DEFINITION: RoleContract(
        ROLE_DEFINITION, (TIER_EXACT, TIER_NORMALIZED, TIER_PHRASE), True
    ),
}

# Registry fields carried onto a candidate as its grounding evidence. Meaning
# only: a downstream reader must be able to tell two candidates apart without
# being handed a table or a column.
EVIDENCE_FIELDS = (
    "kind",
    "labels",
    "aliases",
    "definition",
    "families",
    "grains",
    "period_code",
    "unit_code",
    "currency_policy",
    "allowed_operations",
    "comparison_group",
    "meaning_status",
    "evidence_requirements",
    "domain",
    "range",
    "inverse_of",
)


class VocabularyError(ValueError):
    """The registry payload does not carry what retrieval requires."""


@dataclass(frozen=True)
class SurfaceForm:
    """One registry text that a question could name."""

    semantic_id: str
    role: str
    locale: str
    text: str
    normalized: str

    @property
    def form_id(self) -> str:
        return f"{self.semantic_id}|{self.role}|{self.locale}|{self.normalized}"

    @property
    def contract(self) -> RoleContract:
        return ROLE_CONTRACTS[self.role]

    def allows(self, tier: str) -> bool:
        return tier in self.contract.rule_tiers


@dataclass(frozen=True)
class Term:
    """A registry term reduced to what retrieval may see and pass on."""

    semantic_id: str
    kind: str
    evidence: Mapping[str, object]
    forms: tuple[SurfaceForm, ...]

    @property
    def searchable(self) -> bool:
        return any(form.role != ROLE_SEMANTIC_ID for form in self.forms)

    @property
    def preferred_label(self) -> str:
        for form in self.forms:
            if form.role == ROLE_LABEL:
                return form.text
        return ""


class Vocabulary:
    """Every approved term and surface form, in a deterministic order."""

    def __init__(self, terms: Sequence[Term], content_hash: str, source_path: str) -> None:
        self._terms = tuple(sorted(terms, key=lambda term: term.semantic_id))
        self._by_id = {term.semantic_id: term for term in self._terms}
        self.content_hash = content_hash
        self.source_path = source_path

    def __len__(self) -> int:
        return len(self._terms)

    @property
    def terms(self) -> tuple[Term, ...]:
        return self._terms

    def term(self, semantic_id: str) -> Term:
        try:
            return self._by_id[semantic_id]
        except KeyError as error:
            raise VocabularyError(f"unknown semantic id: {semantic_id}") from error

    def has(self, semantic_id: str) -> bool:
        return semantic_id in self._by_id

    def rule_forms(self) -> tuple[SurfaceForm, ...]:
        """Forms a rule may match, longest first so the most specific wins."""
        forms = [form for term in self._terms for form in term.forms]
        return tuple(sorted(forms, key=lambda form: (-len(form.normalized), form.form_id)))

    def embeddable_forms(self) -> tuple[SurfaceForm, ...]:
        """Forms the embedding index covers, in a stable build order."""
        forms = [
            form
            for term in self._terms
            for form in term.forms
            if ROLE_CONTRACTS[form.role].embedded
        ]
        return tuple(sorted(forms, key=lambda form: form.form_id))

    def unsearchable_ids(self) -> tuple[str, ...]:
        return tuple(term.semantic_id for term in self._terms if not term.searchable)


def _forms_for(entry: Mapping[str, object]) -> tuple[SurfaceForm, ...]:
    semantic_id = str(entry["semantic_id"])
    seen: set[str] = set()
    forms: list[SurfaceForm] = []

    def add(role: str, locale: str, text: str) -> None:
        cleaned = " ".join(str(text).split())
        if not cleaned:
            return
        normalized = normalize(cleaned)
        if not normalized:
            return
        form = SurfaceForm(semantic_id, role, locale, cleaned, normalized)
        if form.form_id in seen:
            return
        seen.add(form.form_id)
        forms.append(form)

    add(ROLE_SEMANTIC_ID, "", semantic_id)
    labels = entry.get("labels") or {}
    if isinstance(labels, Mapping):
        for locale in sorted(labels):
            add(ROLE_LABEL, str(locale), str(labels[locale]))
    for alias in sorted(str(value) for value in (entry.get("aliases") or [])):
        add(ROLE_ALIAS, "", alias)
    add(ROLE_DEFINITION, "", str(entry.get("definition") or ""))
    return tuple(forms)


def content_hash(payload: Mapping[str, object]) -> str:
    """Hash of the registry's meaning, independent of when it was generated.

    ``generated_at`` changes on every regeneration even when nothing semantic
    moved. Keying an index on the file bytes would therefore force a rebuild —
    and a bill — for no reason, so the hash covers the parts an index actually
    depends on.
    """
    hashed = {
        key: payload.get(key)
        for key in ("prefixes", "counts", "ontology_files", "terms")
        if key in payload
    }
    canonical = json.dumps(hashed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_vocabulary(payload: Mapping[str, object], source_path: str = "") -> Vocabulary:
    raw_terms = payload.get("terms")
    if not isinstance(raw_terms, Iterable):
        raise VocabularyError("semantic registry payload has no 'terms' array")
    terms: list[Term] = []
    seen: set[str] = set()
    for entry in raw_terms:
        if not isinstance(entry, Mapping) or "semantic_id" not in entry:
            raise VocabularyError("registry term without a semantic id")
        semantic_id = str(entry["semantic_id"])
        if semantic_id in seen:
            raise VocabularyError(f"duplicate semantic id in registry: {semantic_id}")
        seen.add(semantic_id)
        terms.append(
            Term(
                semantic_id=semantic_id,
                kind=str(entry.get("kind", "")),
                evidence={field: entry.get(field) for field in EVIDENCE_FIELDS},
                forms=_forms_for(entry),
            )
        )
    if not terms:
        raise VocabularyError("semantic registry contains no terms")
    return Vocabulary(terms, content_hash(payload), source_path)


def load_vocabulary(path: Path | None = None) -> Vocabulary:
    registry_path = path or DEFAULT_REGISTRY_PATH
    if not registry_path.is_file():
        raise VocabularyError(
            f"semantic registry not found at {registry_path}; generate it before retrieval"
        )
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    relative = (
        str(registry_path.relative_to(ROOT)).replace("\\", "/")
        if registry_path.is_relative_to(ROOT)
        else str(registry_path)
    )
    return build_vocabulary(payload, relative)
