"""The Runtime View: retrieval candidates, grouped and bound to a product family.

The measured failure this layer exists to stop is a homonym one. "총보수" is an
approved alias of two different product families' terms and "1년 수익률" matches
two more, so a flat candidate list lets a model pick a measure that belongs to a
family the question never asked about — and a surface-form match is no defence,
because both spellings are genuinely exact.

The answer here is structural rather than lexical. Every field candidate is
published already bound to the dataset candidates the Registry can prove it
belongs to, and every family a candidate declares is represented by a dataset
candidate even when retrieval did not return one. A model that picks the wrong
family therefore has to say so in the reference it submits, where the server can
see it, instead of hiding it inside an identical-looking name.

Two silences are deliberately turned into refusals. A field whose family
nothing states is published with an unproven scope rather than being quietly
offered for every dataset, and a class that is queryable only at a portfolio or
security grain is not offered as a query target at all. Both would otherwise let
a plausible-looking binding through on no evidence at all.

"Nothing states" is a real search rather than a shrug. The Semantic Registry is
asked first, and where it declares no family the Execution Registry is asked
which families actually serve the term — a measure bound for four product
families is scoped to those four, and to no others. Only a term neither can
place stays unproven.

What the model receives is deliberately impoverished: per-request opaque
references, human-readable meanings and the distinctions needed to tell
neighbours apart. Stable semantic IDs, retrieval scores, resolved entity keys,
physical bindings and the rest of the Registry stay on the server.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .contract import CONTRACT_STATUS, DATASET_GRAINS, DATASET_GRAINS_SOURCE
from .execution_facts import (
    BindingSummary,
    ExecutionFacts,
    TargetCapabilitySummary,
    bindings_or_empty,
    target_capabilities_or_not_evaluated,
)
from .refs import (
    KIND_CLASS,
    KIND_DATASET,
    KIND_ENTITY,
    KIND_FIELD,
    KIND_PREDICATE,
    RefMinter,
)
from .registry_facts import RegistryFacts

SCOPE_FAMILY_SCOPED = "family_scoped"
SCOPE_EXECUTION_SCOPED = "execution_scoped"
SCOPE_UNPROVEN = "scope_unproven"

MATCH_EXACT = "exact"
MATCH_PARTIAL = "partial"
MATCH_NONE = "none"

RESOLUTION_NOT_IMPLEMENTED = "entity_resolution_not_implemented"

MEANING_LABEL = "label"
MEANING_ALIAS = "alias"
MEANING_UNNAMED = "unnamed_in_registry"

EXCLUDED_NOT_A_CANDIDATE_KIND = "registry_term_is_not_a_query_candidate"
EXCLUDED_CLASS_NOT_QUERYABLE = "class_is_not_queryable_at_a_result_grain"

INTRODUCED_RETRIEVED = "retrieved"
INTRODUCED_FAMILY_CLOSURE = "family_closure"


class ViewError(ValueError):
    """The Runtime View cannot be built from these inputs."""


class BudgetError(ValueError):
    """A candidate budget is not usable."""


@dataclass(frozen=True)
class CandidateProposal:
    """One retrieval proposal, reduced to what this layer is allowed to use.

    ``surface_form_match`` records that the question named an approved
    expression whole. It is a lexical signal only: it says nothing about which
    product family was meant and it never authorises execution.
    """

    semantic_id: str
    surface_form_match: str = MATCH_NONE


@dataclass(frozen=True)
class EntityMention:
    """A product or security the question named, and what resolution knows.

    Entity resolution is a separate layer with verified identifiers and names.
    ``resolved_key`` is what that layer verified; it travels to the server's
    plan and never to the model, which is given only the mention it wrote and
    the fact that resolution succeeded or did not.
    """

    mention_text: str
    resolution_status: str = RESOLUTION_NOT_IMPLEMENTED
    entity_class_id: str = ""
    resolved_key: str = ""

    @property
    def resolved(self) -> bool:
        return bool(self.resolved_key) and bool(self.entity_class_id)


class EntityResolver(Protocol):
    """Resolves question mentions to entity instances. Not term retrieval."""

    def resolve(self, question: str) -> Sequence[EntityMention]: ...


class NullEntityResolver:
    """The current state of the world: mentions are carried, never resolved."""

    def resolve(self, question: str) -> Sequence[EntityMention]:
        return ()


@dataclass(frozen=True)
class CandidateBudget:
    """How many seats each candidate kind may take.

    There is no default. The experiment that would justify one has not been
    re-established, so a caller that wants a budget must state it and a caller
    that does not gets every candidate, still grouped by kind.

    A budget bounds what *retrieval* proposed. Datasets introduced to make a
    family binding visible are exempt: truncating one would delete the evidence
    that a field belongs to another family, which is the opposite of what a
    budget is for. The exemption is counted and reported, not assumed.
    """

    seats: Mapping[str, int]

    def __post_init__(self) -> None:
        allowed = {KIND_DATASET, KIND_FIELD, KIND_PREDICATE}
        unknown = sorted(set(self.seats) - allowed)
        if unknown:
            raise BudgetError(f"budget names candidate kinds that do not exist: {unknown}")
        negative = sorted(key for key, value in self.seats.items() if int(value) < 0)
        if negative:
            raise BudgetError(f"budget seats must not be negative: {negative}")

    def limit_for(self, kind: str) -> int | None:
        value = self.seats.get(kind)
        return None if value is None else int(value)


@dataclass(frozen=True)
class DatasetCandidate:
    ref: str
    semantic_id: str
    meaning: str
    meaning_status: str
    grains: tuple[str, ...]
    families: tuple[str, ...]
    surface_form_match: str
    introduced_by: str
    target_capabilities: tuple[TargetCapabilitySummary, ...] = ()


@dataclass(frozen=True)
class FieldCandidate:
    ref: str
    semantic_id: str
    meaning: str
    meaning_status: str
    belongs_to_dataset_refs: tuple[str, ...]
    dataset_scope: str
    families: tuple[str, ...]
    grains: tuple[str, ...]
    period: str
    unit: str
    currency_policy: str
    allowed_operations: tuple[str, ...]
    surface_form_match: str
    bindings: tuple[BindingSummary, ...] = ()


@dataclass(frozen=True)
class PredicateCandidate:
    ref: str
    semantic_id: str
    meaning: str
    meaning_status: str
    applies_to_dataset_refs: tuple[str, ...]
    families: tuple[str, ...]
    subject_class_ref: str
    object_class_ref: str
    subject_class_meaning: str
    object_class_meaning: str
    inverse_ref: str
    distinct_from_refs: tuple[str, ...]
    relation_mode_group: str
    relation_kinds: tuple[str, ...]
    allowed_operations: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    surface_form_match: str
    bindings: tuple[BindingSummary, ...] = ()


@dataclass(frozen=True)
class EntityCandidate:
    """The model sees the mention; the server keeps the verified key."""

    ref: str
    mention_text: str
    resolution_status: str
    entity_class_ref: str
    entity_class_id: str
    resolved_key: str

    @property
    def resolved(self) -> bool:
        return bool(self.resolved_key) and bool(self.entity_class_id)


@dataclass(frozen=True)
class ExcludedCandidate:
    semantic_id: str
    reason: str


@dataclass
class RuntimeView:
    """One request's candidates, and the server-side map back to the Registry."""

    question: str
    minter: RefMinter
    datasets: tuple[DatasetCandidate, ...]
    fields: tuple[FieldCandidate, ...]
    predicates: tuple[PredicateCandidate, ...]
    entities: tuple[EntityCandidate, ...]
    excluded: tuple[ExcludedCandidate, ...] = ()
    truncated_by_kind: Mapping[str, int] = field(default_factory=dict)
    budget_exempt_datasets: int = 0
    budget_applied: bool = False

    def ref_for(self, semantic_id: str) -> str | None:
        """Server-side lookup. Never exposed to the model."""
        for kind in (KIND_DATASET, KIND_FIELD, KIND_PREDICATE):
            found = self.minter.ref_for(kind, semantic_id)
            if found is not None:
                return found
        return None

    def dataset(self, ref: str) -> DatasetCandidate | None:
        return next((item for item in self.datasets if item.ref == ref), None)

    def field(self, ref: str) -> FieldCandidate | None:
        return next((item for item in self.fields if item.ref == ref), None)

    def predicate(self, ref: str) -> PredicateCandidate | None:
        return next((item for item in self.predicates if item.ref == ref), None)

    def entity(self, ref: str) -> EntityCandidate | None:
        return next((item for item in self.entities if item.ref == ref), None)

    def to_model_payload(self) -> dict[str, Any]:
        """What HCX sees: references and meanings, never IDs, scores or keys."""
        return {
            "contract_status": CONTRACT_STATUS,
            "question": self.question,
            "datasets": [
                {
                    "ref": item.ref,
                    "meaning": item.meaning,
                    "meaning_status": item.meaning_status,
                    "result_grain": list(item.grains),
                    "surface_form_match": item.surface_form_match,
                    "target_capabilities": [
                        row.to_payload() for row in item.target_capabilities
                    ],
                }
                for item in self.datasets
            ],
            "fields": [
                {
                    "ref": item.ref,
                    "meaning": item.meaning,
                    "meaning_status": item.meaning_status,
                    "belongs_to_dataset_refs": list(item.belongs_to_dataset_refs),
                    "dataset_scope": item.dataset_scope,
                    "result_grain": list(item.grains),
                    "period": item.period,
                    "unit": item.unit,
                    "currency_policy": item.currency_policy,
                    "allowed_operations": list(item.allowed_operations),
                    "surface_form_match": item.surface_form_match,
                    "served_by": [row.to_payload() for row in item.bindings],
                }
                for item in self.fields
            ],
            "predicates": [
                {
                    "ref": item.ref,
                    "meaning": item.meaning,
                    "meaning_status": item.meaning_status,
                    "applies_to_dataset_refs": list(item.applies_to_dataset_refs),
                    "subject_kind_ref": item.subject_class_ref,
                    "subject_kind_meaning": item.subject_class_meaning,
                    "object_kind_ref": item.object_class_ref,
                    "object_kind_meaning": item.object_class_meaning,
                    "relation_kinds": list(item.relation_kinds),
                    "same_relation_other_direction_ref": item.inverse_ref,
                    "different_relation_do_not_substitute_refs": list(item.distinct_from_refs),
                    "allowed_operations": list(item.allowed_operations),
                    "surface_form_match": item.surface_form_match,
                    "served_by": [row.to_payload() for row in item.bindings],
                }
                for item in self.predicates
            ],
            "entities": [
                {
                    "ref": item.ref,
                    "mention": item.mention_text,
                    "resolution_status": item.resolution_status,
                    "entity_kind_ref": item.entity_class_ref,
                }
                for item in self.entities
            ],
            "notes": {
                "surface_form_match": (
                    "the question named this expression; it does not decide the product "
                    "family and it does not authorise execution"
                ),
                "family_binding": (
                    "a field may only serve a requirement whose target dataset is one of "
                    "its belongs_to_dataset_refs"
                ),
                "scope_unproven": (
                    "the Registry does not state which product families this field applies "
                    "to, so it cannot be bound to a target and a requirement that needs it "
                    "stays unresolved"
                ),
                "result_grain_source": DATASET_GRAINS_SOURCE,
                "target_capabilities": (
                    "family-and-grain summaries of field and relation bindings available "
                    "to this target; they are not dataset bindings or dataset-wide coverage. "
                    "binding_operation_kinds only lists operations present on bindings and "
                    "does not establish readiness for any population-wide claim. "
                    "A zero binding count means capability evaluation found no described "
                    "binding, not that the dataset is unsupported"
                ),
                "served_by": (
                    "every way the Execution Registry actually serves this meaning, one "
                    "entry per product family and grain; an empty list means the supplied "
                    "adapter did not describe a binding, not proof that the meaning or its "
                    "dataset is unsupported"
                ),
            },
        }


