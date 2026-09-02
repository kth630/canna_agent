"""The approved fixtures, and the gold this experiment is scored against.

No question is written here and none is invented. The corpus is the five
approved fixture files exactly as they stand, and the gold is derived from the
metadata those fixtures already carry: the required candidate keys, the
requirement sets, the span anchors and the declared question structure.

The generator never sees any of this. The scorer reads it after the fact, which
is the only arrangement under which "the server found the anchor" means
anything.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

SPLIT_PRIMARY = "primary"
SPLIT_HOLDOUT = "holdout"

# Which approved view source each fixture family was authored against. The two
# sources use the same key namespace but cover different parts of it, so a
# fixture is scored against the one that declares the keys it names.
_FAMILIES = (
    ("runtime_view_probe.jsonl", "runtime_view_registry.json", SPLIT_PRIMARY),
    ("runtime_view_probe_unseen.jsonl", "runtime_view_registry.json", SPLIT_HOLDOUT),
    ("semantic_grounding.jsonl", "semantic_probe_catalog.json", SPLIT_PRIMARY),
    (
        "semantic_grounding_regression.jsonl",
        "semantic_probe_catalog.json",
        SPLIT_HOLDOUT,
    ),
    (
        "semantic_grounding_verification.jsonl",
        "semantic_probe_catalog.json",
        SPLIT_HOLDOUT,
    ),
)


@dataclass(frozen=True)
class GoldRequirement:
    label: str
    status: str
    kinds: tuple[str, ...]
    span_anchors: tuple[str, ...]
    ref_keys: tuple[tuple[str, ...], ...]
    detail_slots: tuple[str, ...]


@dataclass(frozen=True)
class Case:
    test_id: str
    question: str
    view_source: str
    split: str
    capability: str
    target_keys: tuple[str, ...]
    required_keys: tuple[str, ...]
    neighbor_keys: tuple[str, ...]
    requirement_alternatives: tuple[tuple[GoldRequirement, ...], ...]
    structure_kinds: tuple[str, ...]
    structure_counts: dict[str, int] = field(default_factory=dict)

    @property
    def requirement_counts(self) -> tuple[int, ...]:
        if self.requirement_alternatives:
            return tuple(
                len(alternative) for alternative in self.requirement_alternatives
            )
        return (len(self.structure_kinds),)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value if str(item))


def _gold_requirements(payload: dict) -> tuple[tuple[GoldRequirement, ...], ...]:
    alternatives: list[tuple[GoldRequirement, ...]] = []
    for alternative in payload.get("requirement_sets", ()) or ():
        rows: list[GoldRequirement] = []
        for entry in alternative:
            details = tuple(
                str(item.get("slot", ""))
                for item in (entry.get("details") or ())
                if item.get("slot")
            )
            rows.append(
                GoldRequirement(
                    label=str(entry.get("label", "")),
                    status=str(entry.get("status", "")),
                    kinds=_strings(entry.get("kind_alternatives")),
                    span_anchors=_strings(entry.get("span_anchors")),
                    ref_keys=tuple(
                        _strings(combo)
                        for combo in (entry.get("ref_key_alternatives") or ())
                    ),
                    detail_slots=details,
                )
            )
        alternatives.append(tuple(rows))
    return tuple(alternatives)


def load_cases(root: Path, split: str | None = None) -> tuple[Case, ...]:
    """Every approved fixture, or only one split of them."""
    fixtures = Path(root) / "tests" / "fixtures"
    cases: list[Case] = []
    for name, source_name, fixture_split in _FAMILIES:
        if split is not None and fixture_split != split:
            continue
        path = fixtures / name
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            decision = row.get("expected_decision", {}) or {}
            structure = row.get("question_structure", {}) or {}
            required = _strings(decision.get("required_candidate_ids"))
            declared = _strings(row.get("runtime_view_candidate_keys"))
            alternatives = _gold_requirements(decision)
            keys = set(required)
            keys.update(_strings(decision.get("target_dataset_keys")))
            # ``ref_key_alternatives`` lists *equivalent* readings of one
            # requirement, so a key present in only some of them is optional by
            # the fixture's own contract -- an implicit output field such as a
            # product name is one such. Only the intersection is required, or
            # the scorer would demand an anchor the question never wrote.
            for alternative in alternatives:
                for entry in alternative:
                    if not entry.ref_keys:
                        continue
                    shared = set(entry.ref_keys[0])
                    for combo in entry.ref_keys[1:]:
                        shared &= set(combo)
                    keys.update(shared)
            cases.append(
                Case(
                    test_id=str(row["test_id"]),
                    question=str(row["question"]),
                    view_source=source_name,
                    split=fixture_split,
                    capability=str(row.get("capability_under_test", "")),
                    target_keys=_strings(decision.get("target_dataset_keys")),
                    required_keys=tuple(sorted(keys)),
                    neighbor_keys=_strings(decision.get("required_neighbor_ids"))
                    or tuple(sorted(set(declared) - keys)),
                    requirement_alternatives=alternatives,
                    structure_kinds=tuple(
                        str(item.get("kind", ""))
                        for item in (structure.get("requirements") or ())
                    ),
                    structure_counts={
                        "targets": len(structure.get("targets") or ()),
                        "conditions": len(structure.get("conditions") or ()),
                        "relationships": len(structure.get("relationships") or ()),
                        "nested": len(structure.get("nested") or ()),
                        "comparisons": len(structure.get("comparisons") or ()),
                    },
                )
            )
    return tuple(cases)


def gold_span_anchors(case: Case) -> tuple[str, ...]:
    anchors: list[str] = []
    for alternative in case.requirement_alternatives:
        for entry in alternative:
            for anchor in entry.span_anchors:
                if anchor not in anchors:
                    anchors.append(anchor)
    return tuple(anchors)


def gold_detail_slots(case: Case) -> tuple[str, ...]:
    slots: list[str] = []
    for alternative in case.requirement_alternatives:
        for entry in alternative:
            for slot in entry.detail_slots:
                if slot not in slots:
                    slots.append(slot)
    return tuple(slots)


def expected_kinds(case: Case, produced: int) -> tuple[tuple[str, ...], ...]:
    """The gold requirement kinds, preferring the alternative that fits."""
    if case.requirement_alternatives:
        fitting = [
            alternative
            for alternative in case.requirement_alternatives
            if len(alternative) == produced
        ]
        chosen = fitting[0] if fitting else case.requirement_alternatives[0]
        return tuple(entry.kinds or () for entry in chosen)
    return tuple((kind,) for kind in case.structure_kinds)


def view_source_path(root: Path, case: Case) -> Path:
    return Path(root) / "tests" / "fixtures" / case.view_source


def sources_used(cases: Sequence[Case]) -> tuple[str, ...]:
    return tuple(sorted({case.view_source for case in cases}))
