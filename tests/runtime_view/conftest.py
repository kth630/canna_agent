"""Synthetic Registry material for Runtime View tests.

Every fixture here invents its own product families and terms. The rules under
test must hold for any Registry, so a test that only passed on the real
families' names would be testing the names rather than the rule.

The synthetic Registry deliberately contains the shapes that caused trouble in
the real one: an alias two families share, a family queryable at two different
grains, classes that are not query targets at all, and a relation pair whose
inverse must not be confused with a same-shaped different relation.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from canna.runtime_view.registry_facts import RegistryFacts
from canna.runtime_view.view import EntityMention

FAMILY_A = "alpha_family"
FAMILY_B = "beta_family"


def term(
    semantic_id: str,
    *,
    label: str = "",
    aliases: Sequence[str] = (),
    families: Sequence[str] = (),
    grains: Sequence[str] = ("product",),
    period: str = "",
    unit: str = "none",
    operations: Sequence[str] = ("filter", "order"),
    domain: Sequence[str] = (),
    range_: Sequence[str] = (),
    inverse_of: str = "",
    subclass_of: Sequence[str] = (),
) -> dict[str, object]:
    """One Registry term. No argument names a candidate kind.

    Classification is derived from structure — a domain and a range make a
    relation, a family plus a result grain makes a dataset — so the tests must
    not be able to hand the code the answer.
    """
    return {
        "semantic_id": semantic_id,
        "kind": "term",
        "labels": {"ko": label} if label else {},
        "aliases": list(aliases),
        "definition": "",
        "families": list(families),
        "grains": list(grains),
        "period_code": period,
        "unit_code": unit,
        "currency_policy": "",
        "allowed_operations": list(operations),
        "comparison_group": "",
        "meaning_status": "",
        "evidence_requirements": [],
        "domain": list(domain),
        "range": list(range_),
        "inverse_of": inverse_of,
        "subclass_of": list(subclass_of),
        "shapes": [],
    }


def registry(terms: list[dict[str, object]]) -> RegistryFacts:
    payload = {
        "prefixes": {"syn": "https://canna.local/ontology/synthetic#"},
        "counts": {"total": len(terms)},
        "ontology_files": [],
        "terms": terms,
    }
    return RegistryFacts.from_payload(payload, "synthetic")


def two_family_registry() -> RegistryFacts:
    return registry(
        [
            # Abstract roots and non-target classes: no family, or a grain that
            # is never a result grain. Neither may become a dataset candidate.
            term("syn:Product", label="상품", operations=(), grains=["product"]),
            term("syn:Thing", label="구성요소", operations=(), grains=["security"]),
            term("syn:Book", label="운용 포트폴리오", operations=(), grains=["portfolio"]),
            # Alpha is queryable at two grains; both are dataset candidates.
            term(
                "syn:AlphaProduct",
                label="알파상품",
                families=[FAMILY_A],
                grains=["product"],
                operations=(),
                subclass_of=["syn:Product"],
            ),
            term(
                "syn:AlphaClass",
                label="알파판매클래스",
                families=[FAMILY_A],
                grains=["product_class"],
                operations=(),
                subclass_of=["syn:Product"],
            ),
            term(
                "syn:BetaProduct",
                label="베타상품",
                families=[FAMILY_B],
                grains=["product"],
                operations=(),
                subclass_of=["syn:Product"],
            ),
            # The homonym: one alias, two families.
            term(
                "syn:AlphaCost",
                label="알파 비용",
                aliases=["공용비용"],
                families=[FAMILY_A],
                grains=["product"],
                period="P1Y",
            ),
            term(
                "syn:BetaCost",
                label="베타 비용",
                aliases=["공용비용"],
                families=[FAMILY_B],
                grains=["product"],
                period="P1Y",
            ),
            term("syn:AlphaSize", label="알파 규모", families=[FAMILY_A], grains=["product"]),
            # Same family, other grain: must bind to the class dataset only.
            term(
                "syn:AlphaClassFee",
                label="알파 클래스 보수",
                families=[FAMILY_A],
                grains=["product_class"],
            ),
            # No family declared anywhere: scope cannot be proven.
            term("syn:SharedName", label="이름", grains=["product"]),
            # No label and no alias: there is no meaning to publish.
            term("syn:Unnamed", families=[FAMILY_A], grains=["product"]),
            term(
                "syn:holds",
                label="직접 보유한다",
                domain=["syn:Product"],
                range_=["syn:Thing"],
                inverse_of="syn:isHeldBy",
                grains=["product"],
                operations=["exists", "filter", "count"],
            ),
            term(
                "syn:isHeldBy",
                label="이것을 보유한 상품",
                domain=["syn:Thing"],
                range_=["syn:Product"],
                grains=["security"],
                operations=["exists", "filter", "count"],
            ),
            term(
                "syn:hasIndirectExposureTo",
                label="간접 익스포저를 가진다",
                domain=["syn:Product"],
                range_=["syn:Thing"],
                inverse_of="syn:isIndirectExposureOf",
                grains=["product"],
                operations=["exists", "filter", "count"],
            ),
            term(
                "syn:isIndirectExposureOf",
                label="이것에 간접 익스포저를 가진 상품",
                domain=["syn:Thing"],
                range_=["syn:Product"],
                grains=["security"],
                operations=["exists", "filter", "count"],
            ),
            # A relation that declares a family, so closure has something to do
            # for a question with no field candidate at all.
            term(
                "syn:betaHolds",
                label="베타 전용 보유 관계",
                families=[FAMILY_B],
                domain=["syn:Product"],
                range_=["syn:Thing"],
                grains=["product"],
                operations=["exists"],
            ),
        ]
    )


class StubEntityResolver:
    """Stands in for the entity layer that does not exist yet. Test material."""

    def __init__(self, mentions: Sequence[EntityMention]) -> None:
        self._mentions = tuple(mentions)

    def resolve(self, question: str) -> Sequence[EntityMention]:
        return self._mentions


def resolved(mention_text: str, entity_class_id: str, resolved_key: str) -> EntityMention:
    return EntityMention(
        mention_text=mention_text,
        resolution_status="resolved",
        entity_class_id=entity_class_id,
        resolved_key=resolved_key,
    )


@pytest.fixture
def facts() -> RegistryFacts:
    return two_family_registry()