def inverse_partners(facts: RegistryFacts, semantic_id: str) -> tuple[str, ...]:
    """Predicates the Registry declares as this one's inverse, in both directions."""
    if not facts.has(semantic_id):
        return ()
    found: set[str] = set()
    declared = str(facts.term(semantic_id).evidence.get("inverse_of", ""))
    if declared and facts.has(declared):
        found.add(declared)
    for term in facts.terms:
        if str(term.evidence.get("inverse_of", "")) == semantic_id:
            found.add(term.semantic_id)
    found.discard(semantic_id)
    return tuple(sorted(found))


def _sequence(value: Any) -> tuple[str, ...]:
    if not value or isinstance(value, str | bytes | Mapping):
        return ()
    return tuple(str(item) for item in value)


def _families(facts: RegistryFacts, semantic_id: str) -> tuple[str, ...]:
    if not facts.has(semantic_id):
        return ()
    return _sequence(facts.term(semantic_id).evidence.get("families"))


def _grains(facts: RegistryFacts, semantic_id: str) -> tuple[str, ...]:
    if not facts.has(semantic_id):
        return ()
    return _sequence(facts.term(semantic_id).evidence.get("grains"))


def _endpoints(facts: RegistryFacts, semantic_id: str) -> tuple[str, str]:
    evidence = facts.term(semantic_id).evidence
    domain = _sequence(evidence.get("domain"))
    range_ = _sequence(evidence.get("range"))
    return (domain[0] if domain else "", range_[0] if range_ else "")


