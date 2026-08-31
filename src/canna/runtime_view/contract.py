"""The vocabulary this layer borrows from the canonical documents.

Nothing here is invented. The requirement kinds are the result units named in
``QUESTION_STRUCTURE.md`` section 2; the queryable grains are the units approved
in ``ARCHITECTURE.md`` section 8 and the 2026-08-30 alignment decision. They are
written down once, in one place, with the document that owns each of them
recorded beside it, so that a reader can check them against the source rather
than against another copy in the code.

``CONTRACT_STATUS`` is the honest label for everything else this package
defines. The reason codes and the payload shape are a proposal; no shared
contract has been approved for them, and until one is, they are internal.
"""

from __future__ import annotations

CONTRACT_STATUS = "provisional_internal_pending_shared_contract_approval"

# QUESTION_STRUCTURE.md section 2, "Requirement": 목록, 속성 조회, count,
# aggregation, ranking, grouping, comparison, explanation.
REQUIREMENT_KIND_LISTING = "listing"
REQUIREMENT_KIND_ATTRIBUTE_LOOKUP = "attribute_lookup"
REQUIREMENT_KIND_COUNT = "count"
REQUIREMENT_KIND_AGGREGATION = "aggregation"
REQUIREMENT_KIND_RANKING = "ranking"
REQUIREMENT_KIND_GROUPING = "grouping"
REQUIREMENT_KIND_COMPARISON = "comparison"
REQUIREMENT_KIND_EXPLANATION = "explanation"

REQUIREMENT_KINDS = (
    REQUIREMENT_KIND_LISTING,
    REQUIREMENT_KIND_ATTRIBUTE_LOOKUP,
    REQUIREMENT_KIND_COUNT,
    REQUIREMENT_KIND_AGGREGATION,
    REQUIREMENT_KIND_RANKING,
    REQUIREMENT_KIND_GROUPING,
    REQUIREMENT_KIND_COMPARISON,
    REQUIREMENT_KIND_EXPLANATION,
)
REQUIREMENT_KINDS_SOURCE = "QUESTION_STRUCTURE.md#2-requirement"

# QUESTION_STRUCTURE.md section 5: every explicit requirement ends as exactly one
# of these.
STATUS_MAPPED = "mapped"
STATUS_UNRESOLVED = "unresolved"
STATUS_AMBIGUOUS = "ambiguous"
REQUIREMENT_STATUSES = (STATUS_MAPPED, STATUS_UNRESOLVED, STATUS_AMBIGUOUS)
REQUIREMENT_STATUSES_SOURCE = "QUESTION_STRUCTURE.md#5-requirement-accounting"

# ARCHITECTURE.md section 8 and DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md
# section 4: the grains a user-facing result may be returned at. Portfolio,
# security and observation grains exist in the Registry but are not query
# targets, so a class declared only at one of those is not a dataset.
GRAIN_PRODUCT = "product"
GRAIN_PRODUCT_CLASS = "product_class"
DATASET_GRAINS = (GRAIN_PRODUCT, GRAIN_PRODUCT_CLASS)
DATASET_GRAINS_SOURCE = (
    "ARCHITECTURE.md#8-holdings-grain과-predicate; "
    "DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md#4-조회-단위-원칙"
)

# Canonicalisers the server actually has. ARCHITECTURE.md section 3 requires the
# server to derive comparison operators, ordering, limits and aggregations from
# the question span deterministically; none of those is implemented yet, so the
# set is empty and every requirement that needs one is refused rather than
# executed on a guess.
CANONICALIZER_COMPARISON = "comparison_operator_and_value"
CANONICALIZER_ORDERING = "ordering_direction"
CANONICALIZER_LIMIT = "limit"
CANONICALIZER_AGGREGATION = "aggregation_function"
CANONICALIZER_GROUPING = "grouping"
CANONICALIZER_COMPARISON_REQUIREMENT = "comparison_requirement"
CANONICALIZER_EXPLANATION = "explanation_requirement"

AVAILABLE_CANONICALIZERS: frozenset[str] = frozenset()

# Which canonicaliser each requirement kind needs before it may execute.
KIND_CANONICALIZERS: dict[str, tuple[str, ...]] = {
    REQUIREMENT_KIND_LISTING: (),
    REQUIREMENT_KIND_ATTRIBUTE_LOOKUP: (),
    REQUIREMENT_KIND_COUNT: (),
    REQUIREMENT_KIND_AGGREGATION: (CANONICALIZER_AGGREGATION,),
    REQUIREMENT_KIND_RANKING: (CANONICALIZER_ORDERING, CANONICALIZER_LIMIT),
    REQUIREMENT_KIND_GROUPING: (CANONICALIZER_GROUPING,),
    REQUIREMENT_KIND_COMPARISON: (CANONICALIZER_COMPARISON_REQUIREMENT,),
    REQUIREMENT_KIND_EXPLANATION: (CANONICALIZER_EXPLANATION,),
}

# The server's own decision uses the same three values as the model's status
# (QUESTION_STRUCTURE.md section 5), because a requirement the server refused
# has to end in the same accounting as one the model never resolved.
DECISION_MAPPED = STATUS_MAPPED
DECISION_UNRESOLVED = STATUS_UNRESOLVED
DECISION_AMBIGUOUS = STATUS_AMBIGUOUS

# A requirement that asks for particular values has to name them. A listing or
# a count names its population instead, and a comparison or an explanation is
# not executable at all yet, so neither is required to carry output fields.
KINDS_REQUIRING_OUTPUT = (
    REQUIREMENT_KIND_ATTRIBUTE_LOOKUP,
)