def is_relation(facts: RegistryFacts, semantic_id: str) -> bool:
    """A relation is a term the Registry gives both a domain and a range."""
    if not facts.has(semantic_id):
        return False
    domain, range_ = _endpoints(facts, semantic_id)
    return bool(domain) and bool(range_)


def is_dataset(facts: RegistryFacts, semantic_id: str) -> bool:
    """A dataset is a family's own kind of thing, queryable at a result grain.

    Three Registry facts have to line up. A term you cannot run an operation on
    is a thing rather than a measure of one; a thing with no family is an
    abstract root nobody queries; and a thing whose only grain is portfolio,
    security or observation is reasoned about but never returned as a result
    set. Anything failing one of the three is not a query target.
    """
    if not facts.has(semantic_id) or is_relation(facts, semantic_id):
        return False
    if _sequence(facts.term(semantic_id).evidence.get("allowed_operations")):
        return False
    if not _families(facts, semantic_id):
        return False
    return bool(set(_grains(facts, semantic_id)) & set(DATASET_GRAINS))


def is_field(facts: RegistryFacts, semantic_id: str) -> bool:
    """A field is a term with operations, at a grain, that is not a relation."""
    if not facts.has(semantic_id):
        return False
    if is_relation(facts, semantic_id) or is_dataset(facts, semantic_id):
        return False
    evidence = facts.term(semantic_id).evidence
    return bool(_sequence(evidence.get("allowed_operations"))) and bool(
        _grains(facts, semantic_id)
    )


def candidate_kind(facts: RegistryFacts, semantic_id: str) -> str:
    """Classify from Registry structure, never from a list of names."""
    if not facts.has(semantic_id):
        return ""
    if is_relation(facts, semantic_id):
        return KIND_PREDICATE
    if is_dataset(facts, semantic_id):
        return KIND_DATASET
    if is_field(facts, semantic_id):
        return KIND_FIELD
    return ""


def dataset_terms_for_family(facts: RegistryFacts, family: str) -> tuple[str, ...]:
    """The queryable classes of a family that no other class of that family covers."""
    members = [
        term.semantic_id
        for term in facts.terms
        if family in _families(facts, term.semantic_id) and is_dataset(facts, term.semantic_id)
    ]
    member_ids = set(members)
    return tuple(
        sorted(
            semantic_id
            for semantic_id in members
            if not (facts.ancestors(semantic_id) & (member_ids - {semantic_id}))
        )
    )


def _relation_mode_group(facts: RegistryFacts, semantic_id: str) -> str:
    """A stable server-side key shared by a relation and its opposite direction."""
    domain, range_ = _endpoints(facts, semantic_id)
    return "|".join(sorted({domain, range_}))


def relation_kinds(bindings: Sequence[BindingSummary]) -> tuple[str, ...]:
    """The relation kinds the Execution Registry actually serves this predicate as."""
    return tuple(sorted({row.relation_kind for row in bindings if row.relation_kind}))


def _effective_families(
    facts: RegistryFacts, semantic_id: str, bindings: Sequence[BindingSummary]
) -> tuple[tuple[str, ...], str]:
    """Which product families a term applies to, and on whose authority.

    The Semantic Registry is the first authority: a term that declares its
    families means them. Where it declares none, the Execution Registry is asked
    which families are actually served, which is evidence of provision rather
    than of meaning — so it is labelled differently and never invented.
    """
    declared = _families(facts, semantic_id)
    if declared:
        return declared, SCOPE_FAMILY_SCOPED
    served = tuple(sorted({row.family_id for row in bindings if row.family_id}))
    if served:
        return served, SCOPE_EXECUTION_SCOPED
    return (), SCOPE_UNPROVEN


def _meaning(facts: RegistryFacts, semantic_id: str) -> tuple[str, str]:
    """A human-readable name, or nothing. Never the semantic ID as a fallback."""
    if not facts.has(semantic_id):
        return "", MEANING_UNNAMED
    term = facts.term(semantic_id)
    if term.preferred_label:
        return term.preferred_label, MEANING_LABEL
    aliases = _sequence(term.evidence.get("aliases"))
    if aliases:
        return aliases[0], MEANING_ALIAS
    return "", MEANING_UNNAMED


def build_runtime_view(
    facts: RegistryFacts,
    question: str,
    proposals: Iterable[CandidateProposal],
    *,
    minter: RefMinter | None = None,
    budget: CandidateBudget | None = None,
    entity_resolver: EntityResolver | None = None,
    execution_facts: ExecutionFacts | None = None,
) -> RuntimeView:
    """Group candidates by kind and bind every one of them the Registry can."""
    minter = minter or RefMinter()
    resolver = entity_resolver or NullEntityResolver()

    by_kind: dict[str, list[CandidateProposal]] = {
        KIND_DATASET: [],
        KIND_FIELD: [],
        KIND_PREDICATE: [],
    }
    excluded: list[ExcludedCandidate] = []
    seen: set[str] = set()
    for proposal in proposals:
        if proposal.semantic_id in seen:
            continue
        if not facts.has(proposal.semantic_id):
            raise ViewError(f"candidate is not a Registry term: {proposal.semantic_id!r}")
        seen.add(proposal.semantic_id)
        kind = candidate_kind(facts, proposal.semantic_id)
        if not kind:
            excluded.append(
                ExcludedCandidate(
                    semantic_id=proposal.semantic_id,
                    reason=(
                        EXCLUDED_CLASS_NOT_QUERYABLE
                        if _grains(facts, proposal.semantic_id)
                        else EXCLUDED_NOT_A_CANDIDATE_KIND
                    ),
                )
            )
            continue
        by_kind[kind].append(proposal)

    truncated: dict[str, int] = {}
    if budget is not None:
        for kind, items in by_kind.items():
            limit = budget.limit_for(kind)
            if limit is None:
                continue
            if len(items) > limit:
                truncated[kind] = len(items) - limit
                by_kind[kind] = items[:limit]

    # Every family any surviving candidate declares must be visible as a
    # dataset, or the binding that makes a cross-family pick detectable would
    # not exist. Closure runs after the budget and is exempt from it.
    dataset_ids = [item.semantic_id for item in by_kind[KIND_DATASET]]
    matches = {item.semantic_id: item.surface_form_match for item in by_kind[KIND_DATASET]}
    introduced = dict.fromkeys(dataset_ids, INTRODUCED_RETRIEVED)
    for kind in (KIND_FIELD, KIND_PREDICATE):
        for proposal in by_kind[kind]:
            effective, _scope = _effective_families(
                facts,
                proposal.semantic_id,
                bindings_or_empty(execution_facts, proposal.semantic_id),
            )
            for family in effective:
                for semantic_id in dataset_terms_for_family(facts, family):
                    if semantic_id not in introduced:
                        introduced[semantic_id] = INTRODUCED_FAMILY_CLOSURE
                        dataset_ids.append(semantic_id)

    datasets = tuple(
        DatasetCandidate(
            ref=minter.mint(KIND_DATASET, semantic_id),
            semantic_id=semantic_id,
            meaning=_meaning(facts, semantic_id)[0],
            meaning_status=_meaning(facts, semantic_id)[1],
            grains=_grains(facts, semantic_id),
            families=_families(facts, semantic_id),
            surface_form_match=matches.get(semantic_id, MATCH_NONE),
            introduced_by=introduced[semantic_id],
            target_capabilities=target_capabilities_or_not_evaluated(
                execution_facts,
                _families(facts, semantic_id),
                _grains(facts, semantic_id),
            ),
        )
        for semantic_id in dataset_ids
    )
    by_family: dict[str, list[str]] = {}
    for item in datasets:
        for family in item.families:
            by_family.setdefault(family, []).append(item.ref)

    fields = []
    for proposal in by_kind[KIND_FIELD]:
        semantic_id = proposal.semantic_id
        evidence = facts.term(semantic_id).evidence
        served = bindings_or_empty(execution_facts, semantic_id)
        families, scope = _effective_families(facts, semantic_id, served)
        meaning, meaning_status = _meaning(facts, semantic_id)
        fields.append(
            FieldCandidate(
                ref=minter.mint(KIND_FIELD, semantic_id),
                semantic_id=semantic_id,
                meaning=meaning,
                meaning_status=meaning_status,
                belongs_to_dataset_refs=tuple(
                    ref for family in families for ref in by_family.get(family, ())
                ),
                dataset_scope=scope,
                families=families,
                grains=_grains(facts, semantic_id),
                period=str(evidence.get("period_code", "")),
                unit=str(evidence.get("unit_code", "")),
                currency_policy=str(evidence.get("currency_policy", "")),
                allowed_operations=_sequence(evidence.get("allowed_operations")),
                surface_form_match=proposal.surface_form_match,
                bindings=served,
            )
        )

    predicate_ids = [proposal.semantic_id for proposal in by_kind[KIND_PREDICATE]]
    predicates = []
    for proposal in by_kind[KIND_PREDICATE]:
        semantic_id = proposal.semantic_id
        evidence = facts.term(semantic_id).evidence
        domain, range_ = _endpoints(facts, semantic_id)
        group = _relation_mode_group(facts, semantic_id)
        inverses = inverse_partners(facts, semantic_id)
        siblings = tuple(
            other
            for other in predicate_ids
            if other != semantic_id
            and other not in inverses
            and _relation_mode_group(facts, other) == group
        )
        served = bindings_or_empty(execution_facts, semantic_id)
        families, _scope = _effective_families(facts, semantic_id, served)
        meaning, meaning_status = _meaning(facts, semantic_id)
        predicates.append(
            PredicateCandidate(
                ref=minter.mint(KIND_PREDICATE, semantic_id),
                semantic_id=semantic_id,
                meaning=meaning,
                meaning_status=meaning_status,
                applies_to_dataset_refs=tuple(
                    item.ref for item in datasets if facts.is_kind_of(item.semantic_id, domain)
                ),
                families=families,
                subject_class_ref=minter.mint(KIND_CLASS, domain) if domain else "",
                object_class_ref=minter.mint(KIND_CLASS, range_) if range_ else "",
                subject_class_meaning=_meaning(facts, domain)[0],
                object_class_meaning=_meaning(facts, range_)[0],
                inverse_ref=next(
                    (
                        minter.mint(KIND_PREDICATE, value)
                        for value in inverses
                        if value in predicate_ids
                    ),
                    "",
                ),
                distinct_from_refs=tuple(
                    minter.mint(KIND_PREDICATE, value) for value in siblings
                ),
                relation_mode_group=group,
                relation_kinds=relation_kinds(served),
                allowed_operations=_sequence(evidence.get("allowed_operations")),
                evidence_requirements=_sequence(evidence.get("evidence_requirements")),
                surface_form_match=proposal.surface_form_match,
                bindings=served,
            )
        )

    entities = tuple(
        EntityCandidate(
            ref=minter.mint(KIND_ENTITY, mention.mention_text),
            mention_text=mention.mention_text,
            resolution_status=mention.resolution_status,
            entity_class_ref=(
                minter.mint(KIND_CLASS, mention.entity_class_id)
                if mention.entity_class_id
                else ""
            ),
            entity_class_id=mention.entity_class_id,
            resolved_key=mention.resolved_key,
        )
        for mention in resolver.resolve(question)
    )

    return RuntimeView(
        question=question,
        minter=minter,
        datasets=datasets,
        fields=tuple(fields),
        predicates=tuple(predicates),
        entities=entities,
        excluded=tuple(excluded),
        truncated_by_kind=dict(sorted(truncated.items())),
        budget_exempt_datasets=sum(
            1 for item in datasets if item.introduced_by == INTRODUCED_FAMILY_CLOSURE
        ),
        budget_applied=budget is not None,
    )
